"""
ai.core.execution_engine — Central orchestrator for entity execution.

Manages the full lifecycle: initialization → credit gate → CORTEX setup →
context loading → plan reconciliation → step execution → finalization → billing.

Extracted from worker.py during Phase 10A restructuring.
"""
import asyncio
import copy
import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.common.database import AsyncSessionLocal
from src.ai.models import (
    ExecutionRun, HierarchicalEntity, LLMInteractionLog, EntityType,
    RunStatus, Document, DocumentChunk, ToolInteractionLog, HumanApproval,
)
from src.ai.schemas import (
    RunStatus as RunStatusEnum, EntityStatus, RelationshipType,
    ReasoningMode, StepType, PlanStep, Planning, LogicGate, ContextPolicy,
    HITLCheckpoint, HITLTriggerType,
    DEFAULT_PLANNING_SYSTEM_PROMPT, DEFAULT_REVIEW_SYSTEM_PROMPT,
)
from src.config.service import ConfigService
from src.ai.usage_service import UsageService
from src.billing.credit_service import CreditService, InsufficientCreditsError
from src.billing.billing_service import BillingService, calculate_tb
from src.ai.tool_executor import ToolExecutor
from src.ai.memory.memory_service import MemoryRouter
from src.ai.llm.router import LLMRouter
from src.ai.governance.governance_service import GovernanceService
from src.ai.planning.planner_service import PlannerService
from src.ai.memory.cortex_bridge import CortexBridge
from src.ai.step_executor import StepExecutorService
from src.ai.memory.cortex_service import CortexRouter as CortexService
from src.ai.memory.cortex_models import CortexNodeType
from src.ai.constants import INTERNAL_CONTEXT_KEYS, MAX_REACT_TURNS

# Imports from the ai.core modules.
from src.ai.core.exceptions import (
    AgentError, UncertaintySignal, CreditExhaustedError, BudgetExhaustedError,
    MetaAgentAbort, EntityNotFoundError, CortexError,
)
from src.ai.core.context_utils import store_step_output, sanitize_context_for_persistence

logger = logging.getLogger(__name__)

# Prompt template aliases (backward compat)
DYNAMIC_PLANNER_PROMPT = DEFAULT_PLANNING_SYSTEM_PROMPT
DEFAULT_REVIEW_PROMPT = DEFAULT_REVIEW_SYSTEM_PROMPT

# Alias for backward compat within the class body
_store_step_output = store_step_output
_sanitize_context_for_persistence = sanitize_context_for_persistence

