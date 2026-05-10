from arq import Worker
from arq.connections import RedisSettings
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from uuid import UUID, uuid4
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import logging
from src.common.database import AsyncSessionLocal
from src.ai.models import (
    ExecutionRun, HierarchicalEntity, LLMInteractionLog, EntityType,
    RunStatus, Document, DocumentChunk, ToolInteractionLog, HumanApproval
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
from src.ai.memory_service import MemoryRouter  # S1: Memory
from src.ai.llm_router import LLMRouter        # Model-agnostic LLM dispatch
from src.ai.governance_service import GovernanceService
from src.ai.planner_service import PlannerService
from src.ai.cortex_bridge import CortexBridge
from src.ai.step_executor import StepExecutorService
import src.auth.models
import src.config.models
import src.ai.cortex_models  # Required: EpisodicMemory FK references cortex_trees
from src.ai.cortex_service import CortexRouter as CortexService
from src.ai.cortex_models import CortexNodeType
import asyncio
import json
import re
import copy
from src.ai.constants import INTERNAL_CONTEXT_KEYS, MAX_REACT_TURNS

logger = logging.getLogger(__name__)

# --- Prompt Templates ---
# These are now defined in schemas.py and stored on the entity.
# The constants below are kept only as local aliases for backward compatibility
# when an entity has no override configured.
DYNAMIC_PLANNER_PROMPT = DEFAULT_PLANNING_SYSTEM_PROMPT
DEFAULT_REVIEW_PROMPT = DEFAULT_REVIEW_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Ph-B: UncertaintySignal — raised by _execute_thought when the LLM explicitly
# signals it needs clarification before proceeding.
# Caught by _execute_step_wrapper: routes to HITL or partial-completion annotation.
# ---------------------------------------------------------------------------

class UncertaintySignal(Exception):
    """
    Raised when the LLM explicitly signals it cannot proceed without
    clarification.  The LLM must include the following JSON block anywhere
    in its response to trigger this path:

        {"needs_clarification": true, "question": "...", "confidence": 0.3}

    Attributes:
        question:      The clarifying question the agent wants to ask.
        confidence:    Estimated confidence in completing the task without input (0–1).
        alternatives:  Optional list of alternative interpretations the LLM suggests.
    """
    def __init__(self, question: str, confidence: float = 0.0, alternatives: list = None):
        super().__init__(question)
        self.question = question
        self.confidence = confidence
        self.alternatives = alternatives or []


def _store_step_output(context_state: dict, step_name: str, step_id: str, output: str, cortex_bridge=None) -> None:
    """Store step output in context (Phase 4 — DATA-1).

    Full output is preserved to ensure inter-step data integrity (e.g. research
    findings flowing into synthesis → report → PDF). Context growth for LLM
    prompt construction is managed separately by _maybe_summarize_context(),
    which intelligently trims older entries when the total context exceeds
    configurable thresholds.
    """
    value = output
    # Phase 6 PERF-3: Incremental context size tracking
    old_value = context_state.get(step_name, "")
    context_state[step_name] = value
    if cortex_bridge:
        cortex_bridge.update_context_size(step_name, old_value, value)
    if step_id and step_id != step_name:
        old_id_value = context_state.get(step_id, "")
        context_state[step_id] = value
        if cortex_bridge:
            cortex_bridge.update_context_size(step_id, old_id_value, value)
# ---------------------------------------------------------------------------
# Ph-A: GoalNode — unit of the goal decomposition tree used by
# RecursiveReasoningEngine (defined at module bottom).
# ---------------------------------------------------------------------------

@dataclass
class GoalNode:
    """
    A single node in the goal decomposition tree.

    Fields:
        goal:         Natural-language description of the sub-goal.
        depth:        Current depth in the tree (0 = root).
        confidence:   LLM self-reported confidence for this goal (0–1).
        parent:       Reference to parent GoalNode (None for root).
        children:     Child GoalNodes generated by `expand_goal()`.
        result:       Final string result once the goal is executed.
        status:       'pending' | 'running' | 'completed' | 'failed'
    """
    goal: str
    depth: int = 0
    confidence: float = 1.0
    parent: Optional['GoalNode'] = field(default=None, repr=False)
    children: List['GoalNode'] = field(default_factory=list)
    result: Optional[str] = None
    status: str = 'pending'

    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "depth": self.depth,
            "confidence": self.confidence,
            "status": self.status,
            "result": self.result,
            "children": [c.to_dict() for c in self.children],
        }

# --- Helper Functions ---

def parse_variables(text: str, variables: dict) -> str:
    """Replaces {{variable}} and {variable} in text with values from variables dict.
    
    Supports both double-brace ``{{topic}}`` and single-brace ``{topic}`` syntax.
    Double-brace patterns are replaced first (higher priority / more explicit),
    then single-brace patterns for any remaining placeholders.
    """
    if not text:
        return ""

    def _resolve(key: str, fallback: str):
        val = variables
        parts = key.split('.')
        for i, k in enumerate(parts):
            if isinstance(val, dict):
                val = val.get(k, None)
            else:
                # If we landed on a non-dict value and the remaining part is
                # just "output", the value itself IS the output — return it.
                # This handles {{step_1.output}} when context stores step_1="result text".
                remaining = parts[i:]
                if remaining == ["output"] and val is not None:
                    return str(val)
                return fallback
        if val is None or val is variables:
            return fallback
        return str(val)

    # Pass 1: double-brace {{var}}
    def replace_double(match):
        key = match.group(1).strip()
        return _resolve(key, match.group(0))
    text = re.sub(r'\{\{(.*?)\}\}', replace_double, text)

    # Pass 2: single-brace {var}  (skip if looks like JSON / Python format string)
    def replace_single(match):
        key = match.group(1).strip()
        # Skip patterns that look like JSON or contain spaces/special chars
        if not key or ' ' in key or ':' in key or ',' in key or '"' in key:
            return match.group(0)
        return _resolve(key, match.group(0))
    text = re.sub(r'(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_.]*)\}(?!\})', replace_single, text)

    return text


