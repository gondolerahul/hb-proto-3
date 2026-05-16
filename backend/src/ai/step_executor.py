"""
step_executor.py — Step execution logic extracted from ExecutionEngine.

Extracted during Phase 6 gap closure to reduce worker.py from ~2,826
to ~1,700 lines. Contains all step-level execution handlers:
THOUGHT/ACTION, TOOL_CALL, CHILD_ENTITY_INVOCATION, and supporting
methods (reasoning modes, review, usage logging, context summarization).
"""
import asyncio
import copy
import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID

from src.ai.constants import INTERNAL_CONTEXT_KEYS, MAX_REACT_TURNS
from src.ai.models import (
    ExecutionRun, HierarchicalEntity, LLMInteractionLog,
    ToolInteractionLog, RunStatus,
)
from src.ai.schemas import StepType, PlanStep
from src.ai.tool_executor import ToolExecutor
from src.ai.llm_router import LLMRouter
from src.ai.usage_service import UsageService
from src.billing.credit_service import CreditService, InsufficientCreditsError
from sqlalchemy import select

logger = logging.getLogger(__name__)


# Lazy imports to avoid circular dependencies with worker.py
def _get_worker_helpers():
    from src.ai.worker import (
        parse_variables, build_sandwich_prompt,
        filter_context_for_step, UncertaintySignal,
        DEFAULT_REVIEW_PROMPT,
    )
    return parse_variables, build_sandwich_prompt, filter_context_for_step, UncertaintySignal, DEFAULT_REVIEW_PROMPT


# Module-level lazy cache
_helpers = None

def _helpers_cached():
    global _helpers
    if _helpers is None:
        _helpers = _get_worker_helpers()
    return _helpers


def parse_variables(text, variables):
    return _helpers_cached()[0](text, variables)

def build_sandwich_prompt(**kwargs):
    return _helpers_cached()[1](**kwargs)

def filter_context_for_step(step, context, policy):
    return _helpers_cached()[2](step, context, policy)

def _get_uncertainty_signal():
    return _helpers_cached()[3]

def _get_review_prompt():
    return _helpers_cached()[4]


