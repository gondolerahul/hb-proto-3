"""learning/crons.py — the scheduled halves of LEARN.

Thin arq entry points only; the policy lives in ``pooling.py`` and
``kpi_snapshot.py`` so both stay testable without a worker. Same shape as
``trust/crons.py``.

Ordering inside the quiet hour is deliberate. The KPI snapshot runs at **01:25**,
after C5's dunning sweep (01:10) and before C4's demotion sweep (01:40): a
tenant's readings should reflect the billing state it has just entered, and a
demotion decided at 01:40 belongs to tomorrow's series, not to a row written
half-way through the sweep that caused it.

The pooling job runs at **02:10** over *yesterday*, because a day cannot be
aggregated until it is over.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["drift_sweep", "kpi_snapshot_sweep", "learning_harvest_sweep",
           "platform_pooling_sweep"]


async def kpi_snapshot_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: one day's KPI readings for every tenant, absences included.

    Also reaps past the retention window, in the same job — a reaper on its own
    schedule is a reaper that eventually stops being deployed.
    """
    from src.ai.learning.kpi_snapshot import reap_old_snapshots, snapshot_all
    from src.common.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            summary = await snapshot_all(db)
            await db.commit()
            reaped = await reap_old_snapshots(db)
            await db.commit()
            return {**summary, "reaped": reaped}
    except Exception as exc:  # noqa: BLE001
        logger.error("kpi_snapshot_sweep failed: %s", exc)
        return {"error": str(exc)}


async def learning_harvest_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: grade recent runs, distil, propose (LEARN T6).

    Daily rather than at run completion, because CSAT arrives *after* a run
    ends — see ``harvest.py``. Runs at 02:30, after the pooling sweep, so a
    heavy tenant's harvest never delays the platform aggregate.
    """
    from src.ai.learning.harvest import harvest_all
    from src.common.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            summary = await harvest_all(db)
            await db.commit()
            return summary
    except Exception as exc:  # noqa: BLE001
        logger.error("learning_harvest_sweep failed: %s", exc)
        return {"error": str(exc)}


async def drift_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: measure last week's behaviour and emit drift (LEARN T7).

    **Weekly, on Monday, and it must run before C4's daily demotion sweep can
    read it** — which it does, since Monday 01:05 precedes Monday 01:40. Emits
    only; ``governance/demotion`` decides what a drift finding is worth.
    """
    from src.ai.learning.drift import sweep_company
    from src.common.database import AsyncSessionLocal
    from sqlalchemy import text as _text

    totals = {"entities_measured": 0, "drift_findings": 0}
    try:
        async with AsyncSessionLocal() as db:
            company_ids = [r[0] for r in (await db.execute(
                _text("SELECT id FROM companies WHERE type = 'TENANT'"))).all()]
            for company_id in company_ids:
                try:
                    summary = await sweep_company(db, company_id)
                    totals["entities_measured"] += int(summary["entities_measured"])
                    totals["drift_findings"] += int(summary["drift_findings"])
                    await db.commit()
                except Exception as exc:  # noqa: BLE001
                    await db.rollback()
                    logger.warning("drift sweep failed for company %s: %s", company_id, exc)
            return {**totals, "companies": len(company_ids)}
    except Exception as exc:  # noqa: BLE001
        logger.error("drift_sweep failed: %s", exc)
        return {"error": str(exc)}


async def platform_pooling_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: aggregate yesterday's routing decisions into pooled buckets (B10)."""
    from src.ai.learning.pooling import pool_day
    from src.common.database import AsyncSessionLocal

    yesterday = (datetime.utcnow() - timedelta(days=1)).date()
    try:
        async with AsyncSessionLocal() as db:
            summary = await pool_day(db, yesterday)
            await db.commit()
            return summary
    except Exception as exc:  # noqa: BLE001
        logger.error("platform_pooling_sweep failed: %s", exc)
        return {"error": str(exc)}