class ExecutionEngine:
    def __init__(self, db: AsyncSessionLocal, redis_pool, company_id: UUID = None):
        self.db = db
        self.redis = redis_pool
        self.config_service = ConfigService(db)
        self.usage_service = UsageService(db)
        # Composed services (initialized when company_id is known).
        self.company_id = company_id
        self._governance = GovernanceService(db, redis_pool) if company_id else None
        self._planner = PlannerService(db, company_id) if company_id else None
        self._cortex_bridge = CortexBridge(db, company_id, self.usage_service, redis=redis_pool) if company_id else None
        self._step_executor = StepExecutorService(
            db, redis_pool, company_id, self.usage_service,
            cortex_bridge=self._cortex_bridge,
            execute_run_fn=self.execute_run,
            governance=self._governance,
        ) if company_id else None

    def _ensure_services(self, company_id: UUID):
        """Lazily initialize services when company_id becomes available."""
        if not self._governance:
            self.company_id = company_id
            self._governance = GovernanceService(self.db, self.redis)
            self._planner = PlannerService(self.db, company_id)
            self._cortex_bridge = CortexBridge(self.db, company_id, self.usage_service, redis=self.redis)
            self._step_executor = StepExecutorService(
                self.db, self.redis, company_id, self.usage_service,
                cortex_bridge=self._cortex_bridge,
                execute_run_fn=self.execute_run,
                governance=self._governance,
            )

    # NOTE: child entities run via the legacy ``execute_run`` engine even when
    # ``agent_loop.enabled`` is ON for the top-level run. Routing children
    # through a nested inline AgentLoop was tried (Phase 11 follow-up) but
    # destabilised the doc-factory pipeline: each child became a full retry
    # loop running inline on the shared session, which amplified cost (~$11/
    # child) and could block the worker. Driving sub-entities through the new
    # loop needs a safer mechanism (e.g. async dispatch on a dedicated worker)
    # and is deferred; the flag still governs the top-level engine selection.

    async def _execute_steps_dag(self, run, entity, steps: List[dict], context_state: dict) -> List[dict]:
        """Execute steps respecting dependencies, parallelizing independent ones.

        P1-A: Parallel steps each open their own AsyncSession to avoid
        sharing self.db across concurrent coroutines (which would cause
        PendingRollbackError under SQLAlchemy's asyncio driver).
        The orchestrator-level self.db is retained for status/plan commits.
        """

        # 1. Build Dependency Graph
        step_deps = {s["step_id"]: set() for s in steps}
        step_map = {s["step_id"]: s for s in steps}

        for step in steps:
            s_id = step.get("step_id")
            target = step.get("target") or {}
            if target and "input_dependencies" in target:
                for dep in target.get("input_dependencies", []):
                     step_deps[s_id].add(dep)

            prompt = target.get("prompt_template", "")
            # prompt_template may be a dict if the LLM planner emitted structured input;
            # coerce to string so the regex can still discover {{step_N}} references.
            if isinstance(prompt, dict):
                prompt = json.dumps(prompt, default=str)
            elif not isinstance(prompt, str):
                prompt = str(prompt) if prompt else ""
            vars_needed = re.findall(r'\{\{(.*?)\}\}', prompt)
            for var in vars_needed:
                base_var = var.split('.')[0]
                if base_var in step_map and base_var != s_id:
                    step_deps[s_id].add(base_var)

        completed = set()
        for s in steps:
            if s["step_id"] in context_state and s["step_id"] != "input":
                completed.add(s["step_id"])

        results_map = {}
        logger.info(f"DAG Execution Plan for {len(steps)} steps. Dependencies: {step_deps}")

        while len(completed) < len(steps):
            ready = []
            for s in steps:
                s_id = s["step_id"]
                if s_id not in completed:
                    deps = step_deps[s_id]
                    if deps.issubset(completed) or not deps:
                        ready.append(s)

            if not ready:
                remaining = [s["step_id"] for s in steps if s["step_id"] not in completed]
                logger.warning(f"Circular dependency or stall detected. Remaining: {remaining}. Switching to sequential for remainder.")
                for s in steps:
                    if s["step_id"] not in completed:
                        step_obj = PlanStep(**s)
                        res = await self._execute_step_wrapper(run, entity, step_obj, context_state)
                        results_map[s["step_id"]] = res
                        completed.add(s["step_id"])
                break

            logger.debug(f"Executing batch: {[s['name'] for s in ready]}")

            if len(ready) == 1:
                # ── Phase 9: Dependency validation before execution ──────
                step_obj = PlanStep(**ready[0])
                _dep_missing = False
                if step_obj.target and step_obj.target.prompt_template:
                    _required = re.findall(r'\{\{(.+?)\}\}', str(step_obj.target.prompt_template))
                    for _var in _required:
                        _base = _var.split('.')[0]
                        # Check if it's a step reference that should be in context
                        if _base.startswith('step_') and _base not in context_state:
                            # Check if the dependent step failed
                            _dep_step_name = step_map.get(_base, {}).get('name', _base)
                            _failed_val = context_state.get(_dep_step_name, '')
                            if str(_failed_val).startswith('[FAILED]') or str(_failed_val).startswith('[TOOL_EMPTY]'):
                                logger.warning(
                                    f"Step '{step_obj.name}' depends on '{_base}' which FAILED. "
                                    f"Skipping step to prevent hallucination."
                                )
                                _dep_error = (
                                    f"[DEPENDENCY_FAILED] Cannot execute '{step_obj.name}': "
                                    f"required data from '{_base}' ({_dep_step_name}) failed. "
                                    f"Failure: {str(_failed_val)[:200]}"
                                )
                                _store_step_output(context_state, step_obj.name, step_obj.step_id or step_obj.name, _dep_error)
                                results_map[ready[0]['step_id']] = {'step': step_obj.name, 'output': _dep_error, 'success': False}
                                completed.add(ready[0]['step_id'])
                                _dep_missing = True
                                break
                # ─────────────────────────────────────────────────────────
                if not _dep_missing:
                    result = await self._execute_step_wrapper(run, entity, step_obj, context_state)
                    results_map[ready[0]["step_id"]] = result
                    completed.add(ready[0]["step_id"])
            else:
                # Multi-step parallel batch: each step gets its own AsyncSession.
                # P1-A: This prevents PendingRollbackError when two coroutines
                # share self.db and one fails mid-transaction.
                # Each step gets a deep-copied context to prevent
                # cross-contamination between parallel coroutines.
                # Pass run_id instead of ORM object; reload in
                # isolated session. Use atomic DB increments for cost/tokens.
                async def _isolated_step(step_dict: dict, frozen_ctx: dict) -> dict:
                    async with AsyncSessionLocal() as isolated_db:
                        isolated_engine = ExecutionEngine(isolated_db, self.redis, company_id=self.company_id)
                        step_obj = PlanStep(**step_dict)
                        # Reload run in isolated session to avoid DetachedInstanceError
                        iso_result = await isolated_db.execute(
                            select(ExecutionRun)
                            .options(selectinload(ExecutionRun.entity))
                            .where(ExecutionRun.id == run.id)
                        )
                        iso_run = iso_result.scalar_one()
                        step_result = await isolated_engine._execute_step_wrapper(
                            iso_run, entity, step_obj, frozen_ctx
                        )
                        # Cost/token accounting is owned by StepExecutorService
                        # via _bump_run_cost, which folds each LLM/tool/child
                        # charge into run.total_cost_usd with an ATOMIC
                        # "total_cost_usd = total_cost_usd + delta" UPDATE. That
                        # is concurrency-safe across these parallel isolated
                        # sessions. The previous design merged cost here from
                        # step_result["cost_usd"], but _execute_step never
                        # populated that key, so every parallel step's cost was
                        # silently dropped (the Phase 11 billing leak). A
                        # defensive commit guarantees the final increment is
                        # durable before the isolated session closes.
                        await isolated_db.commit()
                        return step_result

                # Deep-copy context for each parallel step
                tasks = [_isolated_step(s, copy.deepcopy(context_state)) for s in ready]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                # ERR-2 fix: Collect ALL results first, then decide whether to raise.
                # Previously, the first failure discarded successful step results.
                failures = []
                for i, result in enumerate(batch_results):
                    step_id = ready[i]["step_id"]
                    if isinstance(result, Exception):
                        logger.error(f"Step {step_id} failed: {result}")
                        results_map[step_id] = {"error": str(result), "step": ready[i]["name"]}
                        _store_step_output(context_state, ready[i]["name"], step_id, f"[FAILED] {result}")
                        failures.append((step_id, result))
                    else:
                        results_map[step_id] = result
                        completed.add(step_id)
                        # Merge results back into parent context
                        if isinstance(result, dict) and "output" in result:
                            _store_step_output(context_state, ready[i]["name"], step_id, result["output"])

                # Refresh run from DB after parallel steps to get accumulated costs
                await self.db.refresh(run)

                if failures:
                    raise failures[0][1]  # Raise first failure after saving all results

        return [results_map.get(s["step_id"], {}) for s in steps]

    async def _enforce_cost_cap(self, run, governance: dict) -> None:
        """Raise ``BudgetExhaustedError`` if the run's accumulated cost has
        reached the entity's ``governance.max_cost_usd``.

        Best-effort lookup: a failure to read the cost must never crash a
        healthy step, so any non-budget exception is swallowed (the run simply
        proceeds without the guard for that step).
        """
        try:
            max_cost = governance.get("max_cost_usd")
        except AttributeError:
            return
        if not max_cost:
            return
        try:
            cap = float(max_cost)
        except (TypeError, ValueError):
            return
        if cap <= 0:
            return
        try:
            spent_raw = (await self.db.execute(
                select(ExecutionRun.total_cost_usd).where(ExecutionRun.id == run.id)
            )).scalar_one_or_none()
        except Exception:
            return  # never let the guard's own lookup break a step
        if spent_raw is None:
            return
        try:
            spent = float(spent_raw)
        except (TypeError, ValueError):
            return
        if spent >= cap:
            raise BudgetExhaustedError(
                f"Run {run.id} reached governance.max_cost_usd "
                f"(spent ${spent:.4f} ≥ cap ${cap:.2f}); stopping further spend.",
                spent_usd=spent,
                cap_usd=cap,
            )

    async def _execute_step_wrapper(self, run, entity, step_obj, context_state):
        """Wrapper to handle execution + review + context update for a single step.

        Ph-B: If the LLM raises UncertaintySignal, the step result is annotated
        with needs_clarification=True instead of crashing the run.

        Includes:
        - HITL checkpoint evaluation (BEFORE_STEP, COST_THRESHOLD, TOOL_CALL)
        - Timeout enforcement via asyncio.wait_for
        - Observability-gated logging
        """
        # Entity is detached (make_transient) — safe to access .governance etc.
        # without triggering lazy-load / MissingGreenlet.
        observability = entity.observability or {}
        log_thoughts = observability.get("log_thoughts", True)
        governance = entity.governance or {}
        timeout_ms = governance.get("timeout_ms", 60000)

        # ── Budget guard: enforce governance.max_cost_usd as a hard stop ─────
        # The legacy run loop otherwise only guards company-wide credits and
        # HITL COST_THRESHOLD checkpoints — never the entity's own per-run cap.
        # That let a child entity (e.g. doc-xlsx-agent, cap $3) run to $15+.
        # We re-read the run's accumulated cost (a fresh scalar SELECT, never a
        # possibly-expired ORM attribute) and abort BEFORE starting the next
        # billable step once the cap is reached. Enforcement is step-granular:
        # the step that crosses the cap finishes; the following step is blocked.
        await self._enforce_cost_cap(run, governance)

        # ── HITL: Evaluate BEFORE_STEP and COST_THRESHOLD checkpoints ───────
        await self._evaluate_hitl_checkpoints(
            run, entity, step_obj, context_state, phase="BEFORE",
            governance_dict=governance
        )

        # ── Execute with timeout enforcement ────────────────────────────────
        try:
            try:
                step_result = await asyncio.wait_for(
                    self._step_executor._execute_step(run, entity, step_obj, context_state),
                    timeout=timeout_ms / 1000.0,
                )
            except asyncio.TimeoutError:
                step_result = {
                    "step": step_obj.name,
                    "step_id": step_obj.step_id,
                    "output": f"[TIMEOUT] Step '{step_obj.name}' exceeded {timeout_ms}ms timeout.",
                    "error": f"Timeout after {timeout_ms}ms",
                }
                logger.warning(f"Step '{step_obj.name}' timed out after {timeout_ms}ms")
                # DATA-2 fix: write failed step to context so it's not re-executed on retry
                _store_step_output(context_state, step_obj.name, step_obj.step_id or step_obj.name, f"[ERROR] Timeout after {timeout_ms}ms")
        except UncertaintySignal as sig:
            if log_thoughts:
                logger.info(f"UncertaintySignal from step '{step_obj.name}': {sig.question}")
            step_result = {
                "step": step_obj.name,
                "output": f"[Clarification needed] {sig.question}",
                "needs_clarification": True,
                "uncertainty_question": sig.question,
                "uncertainty_confidence": sig.confidence,
                "uncertainty_alternatives": sig.alternatives,
            }

        # ── HITL: Evaluate AFTER_STEP checkpoints ───────────────────────────
        await self._evaluate_hitl_checkpoints(
            run, entity, step_obj, context_state, phase="AFTER",
            governance_dict=governance
        )

        # Review Mechanism
        if (entity.logic_gate or {}).get("review_mechanism", {}).get("enabled"):
            step_result = await self._step_executor._review_step_output(run, entity, step_obj, step_result, context_state)

        # ── Phase 10D: GoalGuard step-level alignment check ─────────────
        # Replaces the 50-line inline goal alignment block from Phase 9.
        reasoning_cfg = (entity.logic_gate or {}).get("reasoning_config", {})
        goal_interval = reasoning_cfg.get("goal_validation_interval", 0)
        if goal_interval > 0 and entity.goal and isinstance(step_result, dict) and step_result.get("output"):
            step_count = context_state.get("__goal_check_counter__", 0) + 1
            context_state["__goal_check_counter__"] = step_count
            if step_count % goal_interval == 0:
                try:
                    from src.ai.planning.goal_guard import GoalGuard
                    guard = GoalGuard(
                        db=self.db,
                        company_id=run.company_id,
                        entity_goal=entity.goal,
                        task_description=context_state.get("input", ""),
                    )
                    guard_result = await guard.check(
                        step_result=step_result,
                        step_name=step_obj.name,
                        step_idx=step_count,
                        all_results=[],
                        total_steps=0,
                    )
                    if guard_result["action"] == "RETRY":
                        _retry_key = f"__retry_{step_obj.step_id or step_obj.name}__"
                        if not context_state.get(_retry_key):
                            context_state[_retry_key] = True
                            correction = guard_result.get("correction_hint", "")
                            context_state["__alignment_correction__"] = (
                                f"⚠️ GOAL DRIFT: {guard_result['reason']}. "
                                f"Correction: {correction}. "
                                f"Focus STRICTLY on the original goal: {entity.goal}"
                            )
                            logger.info(f"GoalGuard: re-executing step '{step_obj.name}'")
                            step_result = await asyncio.wait_for(
                                self._step_executor._execute_step(run, entity, step_obj, context_state),
                                timeout=timeout_ms / 1000.0,
                            )
                            context_state.pop("__alignment_correction__", None)
                        else:
                            logger.warning(f"Step '{step_obj.name}' already retried — skipping")
                except Exception as _ga_err:
                    logger.warning(f"GoalGuard step check error: {_ga_err}")
        # ──────────────────────────────────────────────────────────────────

        # Update Context immediately (Phase 4: capped size)
        if isinstance(step_result, dict) and "output" in step_result:
            _store_step_output(context_state, step_obj.name, step_obj.step_id or "", step_result["output"])

        return step_result

    async def _evaluate_hitl_checkpoints(
        self,
        run: 'ExecutionRun',
        entity: 'HierarchicalEntity',
        step_obj: PlanStep,
        context_state: dict,
        phase: str,
        governance_dict: dict = None,
    ) -> None:
        """Delegate to GovernanceService (Phase 3 extraction)."""
        await self._governance.evaluate_hitl(
            run, entity, step_obj, context_state, phase,
            governance_dict=governance_dict
        )


    # --- Updated execute_run using DAG ---

    async def execute_run(self, run_id: UUID) -> dict:
        # 1. Fetch Run and Entity
        result = await self.db.execute(
            select(ExecutionRun)
            .options(selectinload(ExecutionRun.entity))
            .where(ExecutionRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise AgentError(f"Run {run_id} not found")

        entity = run.entity
        if not entity:
            raise EntityNotFoundError(str(run_id), context="entity missing from run")

        # ── FIX: Prevent MissingGreenlet by eagerly snapshotting all entity
        # JSONB columns BEFORE any commit() can expire the ORM state.
        # After commit(), SQLAlchemy marks all loaded attributes as expired.
        # Subsequent access triggers a lazy-load that requires an active
        # greenlet context — which is gone after asyncio.wait_for timeout.
        # Solution: read every JSONB column now and use make_transient()
        # to fully detach the entity from the session.
        _ = (
            entity.name, entity.type, entity.description, entity.goal,
            entity.identity, entity.governance, entity.observability,
            entity.logic_gate, entity.planning, entity.hierarchy,
            entity.capabilities, entity.io_contract, entity.company_id,
            entity.parent_id, entity.status,
        )
        from sqlalchemy.orm import make_transient
        make_transient(entity)

        # Initialize composed services with company_id.
        self._ensure_services(entity.company_id)

        # 2. Configure logging level from entity's observability settings
        observability = entity.observability or {}
        entity_log_level = observability.get("log_level", "INFO").upper()
        numeric_level = getattr(logging, entity_log_level, logging.INFO)
        logging.getLogger("src.ai").setLevel(numeric_level)
        logging.getLogger("src").setLevel(numeric_level)
        root_logger = logging.getLogger()
        if not root_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            root_logger.addHandler(handler)
        root_logger.setLevel(min(root_logger.level or logging.WARNING, numeric_level))
        logger.info(f"[RUN:{run_id}] Phase 1/7: Initialization complete (entity={entity.name})")

        # 3. Update Status and Initialize Trace
        run.status = RunStatus.RUNNING
        run.started_at = datetime.utcnow()
        if not run.trace_id:
            run.trace_id = run.id
        await self.db.commit()

        # Cache immutable run IDs to prevent MissingGreenlet after session commits
        # expire ORM attributes during the long-running step execution loop.
        # Even with expire_on_commit=False, pool_pre_ping=True can trigger a
        # synchronous connection ping inside an ORM lazy-load if the DB connection
        # was recycled — which crashes without a greenlet.
        await self.db.refresh(run)  # eagerly load ALL columns into instance dict
        _run_id = run.id
        _run_user_id = run.user_id
        _run_company_id = run.company_id
        _run_parent_run_id = run.parent_run_id
        
        # Publish Update
        channel = f"execution:{_run_id}"
        await self.redis.publish(channel, json.dumps({"status": "RUNNING", "run_id": str(_run_id)}))

        # ── Pre-execution credit balance gate (delegated to GovernanceService) ─
        entity_type_str = entity.type.value if hasattr(entity.type, 'value') else str(entity.type)
        await self._governance.check_credit_gate(
            _run_company_id, entity_type_str, is_child=bool(_run_parent_run_id)
        )

        try:
            # ======================================================
            # CORTEX EXECUTION ENGINE
            # All execution uses CORTEX trees as the live cognitive
            # context. The agent's context is always a viewport onto
            # the tree — never an in-memory dict.
            # ======================================================

            # C1: Create or resume CORTEX tree
            cortex = CortexService(db=self.db, company_id=entity.company_id)
            
            # Check if this is a child recursive run (scoped subtree)
            input_data = run.input_data or {}
            cortex_tree_id = input_data.get("cortex_tree_id")
            subtree_root_id = input_data.get("subtree_root_id")
            
            if cortex_tree_id and subtree_root_id:
                # Resuming as a recursive child — scoped to subtree
                cortex = CortexService(
                    db=self.db,
                    company_id=entity.company_id,
                    scoped_subtree_root_id=UUID(subtree_root_id),
                )
                tree, viewport, last_checkpoint = await cortex.resume_tree(UUID(cortex_tree_id))
                logger.info(f"CORTEX child run: scoped to subtree {subtree_root_id} in tree {cortex_tree_id}")
            elif cortex_tree_id:
                # Resuming an existing tree
                tree, viewport, last_checkpoint = await cortex.resume_tree(UUID(cortex_tree_id))
                logger.info(f"CORTEX resumed tree: {cortex_tree_id}")
            else:
                # New execution — create a fresh tree
                task_desc = self._build_task_description(entity, input_data)
                tree = await cortex.create_tree(
                    entity_id=entity.id,
                    user_id=_run_user_id,
                    task_description=task_desc,
                )
                viewport = await cortex.navigate(tree.root_node_id)
                last_checkpoint = None
                logger.info(f"CORTEX new tree: {tree.id}")

            # C2: Retrieve memory context — Phase 10C: unified assembler
            memory_config = (entity.capabilities or {}).get("memory", {})
            _memory_scope = memory_config.get("memory_scope", "FULL")
            _memory_pipeline = memory_config.get("memory_pipeline", "v1")

            from src.ai.memory.assembler import assemble_memory
            memory_context = await assemble_memory(
                db=self.db,
                company_id=entity.company_id,
                entity_id=entity.id,
                user_id=_run_user_id,
                tree_id=tree.id,
                task_description=self._build_task_description(entity, input_data),
                memory_pipeline=_memory_pipeline,
                memory_scope=_memory_scope,
                runtime_tree=tree,
                long_running=True,
            )

            # C3: Build context from viewport (replaces context_state dict)
            context_state = input_data.copy()
            context_state.update(memory_context)

            logger.info(
                f"[RUN:{run_id}] Phase 3/7: Memory assembled "
                f"(scope={_memory_scope}, pipeline={_memory_pipeline}, keys={list(memory_context.keys())})"
            )
            # Inject CORTEX viewport as the primary context
            context_state["__cortex_viewport__"] = viewport.to_prompt_text()
            context_state["__cortex_tree_id__"] = str(tree.id)
            # Cache immutable tree IDs to prevent MissingGreenlet after session commits
            _tree_id = tree.id
            _tree_output_root_id = tree.output_root_id

            # M5: Inject knowledge subtree summary for entities sharing a tree
            # This is critical for the synthesizer: it needs to READ the director's
            # accumulated knowledge nodes from the shared tree.
            try:
                knowledge_root = await cortex.get_knowledge_root(_tree_id)
                if knowledge_root:
                    knowledge_viewport = await cortex.navigate(knowledge_root.id)
                    context_state["__cortex_knowledge__"] = knowledge_viewport.to_prompt_text()
                    logger.info(f"CORTEX: Injected knowledge subtree ({knowledge_root.id}) into context")
            except Exception as _kb_err:
                logger.debug(f"CORTEX: Knowledge subtree injection skipped: {_kb_err}")
                
            all_step_results = []

            # ── Phase 5: Load context_sources from entity config ─────────
            context_engineering = (entity.capabilities or {}).get("context_engineering", {})
            context_sources = context_engineering.get("context_sources", [])
            if context_sources:
                loaded_sources = []
                for src in context_sources:
                    src_type = src.get("source_type", "DOCUMENT")
                    ref_id = src.get("reference_id", "")
                    desc = src.get("description", "")
                    file_name = src.get("file_name", "")
                    if not ref_id:
                        continue
                    try:
                        if src_type == "CORTEX_TREE":
                            # Link to an existing CORTEX tree — inject its root viewport
                            linked_tree = await cortex.get_tree(UUID(ref_id))
                            if linked_tree:
                                linked_viewport = await cortex.navigate(linked_tree.root_node_id)
                                loaded_sources.append(
                                    f"## Context Source: {desc or 'CORTEX Tree'}\n"
                                    f"{linked_viewport.to_prompt_text()}"
                                )
                        elif src_type in ("KNOWLEDGE_BASE", "DOCUMENT"):
                            # Load artifact file content from disk with proper text extraction
                            try:
                                from src.ai.artifact_service import ArtifactService as _ArtSvc
                                _art_svc = _ArtSvc(self.db)
                                _artifact = await _art_svc.get_artifact(UUID(ref_id), entity.company_id)
                                if _artifact:
                                    from pathlib import Path as _Path
                                    _fpath = _Path(_artifact.file_path)
                                    _mime = _artifact.mime_type or ""
                                    _label = desc or file_name or _artifact.file_name

                                    if _mime.startswith(("image/", "audio/", "video/")):
                                        # Binary media: store reference only, no text extraction
                                        loaded_sources.append(
                                            f"## Context Source ({_artifact.file_category}): {_label}\n"
                                            f"File: {_artifact.file_name} ({_mime}, "
                                            f"{_artifact.file_size or 0} bytes)\n"
                                            f"Reference ID: {ref_id}"
                                        )
                                    elif _fpath.exists():
                                        _content = self._extract_text_from_file(_fpath, _mime)
                                        if _content:
                                            loaded_sources.append(
                                                f"## Context Source: {_label}\n{_content[:50000]}"
                                            )
                                        else:
                                            loaded_sources.append(
                                                f"## Context Source: {_label}\n"
                                                f"(Could not extract text from {_artifact.file_name})"
                                            )
                                    else:
                                        logger.warning(f"Artifact file not found on disk: {_artifact.file_path}")
                                        loaded_sources.append(
                                            f"## Context Source: {_label}\n"
                                            f"Reference: {ref_id} (file not found)"
                                        )
                                else:
                                    # Fallback to semantic memory search for KB sources
                                    if src_type == "KNOWLEDGE_BASE":
                                        _memory_router = MemoryRouter(self.db)
                                        _kb_ctx = await _memory_router.retrieve(
                                            entity_id=entity.id,
                                            query=desc or "knowledge base context",
                                            top_k=10,
                                        )
                                        if _kb_ctx:
                                            loaded_sources.append(
                                                f"## Context Source: {desc or 'Knowledge Base'}\n"
                                                f"{_memory_router.format_for_prompt(_kb_ctx)}"
                                            )
                                    else:
                                        loaded_sources.append(
                                            f"## Context Source: {desc or file_name or ref_id}\n"
                                            f"Reference: {ref_id}"
                                        )
                            except Exception as _doc_err:
                                logger.warning(f"{src_type} source load failed for {ref_id}: {_doc_err}")
                                loaded_sources.append(
                                    f"## Context Source: {desc or file_name or ref_id}\n"
                                    f"Reference: {ref_id}"
                                )
                        elif src_type == "DB_RECORDS":
                            # DB Records not yet implemented — skip with warning
                            logger.info(f"DB_RECORDS context source skipped (not yet implemented): {ref_id}")
                        else:
                            loaded_sources.append(
                                f"## Context Source ({src_type}): {desc or ref_id}\n"
                                f"Reference: {ref_id}"
                            )
                    except Exception as src_err:
                        logger.warning(f"Failed to load context source {src_type}:{ref_id}: {src_err}")

                if loaded_sources:
                    context_state["__context_sources__"] = "\n\n".join(loaded_sources)
                    logger.info(f"Loaded {len(loaded_sources)} context source(s) into execution context")

                    # Auto-ingest all loaded sources into CORTEX knowledge root
                    try:
                        _knowledge_root = await cortex.get_knowledge_root(_tree_id)
                        if _knowledge_root:
                            for _src_text in loaded_sources:
                                _title = _src_text.split("\n")[0][:100].replace("## Context Source: ", "").replace("## Context Source", "")
                                # Sanitize: strip null bytes that PostgreSQL UTF-8 rejects
                                _safe_content = _src_text[:50000].replace("\x00", "")
                                _safe_summary = _src_text[:300].replace("\x00", "")
                                _safe_title = f"📎 {_title}".replace("\x00", "")
                                await cortex.write(
                                    parent_id=_knowledge_root.id,
                                    node_type="knowledge",
                                    title=_safe_title,
                                    content=_safe_content,
                                    summary=_safe_summary,
                                    status="complete",
                                    source_ref={"type": "context_source"},
                                )
                            logger.info(f"Auto-ingested {len(loaded_sources)} context source(s) into CORTEX knowledge root")
                    except Exception as _ingest_err:
                        logger.warning(f"CORTEX auto-ingest of context sources failed: {_ingest_err}")
            
            # ── Phase 10D: RECURSIVE engine routing ─────────────────────
            reasoning_config_root = (entity.logic_gate or {}).get("reasoning_config", {})
            engine_type = reasoning_config_root.get("engine_type", "DAG")

            if engine_type == "RECURSIVE":
                from src.ai.core.recursive_engine import RecursiveReasoningEngine
                recursive = RecursiveReasoningEngine(
                    self.db, self.redis, company_id=entity.company_id
                )
                recursive_result = await recursive.execute_tree(
                    run_id=_run_id,
                    root_goal=entity.goal or entity.name,
                    context=context_state,
                    tree_id=_tree_id,
                )
                # Finalize the run with recursive result
                run.status = RunStatus.COMPLETED
                run.result_data = recursive_result
                run.context_state = _sanitize_context_for_persistence(context_state)
                run.completed_at = datetime.utcnow()
                run.execution_time_ms = int(
                    (run.completed_at - run.started_at).total_seconds() * 1000
                )
                # Write episodic memory
                from src.ai.memory.memory_service import MemoryRouter
                await MemoryRouter(self.db).write_episodic(run)
                await self.db.commit()
                await self._governance.settle_billing(run, entity.name)
                await self.redis.publish(
                    channel, json.dumps({"status": "COMPLETED", "result": run.result_data})
                )
                logger.info(
                    f"RecursiveEngine completed: {recursive_result.get('total_expansions', 0)} "
                    f"expansions, cost=${recursive_result.get('total_cost_usd', '0')}"
                )
                return run.result_data
            # ── End RECURSIVE routing ──────────────────────────────────

            # 4. Plan Generation/Reconciliation (DAG mode — default)
            logger.info(f"--- Starting CORTEX Execution {_run_id} for Entity {entity.name} ---")
            plan = await self._get_reconciled_plan(run, entity, context_state)
            steps = plan.get("steps", [])
            logger.info(f"[RUN:{run_id}] Phase 5/7: Plan reconciled ({len(steps)} steps)")
            run.dynamic_plan = plan
            await self.db.commit()

            # Inject execution metadata for observability.
            reasoning_config = (entity.logic_gate or {}).get("reasoning_config", {})
            is_autonomous = reasoning_config.get("execution_mode") == "AUTONOMOUS"
            context_state["__execution_metadata__"] = {
                "engine_type": engine_type,
                "memory_pipeline": _memory_pipeline,
                "memory_scope": _memory_scope,
                "total_steps": len(steps),
                "autonomous": is_autonomous,
            }

            # C4: Get working memory root for writing step outputs
            working_root = await cortex.get_working_root(_tree_id)
            if not working_root:
                logger.warning(f"CORTEX: Working memory root not found for tree {_tree_id}")
                raise CortexError(f"CORTEX tree {_tree_id} has no working memory root")
            # Cache the UUID to prevent MissingGreenlet when ORM attributes expire
            # after session commits during long step execution loops
            working_root_id = working_root.id

            # 5. Execute Plan Steps with CORTEX
            governance = entity.governance or {}
            checkpoint_every_n = int(governance.get("checkpoint_every_n_steps", 3))

            if self._has_parallel_steps(steps):
                all_step_results = await self._execute_steps_dag(run, entity, steps, context_state)
                # Write DAG results to tree
                for sr in all_step_results:
                    await self._write_step_to_cortex(
                        cortex, working_root_id, sr, _run_id
                    )
            else:
                # Autonomous mode configuration
                reasoning_config = (entity.logic_gate or {}).get("reasoning_config", {})
                is_autonomous = reasoning_config.get("execution_mode") == "AUTONOMOUS"
                goal_interval = reasoning_config.get("goal_validation_interval", 2)
                confidence_threshold = reasoning_config.get("confidence_threshold", 0.85)
                max_replans = reasoning_config.get("max_replanning_attempts", 3)
                self_reflect = reasoning_config.get("self_reflection_enabled", False)
                replanning_count = 0

                # Track completed steps using a dedicated set — NOT context_state keys.
                # context_state includes user input_data, which may have keys matching
                # step_ids (e.g. from prompt_template {{variable}} extraction), causing
                # steps to be incorrectly skipped.  For retries, the set is pre-populated
                # from the previous run's __completed_steps__.
                completed_steps: set = set(context_state.get("__completed_steps__", []))

                # ── Refinement mode detection ──────────────────────────────
                refinement_feedback = input_data.get("__refinement_feedback__")
                reuse_outputs = input_data.get("__reuse_outputs__", {})
                skip_steps_set = set(input_data.get("__skip_steps__", []))
                is_refinement = bool(refinement_feedback)
                if is_refinement:
                    logger.info(
                        f"[RUN:{run_id}] Refinement mode: {len(skip_steps_set)} steps to skip, "
                        f"feedback='{refinement_feedback[:80]}...'"
                    )

                for step_idx, step in enumerate(steps):
                    # Refresh run to prevent MissingGreenlet from pool_pre_ping
                    # during long-running pipelines where DB connections may be recycled
                    await self.db.refresh(run)

                    step_obj_check = PlanStep(**step)
                    if step_obj_check.step_id and step_obj_check.step_id in completed_steps:
                        logger.debug(f"Skipping already-completed step: {step_obj_check.name}")
                        continue

                    step_obj = PlanStep(**step)

                    # ── Refinement: skip steps that don't need re-execution ──
                    if is_refinement and step_obj.step_id and step_obj.step_id in skip_steps_set:
                        cached_output = reuse_outputs.get(step_obj.step_id)
                        if cached_output is not None:
                            _store_step_output(
                                context_state, step_obj.name,
                                step_obj.step_id, cached_output
                            )
                            all_step_results.append({
                                "step": step_obj.name,
                                "step_id": step_obj.step_id,
                                "type": step_obj.type,
                                "output": cached_output,
                                "reused": True,
                            })
                            completed_steps.add(step_obj.step_id)
                            context_state["__completed_steps__"] = list(completed_steps)
                            logger.info(f"Refinement: reused cached output for '{step_obj.name}'")

                            # Publish step progress for SSE
                            await self.redis.publish(channel, json.dumps({
                                "status": "STEP_REUSED",
                                "step": step_obj.name,
                                "step_id": step_obj.step_id,
                            }))
                            continue

                    # ── Refinement: inject feedback into context for re-executed steps ──
                    if is_refinement and refinement_feedback:
                        context_state["__refinement_feedback__"] = (
                            f"\n⚠️ REFINEMENT REQUEST from user:\n"
                            f"{refinement_feedback}\n\n"
                            f"Apply the above changes while preserving all other "
                            f"aspects of the original output. Focus ONLY on the "
                            f"requested modifications.\n"
                        )

                    # ── Phase 5: Self-reflection — inject prior knowledge ──
                    if is_autonomous and self_reflect and step_obj.type == StepType.THOUGHT:
                        try:
                            knowledge = await self._cortex_bridge.get_relevant_knowledge(
                                _tree_id, step_obj.description or step_obj.name
                            )
                            if knowledge:
                                context_state["__cortex_knowledge__"] = knowledge
                                logger.debug(f"Injected CORTEX knowledge ({len(knowledge)} chars) before THOUGHT step")
                        except Exception as _kr_err:
                            logger.debug(f"CORTEX knowledge retrieval failed: {_kr_err}")

                    # Handle CORTEX-specific step types
                    if step_obj.type in (StepType.NAVIGATE, StepType.READ, StepType.WRITE,
                                         StepType.RECURSE, StepType.AWAIT_CHILDREN):
                        step_result = await self._execute_cortex_step(
                            run, entity, step_obj, cortex, tree, context_state
                        )
                    else:
                        step_result = await self._execute_step_wrapper(
                            run, entity, step_obj, context_state
                        )

                    all_step_results.append(step_result)

                    # ── Phase 5: Mid-execution re-planning on failure ──
                    if is_autonomous and isinstance(step_result, dict) and step_result.get("error"):
                        if replanning_count < max_replans:
                            replanning_count += 1
                            logger.info(
                                f"Autonomous re-planning ({replanning_count}/{max_replans}) "
                                f"after step '{step_obj.name}' failure"
                            )
                            try:
                                revised = await self._planner.adapt_plan(
                                    original_plan=steps,
                                    completed_steps=all_step_results,
                                    failed_step=step_result,
                                    goal=entity.goal or entity.name,
                                )
                                if revised:
                                    # Replace remaining steps with revised plan
                                    steps = steps[:step_idx + 1] + revised
                                    logger.info(f"Re-planned: {len(revised)} new steps added")
                            except Exception as _replan_err:
                                logger.warning(f"Re-planning failed: {_replan_err}")

                    # ── Incremental billing (delegated to GovernanceService) ──
                    step_cost = Decimal("0")
                    if isinstance(step_result, dict):
                        step_cost = Decimal(str(step_result.get("cost_usd", 0) or 0))
                    if step_cost > 0:
                        await self._governance.consume_step_cost(run, step_obj.name, step_cost)

                    # ── Periodic credit circuit-breaker ────────────────────────
                    await self._governance.check_credit_circuit_breaker(run, step_obj.name)

                    # Write step result as a finding node in the CORTEX tree
                    await self._write_step_to_cortex(
                        cortex, working_root_id, step_result, _run_id
                    )

                    # ── Phase 5: Write reflection node ──
                    if is_autonomous and self_reflect:
                        try:
                            output_summary = str(step_result.get("output", ""))[:500] if isinstance(step_result, dict) else ""
                            if output_summary:
                                await self._cortex_bridge.write_reflection(
                                    _tree_id,
                                    tree.resume_cursor_id or working_root_id,
                                    step_obj.name,
                                    f"Step completed. Output summary: {output_summary}",
                                )
                        except Exception as _ref_err:
                            logger.debug(f"Reflection write failed: {_ref_err}")

                    # Track this step as completed for retry/resume
                    if step_obj.step_id:
                        completed_steps.add(step_obj.step_id)
                        context_state["__completed_steps__"] = list(completed_steps)

                    # Refresh viewport after each step (delegated to CortexBridge)
                    await self._cortex_bridge.refresh_viewport(cortex, tree, context_state)

                    # C5: Auto-checkpoint every N steps (delegated to CortexBridge)
                    if (step_idx + 1) % checkpoint_every_n == 0:
                        await self._cortex_bridge.write_checkpoint(
                            cortex, tree, context_state, step_obj.name
                        )
                        await self.db.commit()

                    # ── Phase 10D: MetaReviewer supervisory hook ──────────
                    governance_cfg = entity.governance or {}
                    meta_review_enabled = governance_cfg.get("meta_review_enabled", False)
                    meta_review_interval = int(governance_cfg.get("meta_review_interval", 5))

                    if (meta_review_enabled and is_autonomous
                            and step_idx > 0 and step_idx % meta_review_interval == 0):
                        try:
                            from src.ai.core.meta_review import MetaReviewer
                            reviewer = MetaReviewer(self.db, entity.company_id)
                            meta_result = await reviewer.review_execution(
                                entity_goal=entity.goal or entity.name,
                                completed_steps=all_step_results,
                                remaining_steps=steps[step_idx + 1:],
                                total_cost_usd=float(run.total_cost_usd or 0),
                            )
                            if meta_result["recommendation"] == "REPLAN":
                                logger.info(f"MetaReviewer: REPLAN — {meta_result['reasoning']}")
                                if replanning_count < max_replans:
                                    replanning_count += 1
                                    revised = await self._planner.adapt_plan(
                                        steps, all_step_results, {}, entity.goal or entity.name
                                    )
                                    if revised:
                                        steps = steps[:step_idx + 1] + revised
                            elif meta_result["recommendation"] == "ABORT":
                                logger.warning(f"MetaReviewer: ABORT — {meta_result['reasoning']}")
                                raise MetaAgentAbort(meta_result["reasoning"])
                        except (ImportError, Exception) as _mr_err:
                            if 'MetaAgentAbort' in type(_mr_err).__name__:
                                raise
                            logger.debug(f"Meta-review failed (non-fatal): {_mr_err}")

                    # ── Phase 10D: GoalGuard validation gate (autonomous) ──
                    if is_autonomous and step_idx > 0 and step_idx % goal_interval == 0:
                        try:
                            from src.ai.planning.goal_guard import GoalGuard
                            guard = GoalGuard(
                                db=self.db,
                                company_id=entity.company_id,
                                entity_goal=entity.goal or entity.name,
                                task_description=context_state.get("input", ""),
                                planner=self._planner,
                                confidence_threshold=confidence_threshold,
                            )
                            guard_result = await guard.check(
                                step_result=step_result,
                                step_name=step_obj.name,
                                step_idx=step_idx,
                                all_results=all_step_results,
                                total_steps=len(steps),
                                is_autonomous=is_autonomous,
                                goal_interval=goal_interval,
                            )
                            if guard_result["action"] == "EARLY_EXIT":
                                logger.info(f"GoalGuard: {guard_result['reason']}")
                                break
                            elif guard_result["action"] == "REPLAN":
                                logger.info(f"GoalGuard: {guard_result['reason']}")
                                if replanning_count < max_replans:
                                    replanning_count += 1
                                    revised = await self._planner.adapt_plan(
                                        steps, all_step_results, {}, entity.goal or entity.name
                                    )
                                    if revised:
                                        steps = steps[:step_idx + 1] + revised
                        except Exception as _gv_err:
                            logger.debug(f"GoalGuard validation failed: {_gv_err}")

                    if self._step_executor._should_exit(step_obj, context_state):
                        break

            # 6. Finalize
            await self.db.refresh(run)  # ensure all attrs loaded before final writes
            run.status = RunStatus.COMPLETED
            # Use full output from all_step_results (not context_state which
            # may be capped at MAX_CONTEXT_VALUE_SIZE for prompt injection).
            # The final user-facing output should always be the complete data.
            last_step_result = all_step_results[-1] if all_step_results else None
            if last_step_result and isinstance(last_step_result, dict):
                final_output = last_step_result.get("output", "") or ""
            else:
                last_step_name = steps[-1]["name"] if steps else None
                final_output = context_state.get(last_step_name) if last_step_name else "Success"
            
            run.result_data = {"output": final_output, "steps": all_step_results}
            # SEC-1 fix: sanitize context before persisting to DB
            run.context_state = _sanitize_context_for_persistence(context_state)
            run.completed_at = datetime.utcnow()
            run.execution_time_ms = int((run.completed_at - run.started_at).total_seconds() * 1000)
            
            # Write final output to the CORTEX output subtree
            if _tree_output_root_id and final_output:
                try:
                    await cortex.write(
                        parent_id=_tree_output_root_id,
                        node_type="output",
                        title="Final Output",
                        summary=str(final_output)[:300],
                        content=str(final_output)[:50000],
                        status="complete",
                    )
                except Exception as e:
                    logger.warning(f"Failed to write final output to CORTEX tree: {e}")

            # S2: Write episodic memory for top-level runs
            # Use direct import instead of removed local variable.
            from src.ai.memory.memory_service import MemoryRouter as _MemRouter
            await _MemRouter(self.db).write_episodic(run)

            # Tree stays ACTIVE for future resumption (not COMPLETE)
            tree.last_active_at = datetime.utcnow()
            _result_data = run.result_data  # cache before commit expires ORM attrs
            
            await self.db.commit()

            # 7. Final Billing Settlement (delegated to GovernanceService)
            await self._governance.settle_billing(run, entity.name)

            await self.redis.publish(channel, json.dumps({"status": "COMPLETED", "result": _result_data}))
            return _result_data

        except CreditExhaustedError as e:
            # Credit exhaustion — expected during billing-gated runs
            try:
                await self.db.rollback()
                async with AsyncSessionLocal() as fresh_db:
                    result = await fresh_db.execute(
                        select(ExecutionRun).where(ExecutionRun.id == run_id)
                    )
                    failed_run = result.scalar_one()
                    failed_run.status = RunStatus.FAILED
                    failed_run.error_message = f"Credits exhausted: {str(e)[:500]}"
                    failed_run.completed_at = datetime.utcnow()
                    if context_state:
                        failed_run.context_state = _sanitize_context_for_persistence(context_state)
                    await fresh_db.commit()
                await self.redis.publish(channel, json.dumps({"status": "FAILED", "error": f"Credits exhausted: {e}"}))
            except Exception:
                logger.error(f"Failed to persist FAILED status for run {run_id}: {e}")
            raise

        except MetaAgentAbort as e:
            # Meta-agent decided to abort — expected in supervised runs
            try:
                await self.db.rollback()
                async with AsyncSessionLocal() as fresh_db:
                    result = await fresh_db.execute(
                        select(ExecutionRun).where(ExecutionRun.id == run_id)
                    )
                    failed_run = result.scalar_one()
                    failed_run.status = RunStatus.FAILED
                    failed_run.error_message = f"Meta-Agent abort: {str(e)[:500]}"
                    failed_run.completed_at = datetime.utcnow()
                    if context_state:
                        failed_run.context_state = _sanitize_context_for_persistence(context_state)
                    await fresh_db.commit()
                await self.redis.publish(channel, json.dumps({"status": "FAILED", "error": f"Meta-Agent abort: {e}"}))
            except Exception:
                logger.error(f"Failed to persist FAILED status for run {run_id}: {e}")
            raise

        except BudgetExhaustedError as e:
            # Per-entity cost cap reached — a clean, terminal stop, NOT a failure.
            # Work completed up to the cap is kept and billed (PARTIAL_COMPLETE),
            # and we do NOT re-raise: re-raising would let arq retry and re-bill
            # the run. The dispatch idempotency guard treats PARTIAL_COMPLETE as
            # terminal, so even an external re-dispatch is a no-op.
            partial_result = None
            try:
                await self.db.rollback()
                async with AsyncSessionLocal() as fresh_db:
                    result = await fresh_db.execute(
                        select(ExecutionRun)
                        .options(selectinload(ExecutionRun.entity))
                        .where(ExecutionRun.id == run_id)
                    )
                    capped_run = result.scalar_one()
                    capped_run.status = RunStatus.PARTIAL_COMPLETE
                    capped_run.error_message = f"Budget cap reached: {str(e)[:500]}"
                    capped_run.completed_at = datetime.utcnow()
                    if context_state:
                        capped_run.context_state = _sanitize_context_for_persistence(context_state)
                    partial_result = capped_run.result_data
                    await fresh_db.commit()
                    # Settle billing for the partial spend on the same fresh session.
                    try:
                        from src.ai.governance.governance_service import GovernanceService
                        _entity_name = getattr(capped_run.entity, "name", "") or ""
                        await GovernanceService(fresh_db, self.redis).settle_billing(
                            capped_run, _entity_name
                        )
                    except Exception:
                        logger.warning(
                            f"Budget-cap billing settle failed for run {run_id}",
                            exc_info=True,
                        )
                await self.redis.publish(
                    channel,
                    json.dumps({"status": "PARTIAL_COMPLETE", "error": str(e)[:500]}),
                )
                logger.warning(f"Run {run_id} stopped at budget cap: {e}")
            except Exception:
                logger.error(f"Failed to persist PARTIAL_COMPLETE for run {run_id}: {e}")
            return partial_result

        except AgentError as e:
            # Agent-level errors (typed, expected failures)
            try:
                await self.db.rollback()
                async with AsyncSessionLocal() as fresh_db:
                    result = await fresh_db.execute(
                        select(ExecutionRun).where(ExecutionRun.id == run_id)
                    )
                    failed_run = result.scalar_one()
                    failed_run.status = RunStatus.FAILED
                    failed_run.error_message = f"{type(e).__name__}: {str(e)[:500]}"
                    failed_run.completed_at = datetime.utcnow()
                    if context_state:
                        failed_run.context_state = _sanitize_context_for_persistence(context_state)
                    await fresh_db.commit()
                await self.redis.publish(channel, json.dumps({"status": "FAILED", "error": str(e)[:500]}))
            except Exception:
                logger.error(f"Failed to persist FAILED status for run {run_id}: {e}")
            raise

        except BaseException as e:
            # Infrastructure failure (timeouts, cancellations, unexpected)
            try:
                await self.db.rollback()
                async with AsyncSessionLocal() as fresh_db:
                    result = await fresh_db.execute(
                        select(ExecutionRun).where(ExecutionRun.id == run_id)
                    )
                    failed_run = result.scalar_one()
                    failed_run.status = RunStatus.FAILED
                    err_type = type(e).__name__
                    failed_run.error_message = f"Infrastructure: {err_type}: {str(e)[:500]}"
                    failed_run.completed_at = datetime.utcnow()
                    if context_state:
                        failed_run.context_state = _sanitize_context_for_persistence(context_state)
                    await fresh_db.commit()
                await self.redis.publish(channel, json.dumps({"status": "FAILED", "error": f"{type(e).__name__}: {str(e)[:500]}"}))
            except Exception:
                logger.error(f"Failed to persist FAILED status for run {run_id}: {e}")
            raise

    # ===================================================================
    # CORTEX Execution Helpers
    # ===================================================================

    def _build_task_description(self, entity: 'HierarchicalEntity', input_data: dict) -> str:
        """Delegate to CortexBridge (Phase 3 extraction)."""
        return self._cortex_bridge.build_task_description(entity, input_data)

    async def _write_step_to_cortex(
        self,
        cortex: 'CortexService',
        working_root_id: UUID,
        step_result: dict,
        run_id: UUID,
    ) -> None:
        """Delegate to CortexBridge (Phase 3 extraction)."""
        await self._cortex_bridge.write_step(cortex, working_root_id, step_result, run_id)

    async def _ingest_tool_result_to_cortex(
        self,
        run: 'ExecutionRun',
        tool_id: str,
        tool_output: str,
        context: dict,
    ) -> None:
        """Delegate to CortexBridge (Phase 3 extraction)."""
        await self._cortex_bridge.ingest_tool_result(run, tool_id, tool_output, context)

    async def _execute_cortex_step(
        self,
        run: 'ExecutionRun',
        entity: 'HierarchicalEntity',
        step: PlanStep,
        cortex: 'CortexService',
        tree,
        context: dict,
    ) -> dict:
        """Delegate to CortexBridge (Phase 3 extraction)."""
        return await self._cortex_bridge.execute_cortex_step(
            run, entity, step, cortex, tree, context
        )

    def _resolve_node_id(self, target, context: dict) -> str:
        """Delegate to CortexBridge (Phase 3 extraction)."""
        return self._cortex_bridge.resolve_node_id(target, context)
            
    def _extract_text_from_file(self, file_path, mime_type: str = "") -> str:
        """Delegate to standalone text_extractor module (Phase 6 dedup)."""
        from src.ai.text_extractor import extract_text_from_file
        return extract_text_from_file(file_path, mime_type)

    def _has_parallel_steps(self, steps: List[dict]) -> bool:
        """Delegate to PlannerService (Phase 3 extraction)."""
        return self._planner.has_parallel_steps(steps)

    async def _get_reconciled_plan(self, run: ExecutionRun, entity: HierarchicalEntity, input_data: dict) -> dict:
        """Delegate to PlannerService (Phase 3 extraction)."""
        return await self._planner.reconcile(run, entity, input_data)


