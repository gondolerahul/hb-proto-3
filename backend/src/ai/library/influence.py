"""library/influence.py — rolling the usage log up, and reaping it (LIB T3).

The raw `retrieval_usages` log is the only unbounded table LIB creates: one row
per chunk per retrieval, written on every agent answer. T2 shipped the writer
without either of these, which is fine for weeks and is not fine forever — the
LIB build notes name T3 as the next thing LIB should build for that reason.

**The ordering guarantee is the load-bearing part.** A reaper and a rollup that
run on independent clocks eventually meet in the wrong order: the worker is
down for a fortnight, the rollup covers only yesterday, and the reaper then
deletes a fortnight of raw rows that were never aggregated. The influence
history has a hole in it and nothing anywhere reports one, because both jobs
did exactly what they were told.

So the reaper here **cannot outrun the rollup**: its cutoff is clamped to the
day after the last rolled-up day, whatever the retention setting says. If the
rollup stops, the log grows — which is a visible, recoverable failure, unlike
silent data loss. That is the trade this module makes on purpose.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "roll_up_day",
    "roll_up_pending",
    "reap_usage_log",
    "influence_for_document",
]


#: The grain has no nullable column, so plain conflict inference works and a
#: day can be re-rolled in place. Re-rolling matters: the lookback window
#: re-aggregates recent days every night, so a row that landed late still
#: reaches its own day's bucket rather than being lost or double-counted.
#:
#: `distinct_entities` counts non-NULL entity ids only — a Pragya turn has no
#: colleague, and counting NULL as a colleague would invent one.
_ROLLUP_SQL = text("""
    INSERT INTO document_influence_daily
        (id, company_id, document_id, day, retrievals, distinct_queries,
         distinct_entities)
    SELECT
        gen_random_uuid(),
        u.company_id,
        u.document_id,
        CAST(u.used_at AS date)          AS day,
        COUNT(*)                         AS retrievals,
        COUNT(DISTINCT u.query_hash)     AS distinct_queries,
        COUNT(DISTINCT u.entity_id)      AS distinct_entities
    FROM retrieval_usages u
    WHERE CAST(u.used_at AS date) = :day
    GROUP BY u.company_id, u.document_id, CAST(u.used_at AS date)
    ON CONFLICT (document_id, day) DO UPDATE SET
        retrievals        = EXCLUDED.retrievals,
        distinct_queries  = EXCLUDED.distinct_queries,
        distinct_entities = EXCLUDED.distinct_entities
    RETURNING id
""")


async def roll_up_day(db: AsyncSession, day: date) -> int:
    """Aggregate one day of the raw log. Returns rows written.

    Idempotent by the upsert, so re-running a day corrects it rather than
    doubling it.

    ``RETURNING id`` rather than ``rowcount``: the async ``Result`` is typed
    without it (the same reason LEARN's reaper projects explicitly), and a
    count the caller can log is worth the extra column.
    """
    return len((await db.execute(_ROLLUP_SQL, {"day": day})).all())


async def roll_up_pending(
    db: AsyncSession, *, lookback_days: int = 7, now: Optional[date] = None,
) -> dict[str, Any]:
    """Roll up every day in the lookback window, ending yesterday.

    A window rather than a single day for two reasons, both of which have bitten
    other sweeps in this codebase: a worker that missed a night would otherwise
    lose that night permanently, and a row written just before midnight against
    a slightly different clock belongs to a day the "yesterday only" job has
    already passed.

    Today is deliberately excluded — a day cannot be aggregated until it is
    over, the same rule LEARN's pooling sweep follows.
    """
    today = now or datetime.utcnow().date()
    days = [today - timedelta(days=offset)
            for offset in range(lookback_days, 0, -1)]

    written = 0
    for day in days:
        written += await roll_up_day(db, day)
    return {"days": len(days), "rows": written,
            "through": days[-1].isoformat() if days else None}


async def _last_rolled_up_day(db: AsyncSession) -> Optional[date]:
    row = (await db.execute(
        text("SELECT MAX(day) FROM document_influence_daily"))).scalar()
    return row if isinstance(row, date) else None


async def reap_usage_log(
    db: AsyncSession, *, retention_days: Optional[int] = None,
    now: Optional[date] = None,
) -> dict[str, Any]:
    """Delete raw usage rows past retention — but never past the rollup.

    Returns the count and the cutoff actually used, because the two can differ
    from what was asked for and a caller logging only the count would never
    see it.

    **The clamp is the point** (see the module docstring). If the rollup has
    not run, `last_rolled_up` is behind the retention cutoff and the reaper
    deletes less than it was asked to — or, when nothing has ever been rolled
    up, nothing at all.
    """
    from src.common.config import settings

    days = retention_days if retention_days is not None else int(
        getattr(settings, "LIB_USAGE_RETENTION_DAYS", 30))
    today = now or datetime.utcnow().date()
    retention_cutoff = today - timedelta(days=days)

    last_rolled = await _last_rolled_up_day(db)
    if last_rolled is None:
        # Nothing has ever been aggregated, so every raw row is the only copy
        # of itself. Refusing here is what makes the guarantee unconditional.
        return {"deleted": 0, "cutoff": None, "clamped": True,
                "reason": "no rollup has run; refusing to reap the only copy"}

    rollup_cutoff = last_rolled + timedelta(days=1)
    cutoff = min(retention_cutoff, rollup_cutoff)
    clamped = cutoff < retention_cutoff

    deleted = (await db.execute(
        text("DELETE FROM retrieval_usages WHERE used_at < :cutoff RETURNING id"),
        {"cutoff": datetime.combine(cutoff, datetime.min.time())})).all()

    if clamped:
        # Worth a warning rather than a debug line: the log is growing past its
        # retention window and the cause is upstream, in the rollup.
        logger.warning(
            "Usage-log reaper clamped to %s (retention wanted %s) — the rollup "
            "is behind; raw rows are being kept rather than lost.",
            cutoff, retention_cutoff)

    return {"deleted": len(deleted), "cutoff": cutoff.isoformat(),
            "clamped": clamped}


async def influence_for_document(
    db: AsyncSession, company_id: Any, document_id: Any, *, days: int = 30,
    now: Optional[date] = None,
) -> dict[str, Any]:
    """The influence panel's read: what this document did over a window.

    Scoped by company *and* document. Passing the company is not belt-and-
    braces — it is the scoping rule, and a read that took only a document id
    would answer for another tenant's document exactly as SEGA T0's tool
    registry did.
    """
    today = now or datetime.utcnow().date()
    since = today - timedelta(days=days)
    row = (await db.execute(text("""
        SELECT COALESCE(SUM(retrievals), 0)        AS retrievals,
               COALESCE(SUM(distinct_queries), 0)  AS queries,
               COALESCE(MAX(distinct_entities), 0) AS peak_entities,
               COUNT(*)                            AS active_days
        FROM document_influence_daily
        WHERE company_id = :company_id AND document_id = :document_id
          AND day >= :since
    """), {"company_id": str(company_id), "document_id": str(document_id),
           "since": since})).mappings().first()

    return {
        "document_id": str(document_id),
        "window_days": days,
        "retrievals": int(row["retrievals"]) if row else 0,
        # Summed across days, so a question asked on two days counts twice.
        # That is the honest reading of "questions answered this month" and it
        # is stated here because the alternative (distinct across the window)
        # is not derivable from a daily rollup at all.
        "questions_answered": int(row["queries"]) if row else 0,
        "peak_distinct_colleagues": int(row["peak_entities"]) if row else 0,
        "active_days": int(row["active_days"]) if row else 0,
    }