def build_sandwich_prompt(
    identity: str,
    goal: Optional[str] = None,
    tools: Optional[List[Dict]] = None,
    few_shot_examples: Optional[List[Dict[str, str]]] = None,
    context: Optional[str] = None,
    current_task: str = "",
    output_schema: Optional[Dict] = None,
    success_criteria: Optional[List[Dict]] = None,
    allowed_deviations: Optional[Dict] = None,
    execution_constraints: Optional[Dict] = None,
) -> str:
    """
    Build structured prompt using the 'Sandwich Method'.
    
    Layers:
    1. Identity & Role (Who I am)
    2. Goal & Objective (What I'm trying to achieve)
    3. Tools & Capabilities (What I can do)
    4. Few-Shot Examples (How I should behave)
    5. Success Criteria (How output will be judged)
    6. Planning Permissions (Dynamic planning deviations)
    7. Output Format (Required output schema)
    8. Execution Constraints (Cost/tool limits)
    9. Context/History (What happened so far)
    10. Current Task (What I need to do now)
    """
    sections = []
    
    # Layer 1: Identity & Role
    sections.append(f"## Identity & Role\n{identity}")
    
    # Layer 2: Goal & Objective
    if goal:
        sections.append(f"## Goal & Objective\n{goal}")
    
    # Layer 3: Tools & Capabilities
    if tools:
        tool_descriptions = "\n".join([
            f"- **{t['name']}**: {t['description']}" for t in tools
        ])
        sections.append(f"## Available Tools\nYou can use the following tools:\n{tool_descriptions}")
    
    # Layer 4: Few-Shot Examples
    if few_shot_examples:
        example_text = "\n\n".join([
            f"**Scenario**: {ex.get('scenario', ex.get('input', ''))}\n**Response**: {ex.get('ideal_response', ex.get('output', ''))}"
            for ex in few_shot_examples
        ])
        sections.append(f"## Examples of Expected Behavior\n{example_text}")
    
    # Layer 5: Success Criteria
    if success_criteria:
        criteria_lines = "\n".join(
            f"- {sc.get('criterion', sc)} (validated by: {sc.get('validation_type', 'llm_judge')})"
            if isinstance(sc, dict) else f"- {sc}"
            for sc in success_criteria
        )
        sections.append(f"## Success Criteria\nYour output will be evaluated against:\n{criteria_lines}")
    
    # Layer 6: Planning Permissions
    if allowed_deviations:
        perm_lines = []
        if allowed_deviations.get("can_add_steps"):
            perm_lines.append("- You MAY add additional steps if needed")
        if allowed_deviations.get("can_skip_optional_steps"):
            perm_lines.append("- You MAY skip optional steps")
        if allowed_deviations.get("can_reorder_steps"):
            perm_lines.append("- You MAY reorder steps for efficiency")
        if allowed_deviations.get("can_change_tools"):
            perm_lines.append("- You MAY choose different tools than specified")
        if perm_lines:
            sections.append(f"## Planning Permissions\n" + "\n".join(perm_lines))
    
    # Layer 7: Output Format
    if output_schema and output_schema.get("properties"):
        schema_str = json.dumps(output_schema, indent=2)
        sections.append(
            f"## Required Output Format\n"
            f"Your response MUST conform to this JSON schema:\n```json\n{schema_str}\n```"
        )
    
    # Layer 8: Execution Constraints
    if execution_constraints:
        constraint_lines = []
        for key, val in execution_constraints.items():
            constraint_lines.append(f"- {key}: {val}")
        sections.append(f"## Execution Constraints\n" + "\n".join(constraint_lines))
    
    # Layer 9: Context/History
    if context:
        sections.append(f"## Previous Context\n{context}")
    
    # Layer 10: Current Task
    sections.append(f"## Current Task\n{current_task}")
    
    return "\n\n".join(sections)


def filter_context_for_step(
    step: PlanStep, 
    full_context: dict, 
    context_policy: Optional[Dict] = None
) -> dict:
    """
    Filter context based on step's explicit inputs and policy.
    
    Args:
        step: The plan step being executed
        full_context: Full execution context dictionary
        context_policy: Policy configuration from logic_gate
        
    Returns:
        Filtered context dictionary
    """
    if not context_policy:
        return full_context
    
    # Check for explicit input dependencies in step target
    if step.target and hasattr(step.target, 'input_dependencies'):
        deps = step.target.input_dependencies or []
        if deps:
            filtered = {"input": full_context.get("input")}
            for dep in deps:
                if dep in full_context:
                    filtered[dep] = full_context[dep]
            return filtered
    
    # Apply context policy
    policy_type = context_policy.get("type", "FULL")
    
    if policy_type == "LAST_N":
        n = context_policy.get("n", 3)
        keys = list(full_context.keys())
        # Always include 'input' and last N keys
        filtered = {"input": full_context.get("input")} if "input" in full_context else {}
        for k in keys[-n:]:
            filtered[k] = full_context[k]
        return filtered
    
    elif policy_type == "SLIDING_WINDOW":
        max_chars = context_policy.get("max_chars", 4000)
        filtered = {}
        total_chars = 0
        # Include from most recent first
        for k in reversed(list(full_context.keys())):
            v_str = str(full_context[k])
            if total_chars + len(v_str) <= max_chars:
                filtered[k] = full_context[k]
                total_chars += len(v_str)
            else:
                break
        return dict(reversed(list(filtered.items())))
    
    elif policy_type == "EXPLICIT":
        explicit_keys = context_policy.get("explicit_keys", [])
        return {k: full_context[k] for k in explicit_keys if k in full_context}
    
    # FULL - return everything
    return full_context



