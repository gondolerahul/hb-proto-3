"""
planner_service.py — Plan reconciliation, validation, and step management.

Extracted from ExecutionEngine during Phase 6 monolith decomposition
(Step 3.2). Handles static/dynamic plan merging, CHILD_ENTITY_INVOCATION
injection, and step-id generation.
"""
import copy
import json
import logging
from uuid import UUID, uuid4
from typing import List, Optional

from src.ai.models import ExecutionRun, HierarchicalEntity, LLMInteractionLog
from src.ai.schemas import (
    EntityType, PlanStep,
    DEFAULT_PLANNING_SYSTEM_PROMPT,
)
from src.ai.llm.router import LLMRouter
from src.ai.usage_service import UsageService

logger = logging.getLogger(__name__)


class PlannerService:
    """Generates and reconciles execution plans from entity configuration."""

    def __init__(self, db, company_id: UUID):
        self.db = db
        self.company_id = company_id
        self.llm = LLMRouter(db=db, company_id=company_id)
        self.usage_service = UsageService(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def reconcile(
        self,
        run: ExecutionRun,
        entity: HierarchicalEntity,
        input_data: dict,
    ) -> dict:
        """Merges static and dynamic plans based on strategy.

        Returns a plan dict with a ``steps`` key containing the final
        ordered list of step dicts.
        """
        planning = entity.planning or {}
        static_plan = copy.deepcopy(planning.get("static_plan", {})) or {}

        if "steps" not in static_plan:
            static_plan["steps"] = []

        # Fallback: If no steps and it is a leaf action/skill, add a default step
        if not static_plan["steps"] and entity.type in [EntityType.ACTION, EntityType.SKILL]:
            static_plan["steps"] = [{
                "step_id": "auto_generated",
                "order": 1,
                "name": "Execute",
                "description": f"Executing {entity.name}",
                "type": "ACTION",
                "target": {
                    "prompt_template": entity.description or "Process instruction: {{instruction}}"
                },
                "required": True
            }]

        dynamic_config = planning.get("dynamic_planning", {}) or {}

        if not dynamic_config.get("enabled"):
            return static_plan

        # Generate dynamic plan via LLM
        logger.info(
            f"Generating dynamic plan for {entity.name} "
            f"with input keys: {list(input_data.keys())}"
        )

        return await self._generate_dynamic_plan(
            run, entity, input_data, static_plan, dynamic_config
        )

    def has_parallel_steps(self, steps: List[dict]) -> bool:
        """Return True ONLY if at least two steps can run simultaneously.

        The previous implementation returned True whenever *any* step had
        input_dependencies — but that means 'this step needs output from step X',
        NOT 'run me in parallel'.  A pure chain like:

            step1 (no deps) → step2 (deps=[step1]) → step3 (deps=[step2])

        has input_dependencies on steps 2 and 3 but is 100% sequential and must
        NEVER be routed to the DAG/parallel executor (which opens isolated
        AsyncSessions per step and races for the shared self.db).

        Correct logic: simulate one round of DAG scheduling.  If the first wave
        of 'ready' steps (those whose deps are all absent/empty) has two or more
        members, genuine parallelism exists → use the DAG executor.  Otherwise
        the plan is sequential → use the sequential loop.
        """
        if not steps:
            return False

        # Build dep sets from explicit input_dependencies + {{step_id}} refs
        step_ids = {s.get("step_id") for s in steps if s.get("step_id")}
        step_deps: dict = {}

        for s in steps:
            s_id = s.get("step_id")
            if not s_id:
                continue
            deps: set = set()
            target = s.get("target") or {}
            for dep in target.get("input_dependencies", []):
                if dep in step_ids:
                    deps.add(dep)
            # Also honour {{step_id}} template references
            prompt = target.get("prompt_template", "") or ""
            if isinstance(prompt, dict):
                import json as _json
                prompt = _json.dumps(prompt)
            import re as _re
            for var in _re.findall(r'\{\{(.*?)\}\}', str(prompt)):
                base = var.split('.')[0]
                if base in step_ids and base != s_id:
                    deps.add(base)
            step_deps[s_id] = deps

        # Count steps that are immediately ready (no dependencies at all)
        initially_ready = sum(1 for deps in step_deps.values() if not deps)
        return initially_ready >= 2


    async def validate_goal_progress(
        self,
        goal: str,
        completed_steps: List[dict],
        total_steps: int,
    ) -> dict:
        """Lightweight LLM call to assess goal completion progress.

        Phase 5: Used by the autonomous loop to decide whether to
        early-exit (goal achieved) or trigger re-planning (low progress).

        Returns ``{"score": 0-100, "reasoning": "...", "goal_achieved": bool}``.
        """
        step_summaries = json.dumps(
            [
                {
                    "name": s.get("name", s.get("step", "")),
                    "output_summary": str(s.get("output", ""))[:500],
                }
                for s in completed_steps
            ],
            indent=2,
        )
        prompt = (
            f"Given the original goal and completed work, assess progress.\n\n"
            f"Goal: {goal}\n\n"
            f"Completed steps ({len(completed_steps)}/{total_steps}):\n"
            f"{step_summaries}\n\n"
            f'Respond with JSON: {{"score": 0-100, "reasoning": "...", "goal_achieved": true/false}}'
        )
        try:
            result = await self.llm.call_llm(
                task_type="goal_validation",
                system_prompt="You assess goal completion progress. Be precise and conservative.",
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=300,
            )
            # Parse JSON from response
            output = result.output.strip()
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0]
            elif "{" in output:
                output = output[output.find("{"):output.rfind("}") + 1]
            return json.loads(output)
        except Exception as e:
            logger.warning(f"Goal validation failed: {e}")
            return {"score": 50, "reasoning": f"Validation failed: {e}", "goal_achieved": False}

    async def adapt_plan(
        self,
        original_plan: list,
        completed_steps: list,
        failed_step: dict,
        goal: str,
    ) -> List[dict]:
        """Mid-execution re-planning (Phase 5 — Autonomous Loop).

        When a step fails in autonomous mode, generates a revised plan
        for the remaining work based on what has already succeeded and
        what failed.

        Returns a list of revised step dicts with fresh step_ids.
        """
        completed_ids = {s.get("step_id") for s in completed_steps if s.get("step_id")}
        remaining = [s for s in original_plan if s.get("step_id") not in completed_ids]

        prompt = (
            f"The original plan partially executed. Revise the remaining steps.\n\n"
            f"Goal: {goal}\n\n"
            f"Completed successfully:\n"
            f"{json.dumps([{'name': s.get('name', ''), 'output': str(s.get('output', ''))[:300]} for s in completed_steps], indent=2)}\n\n"
            f"Failed step:\n"
            f"{json.dumps({'name': failed_step.get('name', ''), 'error': str(failed_step.get('error', ''))[:500]}, indent=2)}\n\n"
            f"Original remaining steps:\n"
            f"{json.dumps(remaining, indent=2, default=str)}\n\n"
            f"Generate a revised plan (JSON array) for the remaining work. "
            f"You may add, remove, or modify steps."
        )

        try:
            result = await self.llm.call_llm(
                task_type="thinking",
                system_prompt=DEFAULT_PLANNING_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.4,
            )
            revised = self._parse_plan_output(result.output)
            # Assign fresh step_ids starting after the completed count
            return self._assign_step_ids(revised, start_from=len(completed_steps) + 1)
        except Exception as e:
            logger.warning(f"Plan adaptation failed: {e}. Returning original remaining steps.")
            return remaining

    def _assign_step_ids(self, steps: list, start_from: int = 1) -> list:
        """Assign sequential step_ids to a list of step dicts."""
        for i, s in enumerate(steps):
            s["step_id"] = f"step_{start_from + i}_{str(uuid4())[:8]}"
            s["order"] = start_from + i
        return steps

    # ------------------------------------------------------------------
    # Private: Dynamic Plan Generation
    # ------------------------------------------------------------------

    async def _generate_dynamic_plan(
        self,
        run: ExecutionRun,
        entity: HierarchicalEntity,
        input_data: dict,
        static_plan: dict,
        dynamic_config: dict,
    ) -> dict:
        """Call LLM to generate a dynamic plan, then reconcile with static plan."""

        # 1. Prepare planning prompt
        user_input = input_data.get("input") or {
            k: v for k, v in input_data.items()
            if k not in ("__memory__", "company_id", "user_id")
        }
        if isinstance(user_input, dict):
            user_input = json.dumps(user_input, default=str)

        entity_goal = entity.goal or ""
        entity_identity = entity.identity or {}
        entity_system_prompt = entity_identity.get("system_prompt", "")

        tools_list = (
            [t.get("tool_id", t.get("name")) for t in entity.capabilities.get("tools", [])]
            if entity.capabilities else []
        )

        # Build a lookup of CHILD_ENTITY_INVOCATION steps from the static plan.
        # LLM-generated dynamic plans cannot produce valid entity_ids, so we
        # must preserve them from the static plan and re-inject after planning.
        static_child_invocations = {}  # name -> step dict
        for s in static_plan.get("steps", []):
            if s.get("type") == "CHILD_ENTITY_INVOCATION":
                static_child_invocations[s.get("name", "")] = s

        # Include static plan steps as a reference for the planner
        static_steps_ref = self._build_static_reference(
            static_plan, static_child_invocations
        )

        custom_planning = dynamic_config.get("planning_prompt", "")
        system_prompt = (
            dynamic_config.get("planning_system_prompt")
            or DEFAULT_PLANNING_SYSTEM_PROMPT
        )
        if custom_planning:
            system_prompt += f"\n\n## Additional Planning Instructions\n{custom_planning}"
        if entity_system_prompt:
            system_prompt += f"\n\n## Agent Instructions (from system prompt)\n{entity_system_prompt}"

        # ── Tier 1 Meta-Cognition: Inject platform awareness ───────────
        # Gives the planner knowledge of tool descriptions, step types,
        # entity hierarchy, and behavioral rules — enabling informed planning.
        from src.ai.meta.platform_schema_compiler import resolve_meta_cognition
        meta_config = resolve_meta_cognition(entity)

        if meta_config.get("platform_awareness"):
            try:
                from src.ai.meta.platform_schema_compiler import get_platform_summary
                manifest_summary = await get_platform_summary(
                    db=self.db,
                    company_id=self.company_id,
                )
                if manifest_summary:
                    system_prompt += f"\n\n{manifest_summary}"
                    logger.info(
                        f"Tier 1: Injected platform awareness into planner "
                        f"({len(manifest_summary)} chars) for {entity.name}"
                    )
            except Exception as e:
                logger.warning(f"Tier 1: Failed to inject platform awareness into planner: {e}")

        # ── Inject children descriptions for PROCESS/AGENT entities ────
        # So the planner knows what child entities are available to delegate to.
        entity_type = getattr(entity, "type", "")
        if isinstance(entity_type, str):
            entity_type = entity_type.upper()

        if entity_type in ("PROCESS", "AGENT"):
            try:
                from src.ai.meta.platform_schema_compiler import describe_entity_children
                children_desc = await describe_entity_children(
                    db=self.db,
                    entity_id=entity.id,
                    company_id=self.company_id,
                )
                if children_desc:
                    system_prompt += f"\n\n{children_desc}"
                    logger.info(
                        f"Planner: Injected children descriptions "
                        f"({len(children_desc)} chars) for {entity.name}"
                    )
            except Exception as e:
                logger.warning(f"Failed to inject children descriptions into planner: {e}")
        # ───────────────────────────────────────────────────────────────

        user_prompt = f"Entity: {entity.name}\n"
        if entity_goal:
            user_prompt += f"Agent Goal: {entity_goal}\n"
        user_prompt += f"User Input: {user_input}\n"
        user_prompt += f"Available Tools: {tools_list}\n"
        user_prompt += static_steps_ref
        user_prompt += (
            "\nGenerate the execution plan. "
            "Make sure to use ALL relevant tools to accomplish the full goal."
        )

        # 2. Call Planner LLM
        try:
            plan_result_resp = await self.llm.call_llm(
                task_type="thinking",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.4,
            )

            # Log planner LLM interaction and usage
            planner_log = LLMInteractionLog(
                run_id=run.id,
                model_provider=plan_result_resp.provider,
                model_name=plan_result_resp.model_name,
                input_prompt=f"System: {system_prompt[:2000]}\nUser: {user_prompt[:2000]}",
                output_response=(
                    plan_result_resp.output[:2000] if plan_result_resp.output else ""
                ),
                prompt_tokens=plan_result_resp.prompt_tokens,
                completion_tokens=plan_result_resp.completion_tokens,
                latency_ms=plan_result_resp.latency_ms,
                reasoning_mode="PLANNER",
                step_name="__planner__",
            )
            self.db.add(planner_log)
            await self._log_planner_usage(
                run, plan_result_resp, planner_log
            )

            # 3. Parse and Validate Plan
            valid_steps = self._parse_plan_output(plan_result_resp.output)

            # 4. Reconcile CHILD_ENTITY_INVOCATION steps
            if static_child_invocations:
                self._reconcile_child_invocations(
                    valid_steps, static_child_invocations
                )

            return {"steps": valid_steps}

        except Exception as e:
            logger.warning(f"Dynamic planning failed: {e}. Falling back to static plan.")
            return static_plan

    # ------------------------------------------------------------------
    # Private Helpers
    # ------------------------------------------------------------------

    def _build_static_reference(
        self, static_plan: dict, static_child_invocations: dict
    ) -> str:
        """Build a text reference of static plan steps for the LLM."""
        if not static_plan.get("steps"):
            return ""

        ref = "\n\n## Reference Plan (use as guidance)\n"
        for s in static_plan["steps"]:
            step_type = s.get("type", "?")
            tool_ref = s.get("target", {}).get("tool_id", "N/A")
            entity_ref = s.get("target", {}).get("entity_id", "")
            extra = f", entity_id: {entity_ref}" if entity_ref else ""
            ref += (
                f"- Step {s.get('order', '?')}: {s.get('name', 'unnamed')} "
                f"(type: {step_type}, tool: {tool_ref}{extra}) — "
                f"{s.get('description', '')}\n"
            )
        if static_child_invocations:
            ref += (
                "\nIMPORTANT: Steps of type CHILD_ENTITY_INVOCATION MUST be "
                "preserved exactly as shown above. Keep their name, type, "
                "and entity_id unchanged.\n"
            )
        return ref

    def _parse_plan_output(self, output_text: str) -> List[dict]:
        """Parse LLM plan output into a validated list of step dicts."""
        json_str = output_text
        if "```json" in output_text:
            json_str = output_text.split("```json")[1].split("```")[0]
        elif "[" in output_text and "]" in output_text:
            json_str = output_text[output_text.find("["):output_text.rfind("]") + 1]

        steps = json.loads(json_str)

        valid_steps = []
        for i, s in enumerate(steps):
            # Ensure GUID step_ids
            if not s.get("step_id"):
                s["step_id"] = f"step_{i + 1}_{str(uuid4())[:8]}"

            # Sanitize target.prompt_template: LLM may emit it as a dict
            target = s.get("target")
            if isinstance(target, dict):
                pt = target.get("prompt_template")
                if isinstance(pt, (dict, list)):
                    target["prompt_template"] = json.dumps(pt, default=str)

            # Hoist top-level input_dependencies into target
            if "input_dependencies" in s and "target" not in s:
                s["target"] = {"input_dependencies": s.pop("input_dependencies")}
            elif "input_dependencies" in s and isinstance(s.get("target"), dict):
                s["target"].setdefault(
                    "input_dependencies", s.pop("input_dependencies")
                )

            valid_steps.append(s)

        return valid_steps

    def _reconcile_child_invocations(
        self,
        valid_steps: List[dict],
        static_child_invocations: dict,
    ) -> None:
        """Reconcile LLM-generated steps with static CHILD_ENTITY_INVOCATION steps.

        Mutates ``valid_steps`` in-place: injects entity_ids from static plan
        and re-adds any dropped invocation steps.
        """
        seen_invocations = set()

        for s in valid_steps:
            if s.get("type") == "CHILD_ENTITY_INVOCATION":
                step_name = s.get("name", "")
                # Try exact name match first
                matched_static = static_child_invocations.get(step_name)
                # Fuzzy match: compare lowercase/stripped names
                if not matched_static:
                    for sn, sv in static_child_invocations.items():
                        if (sn.lower().strip() in step_name.lower().strip()
                                or step_name.lower().strip() in sn.lower().strip()):
                            matched_static = sv
                            step_name = sn
                            break

                if matched_static:
                    static_target = matched_static.get("target", {})
                    if not s.get("target"):
                        s["target"] = {}
                    s["target"]["entity_id"] = static_target.get("entity_id")
                    if (not s["target"].get("prompt_template")
                            and static_target.get("prompt_template")):
                        s["target"]["prompt_template"] = static_target["prompt_template"]
                    if (not s["target"].get("input_dependencies")
                            and static_target.get("input_dependencies")):
                        s["target"]["input_dependencies"] = static_target["input_dependencies"]
                    seen_invocations.add(step_name)
                else:
                    logger.warning(
                        f"Dynamic plan has CHILD_ENTITY_INVOCATION step '{step_name}' "
                        f"with no matching static step — entity_id will be missing."
                    )

        # Inject any missing CHILD_ENTITY_INVOCATION steps
        missing = {
            name: step for name, step in static_child_invocations.items()
            if name not in seen_invocations
        }
        if missing:
            logger.info(
                f"Re-injecting {len(missing)} dropped CHILD_ENTITY_INVOCATION "
                f"steps from static plan: {list(missing.keys())}"
            )
            for name, static_step in sorted(
                missing.items(), key=lambda x: x[1].get("order", 999)
            ):
                injected = copy.deepcopy(static_step)
                if not injected.get("step_id"):
                    injected["step_id"] = f"static_inject_{str(uuid4())[:8]}"
                target_order = injected.get("order", 999)
                insert_idx = len(valid_steps)
                for idx, vs in enumerate(valid_steps):
                    if vs.get("order", 999) > target_order:
                        insert_idx = idx
                        break
                valid_steps.insert(insert_idx, injected)

    async def _log_planner_usage(
        self, run, plan_result_resp, planner_log
    ) -> None:
        """Log LLM usage for the planner call."""
        try:
            model_name = plan_result_resp.model_name or "unknown"
            in_sku = f"{model_name}-in"
            out_sku = f"{model_name}-out"

            in_usage = await self.usage_service.log_usage(
                company_id=run.company_id,
                service_sku=in_sku,
                raw_quantity=float(plan_result_resp.prompt_tokens or 0),
                execution_id=run.id,
            )
            out_usage = await self.usage_service.log_usage(
                company_id=run.company_id,
                service_sku=out_sku,
                raw_quantity=float(plan_result_resp.completion_tokens or 0),
                execution_id=run.id,
            )

            from decimal import Decimal
            if run.total_cost_usd is None:
                run.total_cost_usd = Decimal("0")
            if in_usage:
                run.total_cost_usd += in_usage.calculated_cost
            if out_usage:
                run.total_cost_usd += out_usage.calculated_cost
        except Exception as e:
            logger.debug(f"Planner usage logging failed: {e}")
