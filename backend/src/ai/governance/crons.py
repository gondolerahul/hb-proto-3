"""governance/crons.py — the scheduled half of C4.

The demotion sweep runs **daily**, not on the 60-second signal sweeper. Its
observation window is seven days, so evaluating it every minute would do the
same work 1,440 times to reach the same answer, and the queries are per-agent
aggregates over ``execution_runs`` — the most expensive thing to do casually.

Daily is also the right *semantic* cadence: demotion is a judgment about a
trend, and a trend does not change between two consecutive minutes.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["demotion_sweep"]


async def demotion_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: evaluate C4 demotion triggers for every active company.

    Idempotent — an agent already demoted for a trigger sits a level lower, so
    the next pass measures the same window and either finds it recovered or
    demotes it again toward A0. It never oscillates upward, because promotion
    is a separate, evidenced path.
    """
    from sqlalchemy import select

    from src.ai.governance.demotion_sweep import apply_demotions
    from src.auth.models import Company
    from src.common.database import AsyncSessionLocal

    demoted = 0
    evaluated = 0
    try:
        async with AsyncSessionLocal() as db:
            company_ids = (await db.execute(
                select(Company.id).where(Company.status == "active")
            )).scalars().all()

            for company_id in company_ids:
                try:
                    verdicts = await apply_demotions(db, company_id)
                except Exception as exc:  # noqa: BLE001
                    # One tenant's bad data must not stop the sweep for the rest.
                    logger.error("demotion sweep failed for %s: %s", company_id, exc)
                    continue
                evaluated += len(verdicts)
                demoted += sum(1 for v in verdicts if v.demote)

            await db.commit()

        result = {"companies": len(company_ids), "agents_evaluated": evaluated,
                  "demoted": demoted}
        if demoted:
            logger.info("demotion sweep: %s", result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("demotion_sweep failed: %s", exc, exc_info=True)
        return {"error": str(exc)}