# ---------------------------------------------------------------------------
# SEC-1: Strip sensitive keys from context_state before persisting to DB.
# Prevents accidental exposure of API keys, secrets, and internal
# bookkeeping data in DB dumps or API responses.
# ---------------------------------------------------------------------------
_SENSITIVE_CONTEXT_KEYS = frozenset({
    "api_key", "api_secret", "secret", "token", "password",
    "auth", "authorization", "credential", "credentials",
    "__model_override",
})


def _sanitize_context_for_persistence(ctx: dict) -> dict:
    """Return a shallow copy of ctx with sensitive keys redacted."""
    if not ctx:
        return ctx
    sanitized = {}
    for k, v in ctx.items():
        key_lower = k.lower()
        if any(sk in key_lower for sk in _SENSITIVE_CONTEXT_KEYS):
            continue  # drop entirely
        sanitized[k] = v
    return sanitized


# --- Execution Engine ---

class ExecutionEngine:
    def __init__(self, db: AsyncSessionLocal, redis_pool, company_id: UUID = None):
        self.db = db
        self.redis = redis_pool
        self.config_service = ConfigService(db)
        self.usage_service = UsageService(db)
        # Phase 3: Composed services (initialized when company_id is known)
        self.company_id = company_id
        self._governance = GovernanceService(db, redis_pool) if company_id else None
        self._planner = PlannerService(db, company_id) if company_id else None
        self._cortex_bridge = CortexBridge(db, company_id, self.usage_service, redis=redis_pool) if company_id else None
        self._step_executor = StepExecutorService(
            db, redis_pool, company_id, self.usage_service,
            cortex_bridge=self._cortex_bridge,
            execute_run_fn=self.execute_run,
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
            )

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
                # Single-step batch: run on self.db (no isolation overhead)
                step_obj = PlanStep(**ready[0])
                result = await self._execute_step_wrapper(run, entity, step_obj, context_state)
                results_map[ready[0]["step_id"]] = result
                completed.add(ready[0]["step_id"])
            else:
                # Multi-step parallel batch: each step gets its own AsyncSession.
                # P1-A: This prevents PendingRollbackError when two coroutines
                # share self.db and one fails mid-transaction.
                # RACE-1 fix: Each step gets a deep-copied context to prevent
                # cross-contamination between parallel coroutines.
                # RACE-2 fix: Pass run_id instead of ORM object; reload in
                # isolated session. Use atomic DB increments for cost/tokens.
                async def _isolated_step(step_dict: dict, frozen_ctx: dict) -> dict:
                    async with AsyncSessionLocal() as isolated_db:
                        isolated_engine = ExecutionEngine(isolated_db, self.redis)
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
                        # Atomic cost/token increment (RACE-2 fix)
                        step_cost = step_result.get("cost_usd", Decimal("0")) if isinstance(step_result, dict) else Decimal("0")
                        step_tokens = step_result.get("tokens", 0) if isinstance(step_result, dict) else 0
                        if step_cost or step_tokens:
                            await isolated_db.execute(
                                update(ExecutionRun)
                                .where(ExecutionRun.id == run.id)
                                .values(
                                    total_cost_usd=ExecutionRun.total_cost_usd + step_cost,
                                    total_tokens=ExecutionRun.total_tokens + step_tokens,
                                )
                            )
                            await isolated_db.commit()
                        return step_result

                # RACE-1 fix: deep-copy context for each parallel step
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

    async def _execute_step_wrapper(self, run, entity, step_obj, context_state):
        """Wrapper to handle execution + review + context update for a single step.

        Ph-B: If the LLM raises UncertaintySignal, the step result is annotated
        with needs_clarification=True instead of crashing the run.

        Includes:
        - HITL checkpoint evaluation (BEFORE_STEP, COST_THRESHOLD, TOOL_CALL)
        - Timeout enforcement via asyncio.wait_for
        - Observability-gated logging
        """
        observability = entity.observability or {}
        log_thoughts = observability.get("log_thoughts", True)
        governance = entity.governance or {}
        timeout_ms = governance.get("timeout_ms", 60000)

        # ── HITL: Evaluate BEFORE_STEP and COST_THRESHOLD checkpoints ───────
        await self._evaluate_hitl_checkpoints(
            run, entity, step_obj, context_state, phase="BEFORE"
        )

        # ── Execute with timeout enforcement ────────────────────────────────
        try:
            try:
                step_result = await asyncio.wait_for(
                    self._execute_step(run, entity, step_obj, context_state),
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
            run, entity, step_obj, context_state, phase="AFTER"
        )

        # Review Mechanism
        if entity.logic_gate and entity.logic_gate.get("review_mechanism", {}).get("enabled"):
            step_result = await self._review_step_output(run, entity, step_obj, step_result, context_state)

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
    ) -> None:
        """Delegate to GovernanceService (Phase 3 extraction)."""
        await self._governance.evaluate_hitl(run, entity, step_obj, context_state, phase)


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
            raise Exception(f"Run {run_id} not found")

        entity = run.entity
        if not entity:
            raise Exception(f"Entity for run {run_id} not found")

        # Phase 3: Initialize composed services with company_id
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
        logger.info(f"Logging level set to {entity_log_level} for entity {entity.name}")

        # 3. Update Status and Initialize Trace
        run.status = RunStatus.RUNNING
        run.started_at = datetime.utcnow()
        if not run.trace_id:
            run.trace_id = run.id
        await self.db.commit()
        
        # Publish Update
        channel = f"execution:{run.id}"
        await self.redis.publish(channel, json.dumps({"status": "RUNNING", "run_id": str(run.id)}))

        # ── Pre-execution credit balance gate (delegated to GovernanceService) ─
        entity_type_str = entity.type.value if hasattr(entity.type, 'value') else str(entity.type)
        await self._governance.check_credit_gate(
            run.company_id, entity_type_str, is_child=bool(run.parent_run_id)
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
                    user_id=run.user_id,
                    task_description=task_desc,
                )
                viewport = await cortex.navigate(tree.root_node_id)
                last_checkpoint = None
                logger.info(f"CORTEX new tree: {tree.id}")

            # C2: Retrieve memory context with tree ID
            memory_router = MemoryRouter(self.db)
            memory_ctx = await memory_router.retrieve(
                entity_id=entity.id,
                user_id=run.user_id,
                tree_id=tree.id,
                long_running=True,
            )

            # C3: Build context from viewport (replaces context_state dict)
            context_state = input_data.copy()
            memory_text = memory_router.format_for_prompt(memory_ctx)
            if memory_text:
                context_state["__memory__"] = memory_text
            # Inject CORTEX viewport as the primary context
            context_state["__cortex_viewport__"] = viewport.to_prompt_text()
            context_state["__cortex_tree_id__"] = str(tree.id)

            # M5: Inject knowledge subtree summary for entities sharing a tree
            # This is critical for the synthesizer: it needs to READ the director's
            # accumulated knowledge nodes from the shared tree.
            try:
                knowledge_root = await cortex.get_knowledge_root(tree.id)
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
                        _knowledge_root = await cortex.get_knowledge_root(tree.id)
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
            
            # 4. Plan Generation/Reconciliation
            logger.info(f"--- Starting CORTEX Execution {run.id} for Entity {entity.name} ---")
            plan = await self._get_reconciled_plan(run, entity, context_state)
            steps = plan.get("steps", [])
            logger.info(f"Plan reconciled. Steps to execute: {len(steps)}")
            run.dynamic_plan = plan
            await self.db.commit()

            # C4: Get working memory root for writing step outputs
            working_root = await cortex.get_working_root(tree.id)
            if not working_root:
                logger.warning(f"CORTEX: Working memory root not found for tree {tree.id}")
                raise Exception(f"CORTEX tree {tree.id} has no working memory root")

            # 5. Execute Plan Steps with CORTEX
            governance = entity.governance or {}
            checkpoint_every_n = int(governance.get("checkpoint_every_n_steps", 3))

            if self._has_parallel_steps(steps):
                all_step_results = await self._execute_steps_dag(run, entity, steps, context_state)
                # Write DAG results to tree
                for sr in all_step_results:
                    await self._write_step_to_cortex(
                        cortex, working_root.id, sr, run.id
                    )
            else:
                # Phase 5: Autonomous mode configuration
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

                for step_idx, step in enumerate(steps):
                    step_obj_check = PlanStep(**step)
                    if step_obj_check.step_id and step_obj_check.step_id in completed_steps:
                        logger.debug(f"Skipping already-completed step: {step_obj_check.name}")
                        continue

                    step_obj = PlanStep(**step)

                    # ── Phase 5: Self-reflection — inject prior knowledge ──
                    if is_autonomous and self_reflect and step_obj.type == StepType.THOUGHT:
                        try:
                            knowledge = await self._cortex_bridge.get_relevant_knowledge(
                                tree.id, step_obj.description or step_obj.name
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
                        cortex, working_root.id, step_result, run.id
                    )

                    # ── Phase 5: Write reflection node ──
                    if is_autonomous and self_reflect:
                        try:
                            output_summary = str(step_result.get("output", ""))[:500] if isinstance(step_result, dict) else ""
                            if output_summary:
                                await self._cortex_bridge.write_reflection(
                                    tree.id,
                                    tree.resume_cursor_id or working_root.id,
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

                    # ── Phase 5: Goal validation gate (autonomous mode) ──
                    if is_autonomous and step_idx > 0 and step_idx % goal_interval == 0:
                        try:
                            validation = await self._planner.validate_goal_progress(
                                goal=entity.goal or entity.name,
                                completed_steps=all_step_results,
                                total_steps=len(steps),
                            )
                            score = validation.get("score", 0)
                            if score > confidence_threshold * 100:
                                logger.info(
                                    f"Goal achieved early at step {step_idx}: "
                                    f"score={score}, reasoning={validation.get('reasoning', '')[:200]}"
                                )
                                break  # Early exit — goal met
                            elif score < 30 and step_idx > len(steps) // 2:
                                logger.info(
                                    f"Low goal progress ({score}) past midpoint — "
                                    f"triggering re-plan"
                                )
                                if replanning_count < max_replans:
                                    replanning_count += 1
                                    revised = await self._planner.adapt_plan(
                                        steps, all_step_results, {}, entity.goal or entity.name
                                    )
                                    if revised:
                                        steps = steps[:step_idx + 1] + revised
                        except Exception as _gv_err:
                            logger.debug(f"Goal validation failed: {_gv_err}")

                    if self._should_exit(step_obj, context_state):
                        break

            # 6. Finalize
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
            if tree.output_root_id and final_output:
                try:
                    await cortex.write(
                        parent_id=tree.output_root_id,
                        node_type="output",
                        title="Final Output",
                        summary=str(final_output)[:300],
                        content=str(final_output)[:50000],
                        status="complete",
                    )
                except Exception as e:
                    logger.warning(f"Failed to write final output to CORTEX tree: {e}")

            # S2: Write episodic memory for top-level runs
            await memory_router.write_episodic(run)

            # Tree stays ACTIVE for future resumption (not COMPLETE)
            tree.last_active_at = datetime.utcnow()
            
            await self.db.commit()

            # 7. Final Billing Settlement (delegated to GovernanceService)
            await self._governance.settle_billing(run, entity.name)

            await self.redis.publish(channel, json.dumps({"status": "COMPLETED", "result": run.result_data}))
            return run.result_data

        except BaseException as e:
            # BaseException catches TimeoutError / CancelledError too,
            # ensuring orphaned runs are never left in RUNNING status.
            # ERR-1 fix: Use fresh session to persist FAILED status, since
            # the current session may be in a broken state.
            # ERR-2 fix: Use run_id (parameter) instead of run.id (ORM attribute)
            # because after rollback the ORM object is expired and accessing .id
            # triggers a synchronous lazy-load → MissingGreenlet in async context.
            try:
                await self.db.rollback()
                async with AsyncSessionLocal() as fresh_db:
                    result = await fresh_db.execute(
                        select(ExecutionRun).where(ExecutionRun.id == run_id)
                    )
                    failed_run = result.scalar_one()
                    failed_run.status = RunStatus.FAILED
                    err_type = type(e).__name__
                    failed_run.error_message = f"{err_type}: {str(e)[:500]}"
                    failed_run.completed_at = datetime.utcnow()
                    # SEC-1 fix: sanitize context before persisting
                    if context_state:
                        failed_run.context_state = _sanitize_context_for_persistence(context_state)
                    await fresh_db.commit()
                await self.redis.publish(channel, json.dumps({"status": "FAILED", "error": str(e)[:500]}))
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

    async def _execute_step(self, run: ExecutionRun, entity: HierarchicalEntity, step: PlanStep, context: dict) -> dict:
        """Delegate to StepExecutorService (Phase 6 extraction)."""
        return await self._step_executor._execute_step(run, entity, step, context)

    async def _execute_child_invocation(self, run: ExecutionRun, entity: HierarchicalEntity, step: PlanStep, context: dict) -> dict:
        """Delegate to StepExecutorService (Phase 6 extraction)."""
        return await self._step_executor._execute_child_invocation(run, entity, step, context)

    async def _execute_tool_call(self, run: ExecutionRun, entity: HierarchicalEntity, step: PlanStep, context: dict) -> dict:
        """Delegate to StepExecutorService (Phase 6 extraction)."""
        return await self._step_executor._execute_tool_call(run, entity, step, context)

    async def _execute_thought(self, run: ExecutionRun, entity: HierarchicalEntity, step: PlanStep, context: dict) -> dict:
        """Delegate to StepExecutorService (Phase 6 extraction)."""
        return await self._step_executor._execute_thought(run, entity, step, context)

    async def _log_usage(self, run, model_name: str, prompt_tokens: int, completion_tokens: int, log):
        """Delegate to StepExecutorService (Phase 6 extraction)."""
        return await self._step_executor._log_usage(run, model_name, prompt_tokens, completion_tokens, log)

    async def _maybe_summarize_context(self, run, entity, context_state: dict) -> dict:
        """Delegate to StepExecutorService (Phase 6 extraction)."""
        return await self._step_executor._maybe_summarize_context(run, entity, context_state)

    async def _review_step_output(self, run, entity, step, result, context_state: dict = None) -> dict:
        """Delegate to StepExecutorService (Phase 6 extraction)."""
        return await self._step_executor._review_step_output(run, entity, step, result, context_state)

    def _should_exit(self, step: PlanStep, context: dict) -> bool:
        """Delegate to StepExecutorService (Phase 6 extraction)."""
        return self._step_executor._should_exit(step, context)
# --- Arq Jobs ---

async def run_execution_recursive(ctx, run_id_str: str):
    run_id = UUID(run_id_str)
    import redis.asyncio as redis
    from src.common.config import settings
    
    redis_pool = redis.from_url(settings.REDIS_URL or "redis://localhost:6379")
    
    async with AsyncSessionLocal() as db:
        engine = ExecutionEngine(db, redis_pool)
        await engine.execute_run(run_id)
    
    await redis_pool.close()


async def process_gateway_event(ctx, envelope_dict: dict):
    """Process a gateway event (webhook/internal) by routing to the correct handler.

    This is the arq job function invoked by the CentralDispatcher when a webhook
    event arrives at the gateway.

    Routing:
      - sheet.row_inserted → Campaign-based outbound call pipeline
      - other events        → ExecutionRun via ExecutionEngine (text agents)
    """
    import redis.asyncio as redis
    from src.common.config import settings
    from src.ai.models import HierarchicalEntity, ExecutionRun, RunStatus

    client_id = envelope_dict.get("client_id", "")
    if not client_id:
        logger.warning("[process_gateway_event] No client_id in envelope — skipping")
        return

    raw_data = envelope_dict.get("raw_data", {})
    event_type = envelope_dict.get("event_type", "generic_event")
    source = envelope_dict.get("source", "unknown")
    correlation_id = envelope_dict.get("id", "")

    redis_pool = redis.from_url(settings.REDIS_URL or "redis://localhost:6379")

    try:
        async with AsyncSessionLocal() as db:
            # ── Entity resolution: prefer explicit entity_id from payload ────
            entity = None
            payload_entity_id = raw_data.get("raw", {}).get("entity_id") if isinstance(raw_data, dict) else None

            if payload_entity_id:
                try:
                    result = await db.execute(
                        select(HierarchicalEntity).where(
                            HierarchicalEntity.id == UUID(payload_entity_id),
                            HierarchicalEntity.company_id == UUID(client_id),
                            HierarchicalEntity.status != 'ARCHIVED',
                        )
                    )
                    entity = result.scalar_one_or_none()
                except Exception as e:
                    logger.warning(f"[process_gateway_event] entity_id lookup failed: {e}")

            # Fallback: first active entity for the company
            if not entity:
                result = await db.execute(
                    select(HierarchicalEntity).where(
                        HierarchicalEntity.company_id == UUID(client_id),
                        HierarchicalEntity.status != 'ARCHIVED',
                    ).limit(1)
                )
                entity = result.scalar_one_or_none()

            if not entity:
                logger.warning(
                    f"[process_gateway_event] No active entity for company {client_id}"
                )
                return

            logger.info(
                f"[process_gateway_event] Resolved entity '{entity.name}' "
                f"({entity.id}) — event={event_type} source={source}"
            )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # APPROACH C: Sheet row → Campaign-based outbound voice call
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if event_type == "sheet.row_inserted":
                await _handle_sheet_row_campaign(
                    db=db,
                    entity=entity,
                    client_id=client_id,
                    raw_data=raw_data,
                    correlation_id=correlation_id,
                    redis_pool=redis_pool,
                )
                return

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # Default: ExecutionRun path (text-based agents)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            run = ExecutionRun(
                company_id=UUID(client_id),
                entity_id=entity.id,
                input_data={
                    "input": json.dumps(raw_data),
                    "channel": envelope_dict.get("channel", "webhook"),
                    "source": source,
                    "event_type": event_type,
                    "correlation_id": correlation_id,
                },
                status=RunStatus.PENDING,
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)

            logger.info(
                f"[process_gateway_event] ExecutionRun {run.id} created — executing..."
            )

            engine = ExecutionEngine(db, redis_pool)
            await engine.execute_run(run.id)

            logger.info(
                f"[process_gateway_event] ExecutionRun {run.id} finished "
                f"(status={run.status})"
            )
    except Exception as exc:
        logger.error(
            f"[process_gateway_event] Failed for correlation={correlation_id}: {exc}",
            exc_info=True,
        )
    finally:
        await redis_pool.close()


