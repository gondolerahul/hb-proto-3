"""learning/kpi_snapshot.py — the daily KPI reading, absences included (VG-12).

Increment 6 exists to make "Week 12 > Week 1" *measured* rather than asserted,
and until this job runs there is nothing that records Week 1. `kpi/compute.py`
has always been able to compute a KPI; it computes **now**, from records that
change, so yesterday's value is not recoverable tomorrow. That is the whole
difference between this and the `kpi_daily_rollup` materialised view, which can
always be rebuilt from `execution_runs` — a reader who confuses the two will
conclude this job is redundant.

**Absences are written, not skipped.** A KPI whose prerequisites are unmet
stores `value = NULL`, `measurable = false` and the `missing` list. That row is
history: it is what later lets an answer say *"this became measurable in Week
5, and here is the series since"* instead of showing a chart that silently
starts in the middle. Skipping unmeasurable KPIs would make the series look
cleaner and mean less.

Cost: pure SQL against the tenant plane and the control plane — no LLM tokens,
so no `CostAttribution` and no budget envelope. It does add roughly ten queries
per tenant per day to the idle floor, which belongs as a line in E1's idle-cost
model rather than in a wallet.

Design: docs/product-road-map/increment-6/01_learn.md §6.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = ["snapshot_company", "snapshot_all", "reap_old_snapshots"]


#: A plain unique constraint here (no nullable column in the grain), so ordinary
#: conflict inference works and the day can be re-run in place.
_UPSERT_SQL = text("""
    INSERT INTO kpi_snapshots
        (id, company_id, kpi_key, captured_on, value, measurable, missing,
         baseline_value, sample_size, window_days, unit, created_at)
    VALUES
        (:id, :company_id, :kpi_key, :captured_on, :value, :measurable,
         CAST(:missing AS jsonb), :baseline_value, :sample_size, :window_days,
         :unit, now())
    ON CONFLICT (company_id, kpi_key, captured_on) DO UPDATE SET
        value          = EXCLUDED.value,
        measurable     = EXCLUDED.measurable,
        missing        = EXCLUDED.missing,
        baseline_value = EXCLUDED.baseline_value,
        sample_size    = EXCLUDED.sample_size,
        window_days    = EXCLUDED.window_days,
        unit           = EXCLUDED.unit
""")

#: Every business being measured. `companies` has no `deleted_at`, and APP /
#: PARTNER rows are not businesses with an open pipeline or an invoice ledger,
#: so the scope is tenants. Suspended and read-only tenants are **included** on
#: purpose: a KPI series should not acquire a hole because of a billing state —
#: the series is evidence about the business, and C5's ladder is about payment.
_TENANTS_SQL = text("SELECT id FROM companies WHERE type = 'TENANT'")


async def snapshot_company(
    db: AsyncSession, company_id: uuid.UUID, *, on: date | None = None,
) -> int:
    """Write one day's readings for one company. Returns rows written.

    Idempotent: re-running for the same day overwrites that day rather than
    appending to it, so a retried or manually re-run job cannot double a series.
    """
    import json

    from src.ai.kpi.compute import compute_all

    captured_on = on or datetime.utcnow().date()
    results = await compute_all(db, company_id)

    for result in results:
        await db.execute(_UPSERT_SQL, {
            "id": uuid.uuid4(),
            "company_id": company_id,
            "kpi_key": result.key,
            "captured_on": captured_on,
            # None here is the honest-absence rule reaching storage. It must
            # never be coerced to 0: zero is a measurement ("you are owed
            # nothing") and absence is the lack of one.
            "value": result.value,
            "measurable": result.measurable,
            "missing": json.dumps(result.missing or []),
            "baseline_value": result.baseline_value,
            "sample_size": result.sample_size,
            "window_days": result.window_days,
            "unit": result.unit,
        })
    return len(results)


async def snapshot_all(db: AsyncSession, *, on: date | None = None) -> dict[str, Any]:
    """Snapshot every tenant. One tenant's failure must not lose the rest.

    A tenant whose schema is mid-provision, or whose records are in a state
    `compute_all` chokes on, is logged and skipped — the alternative is a single
    bad tenant costing every other tenant a day of history, and days of history
    are the one thing this workstream cannot get back.
    """
    captured_on = on or datetime.utcnow().date()
    company_ids = [r[0] for r in (await db.execute(_TENANTS_SQL)).all()]

    written = 0
    failed: list[str] = []
    for company_id in company_ids:
        try:
            written += await snapshot_company(db, company_id, on=captured_on)
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            failed.append(str(company_id))
            logger.warning("kpi snapshot failed for company %s: %s", company_id, exc)

    return {
        "captured_on": captured_on.isoformat(),
        "companies": len(company_ids),
        "rows": written,
        "failed": failed,
    }


async def reap_old_snapshots(
    db: AsyncSession, *, retention_days: int | None = None, now: date | None = None,
) -> int:
    """Delete snapshots past the retention window. Returns rows deleted.

    A store with no reaper is an unbounded archive — the lesson
    `voice_deferred_reap` records. Ten KPIs a day is about 3,650 rows per tenant
    per year, so the window is generous rather than tight; the reaper exists to
    bound the table, not to save space.
    """
    from src.common.config import settings

    days = retention_days if retention_days is not None else int(
        getattr(settings, "LEARN_KPI_RETENTION_DAYS", 400))
    cutoff = (now or datetime.utcnow().date()) - timedelta(days=days)
    # RETURNING rather than ``rowcount``: the async ``Result`` is typed without
    # it, and a count the caller can log is worth an explicit projection.
    deleted = (await db.execute(
        text("DELETE FROM kpi_snapshots WHERE captured_on < :cutoff RETURNING id"),
        {"cutoff": cutoff})).all()
    return len(deleted)
