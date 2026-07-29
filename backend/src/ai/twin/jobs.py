"""twin/jobs.py — the scenario as background work (GLASS X3, decision 2).

A rehearsal runs the way real work runs: same queue, same worker, same
loop. That is the fidelity argument, and it is also the practical one —
a 500-signal replay has no business on a request thread.

**Stated consequence, on the record:** the arq worker is a known single
point of failure in this platform. When it is down, scenarios queue and
nothing runs — visible in the shelf as a scenario that never produced a
run, rather than silently swallowed.

The job is a thin entry point; the policy is all in ``runner.py``, the
same shape ``learning/crons.py`` and ``trust/crons.py`` keep.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["twin_scenario_run", "enqueue_scenario_run"]


async def twin_scenario_run(ctx: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    """Arq job: rehearse one scenario.

    Never raises out: a scenario that cannot run is a refusal row the
    shelf can show, and an unexpected fault is logged with the scenario
    named rather than lost in a worker traceback.
    """
    from src.ai.twin.models import TwinScenario
    from src.ai.twin.runner import run_scenario
    from src.common.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            scenario = await db.get(TwinScenario, uuid.UUID(scenario_id))
            if scenario is None:
                return {"scenario_id": scenario_id, "outcome": "not_found"}
            outcome = await run_scenario(
                db, scenario, redis=ctx.get("redis"))
            return {
                "scenario_id": scenario_id,
                "run_id": str(outcome.run.id),
                "grade": outcome.run.grade,
                "outcome": "refused" if outcome.refused else "ran",
            }
    except Exception as exc:  # noqa: BLE001 — one scenario must not kill the worker
        logger.error("twin_scenario_run failed for %s: %s",
                     scenario_id, exc, exc_info=True)
        return {"scenario_id": scenario_id, "outcome": "error", "error": str(exc)}


async def enqueue_scenario_run(redis: Any, scenario_id: uuid.UUID) -> bool:
    """Queue a scenario. Returns whether it was queued.

    Best-effort in the dispatcher's shape: a queue failure is reported to
    the caller (which tells the tenant) rather than raised — but unlike a
    signal, an unqueued scenario has no row to leave PENDING, so the API
    says so directly.
    """
    if redis is None:
        logger.error("no redis — scenario %s not queued", scenario_id)
        return False
    try:
        from arq.connections import ArqRedis

        arq = redis if isinstance(redis, ArqRedis) else ArqRedis(
            getattr(redis, "connection_pool", redis))
        await arq.enqueue_job(
            "twin_scenario_run", str(scenario_id), _queue_name="arq:queue")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("scenario enqueue failed (%s): %s", scenario_id, exc)
        return False