async def _handle_sheet_row_campaign(
    db,
    entity,
    client_id: str,
    raw_data: dict,
    correlation_id: str,
    redis_pool,
):
    """Create a single-contact Campaign from a Google Sheets row and trigger outbound call.

    Pipeline: Campaign → CampaignExecutor._place_tata_call() → Tata Tele webhook
    → TataStreamHandler → GeminiLiveClient (speech-to-speech conversation)
    """
    from src.ai.campaign_models import Campaign, CampaignCall
    from arq.connections import RedisSettings, create_pool
    from src.common.config import settings as app_settings
    from src.auth.models import User

    # ── 1. Extract lead data from the webhook payload ───────────────────
    raw_payload = raw_data.get("raw", {}) if isinstance(raw_data, dict) else {}
    row_data = raw_payload.get("data", {})

    # Try common column names for phone number
    phone = (
        row_data.get("Phone")
        or row_data.get("phone")
        or row_data.get("Mobile")
        or row_data.get("mobile")
        or row_data.get("Phone Number")
        or row_data.get("phone_number")
        or row_data.get("Contact")
        or row_data.get("contact")
        or row_data.get("Number")
        or row_data.get("number")
    )

    if not phone:
        logger.warning(
            f"[sheet_campaign] No phone number found in row data. "
            f"Available columns: {list(row_data.keys())}. Skipping."
        )
        return

    # Normalize phone to string
    phone = str(phone).strip()
    # Remove .0 suffix from numeric cells (e.g. 9876543210.0)
    if phone.endswith(".0"):
        phone = phone[:-2]

    name = (
        row_data.get("Name")
        or row_data.get("name")
        or row_data.get("Lead Name")
        or row_data.get("Full Name")
        or "Lead"
    )

    logger.info(
        f"[sheet_campaign] Lead detected: name='{name}', phone='{phone}', "
        f"entity='{entity.name}', correlation={correlation_id}"
    )

    # ── 2. Resolve created_by (Campaign.created_by is NOT NULL) ─────────
    created_by_id = entity.created_by
    if not created_by_id:
        # Fallback: find any user in the company
        user_result = await db.execute(
            select(User.id).where(
                User.company_id == UUID(client_id),
            ).limit(1)
        )
        user_row = user_result.scalar_one_or_none()
        if user_row:
            created_by_id = user_row
        else:
            logger.error(
                f"[sheet_campaign] No users found for company {client_id}. "
                f"Cannot create campaign."
            )
            return

    # ── 3. Determine telephony provider from entity config ──────────────
    entity_meta = entity.metadata_extensions or {}
    provider = entity_meta.get("telephony_provider", "tata_tele")

    # ── 4. Create single-contact Campaign ───────────────────────────────
    from datetime import datetime as _dt
    campaign = Campaign(
        company_id=UUID(client_id),
        created_by=created_by_id,
        agent_id=entity.id,
        name=f"Auto: {name} ({_dt.utcnow().strftime('%Y-%m-%d %H:%M')})",
        description=(
            f"Auto-generated campaign from Google Sheets webhook. "
            f"Lead: {name}, Phone: {phone}. "
            f"Correlation: {correlation_id}"
        ),
        total_contacts=1,
        contact_list=[{"phone": phone, "name": str(name), **{k: str(v) for k, v in row_data.items()}}],
        provider=provider,
        max_concurrent_calls=1,
        status="draft",
        campaign_metadata={
            "source": "google_sheets_webhook",
            "correlation_id": correlation_id,
            "sheet_name": raw_payload.get("sheet_name"),
            "spreadsheet_id": raw_payload.get("spreadsheet_id"),
            "row_index": raw_payload.get("row_index"),
        },
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    # ── 5. Create CampaignCall ──────────────────────────────────────────
    campaign_call = CampaignCall(
        campaign_id=campaign.id,
        contact_data={"phone": phone, "name": str(name), **{k: str(v) for k, v in row_data.items()}},
        status="pending",
    )
    db.add(campaign_call)
    await db.commit()

    logger.info(
        f"[sheet_campaign] Campaign {campaign.id} created with 1 contact. "
        f"Enqueuing execute_campaign_task..."
    )

    # ── 6. Enqueue campaign execution via arq ───────────────────────────
    try:
        from urllib.parse import urlparse
        parsed = urlparse(app_settings.REDIS_URL or "redis://localhost:6379")
        redis_settings = RedisSettings(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
        )
        arq_pool = await create_pool(redis_settings)
        job = await arq_pool.enqueue_job(
            "execute_campaign_task",
            str(campaign.id),
        )
        await arq_pool.aclose()

        job_id = job.job_id if job else "queued"
        logger.info(
            f"[sheet_campaign] Campaign {campaign.id} enqueued as arq job {job_id}. "
            f"Call will be placed to {phone} via {provider}."
        )
    except Exception as enq_err:
        logger.error(
            f"[sheet_campaign] Failed to enqueue campaign {campaign.id}: {enq_err}",
            exc_info=True,
        )
        # Fallback: execute in-process
        try:
            from src.ai.campaign_executor import CampaignExecutor
            executor = CampaignExecutor(db)
            await executor.start_campaign(campaign.id)
            logger.info(f"[sheet_campaign] In-process fallback completed for campaign {campaign.id}")
        except Exception as exec_err:
            logger.error(
                f"[sheet_campaign] In-process fallback also failed: {exec_err}",
                exc_info=True,
            )


async def process_document(ctx, document_id_str: str, file_content: bytes, file_type: str, filename: str):
    from src.ai.models import Document, DocumentChunk
    import io
    
    document_id = UUID(document_id_str)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == document_id))
        document = result.scalar_one_or_none()
        if not document:
            return
            
        try:
            if file_type == "txt":
                text = file_content.decode("utf-8")
            elif file_type == "pdf":
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            elif file_type == "docx":
                import docx
                doc = docx.Document(io.BytesIO(file_content))
                text = "\n".join([p.text for p in doc.paragraphs])
            else:
                text = file_content.decode("utf-8", errors="ignore")
                
            chunk_size = 500
            chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
            
            from src.ai.constants import EMBEDDING_MODEL
            model_name = EMBEDDING_MODEL
            
            # Build Vertex AI client for embedding
            from src.common.genai_factory import build_vertex_genai_client
            from google.genai import types as _types
            _embed_client = await build_vertex_genai_client(
                db, document.company_id,
                http_options={"api_version": "v1beta"}
            )
            for idx, chunk_text in enumerate(chunks):
                try:
                    embed_response = _embed_client.models.embed_content(
                        model=model_name,
                        contents=chunk_text,
                        config=_types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
                    )
                    embedding = embed_response.embeddings[0].values
                except Exception as _embed_err:
                    logger.warning(f"Embedding error for chunk {idx}: {_embed_err}")
                    continue

                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=str(idx),
                    content=chunk_text,
                    embedding=embedding
                )
                db.add(chunk)
            
            document.upload_status = "completed"
            await db.commit()
            
        except Exception as e:
            document.upload_status = "failed"
            await db.commit()
            logger.error(f"Doc processing failed: {e}")

