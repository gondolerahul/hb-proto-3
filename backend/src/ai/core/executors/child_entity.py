"""
ChildEntityExecutor — adapter around step_executor child invocation.

CHILD_ENTITY_INVOCATION steps in a plan spawn a sub-run (synchronous
or async-dispatched per governance config). The legacy path lives in
``step_executor``; this adapter wraps it so AgentLoop can drive it.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.ai.core.agent_state import AgentState
from src.ai.core.executors.base import ActionResult, register_executor
from src.ai.core.executors.single_step import _resolve_redis
from src.ai.core.strategist import Move
from src.ai.core.trace import span
from src.ai.orm.execution import ExecutionRun

logger = logging.getLogger(__name__)


class ChildEntityExecutor:
    name = "ChildEntity"

    async def execute(
        self,
        move: Move,
        state: AgentState,
        db: Any,
    ) -> ActionResult:
        if not move.plan_fragment:
            return ActionResult(
                success=False,
                error="ChildEntityExecutor invoked with empty plan_fragment",
            )

        step = move.plan_fragment[0]
        from src.ai.core.execution_engine import ExecutionEngine

        redis = _resolve_redis(state)
        engine = ExecutionEngine(db, redis, state.company_id)
        engine._ensure_services(state.company_id)

        run = await self._reload_run(db, state.run_id)
        entity = run.entity

        step_obj = self._coerce_step(step)
        ctx = await state.materialise_context_dict()
        start = time.time()

        # ── Async child dispatch (suspend/resume) ────────────────────────────
        # When the entity opts in and Redis is available, create the child run,
        # enqueue it as its OWN isolated job (own session + own budget), and
        # return an ``awaiting_children`` marker. The AgentLoop snapshots and
        # suspends (WAITING_ON_CHILDREN) instead of blocking this worker; the
        # child's finalize enqueues ``resume_parent_run`` which folds the result
        # back in. This is the mechanism that lets a PROCESS's children run
        # without the inline-nested-loop cost amplification.
        governance = (entity.governance or {}) if entity else {}
        if governance.get("async_child_dispatch") and redis is not None:
            try:
                return await self._dispatch_async(
                    engine, redis, run, entity, step_obj, state, start,
                )
            except Exception as exc:                                       # noqa: BLE001
                # Dispatch failure must not strand the run — fall through to the
                # inline path below so behaviour degrades to the legacy mode.
                logger.warning(
                    "Async child dispatch failed (%s); falling back to inline.",
                    exc,
                )

        _child_name = str(getattr(step_obj, "name", "") or getattr(step_obj, "step_id", "") or "child")
        async with span(
            "child", _child_name,
            step_id=str(getattr(step_obj, "step_id", "") or ""),
            instruction=getattr(step_obj, "instruction", None) or getattr(step_obj, "description", None),
        ) as _child_span:
            try:
                result = await engine._execute_step_wrapper(run, entity, step_obj, ctx)
            except Exception as exc:                                       # noqa: BLE001
                _child_span.set_error(f"{type(exc).__name__}: {exc}")
                return ActionResult(
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                    latency_ms=int((time.time() - start) * 1000),
                )

            latency_ms = int((time.time() - start) * 1000)
            await state.absorb_context_dict(ctx)

            step_id = str(getattr(step_obj, "step_id", None) or step_obj.name or "")
            cost = Decimal(str((result or {}).get("cost_usd", 0) or 0))
            child_run_ids: list = []
            child_id = (result or {}).get("child_run_id") or (result or {}).get("run_id")
            if child_id:
                try:
                    from uuid import UUID

                    child_run_ids.append(UUID(str(child_id)))
                except Exception:
                    pass

            # Link the span to the spawned sub-run so the UI can deep-link into
            # the child's own trace tree.
            if child_run_ids:
                _child_span.set_child_run_id(child_run_ids[0])
            _child_span.set_cost(cost)
            _child_span.set_output(str((result or {}).get("output", ""))[:8000])
            if (result or {}).get("error"):
                _child_span.set_error(str((result or {}).get("error")))

        return ActionResult(
            output=str((result or {}).get("output", ""))[:8000],
            cost_usd=cost,
            latency_ms=latency_ms,
            success=not (result or {}).get("error"),
            error=str((result or {}).get("error", ""))[:500],
            completed_step_ids=[step_id] if step_id else [],
            children_run_ids=child_run_ids,
        )

    async def _dispatch_async(
        self,
        engine: Any,
        redis: Any,
        run: ExecutionRun,
        entity: Any,
        step_obj: Any,
        state: AgentState,
        start: float,
    ) -> ActionResult:
        """Create the child run, enqueue it as its own job, return an
        ``awaiting_children`` ActionResult so the loop suspends."""
        from arq.connections import ArqRedis

        ctx = await state.materialise_context_dict()
        child_run = await engine._step_executor.create_child_run(
            run, entity, step_obj, ctx
        )
        await state.absorb_context_dict(ctx)

        step_id = str(getattr(step_obj, "step_id", None) or getattr(step_obj, "name", "") or "")

        # Enqueue the child as its own isolated run job (same entry point a
        # top-level run uses → its own session, budget, and AgentLoop).
        arq_redis = ArqRedis(redis.connection_pool)
        await arq_redis.enqueue_job("run_execution_recursive", str(child_run.id))

        logger.info(
            "Async-dispatched child run %s (step=%s) for parent %s; suspending.",
            child_run.id, step_id, run.id,
        )
        return ActionResult(
            success=True,
            output="",
            latency_ms=int((time.time() - start) * 1000),
            children_run_ids=[child_run.id],
            awaiting_children=[{
                "run_id": str(child_run.id),
                "step_id": step_id,
                "status": "PENDING",
            }],
        )

    @staticmethod
    async def _reload_run(db: Any, run_id: Any) -> ExecutionRun:
        result = await db.execute(
            select(ExecutionRun)
            .options(selectinload(ExecutionRun.entity))
            .where(ExecutionRun.id == run_id)
        )
        return result.scalar_one()

    @staticmethod
    def _coerce_step(step: Any) -> Any:
        from src.ai.schemas.planning import PlanStep

        if isinstance(step, PlanStep):
            return step
        if isinstance(step, dict):
            return PlanStep.model_validate(step)
        return step


register_executor(ChildEntityExecutor())
