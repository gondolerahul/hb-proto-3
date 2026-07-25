"""learning/harvest.py — the runner that closes the loop (LEARN T6).

T5 built the pieces: grade a run, emit an observation, distil repeated
observations into a candidate, propose a prose change. Nothing called them.
This does.

**A sweep, not a completion hook — and that is a correction to the design.**
The obvious place to grade a run is the moment it finishes, and it is the wrong
place: ``csat_score`` arrives *after* the run ends, when a human comes back and
rates the work. A hook at completion would therefore systematically miss the
single best piece of evidence the platform has, and would grade every run on
the weakest signal available (did it fail?). Harvesting on a delay is what lets
the strongest evidence be counted. It also keeps a new write off the hot loop
path, and off ``core/agent_loop.py``, which is pinned at its line cap.

The window overlaps deliberately (default 48h against a daily cron): a run
finished at 23:59 and rated at 00:30 must not fall between two sweeps. Double
counting is impossible because ``record_outcome`` dedupes on the run id.

Design: docs/product-road-map/increment-6/01_learn.md §5, §7.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.learning.outcomes import (
    classify_outcome,
    distil,
    observed_outcomes,
    record_outcome,
    write_candidate,
)
from src.ai.learning.tuning import emit_proposal, propose_from_candidate

logger = logging.getLogger(__name__)

__all__ = ["HARVEST_WINDOW_HOURS", "DISTIL_WINDOW_DAYS", "harvest_company", "harvest_all"]

#: Overlapping look-back for grading, per the module docstring.
HARVEST_WINDOW_HOURS = 48
#: How far back distillation looks for corroboration. Long enough that three
#: observations mean a pattern, short enough that a fixed problem stops being
#: proposed — a loop that keeps citing last quarter's failures is noise.
DISTIL_WINDOW_DAYS = 30

_FINISHED_RUNS_SQL = text("""
    SELECT er.id            AS run_id,
           er.entity_id     AS entity_id,
           er.status        AS status,
           er.csat_score    AS csat_score,
           COALESCE(
               array_agg(ha.status) FILTER (WHERE ha.status IS NOT NULL),
               '{}'
           )                AS approval_statuses
    FROM execution_runs er
    LEFT JOIN human_approvals ha ON ha.run_id = er.id
    WHERE er.company_id = :company_id
      AND er.entity_id IS NOT NULL
      AND COALESCE(er.completed_at, er.created_at) >= :since
    GROUP BY er.id, er.entity_id, er.status, er.csat_score
""")


async def harvest_company(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    now: datetime | None = None,
    propose: bool = True,
) -> dict[str, Any]:
    """Grade recent runs, distil the window, and propose what has corroborated.

    ``propose=False`` observes and distils without emitting tuning proposals —
    useful for a tenant that wants the learning visible before it wants the
    loop acting. The caller commits.
    """
    at = now or datetime.utcnow()

    rows = (await db.execute(_FINISHED_RUNS_SQL, {
        "company_id": company_id,
        "since": at - timedelta(hours=HARVEST_WINDOW_HOURS),
    })).all()

    observed = 0
    for row in rows:
        outcome = classify_outcome(
            entity_id=row.entity_id,
            run_id=row.run_id,
            status=row.status,
            csat_score=row.csat_score,
            approval_statuses=tuple(row.approval_statuses or ()),
        )
        if outcome is None:
            continue                       # the common case; see outcomes.py
        if await record_outcome(db, company_id=company_id, outcome=outcome) is not None:
            observed += 1

    outcomes = await observed_outcomes(
        db, company_id, since=at - timedelta(days=DISTIL_WINDOW_DAYS))
    candidates = distil(outcomes)

    written = 0
    proposed = 0
    for candidate in candidates:
        if await write_candidate(db, company_id=company_id, candidate=candidate) is not None:
            written += 1
            if propose:
                proposal = propose_from_candidate(candidate)
                if await emit_proposal(
                        db, company_id=company_id, proposal=proposal) is not None:
                    proposed += 1

    return {
        "graded_runs": len(rows),
        "observed": observed,
        "candidates": len(candidates),
        "candidates_written": written,
        "proposals": proposed,
    }


async def harvest_all(db: AsyncSession, *, now: datetime | None = None) -> dict[str, Any]:
    """Harvest every tenant. One tenant's failure must not stop the others."""
    company_ids = [r[0] for r in (await db.execute(
        text("SELECT id FROM companies WHERE type = 'TENANT'"))).all()]

    totals = {"graded_runs": 0, "observed": 0, "candidates": 0,
              "candidates_written": 0, "proposals": 0}
    failed: list[str] = []
    for company_id in company_ids:
        try:
            summary = await harvest_company(db, company_id, now=now)
            for key in totals:
                totals[key] += int(summary[key])
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            failed.append(str(company_id))
            logger.warning("learning harvest failed for company %s: %s", company_id, exc)

    return {**totals, "companies": len(company_ids), "failed": failed}