# Import campaign worker functions
from src.ai.campaign_worker import execute_campaign_task, pause_campaign_task, stop_campaign_task

# ---------------------------------------------------------------------------
# Ph-C: resume_execution — Arq job to resume a checkpointed run
# ---------------------------------------------------------------------------
async def resume_execution(ctx: dict, run_id_str: str) -> dict:
    """
    Resume a previously checkpointed execution run.
    Reloads `run.context_state` and skips steps that are already completed.
    """
    from src.common.database import AsyncSessionLocal
    
    run_id = UUID(run_id_str)
    async with AsyncSessionLocal() as db:
        redis = ctx.get('redis')
        engine = ExecutionEngine(db, redis)
        logger.info(f"Resuming ExecutionRun: {run_id}")
        return await engine.execute_run(run_id)


# ---------------------------------------------------------------------------
# Gap #5: Scheduled CORTEX wake-ups — Arq cron job
# ---------------------------------------------------------------------------
async def cortex_resume_scheduled(ctx: dict) -> dict:
    """
    Periodic cron job that wakes up suspended CORTEX trees whose
    next_resume_at timestamp has arrived. Creates a new execution run
    for each tree and enqueues it.
    """
    from src.common.database import AsyncSessionLocal
    from src.ai.cortex_models import CortexTree, CortexTreeStatus
    from sqlalchemy import select

    resumed = 0
    try:
        async with AsyncSessionLocal() as db:
            # Find trees scheduled for resumption
            result = await db.execute(
                select(CortexTree).where(
                    CortexTree.status == CortexTreeStatus.SUSPENDED,
                    CortexTree.next_resume_at != None,
                    CortexTree.next_resume_at <= datetime.utcnow(),
                )
            )
            trees = result.scalars().all()

            for tree in trees:
                try:
                    # Create a new execution run to resume this tree
                    from src.ai.models import ExecutionRun
                    resume_run = ExecutionRun(
                        entity_id=tree.entity_id,
                        company_id=tree.company_id,
                        user_id=tree.user_id,
                        input_data={"cortex_tree_id": str(tree.id)},
                        status="PENDING",
                    )
                    db.add(resume_run)
                    await db.flush()

                    # Clear the schedule to prevent re-triggering
                    tree.next_resume_at = None

                    # Enqueue to Arq
                    redis = ctx.get('redis')
                    if redis:
                        from arq.connections import ArqRedis
                        arq = ArqRedis(redis)
                        await arq.enqueue_job("execute_run", str(resume_run.id))
                        resumed += 1
                        logger.info(f"CORTEX scheduled resume: tree {tree.id} → run {resume_run.id}")

                except Exception as e:
                    logger.error(f"CORTEX scheduled resume failed for tree {tree.id}: {e}")

            await db.commit()
    except Exception as e:
        logger.error(f"CORTEX scheduled wake-up cron error: {e}")

    return {"resumed": resumed}


