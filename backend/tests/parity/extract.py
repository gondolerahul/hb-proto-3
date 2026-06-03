"""
tests/parity/extract.py — Build a RunResult from a live ExecutionRun.

Two callers:
  1. ``record_golden_runs.py`` — runs the LEGACY ExecutionEngine, then
     extracts a RunResult to disk for later comparison.
  2. Track 2+ parity tests — run the NEW AgentLoop, extract a
     RunResult, and compare against the recorded golden one.

Kept here (not in src/ai/) because it is a TEST concern: it knows the
DB shape but not the business logic.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from tests.harness import RunResult, StepSummary


async def extract_run_result(
    db: AsyncSession,
    run_id: str,
    *,
    iterations: Optional[int] = None,
    output_text: str = "",
) -> RunResult:
    """Read a completed ExecutionRun and its child logs; return a RunResult.

    The new AgentLoop will track ``iterations`` distinctly from step
    count; legacy callers pass ``iterations=None`` and we fall back to
    ``step_count``.
    """
    # Local imports so the harness loads even before the kernel does.
    from sqlalchemy import select

    from src.ai.orm.execution import (
        ExecutionRun,
        LLMInteractionLog,
        ToolInteractionLog,
    )

    run = (await db.execute(
        select(ExecutionRun).where(ExecutionRun.id == run_id)
    )).scalar_one()

    llm_rows = (await db.execute(
        select(LLMInteractionLog).where(LLMInteractionLog.run_id == run_id)
        .order_by(LLMInteractionLog.created_at)
    )).scalars().all()

    tool_rows = (await db.execute(
        select(ToolInteractionLog).where(ToolInteractionLog.run_id == run_id)
        .order_by(ToolInteractionLog.created_at)
    )).scalars().all()

    # Plan-step shapes come from ``run.dynamic_plan``. Either is fine.
    plan = run.dynamic_plan or {}
    plan_steps = plan.get("steps") if isinstance(plan, dict) else None
    plan_step_types: list[str] = []
    step_summaries: list[StepSummary] = []

    if isinstance(plan_steps, list):
        for s in plan_steps:
            t = s.get("type", "")
            plan_step_types.append(str(t))
            step_summaries.append(
                StepSummary(
                    step_id=str(s.get("step_id") or s.get("id") or ""),
                    name=str(s.get("name") or ""),
                    type=str(t),
                    status=str(s.get("status") or "success"),
                    tool_id=(s.get("target") or {}).get("tool_id") if isinstance(s.get("target"), dict) else None,
                )
            )

    # Attach per-step LLM + tool costs by step_name match where possible.
    for row in llm_rows:
        if not row.step_name:
            continue
        for summ in step_summaries:
            if summ.name == row.step_name or summ.step_id == row.step_name:
                summ.cost_usd += float(row.cost_usd or 0)
                summ.latency_ms += int(row.latency_ms or 0)
                summ.output_len += len(row.output_response or "")

    for row in tool_rows:
        for summ in step_summaries:
            if summ.tool_id == row.tool_id and summ.status == "success":
                summ.latency_ms += int(row.latency_ms or 0)
                summ.output_len += len(str(row.output_result or ""))

    derived_output = output_text
    if not derived_output:
        # Best-effort: stringify result_data so similarity comparisons
        # have something to chew on.
        if run.result_data:
            derived_output = str(run.result_data)

    return RunResult(
        run_id=str(run.id),
        entity_id=str(run.entity_id),
        status=str(run.status),
        total_cost_usd=float(run.total_cost_usd or 0),
        total_tokens=int(run.total_tokens or 0),
        execution_time_ms=int(run.execution_time_ms or 0),
        iterations=int(iterations if iterations is not None else len(step_summaries) or 0),
        step_count=len(step_summaries),
        error_message=run.error_message,
        output_text=derived_output,
        plan_step_types=plan_step_types,
        steps=step_summaries,
        meta={
            "llm_call_count": len(llm_rows),
            "tool_call_count": len(tool_rows),
        },
    )
