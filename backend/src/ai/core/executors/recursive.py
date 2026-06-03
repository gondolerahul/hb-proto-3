"""
RecursiveExecutor — adapter around RecursiveReasoningEngine (Track 2).

For goal-only AGENTs without a static plan, the recursive engine
decomposes the goal into a tree of subgoals and executes the leaves.
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
from src.ai.orm.execution import ExecutionRun

logger = logging.getLogger(__name__)


class RecursiveExecutor:
    name = "Recursive"

    async def execute(
        self,
        move: Move,                # noqa: ARG002
        state: AgentState,
        db: Any,
    ) -> ActionResult:
        from src.ai.core.execution_engine import ExecutionEngine

        engine = ExecutionEngine(db, _resolve_redis(state), state.company_id)
        engine._ensure_services(state.company_id)

        run = await self._reload_run(db, state.run_id)
        start = time.time()

        try:
            result = await engine.execute_run(state.run_id)
        except Exception as exc:                                           # noqa: BLE001
            return ActionResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=int((time.time() - start) * 1000),
            )

        latency_ms = int((time.time() - start) * 1000)
        cost = Decimal(str((result or {}).get("total_cost_usd",
                                              float(run.total_cost_usd or 0)) or 0))
        return ActionResult(
            output=str((result or {}).get("output", ""))[:8000],
            cost_usd=cost,
            latency_ms=latency_ms,
            success=True,
        )

    @staticmethod
    async def _reload_run(db: Any, run_id: Any) -> ExecutionRun:
        result = await db.execute(
            select(ExecutionRun)
            .options(selectinload(ExecutionRun.entity))
            .where(ExecutionRun.id == run_id)
        )
        return result.scalar_one()


register_executor(RecursiveExecutor())