class StepExecutorService:
    """Handles individual step execution: THOUGHT, TOOL_CALL, CHILD_ENTITY_INVOCATION.

    Extracted from ExecutionEngine to reduce monolith size. Receives
    dependencies via constructor; does NOT own the DB session or run lifecycle.
    """

    def __init__(self, db, redis, company_id: UUID, usage_service: UsageService, cortex_bridge=None, execute_run_fn=None):
        self.db = db
        self.redis = redis
        self.company_id = company_id
        self.usage_service = usage_service
        self._cortex_bridge = cortex_bridge
        # Callback to ExecutionEngine.execute_run — avoids circular import
        self._execute_run_fn = execute_run_fn

    # ------------------------------------------------------------------
    # Phase B: Async child entity dispatch via Arq + Redis pub/sub
    # ------------------------------------------------------------------

    async def _dispatch_child_async(self, child_run: ExecutionRun, governance: dict) -> dict:
        """Dispatch child run as Arq job and wait for completion via pub/sub.

        Falls back to recursive execution if no response within timeout.
        """
        from arq.connections import ArqRedis
        timeout_ms = governance.get("timeout_ms", 120000)
        # Double the timeout for async dispatch to account for queue wait
        max_wait = (timeout_ms * 2) / 1000.0

        channel = f"run:{child_run.id}:status"
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            # Enqueue job
            arq_redis = ArqRedis(self.redis.connection_pool)
            await arq_redis.enqueue_job('run_execution_recursive', str(child_run.id))
            logger.info(f"Dispatched child run {child_run.id} via Arq")

            # Wait for completion
            async def _wait_for_result():
                async for msg in pubsub.listen():
                    if msg["type"] == "message":
                        data = json.loads(msg["data"])
                        if data.get("status") in ("COMPLETED", "FAILED"):
                            return data
                return None

            result_data = await asyncio.wait_for(_wait_for_result(), timeout=max_wait)

            if result_data and result_data.get("status") == "FAILED":
                raise Exception(f"Child run {child_run.id} failed: {result_data.get('error', 'Unknown')}")

            # Reload child_run to get result_data
            await self.db.refresh(child_run)
            return child_run.result_data or {}

        except asyncio.TimeoutError:
            logger.warning(
                f"Async child dispatch timed out after {max_wait}s for run {child_run.id}. "
                f"Falling back to recursive execution."
            )
            return await self._execute_run_fn(child_run.id)
        finally:
            await pubsub.unsubscribe(channel)

    # ------------------------------------------------------------------
    # CORTEX delegation
    # ------------------------------------------------------------------

    async def _ingest_tool_result_to_cortex(self, run, tool_id, tool_output, context):
        """Delegate to CortexBridge if available."""
        if self._cortex_bridge:
            await self._cortex_bridge.ingest_tool_result(run, tool_id, tool_output, context)

    async def _execute_step(self, run: ExecutionRun, entity: HierarchicalEntity, step: PlanStep, context: dict) -> dict:
        """Routes execution to specific step handler."""
        if step.type == StepType.CHILD_ENTITY_INVOCATION:
            return await self._execute_child_invocation(run, entity, step, context)
        elif step.type == StepType.TOOL_CALL:
            return await self._execute_tool_call(run, entity, step, context)
        elif step.type == StepType.THOUGHT or step.type == StepType.ACTION:
            return await self._execute_thought(run, entity, step, context)
        return {"error": "Unknown step type"}

    async def _execute_child_invocation(self, run: ExecutionRun, entity: HierarchicalEntity, step: PlanStep, context: dict) -> dict:
        entity_id = step.target.entity_id if step.target else None

        # ── Fallback: resolve entity_id from parent entity's hierarchy ──
        # If the dynamic planner dropped the entity_id, look it up from the
        # parent entity's hierarchy.children or planning.static_plan.steps.
        if not entity_id and entity:
            # Strategy 1: Match by step name against static plan steps
            planning = entity.planning or {}
            static_steps = (planning.get("static_plan") or {}).get("steps", [])
            for ss in static_steps:
                if ss.get("type") == "CHILD_ENTITY_INVOCATION" and \
                   ss.get("name", "").lower().strip() == (step.name or "").lower().strip():
                    entity_id = ss.get("target", {}).get("entity_id")
                    if entity_id:
                        logger.info(f"Resolved entity_id {entity_id} for step '{step.name}' from static plan")
                        break

            # Strategy 2: Match by order index against hierarchy children
            if not entity_id:
                hierarchy = entity.hierarchy or {}
                children = hierarchy.get("children", [])
                # Find which CHILD_ENTITY_INVOCATION step index this is
                # (0-based among all child invocation steps)
                invocation_steps = [
                    ss for ss in static_steps
                    if ss.get("type") == "CHILD_ENTITY_INVOCATION"
                ]
                for idx, inv_step in enumerate(invocation_steps):
                    if inv_step.get("name", "").lower().strip() == (step.name or "").lower().strip():
                        if idx < len(children):
                            entity_id = children[idx].get("child_id")
                            logger.info(f"Resolved entity_id {entity_id} for step '{step.name}' from hierarchy children[{idx}]")
                        break

        if not entity_id:
            raise Exception(f"Child invocation missing entity_id for step {step.name}")
        
        # Ensure entity_id is a UUID
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)

        # ── Runtime safety net: validate child entity belongs to this company ──
        # This catches cases where the pre-flight check in trigger_execution()
        # was bypassed, or entity references became stale after cloning.
        child_entity_check = await self.db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.id == entity_id,
                HierarchicalEntity.company_id == run.company_id,
            )
        )
        if not child_entity_check.scalar_one_or_none():
            raise Exception(
                f"Child entity {entity_id} not found in company {run.company_id}. "
                f"The process template was not fully cloned. "
                f"Please re-clone the template to create all child entities."
            )

        # Fix E: Propagate CORTEX tree ID so all entities share one tree
        child_input = dict(context)
        if "__cortex_tree_id__" in context:
            child_input["cortex_tree_id"] = context["__cortex_tree_id__"]
            logger.info(f"Propagating CORTEX tree {context['__cortex_tree_id__']} to child entity {entity_id}")

        # Fix G: Set child's 'input' key to the RENDERED prompt_template.
        # Without this, the child inherits the parent's raw 'input' key (often
        # just the original topic string).  The prompt_template typically
        # references variables like {{step_1}} or {{Research Phase}} that
        # contain the actual research data.  After rendering, the full content
        # becomes the child's 'input', so {{input}} at the child level
        # resolves to the complete data instead of the original topic.
        if step.target and step.target.prompt_template:
            rendered_input = parse_variables(step.target.prompt_template, context)
            # Only override if the template actually resolved (isn't just "{{input}}")
            if rendered_input != step.target.prompt_template and rendered_input.strip():
                child_input["input"] = rendered_input
                logger.info(
                    f"Set child input to rendered prompt_template "
                    f"({len(rendered_input)} chars) for step '{step.name}'"
                )

        # Fix F: Strip parent step_id keys to prevent child step-skip collision.
        # The parent context contains keys like "step_1", "step_2" from its own
        # execution.  When passed to the child, the child's execute_run loop
        # sees "step_1" already in context_state and wrongly skips the child's
        # own step_1.  We remove all generic step_id keys (step_N pattern) while
        # keeping named step outputs and internal context keys.
        import re as _re
        _step_id_pattern = _re.compile(r'^step_\d+$')
        parent_step_keys = [k for k in child_input if _step_id_pattern.match(k)]
        for k in parent_step_keys:
            del child_input[k]
        if parent_step_keys:
            logger.info(
                f"Stripped {len(parent_step_keys)} parent step_id keys from child "
                f"context to prevent step-skip collision: {parent_step_keys}"
            )

        # Fix H: Strip parent-scoped memory/episodic context to prevent
        # child entities from being confused by previous execution history.
        # The parent's CORTEX __memory__ contains past run summaries that
        # cause child agents to replicate past actions instead of analyzing
        # the current instruction.
        _parent_only_keys = [
            "__memory__", "__episodic_memory__", "__semantic_context__",
            "__memory_context__", "__context_sources__",
        ]
        stripped_parent_keys = [k for k in _parent_only_keys if k in child_input]
        for k in stripped_parent_keys:
            del child_input[k]
        if stripped_parent_keys:
            logger.info(
                f"Stripped {len(stripped_parent_keys)} parent-scoped memory keys "
                f"from child context: {stripped_parent_keys}"
            )

        # ── Credit gate before spawning child run ─────────────────────────
        # Check that the parent still has credits remaining before launching
        # a potentially expensive child entity (e.g. Research Director).
        try:
            _child_credit_svc = CreditService(self.db)
            _parent_accumulated = Decimal(str(run.total_cost_usd or 0))
            _child_effective = await _child_credit_svc.get_effective_balance(
                run.company_id, _parent_accumulated
            )
            if _child_effective <= 0:
                raise InsufficientCreditsError(
                    f"Cannot spawn child entity {entity_id}: parent run has accumulated "
                    f"${_parent_accumulated:.4f} cost with no remaining credits. "
                    f"Please top up credits and retry."
                )
            logger.info(f"Child run credit gate passed: ${_child_effective:.4f} remaining "
                  f"(parent accumulated: ${_parent_accumulated:.4f})")
        except InsufficientCreditsError:
            raise
        except Exception as _child_credit_err:
            logger.warning(f"Child run credit gate check failed: {_child_credit_err}")

        # Create Child Run
        child_run = ExecutionRun(
            company_id=run.company_id,
            user_id=run.user_id,
            entity_id=entity_id,
            parent_run_id=run.id,
            trace_id=run.trace_id,
            input_data=child_input,
            status=RunStatus.PENDING
        )
        self.db.add(child_run)
        await self.db.commit()
        await self.db.refresh(child_run)
        
        # Recursive Execute
        # Phase B: Feature-flagged async child dispatch
        governance = entity.governance or {}
        use_async = governance.get("async_child_dispatch", False)

        if use_async and self.redis:
            child_result = await self._dispatch_child_async(child_run, governance)
        else:
            # Legacy recursive path — uses callback to ExecutionEngine.execute_run
            child_result = await self._execute_run_fn(child_run.id)
        
        # rollup metrics
        run.total_cost_usd = (run.total_cost_usd or Decimal("0")) + Decimal(str(child_run.total_cost_usd or 0))
        run.total_tokens = (run.total_tokens or 0) + (child_run.total_tokens or 0)
        await self.db.commit()
        
        # Fix B: Accumulate ALL child step outputs (not just the last one)
        # The director produces ~69KB across 8 steps but previously only the
        # last step's 16KB reached the synthesizer. Now all outputs are passed.
        all_step_outputs = child_result.get("steps", [])
        accumulated_output = "\n\n---\n\n".join(
            f"## {s.get('step', 'Unknown')}\n{s.get('output', '')}"
            for s in all_step_outputs
            if s.get("output")
        )
        # Fallback to last step output if steps array is empty
        final_output = accumulated_output or child_result.get("output", "")
        return {"step": step.name, "output": final_output, "child_run_id": str(child_run.id)}

    async def _execute_tool_call(self, run: ExecutionRun, entity: HierarchicalEntity, step: PlanStep, context: dict) -> dict:
        tool_id = step.target.tool_id if step.target else None
        if not tool_id:
            raise Exception(f"Tool call missing tool_id for step {step.name}")
        
        start_time = datetime.utcnow()
        try:
            # Prepare inputs from context/variables
            # Internal keys that should never be passed as tool input
            _INTERNAL_KEYS = INTERNAL_CONTEXT_KEYS
            raw_input = None

            # 1. If the step has a prompt_template, use variable substitution
            if step.target and step.target.prompt_template:
                raw_input = parse_variables(step.target.prompt_template, context)
                # If unresolved {{...}} patterns remain after substitution,
                # the planner used variable names that don't match context keys.
                # Fall back to context-based input resolution instead of
                # sending the literal template string (e.g. "{{url_from_step_2}}")
                # to the tool.
                if re.search(r'\{\{.+?\}\}', raw_input):
                    logger.warning(f"Unresolved variables in tool input after parsing: {raw_input[:200]}")
                    raw_input = None  # trigger fallback below

            # 2. Fallback: use context data
            if raw_input is None:
                if context.get("input"):
                    raw_input = context["input"]
                else:
                    user_ctx = {k: v for k, v in context.items() if k not in _INTERNAL_KEYS}
                    # Prefer the most recent step output (last key that looks like step data)
                    step_keys = [k for k in user_ctx if k.startswith("step_") or "step" in k.lower()]
                    if step_keys:
                        raw_input = str(user_ctx[step_keys[-1]])
                    elif len(user_ctx) == 1:
                        raw_input = str(next(iter(user_ctx.values())))
                    elif user_ctx:
                        raw_input = json.dumps(user_ctx, default=str)
                    else:
                        raw_input = ""
            
            extra_context = {
                "company_id": str(run.company_id),
                "user_id": str(run.user_id) if run.user_id else "default",
            }
                
            result = await ToolExecutor.execute_tools([{"tool": tool_id, "input": raw_input}], extra_context=extra_context)
            tool_result = result[0]  # ToolResult dataclass (P3.2)

            # ── Self-Healing Retry: If the tool failed due to a FORMAT error,
            # ask the LLM to reformat the input and retry once. ────────────
            # Only triggers on parsing/formatting errors, not infrastructure
            # failures (missing API key, network timeout, etc.).
            _FORMAT_ERROR_KEYWORDS = {"invalid json", "json", "parse", "format", "delimiter", "control character", "expecting", "decode"}
            # Also handle filesystem errors caused by bad LLM-generated filenames
            _IO_ERROR_KEYWORDS = {"no such file or directory", "errno 2", "errno 22", "invalid argument", "file name too long"}
            tool_output_str = str(tool_result.output).lower()
            
            _is_format_err = self._is_format_error(tool_output_str, _FORMAT_ERROR_KEYWORDS)
            _is_io_err = (
                not tool_result.success
                and any(kw in tool_output_str for kw in _IO_ERROR_KEYWORDS)
            )

            if _is_format_err or _is_io_err:
                _err_kind = "format" if _is_format_err else "filesystem/IO"
                logger.info(f"Tool '{tool_id}' returned {_err_kind} error. Attempting LLM reformat...")
                reformatted_input = await self._reformat_tool_input(
                    run=run,
                    entity=entity,
                    tool_id=tool_id,
                    original_input=raw_input,
                    error_message=str(tool_result.output),
                    step_description=step.description or step.name,
                )
                if reformatted_input and reformatted_input != raw_input:
                    logger.info(f"Retrying tool '{tool_id}' with reformatted input ({len(reformatted_input)} chars)")
                    retry_result = await ToolExecutor.execute_tools(
                        [{"tool": tool_id, "input": reformatted_input}],
                        extra_context=extra_context,
                    )
                    retry_tool_result = retry_result[0]
                    # Use retry result if it succeeded or at least produced different output
                    retry_output_str = str(retry_tool_result.output).lower()
                    _retry_still_bad = (
                        self._is_format_error(retry_output_str, _FORMAT_ERROR_KEYWORDS)
                        or any(kw in retry_output_str for kw in _IO_ERROR_KEYWORDS)
                    )
                    if not _retry_still_bad:
                        logger.info(f"Retry succeeded for tool '{tool_id}'")
                        tool_result = retry_tool_result
                    else:
                        logger.warning(f"Retry also failed for tool '{tool_id}', using original result")
            # ─────────────────────────────────────────────────────────────
            
            latency = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Log Tool Call — tool_result is a ToolResult dataclass, not a dict
            log = ToolInteractionLog(
                run_id=run.id,
                tool_id=tool_id,
                tool_name=tool_id,
                input_parameters={"input": raw_input},
                output_result=str(tool_result.output),
                success=tool_result.success,
                latency_ms=latency
            )
            self.db.add(log)

            # ── Track tool cost in run.total_cost_usd ────────────────────────────
            # Look up cost for this tool from integration registry.
            # Match by: service_sku for the tool directly, or by specific
            # service_sku values known to correspond to this tool's backend.
            # Excludes LLM entries to avoid cross-contamination.
            try:
                from src.config.models import IntegrationRegistry as _IR
                from sqlalchemy import select as _sel, or_ as _or
                from decimal import Decimal as _Dec
                # Map built-in tool IDs → known integration registry service_skus
                _TOOL_SKU_MAP = {
                    "web_search": ["serp-api-key"],
                    "scraper_tool": ["firecrawl"],
                    "headless_browser": ["headless-browser"],
                    "pdf_generator": ["pdf-generator"],
                    "image_generation": ["imagen-4.0-generate-001"],
                }
                # Fixed per-call costs for tools that bill independently
                # (used as fallback when IntegrationRegistry has no entry)
                _TOOL_FIXED_COST = {
                    "image_generation": _Dec("0.04"),   # Imagen 4 standard
                    "video_generation": _Dec("0.05"),   # Veo per-call
                }
                _sku_matches = _TOOL_SKU_MAP.get(tool_id, [])
                _or_clauses = [
                    _IR.service_sku == tool_id,
                    _IR.service_category == "CUSTOM_API",
                ]
                for _sku in _sku_matches:
                    _or_clauses.append(_IR.service_sku == _sku)
                _ir_result = await self.db.execute(
                    _sel(_IR).where(
                        _IR.company_id == run.company_id,
                        _or(*_or_clauses),
                        _IR.status == "active",
                        _IR.internal_cost.isnot(None),
                        _IR.service_category != "LLM",  # Exclude LLM entries
                    ).limit(1)
                )
                _ir_entry = _ir_result.scalar_one_or_none()
                if _ir_entry and _ir_entry.internal_cost:
                    _tool_cost = _Dec(str(_ir_entry.internal_cost))
                    run.total_cost_usd = (run.total_cost_usd or _Dec("0")) + _tool_cost
                    logger.info(f"Tool cost for '{tool_id}': ${_tool_cost} (via {_ir_entry.provider_name}/{_ir_entry.service_sku})")
                    # Log to usage_logs as well
                    from src.ai.models import UsageLog as _UL
                    self.db.add(_UL(
                        company_id=run.company_id,
                        run_id=run.id,
                        sku_id=_ir_entry.id,
                        raw_quantity=_Dec("1"),
                        calculated_cost=_tool_cost,
                        log_metadata={"tool": tool_id, "latency_ms": latency},
                    ))
                elif tool_id in _TOOL_FIXED_COST:
                    _tool_cost = _TOOL_FIXED_COST[tool_id]
                    run.total_cost_usd = (run.total_cost_usd or _Dec("0")) + _tool_cost
                    logger.info(f"Tool cost for '{tool_id}': ${_tool_cost} (fixed fallback)")
                else:
                    logger.warning(f"No cost entry found for tool '{tool_id}' — cost not tracked")
            except Exception as _ce:
                logger.warning(f"Could not log tool cost for '{tool_id}': {_ce}")
            # ─────────────────────────────────────────────────────────────────────

            await self.db.commit()
            
            # ── CORTEX Knowledge Ingestion ─────────────────────────────
            # When a scraper/browser tool runs during a CORTEX execution,
            # also write the scraped content as a knowledge node in the
            # CORTEX tree's knowledge subtree. This enables tree-based
            # navigation of research sources.
            if tool_id in ("scraper_tool", "headless_browser") and tool_result.success:
                await self._ingest_tool_result_to_cortex(
                    run=run,
                    tool_id=tool_id,
                    tool_output=tool_result.output,
                    context=context,
                )
            # ───────────────────────────────────────────────────────────
            
            return {"step": step.name, "output": tool_result.output}
        except Exception as e:
            return {"step": step.name, "error": str(e), "success": False}

    def _is_format_error(self, output_lower: str, keywords: set) -> bool:
        """Check if a tool output indicates a formatting/parsing error (not infra)."""
        # Must contain "error" to be an error at all
        if '"error"' not in output_lower and 'error:' not in output_lower:
            return False
        # Exclude infrastructure errors that reformatting can't fix
        _INFRA_KEYWORDS = {"api key", "not configured", "timeout", "connection", "unauthorized", "403", "401", "rate limit"}
        if any(k in output_lower for k in _INFRA_KEYWORDS):
            return False
        # Check for format-related error keywords
        return any(k in output_lower for k in keywords)

    async def _reformat_tool_input(
        self,
        run: 'ExecutionRun',
        entity: 'HierarchicalEntity',
        tool_id: str,
        original_input: str,
        error_message: str,
        step_description: str,
    ) -> Optional[str]:
        """
        Ask the LLM to reformat tool input after a format error.

        Provides the LLM with:
          - The tool's expected JSON schema
          - The original (malformed) input
          - The exact error message from the tool
          - The step's intent (description)

        Returns the reformatted input string, or None if reformatting fails.
        Capped cost: ~200–400 tokens (single fast LLM call).
        """
        try:
            # Get the tool's expected input schema
            tool_schemas = ToolExecutor.get_tool_schemas([tool_id])
            schema_str = json.dumps(tool_schemas[0], indent=2) if tool_schemas else f"Tool '{tool_id}' expects a JSON object."

            system_prompt = (
                "You are a JSON formatting assistant. A tool call failed because "
                "the input was malformed. Your ONLY job is to reformat the input "
                "into valid JSON that matches the tool's expected schema.\n\n"
                "Rules:\n"
                "- Output ONLY the corrected JSON. No explanation, no markdown fences.\n"
                "- Escape all special characters properly (newlines as \\n, tabs as \\t).\n"
                "- Do NOT change the semantic content — only fix the formatting.\n"
                "- If the input is a list of items but the tool expects a single item, "
                "  wrap the first item in the correct schema format."
            )

            user_prompt = (
                f"## Tool Schema\n```json\n{schema_str}\n```\n\n"
                f"## Step Intent\n{step_description}\n\n"
                f"## Original Input (malformed)\n```\n{original_input[:3000]}\n```\n\n"
                f"## Error from Tool\n{error_message}\n\n"
                f"Reformat the input to match the tool's expected JSON schema. "
                f"Output ONLY the corrected JSON:"
            )

            llm_router = LLMRouter(db=self.db, company_id=entity.company_id)
            resp = await llm_router.call_llm(
                task_type="text_generation",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,  # Low temperature for deterministic formatting
                max_tokens=4000,
            )

            # Log the reformat LLM call for billing transparency
            reformat_log = LLMInteractionLog(
                run_id=run.id,
                model_provider=resp.provider,
                model_name=resp.model_name,
                input_prompt=f"[REFORMAT] Tool: {tool_id}",
                output_response=resp.output[:500] if resp.output else "",
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
                latency_ms=resp.latency_ms,
                reasoning_mode="REFORMAT",
                step_name=step.name if step else "__reformat__",
            )
            self.db.add(reformat_log)
            await self._log_usage(run, resp.model_name, resp.prompt_tokens, resp.completion_tokens, reformat_log)

            reformatted = resp.output.strip()

            # Strip markdown fences if the LLM wrapped the output
            if reformatted.startswith("```"):
                lines = reformatted.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                reformatted = "\n".join(lines).strip()

            logger.debug(f"LLM reformatted tool input: {reformatted[:200]}...")
            return reformatted

        except Exception as e:
            logger.warning(f"LLM reformat failed: {e}")
            return None

    async def _execute_thought(self, run: ExecutionRun, entity: HierarchicalEntity, step: PlanStep, context: dict) -> dict:
        """Execute a THOUGHT or ACTION step using the model-agnostic LLMRouter."""
        logger.debug(f"Executing Thought/Action step: {step.name}")
        logic_gate = entity.logic_gate or {}
        config = logic_gate.get("reasoning_config") or {}

        # Resolve task_type from entity config (new model-agnostic field)
        task_type = config.get("task_type", "text_generation")
        # Fix D: Allow entity-level model override (e.g. Pro for synthesizer)
        model_override = config.get("model_name")

        # Filter and optionally summarize context
        filtered_context = filter_context_for_step(step, context, logic_gate.get("context_policy"))
        filtered_context = await self._maybe_summarize_context(run, entity, filtered_context)

        # --- Extract identity fields ---
        identity = entity.identity or {}
        system_prompt = identity.get("system_prompt", "You are a helpful assistant.")
        if "persona" in identity:
            system_prompt = identity.get("persona", {}).get("system_prompt", system_prompt)

        # Wire identity.role into the system prompt
        entity_role = identity.get("role") or (identity.get("persona", {}) or {}).get("role", "")
        if entity_role and entity_role != "AI Assistant":
            role_prefix = f"You are {entity.name}, a {entity_role}."
            if not system_prompt.startswith(role_prefix):
                system_prompt = f"{role_prefix}\n\n{system_prompt}"

        few_shot_examples = identity.get("few_shot_examples", [])
        if "persona" in identity:
            few_shot_examples = identity.get("persona", {}).get("few_shot_examples", few_shot_examples)

        # --- Extract architecture fields for prompt ---
        entity_goal = entity.goal or ""
        io_contract = entity.io_contract or {}
        output_schema = io_contract.get("output_schema")
        review_config = logic_gate.get("review_mechanism") or {}
        success_criteria = review_config.get("success_criteria") if review_config.get("enabled") else None
        planning = entity.planning or {}
        dynamic_config = planning.get("dynamic_planning", {})
        allowed_deviations = dynamic_config.get("allowed_deviations") if dynamic_config.get("enabled") else None
        governance = entity.governance or {}

        # Build execution constraints dict
        exec_constraints = {}
        exec_limits = governance.get("execution_limits") or {}
        max_tool_calls = exec_limits.get("max_tool_calls")
        if max_tool_calls:
            used = sum(context.get('tool_call_counts', {}).values())
            exec_constraints["Tool calls remaining"] = f"{max_tool_calls - used} of {max_tool_calls}"
        max_cost = governance.get("max_cost_usd")
        if max_cost:
            current_cost = float(run.total_cost_usd or 0)
            exec_constraints["Cost budget"] = f"${current_cost:.4f} spent of ${max_cost:.2f} max"
        max_depth = governance.get("max_recursion_depth")
        if max_depth:
            exec_constraints["Max recursion depth"] = str(max_depth)

        # --- Build tools ---
        # Only AUTONOMOUS and BOTH tools are injected into the LLM prompt.
        # PLANNED-only tools are executed deterministically by the static plan executor.
        tool_ids = []
        tool_schemas = []
        if entity.capabilities and entity.capabilities.get("tools"):
            all_tools = entity.capabilities.get("tools", [])
            autonomous_tools = [
                t for t in all_tools
                if t.get("usage", "AUTONOMOUS") in ("AUTONOMOUS", "BOTH")
            ]
            tool_ids = [t.get("tool_id") for t in autonomous_tools]

        # ── Meta-Cognition: Auto-inject meta-tools by tier ─────────────
        from src.ai.meta.platform_schema_compiler import resolve_meta_cognition
        meta_config = resolve_meta_cognition(entity)

        # Tier 2: Registry Search (AGENT + PROCESS)
        if meta_config.get("registry_search"):
            if "meta_registry_search" not in tool_ids:
                tool_ids.append("meta_registry_search")
                logger.debug(f"Tier 2: Auto-injected meta_registry_search for {entity.name}")

        # Tier 3: Self-Modification (AGENT + PROCESS)
        if meta_config.get("self_modification"):
            for meta_tool in ["meta_entity_creator", "meta_entity_executor"]:
                if meta_tool not in tool_ids:
                    tool_ids.append(meta_tool)
            logger.debug(f"Tier 3: Auto-injected meta_entity_creator/executor for {entity.name}")
        # ───────────────────────────────────────────────────────────────

        tool_schemas = ToolExecutor.get_tool_schemas(tool_ids)

        # ── Tier 1: Platform Awareness ─────────────────────────────────
        platform_awareness_text = None
        if meta_config.get("platform_awareness"):
            try:
                from src.ai.meta.platform_schema_compiler import get_platform_summary
                platform_awareness_text = await get_platform_summary(
                    db=self.db,
                    company_id=run.company_id,
                    redis=self.redis,
                )
                logger.debug(f"Tier 1: Injected platform awareness ({len(platform_awareness_text)} chars) for {entity.name}")
            except Exception as e:
                logger.warning(f"Tier 1: Failed to load platform awareness: {e}")
        # ───────────────────────────────────────────────────────────────

        # --- Build sandwich system prompt with all architecture fields ---
        # Inject context_sources if available
        ctx_sources_text = filtered_context.get("__context_sources__")
        full_system_prompt = build_sandwich_prompt(
            identity=system_prompt,
            goal=entity_goal,
            tools=tool_schemas,
            few_shot_examples=few_shot_examples,
            context=ctx_sources_text,
            current_task="",
            output_schema=output_schema,
            success_criteria=success_criteria,
            allowed_deviations=allowed_deviations,
            execution_constraints=exec_constraints if exec_constraints else None,
            platform_awareness=platform_awareness_text,
        )

        # --- Resolve reasoning mode and dispatch ---
        reasoning_mode = config.get("reasoning_mode", "REACT")

        input_vars = {**filtered_context}
        raw_template = step.target.prompt_template if step.target and step.target.prompt_template else "{{input}}"
        user_prompt = parse_variables(raw_template, input_vars)

        # ── Enrich user prompt with prior step context ──────────────────────
        # Dynamic-plan THOUGHT/ACTION steps often have descriptions like
        # "Extract URLs from search results" but no explicit {{step_1.output}}
        # in their prompt_template.  Without appending the actual context data,
        # the LLM receives the instruction but none of the data to work with.
        _INTERNAL_KEYS = INTERNAL_CONTEXT_KEYS
        step_outputs = {
            k: v for k, v in filtered_context.items()
            if k not in _INTERNAL_KEYS and v  # skip empty/None
        }
        if step_outputs:
            context_block = "\n\n## Available Context from Previous Steps\n"
            for ctx_key, ctx_val in step_outputs.items():
                val_str = str(ctx_val)
                # Truncate very large values to avoid overwhelming the prompt
                if len(val_str) > 30000:
                    val_str = val_str[:30000] + "\n... (truncated)"
                context_block += f"\n### {ctx_key}\n{val_str}\n"
            user_prompt += context_block

        # Also include the step description as task instruction if it's not
        # already the prompt (i.e., when prompt_template was a {{variable}} reference)
        if step.description and step.description not in user_prompt:
            user_prompt = f"## Current Task\n{step.description}\n\n{user_prompt}"

        logger.debug(f"Routing via LLMRouter → task_type={task_type}, reasoning_mode={reasoning_mode}, model_override={model_override}")
        # Inject model_override into config so reasoning methods can forward it
        config["__model_override"] = model_override

        # Common tool executor setup
        extra_context = {
            **filtered_context,
            "company_id": str(run.company_id),
            "user_id": str(run.user_id) if run.user_id else "default",
        }
        context['tool_call_counts'] = {}  # Always reset per step to prevent stale counts on retry/resume

        all_tool_results = []

        async def _execute_tools(function_calls: list) -> list:
            """Adapter: called by LLMRouter's REACT loop per tool-call turn."""
            results = []
            for fc in function_calls:
                _tr_list = await ToolExecutor.execute_from_function_calls(
                    [fc],
                    extra_context=extra_context,
                    call_counts=context.get('tool_call_counts', {}),
                )
                for _tr in _tr_list:
                    self.db.add(ToolInteractionLog(
                        run_id=run.id,
                        tool_id=_tr.tool,
                        tool_name=_tr.tool,
                        input_parameters=_tr.args,
                        output_result=str(_tr.output),
                        success=_tr.success,
                        latency_ms=_tr.latency_ms,
                    ))
                    all_tool_results.append(_tr.to_dict())
                    results.append({"tool": _tr.tool, "output": _tr.output, "success": _tr.success})
                    # CORTEX: ingest scraper/browser results as knowledge nodes
                    if _tr.tool in ("scraper_tool", "headless_browser") and _tr.success:
                        await self._ingest_tool_result_to_cortex(
                            run=run,
                            tool_id=_tr.tool,
                            tool_output=_tr.output,
                            context=context,
                        )
            return results

        llm_router = LLMRouter(db=self.db, company_id=run.company_id)

        # ═══════════════════════════════════════════════════════════════════
        # Reasoning Mode Dispatch
        # ═══════════════════════════════════════════════════════════════════
        if reasoning_mode == "CHAIN_OF_THOUGHT":
            output, response = await self._execute_chain_of_thought(
                llm_router, full_system_prompt, user_prompt, task_type,
                config, tool_schemas, _execute_tools
            )
        elif reasoning_mode == "REFLECTION":
            output, response = await self._execute_reflection(
                llm_router, full_system_prompt, user_prompt, task_type,
                config, tool_schemas, _execute_tools
            )
        elif reasoning_mode == "TREE_OF_THOUGHTS":
            output, response = await self._execute_tree_of_thoughts(
                llm_router, full_system_prompt, user_prompt, task_type,
                config, tool_schemas, _execute_tools
            )
        else:
            # Default: REACT mode (tool-calling loop)
            response = await llm_router.call_llm_react(
                task_type=task_type,
                system_prompt=full_system_prompt,
                user_prompt=user_prompt,
                tool_schemas=tool_schemas,
                execute_tool_fn=_execute_tools,
                temperature=config.get("temperature", 0.7),
                max_tokens=config.get("max_tokens"),
                max_react_turns=MAX_REACT_TURNS,
                model_override=model_override,
            )
            output = response.output

        # If tools ran, always append a structured summary of tool results
        # so downstream consumers (critic, context) see the full picture.
        if all_tool_results:
            tool_summary = ToolExecutor.format_tool_results(all_tool_results)
            if not output.strip():
                # LLM gave no final text — use tool results as the output
                output = tool_summary
            else:
                # LLM DID produce analysis text — append tool results as reference
                output = output + "\n\n=== Tool Execution Results ===\n" + tool_summary

        # Detect UncertaintySignal from LLM output
        UncertaintySignal = _get_uncertainty_signal()
        if output and '"needs_clarification": true' in output.lower():
            try:
                _parsed = json.loads(output)
                if _parsed.get("needs_clarification"):
                    raise UncertaintySignal(
                        question=_parsed.get("question", "Uncertain about how to proceed."),
                        confidence=_parsed.get("confidence", 0.0),
                        alternatives=_parsed.get("alternatives", []),
                    )
            except json.JSONDecodeError:
                pass

        logger.debug(f"{reasoning_mode} complete. Tokens: {response.prompt_tokens}+{response.completion_tokens}, latency: {response.latency_ms}ms")

        # Log the interaction
        log = LLMInteractionLog(
            run_id=run.id,
            model_provider=response.provider,
            model_name=response.model_name,
            input_prompt=f"System: {full_system_prompt[:2000]}\nUser: {user_prompt[:2000]}",
            output_response=output,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
            reasoning_mode=reasoning_mode,
            step_name=step.name,
        )
        self.db.add(log)

        await self._log_usage(run, response.model_name, response.prompt_tokens, response.completion_tokens, log)
        await self.db.commit()
        return {"step": step.name, "output": output}

    # ═══════════════════════════════════════════════════════════════════════
    # Reasoning Mode Implementations
    # ═══════════════════════════════════════════════════════════════════════

    async def _execute_chain_of_thought(self, llm_router, system_prompt, user_prompt,
                                         task_type, config, tool_schemas, execute_tool_fn):
        """CHAIN_OF_THOUGHT: Structured thinking with explicit reasoning chain extraction."""
        cot_system = system_prompt + """

## Reasoning Instructions
Think through this problem step by step. Structure your response as:

<thinking>
Step 1: [your analysis]
Step 2: [your analysis]
...
</thinking>

<answer>
[Your final answer here]
</answer>"""

        response = await llm_router.call_llm_react(
            task_type=task_type,
            system_prompt=cot_system,
            user_prompt=user_prompt,
            tool_schemas=tool_schemas,
            execute_tool_fn=execute_tool_fn,
            temperature=config.get("temperature", 0.5),
            max_tokens=config.get("max_tokens"),
            max_react_turns=MAX_REACT_TURNS,
            model_override=config.get("__model_override"),
        )

        output = response.output
        # Extract <answer> block if present, otherwise use full output
        answer_match = re.search(r'<answer>(.*?)</answer>', output, re.DOTALL)
        if answer_match:
            output = answer_match.group(1).strip()

        return output, response

    async def _execute_reflection(self, llm_router, system_prompt, user_prompt,
                                   task_type, config, tool_schemas, execute_tool_fn):
        """REFLECTION: Three-phase generate → critique → improve cycle."""
        # Phase 1: Initial generation
        _model_ovr = config.get("__model_override")
        initial_response = await llm_router.call_llm_react(
            task_type=task_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schemas=tool_schemas,
            execute_tool_fn=execute_tool_fn,
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens"),
            max_react_turns=MAX_REACT_TURNS,
            model_override=_model_ovr,
        )
        initial_output = initial_response.output

        # Phase 2: Self-critique
        critique_prompt = (
            "Critically evaluate the following response. Identify specific weaknesses, "
            "logical gaps, factual errors, missing information, or areas that could be improved. "
            "Be constructive and specific.\n\n"
            f"ORIGINAL TASK:\n{user_prompt}\n\n"
            f"RESPONSE TO EVALUATE:\n{initial_output}"
        )
        critique_response = await llm_router.call_llm(
            task_type=task_type,
            system_prompt="You are a rigorous, constructive critic. Find specific weaknesses.",
            user_prompt=critique_prompt,
            temperature=0.3,
            max_tokens=config.get("max_tokens"),
            model_override=_model_ovr,
        )

        # Phase 3: Improved version
        improve_prompt = (
            f"Here is the original task, an initial response, and a critique of that response. "
            f"Produce an improved version that addresses all the critique points.\n\n"
            f"ORIGINAL TASK:\n{user_prompt}\n\n"
            f"INITIAL RESPONSE:\n{initial_output}\n\n"
            f"CRITIQUE:\n{critique_response.output}\n\n"
            f"IMPROVED RESPONSE:"
        )
        improved_response = await llm_router.call_llm(
            task_type=task_type,
            system_prompt=system_prompt,
            user_prompt=improve_prompt,
            temperature=config.get("temperature", 0.5),
            max_tokens=config.get("max_tokens"),
            model_override=_model_ovr,
        )

        # Aggregate token counts for accurate billing
        total_response = copy.copy(improved_response)
        total_response.prompt_tokens = (
            initial_response.prompt_tokens + critique_response.prompt_tokens + improved_response.prompt_tokens
        )
        total_response.completion_tokens = (
            initial_response.completion_tokens + critique_response.completion_tokens + improved_response.completion_tokens
        )
        total_response.latency_ms = (
            initial_response.latency_ms + critique_response.latency_ms + improved_response.latency_ms
        )

        return improved_response.output, total_response

    async def _execute_tree_of_thoughts(self, llm_router, system_prompt, user_prompt,
                                         task_type, config, tool_schemas, execute_tool_fn):
        """TREE_OF_THOUGHTS: Generate N candidate paths in parallel, score, select best."""
        num_paths = config.get("tot_num_paths", 3)
        _model_ovr = config.get("__model_override")

        # Phase 1: Generate N candidate responses in parallel with higher temperature
        async def _generate_candidate(i):
            return await llm_router.call_llm(
                task_type=task_type,
                system_prompt=system_prompt + f"\n\nGenerate approach #{i+1}. Be creative and thorough.",
                user_prompt=user_prompt,
                temperature=min(config.get("temperature", 0.7) + 0.2, 1.0),
                max_tokens=config.get("max_tokens"),
                model_override=_model_ovr,
            )

        candidates = await asyncio.gather(*[_generate_candidate(i) for i in range(num_paths)])

        # Phase 2: Score each candidate
        candidates_text = "\n\n---\n\n".join([
            f"## Candidate {i+1}\n{c.output}" for i, c in enumerate(candidates)
        ])
        scoring_prompt = (
            f"You are evaluating {num_paths} different responses to the same task. "
            f"For each candidate, rate it 1-10 on: accuracy, completeness, clarity, and relevance. "
            f"Then select the BEST candidate number.\n\n"
            f"ORIGINAL TASK:\n{user_prompt}\n\n"
            f"CANDIDATES:\n{candidates_text}\n\n"
            f"Respond with JSON: {{\"scores\": [{{\"candidate\": 1, \"score\": 8, \"reason\": \"...\"}}], "
            f"\"best\": <candidate_number>}}"
        )
        scoring_response = await llm_router.call_llm(
            task_type=task_type,
            system_prompt="You are an impartial evaluator. Select the best response.",
            user_prompt=scoring_prompt,
            temperature=0.2,
            max_tokens=1000,
            model_override=_model_ovr,
        )

        # Parse scoring to find best candidate
        best_idx = 0  # Default to first candidate
        try:
            score_text = scoring_response.output
            if "{" in score_text and "}" in score_text:
                json_str = score_text[score_text.find("{"):score_text.rfind("}") + 1]
                parsed = json.loads(json_str)
                best_num = parsed.get("best", 1)
                best_idx = max(0, min(best_num - 1, num_paths - 1))
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        best_output = candidates[best_idx].output

        # Aggregate token counts
        total_prompt = sum(c.prompt_tokens for c in candidates) + scoring_response.prompt_tokens
        total_completion = sum(c.completion_tokens for c in candidates) + scoring_response.completion_tokens
        total_latency = max(c.latency_ms for c in candidates) + scoring_response.latency_ms  # parallel, so max

        total_response = copy.copy(candidates[best_idx])
        total_response.prompt_tokens = total_prompt
        total_response.completion_tokens = total_completion
        total_response.latency_ms = total_latency

        return best_output, total_response

    async def _log_usage(self, run, model_name: str, prompt_tokens: int, completion_tokens: int, log):
        """Helper to log LLM usage stats using model_name from LLMResponse."""
        input_sku = f"{model_name}-in" if model_name else "unknown-in"
        output_sku = f"{model_name}-out" if model_name else "unknown-out"

        logger.debug(f"Logging LLM usage: model={model_name}, in={prompt_tokens}, out={completion_tokens}")

        input_usage = await self.usage_service.log_usage(
            company_id=run.company_id,
            service_sku=input_sku,
            raw_quantity=float(prompt_tokens),
            execution_id=run.id
        )

        output_usage = await self.usage_service.log_usage(
            company_id=run.company_id,
            service_sku=output_sku,
            raw_quantity=float(completion_tokens),
            execution_id=run.id
        )

        # Ensure null-safe accumulation
        if run.total_cost_usd is None:
            run.total_cost_usd = Decimal("0")
        if log.cost_usd is None:
            log.cost_usd = Decimal("0")
        if run.total_tokens is None:
            run.total_tokens = 0

        if input_usage:
            log.cost_usd += input_usage.calculated_cost
            run.total_cost_usd += input_usage.calculated_cost
            logger.info(f"LLM input cost ({input_sku}): {prompt_tokens} tokens → ${input_usage.calculated_cost}")
        else:
            logger.warning(f"No registry entry for SKU '{input_sku}' — input cost not tracked")

        if output_usage:
            log.cost_usd += output_usage.calculated_cost
            run.total_cost_usd += output_usage.calculated_cost
            logger.info(f"LLM output cost ({output_sku}): {completion_tokens} tokens → ${output_usage.calculated_cost}")
        else:
            logger.warning(f"No registry entry for SKU '{output_sku}' — output cost not tracked")

        run.total_tokens += (prompt_tokens + completion_tokens)
        logger.info(f"Run total cost so far: ${run.total_cost_usd}, total tokens: {run.total_tokens}")

    async def _maybe_summarize_context(self, run, entity, context_state: dict) -> dict:
        """Smartly trim context if it exceeds threshold, preserving critical keys."""
        if not entity.logic_gate:
            return context_state

        context_policy = (entity.logic_gate or {}).get("context_policy") or {}
        threshold = context_policy.get("summarize_threshold", 20000)

        context_str = json.dumps(context_state, default=str)
        if len(context_str) <= threshold:
            return context_state

        logger.debug(f"Context size {len(context_str)} exceeds threshold {threshold}. Smart-trimming...")

        always_keep = {"input"}
        explicit_preserve = set(context_policy.get("preserve_keys", []))
        always_keep |= explicit_preserve

        all_keys = list(context_state.keys())
        step_keys = [k for k in all_keys if k not in always_keep]
        recent_keys = set(step_keys[-3:]) if step_keys else set()

        trimmed = {k: context_state[k] for k in all_keys if k in always_keep or k in recent_keys}

        trimmed_str = json.dumps(trimmed, default=str)
        if len(trimmed_str) <= threshold:
            logger.debug(f"Smart-trim reduced context to {len(trimmed_str)} chars.")
            return trimmed

        old_keys = [k for k in step_keys if k not in recent_keys]
        if old_keys:
            old_context_str = json.dumps(
                {k: context_state[k] for k in old_keys}, default=str
            )
            try:
                llm_router = LLMRouter(db=self.db, company_id=run.company_id)
                summary_resp = await llm_router.call_llm(
                    task_type="text_generation",
                    system_prompt=(
                        "Summarise the following execution context into 2-3 concise sentences. "
                        "Preserve any specific names, numbers, facts, or JSON structures mentioned."
                    ),
                    user_prompt=old_context_str,
                    temperature=0.3,
                    max_tokens=800,
                )
                trimmed["earlier_context_summary"] = summary_resp.output
            except Exception as e:
                logger.warning(f"Context summarization failed: {e}. Using trimmed context without summary.")

        final_str = json.dumps(trimmed, default=str)
        logger.debug(f"Context trimmed {len(context_str)} -> {len(final_str)} chars.")
        return trimmed

    async def _review_step_output(self, run, entity, step, result, context_state: dict = None) -> dict:
        """Self-critique review mechanism with retry logic."""
        review_config = (entity.logic_gate or {}).get("review_mechanism") or {}
        if not review_config.get("enabled"):
            return result
        
        # Don't review errors or tools for now
        if "error" in result:
            return result

        max_retries = ((entity.logic_gate or {}).get("retry_policy") or {}).get("max_retries", 3)

        # Fix 4 (Option A): Cap retries for expensive reasoning modes.
        # REFLECTION steps are 2-3x more expensive per retry (~90s each);
        # burning 3 retries can consume the entire execution budget.
        step_reasoning = getattr(step.target, 'reasoning_mode', None) if step.target else None
        if not step_reasoning:
            # Fall back to entity-level reasoning mode
            step_reasoning = ((entity.logic_gate or {}).get("reasoning_config") or {}).get("reasoning_mode", "")
        if str(step_reasoning).upper() == "REFLECTION" and max_retries > 1:
            max_retries = 1
            logger.info(f"Capped retries to {max_retries} for REFLECTION step '{step.name}'")

        custom_criteria = review_config.get("review_prompt", "")
        # Use entity-configured review system prompt, falling back to the schema default
        base_review_prompt = review_config.get("review_system_prompt") or _get_review_prompt()
        if custom_criteria:
            review_prompt = base_review_prompt + f"\n\n## Additional Review Criteria\nAlso evaluate the output against these criteria:\n{custom_criteria}"
        else:
            review_prompt = base_review_prompt

        # Critic strictness: 'strict' (default) or 'lenient'.
        # In lenient mode, the critic passes if tools executed successfully
        # and the step produced meaningful content, even if not all
        # deliverables in the description are fully covered.
        critic_strictness = review_config.get("critic_strictness", "strict")
        
        # Get independent API key for critic
        # Use entity's reasoning config or LLM config
        config = (entity.logic_gate or {}).get("reasoning_config") or {}
        task_type = config.get("task_type", "text_generation")
        
        current_result = result

        # Lenient early-pass: if the step produced non-trivial output
        # and no error was raised, skip the expensive critic LLM call.
        if critic_strictness == "lenient":
            step_output = current_result.get("output", "")
            has_meaningful_output = len(str(step_output)) > 200  # not empty/tiny
            has_no_error = "error" not in str(step_output).lower()[:100]
            if has_meaningful_output and has_no_error:
                logger.info(f"Lenient critic: passing step '{step.name}' (output={len(str(step_output))} chars)")
                return current_result

        # Budget guard: skip expensive retries if the run has consumed
        # too much wall-clock time (>80% of the job timeout).
        # Read per-entity timeout from config; fall back to global ceiling.
        entity_timeout = (
            (entity.logic_gate or {}).get("reasoning_config", {})
            .get("max_execution_time_seconds", 3600)
        )
        MAX_RUN_SECONDS = min(int(entity_timeout), 7200)  # capped at global ceiling
        BUDGET_PCT = 0.80
        elapsed = (datetime.utcnow() - run.started_at).total_seconds() if run.started_at else 0
        if elapsed > MAX_RUN_SECONDS * BUDGET_PCT:
            logger.warning(
                f"Skipping critic review for step '{step.name}' — "
                f"run has consumed {elapsed:.0f}s / {MAX_RUN_SECONDS}s budget"
            )
            return current_result
        
        for attempt in range(max_retries):
            logger.debug(f"Running Review/Critic Attempt {attempt+1}/{max_retries} for step {step.name}")
            
            # Call critic LLM
            critic_input = json.dumps({
                "step_description": step.description,
                "step_output": current_result.get("output"),
                "success_criteria": review_config.get("success_criteria", [])
            }, default=str)
            
            llm_router = LLMRouter(db=self.db, company_id=run.company_id)
            critic_resp = await llm_router.call_llm(
                task_type=task_type,
                system_prompt=review_prompt,
                user_prompt=critic_input,
                temperature=0.2,
            )
            critique_text = critic_resp.output
            
            # Log critic LLM interaction and usage
            critic_log = LLMInteractionLog(
                run_id=run.id,
                model_provider=critic_resp.provider,
                model_name=critic_resp.model_name,
                input_prompt=f"System: {review_prompt[:2000]}\nUser: {critic_input[:2000]}",
                output_response=critique_text[:2000] if critique_text else "",
                prompt_tokens=critic_resp.prompt_tokens,
                completion_tokens=critic_resp.completion_tokens,
                latency_ms=critic_resp.latency_ms,
                reasoning_mode="CRITIC",
                step_name=step.name,
            )
            self.db.add(critic_log)
            await self._log_usage(run, critic_resp.model_name, critic_resp.prompt_tokens, critic_resp.completion_tokens, critic_log)
            
            passed = False
            reason = ""
            suggestion = ""
            
            try:
                # Try to parse JSON output from critic
                if "{" in critique_text and "}" in critique_text:
                    json_str = critique_text[critique_text.find("{"):critique_text.rfind("}")+1]
                    critique_json = json.loads(json_str)
                    passed = critique_json.get("passed", False)
                    reason = critique_json.get("reason", "")
                    suggestion = critique_json.get("suggestion", "")
                else:
                    # Fallback text parsing
                    passed = "passed" in critique_text.lower() and "true" in critique_text.lower()
                    reason = critique_text
            except Exception as e:
                logger.warning(f"Failed to parse critique: {e}")
                passed = False
                reason = "Critique parsing failed"

            if passed:
                return current_result
            
            # Retry with feedback if not passed
            if attempt < max_retries - 1:
                feedback = f"\n\nCRITIC FEEDBACK (Previous Attempt Failed): {reason}. Suggestion: {suggestion}\nPlease improve your response based on this."
                
                # Re-execute step context with feedback appended
                # This is a recursive call to _execute_thought but with modified context/prompt handling requires structural change
                # For MVP, we'll just append feedback to the next prompt or return the annotated result
                # Ideally we want to re-run the step.
                
                # Simplified Retry: Re-run the step with feedback in context
                # NOTE: This recursively calls _execute_step's logic
                retry_context = copy.deepcopy(context_state if context_state is not None else run.context_state or {})
                retry_context["input"] = (retry_context.get("input", "") + feedback)
                
                # We need to know which type of step it was to retry correctly
                if step.type in [StepType.THOUGHT, StepType.ACTION]:
                    current_result = await self._execute_thought(run, entity, step, retry_context)
                elif step.type == StepType.TOOL_CALL:
                    # Tools usually static, maybe just retry?
                    current_result = await self._execute_tool_call(run, entity, step, retry_context)
                    
            else:
                # Handle failure per on_failure policy
                on_failure = review_config.get("on_failure", "RETRY")
                if on_failure == "ESCALATE":
                    current_result["requires_human_review"] = True
                    current_result["review_failure_reason"] = reason
                elif on_failure == "ABORT":
                    raise Exception(f"Step {step.name} failed verification after {max_retries} attempts: {reason}")
        
        return current_result

    def _should_exit(self, step: PlanStep, context: dict) -> bool:
        """Evaluates exit conditions for early termination."""
        for condition in step.exit_conditions:
            # Simplified evaluation
            if "error" in str(context.get(step.name, "")).lower():
                if condition.next_step == 'ESCALATE':
                    return True
        return False