# ---------------------------------------------------------------------------
# Ph-A: RecursiveReasoningEngine — extends ExecutionEngine with Goal Trees
# ---------------------------------------------------------------------------
class RecursiveReasoningEngine(ExecutionEngine):
    """
    Experimental engine supporting dynamic goal decomposition (Phase A).
    Instead of a flat DAG of steps, goals are recursively decomposed into
    a tree of sub-goals until the LLM's confidence exceeds a threshold.
    """
    def __init__(self, db, redis_pool, company_id=None):
        super().__init__(db, redis_pool)
        self._company_id = company_id

    async def execute_tree(self, run: ExecutionRun, root_goal: GoalNode, context: dict) -> str:
        """Evaluate the tree DFS, expanding unconfident nodes."""
        logger.debug(f"GoalTree: Executing node: {root_goal.goal} (Depth {root_goal.depth})")
        
        # Base case: execute node if it's confident enough to be a leaf
        if root_goal.is_leaf() and root_goal.confidence >= 0.7:
            result = await self._execute_goal_leaf(run, root_goal, context)
            root_goal.result = result
            root_goal.status = "completed"
            return result
            
        # Recursive case: expand goal into children if it hasn't been yet
        if not root_goal.children:
            await self._expand_goal(root_goal, context)
            
        # Execute children
        child_results = []
        for child in root_goal.children:
            res = await self.execute_tree(run, child, context)
            child_results.append(res)
            
        root_goal.result = "\n".join(child_results)
        root_goal.status = "completed"
        return root_goal.result

    async def _expand_goal(self, node: GoalNode, context: dict) -> None:
        """Call LLM to decompose a complex goal into 2-5 subgoals."""
        prompt = (
            f"Decompose the following complex goal into atomic, sequential subgoals.\n"
            f"Goal: {node.goal}\n"
            f"Current Context: {json.dumps(context)[:1000]}\n\n"
            f"Output JSON array of subgoal strings."
        )
        # Use the generic router for the thinking/decomposition task type
        from .llm_router import LLMRouter
        llm_router = LLMRouter(db=self.db, company_id=getattr(self, '_company_id', None))
        
        try:
            res = await llm_router.call_llm(
                task_type="thinking",
                system_prompt="You are a goal decomposition expert. Output only JSON array wrapper [\"goal1\", \"goal2\"].",
                user_prompt=prompt,
                temperature=0.4
            )
            subgoals = json.loads(res.output)
            for sg in subgoals:
                node.children.append(GoalNode(goal=sg, depth=node.depth + 1, parent=node, status="pending"))
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f"Failed to expand goal: {node.goal}")
            # act as leaf
            pass
            
    async def _execute_goal_leaf(self, run: ExecutionRun, node: GoalNode, context: dict) -> str:
        """Execute a concrete atomic goal via flat engine _execute_step."""
        step = PlanStep(
            step_id=str(uuid4()),
            name=f"leaf_{node.depth}",
            description=node.goal,
            type="THOUGHT",  # defaults to REACT thought
            target={"prompt_template": node.goal}
        )
        res = await self._execute_step(run, run.entity, step, context)
        return res.get("output", "Empty leaf result")


class WorkerSettings:
    functions = [
        run_execution_recursive, 
        process_gateway_event,
        process_document,
        execute_campaign_task,
        pause_campaign_task,
        stop_campaign_task,
        resume_execution,
    ]
    # Gap #5: Register CORTEX scheduled wake-up cron
    cron_jobs = [
        # Run every 5 minutes to check for scheduled tree resumptions
        # arq expects: cron(coroutine, minute=set, hour=set, ...)
    ]
    
    job_timeout = 7200  # 2-hour absolute ceiling; per-entity timeout via logic_gate config
    
    # Parse Redis URL from environment config
    @staticmethod
    def _parse_redis_url():
        from src.common.config import settings
        from urllib.parse import urlparse
        parsed = urlparse(settings.REDIS_URL or "redis://localhost:6379")
        return parsed.hostname or "localhost", parsed.port or 6379
    
    _host, _port = _parse_redis_url.__func__()
    redis_settings = RedisSettings(host=_host, port=_port)


# Register the cron job after class definition (arq pattern)
try:
    from arq.cron import cron
    WorkerSettings.cron_jobs = [
        cron(cortex_resume_scheduled, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
    ]
except ImportError:
    pass  # arq.cron may not be available in all versions
