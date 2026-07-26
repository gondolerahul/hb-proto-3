"""strategy/review_sweep.py — a mandate's promise to come back (STRAT T6).

`Mandate.review_due` is the only required date in the eight sheets, because the
whole point of the fifth loop step is that the loop closes. Making the date real
needs a sweep, and the sweep has to obey L8 (*silence*): a mandate returns to
its owner **only** at review time or on exception.

**It writes no Review — it asks for one.** A review the platform filled in by
itself is a review nobody read, and the predicted-vs-realized numbers
(`realized.py`) are an input to a human's judgement rather than a substitute
for it.

Daily at 02:20 UTC, after LIB's staleness sweep and before nothing in
particular; the placement matters only in that it is inside the quiet hour.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = ["due_mandates", "sweep_company", "sweep_all"]

#: Statuses a review notice still applies to. `closed` is done and `reviewed`
#: already produced one — chasing either is the kind of noise that teaches
#: people to ignore the tray.
_OPEN_STATUSES = ("issued", "in_flight")


async def due_mandates(
    ts: AsyncSession, company_id: uuid.UUID, *, today: Optional[date] = None,
) -> list[dict[str, Any]]:
    """Mandates whose review is due on or before today and still open.

    "On or before", not "on": a sweep that only matched today's date would drop
    every mandate whose review date fell on a day the worker was down, silently
    and permanently. The same reasoning LIB's rollup lookback window follows.

    Built with the **ORM, not `text()`** — deliberately. Tenant routing is a
    SQLAlchemy `schema_translate_map` (symbolic `tenant` → `t_<hex>`), and a raw
    statement bypasses it: the literal schema name it names does not exist. Any
    tenant-plane query has to go through mapped constructs to be routed at all.
    """
    from src.ai.tenant_schema.models import TenantEntityDef, TenantRecord

    at = today or datetime.utcnow().date()
    due_on = TenantRecord.data["review_due"].astext
    status = TenantRecord.data["status"].astext

    rows = (await ts.execute(
        select(TenantRecord.id, TenantRecord.data)
        .join(TenantEntityDef, TenantEntityDef.id == TenantRecord.entity_def_id)
        .where(
            TenantRecord.company_id == company_id,
            TenantEntityDef.name == "Mandate",
            TenantRecord.deleted_at.is_(None),
            due_on.isnot(None),
            # A date stored as an ISO-8601 string compares correctly
            # lexicographically, which is the one thing that makes this
            # readable without a cast.
            due_on <= at.isoformat(),
            func.coalesce(status, "issued").in_(_OPEN_STATUSES),
        )
    )).all()

    return [{"record_id": str(row[0]), **(row[1] or {})} for row in rows]


async def sweep_company(
    company_id: uuid.UUID, *, today: Optional[date] = None,
) -> dict[str, Any]:
    """Emit `strategy.review_due` for one tenant's due mandates.

    The read is tenant-plane and the emit is control-plane, so they run in
    **separate transactions** — never assume one transaction spans both planes
    (HANDOFF §5).
    """
    from src.ai.tenant_schema.data_plane import tenant_data_plane

    at = today or datetime.utcnow().date()
    try:
        async with tenant_data_plane.session(company_id) as ts:
            mandates = await due_mandates(ts, company_id, today=at)
    except Exception as exc:  # noqa: BLE001
        # A tenant with no schema yet, or a provisioning failure. One tenant
        # must not cost the others their sweep.
        logger.debug("review sweep skipped for company %s: %s", company_id, exc)
        return {"due": 0, "emitted": 0, "skipped": True}

    emitted = 0
    for mandate in mandates:
        if await _emit_review_due(company_id, mandate, at):
            emitted += 1
    return {"due": len(mandates), "emitted": emitted, "skipped": False}


async def _emit_review_due(
    company_id: uuid.UUID, mandate: dict[str, Any], at: date,
) -> bool:
    from src.ai.signals.models import SignalSource, SignalTrust, SignalTypes
    from src.ai.signals.service import emit_signal
    from src.common.database import AsyncSessionLocal

    record_id = mandate.get("record_id")
    try:
        async with AsyncSessionLocal() as cp:
            signal_id = await emit_signal(
                cp, company_id=company_id, source=SignalSource.SCHEDULE,
                type=SignalTypes.STRATEGY_REVIEW_DUE, trust=SignalTrust.INTERNAL,
                payload={
                    "mandate_record_id": record_id,
                    "title": mandate.get("title"),
                    "review_due": mandate.get("review_due"),
                    "owning_process": mandate.get("owning_process"),
                    "status": mandate.get("status"),
                },
                # Deduped per mandate per **day**, not per mandate: an overdue
                # mandate should keep asking, once a day, rather than firing
                # once and going quiet — but a restarted worker must not
                # re-announce what it already announced this morning.
                dedupe_key=f"review-due:{record_id}:{at.isoformat()}",
                object_refs=[str(record_id)] if record_id else None,
            )
            await cp.commit()
            return signal_id is not None
    except Exception as exc:  # noqa: BLE001
        logger.warning("strategy.review_due emit failed for mandate %s: %s",
                       record_id, exc)
        return False


async def sweep_all(*, today: Optional[date] = None) -> dict[str, Any]:
    """Every tenant. Returns totals; a failing tenant is counted, not fatal."""
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as cp:
        company_ids = [r[0] for r in (await cp.execute(
            text("SELECT id FROM companies WHERE type = 'TENANT'"))).all()]

    totals = {"due": 0, "emitted": 0, "skipped": 0}
    for company_id in company_ids:
        summary = await sweep_company(company_id, today=today)
        totals["due"] += int(summary["due"])
        totals["emitted"] += int(summary["emitted"])
        totals["skipped"] += 1 if summary["skipped"] else 0
    return {**totals, "companies": len(company_ids)}
