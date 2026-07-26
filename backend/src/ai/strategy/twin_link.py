"""strategy/twin_link.py — a proposition tried in the Glasshouse (STRAT T9).

The one seam between the strategy pipeline and TWIN, and it is deliberately
one-directional: STRAT **reads** a twin run's grade and copies it onto the
Proposition. TWIN knows nothing about Planning.

**The grade is copied, never composed.** `grading.py` computes a grade and no
function or model in TWIN accepts one — asserted there by reflection so adding
a setter fails a test rather than quietly softening L6. This module must not
become the back door around that, so it reads the run and refuses anything it
cannot read: a proposition whose grade could not be established stays
`untested`, which is the honest state and the default.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = ["GradeStamp", "read_grade", "stamp_fields"]

UNTESTED = "untested"


@dataclass(frozen=True)
class GradeStamp:
    """What a Glasshouse run contributes to a Proposition."""

    honesty_grade: str
    twin_run_id: Optional[str]
    #: How the number was arrived at, in TWIN's own words — "replayed 63
    #: signals", "seasonal-naive over 14 daily points". Carried so a review can
    #: say *why* a grade is what it is rather than only what it is.
    method: Optional[str] = None

    @property
    def is_tested(self) -> bool:
        return self.honesty_grade != UNTESTED


async def read_grade(
    db: AsyncSession, company_id: uuid.UUID, twin_run_id: Any,
) -> GradeStamp:
    """Read a twin run's grade, scoped by company.

    Scoped because a grade is an assertion about *this* tenant's business, and
    borrowing another tenant's run id would attach their evidence to your
    decision — a cross-tenant read of exactly the shape VG-05 and SEGA T0 both
    turned out to be.

    An unreadable or missing run yields `untested`, not an exception: a
    proposition that could not be graded is honestly ungraded, and failing the
    whole write would make the Glasshouse a hazard rather than an aid.
    """
    from src.ai.twin.models import TwinRun

    run_uuid = _as_uuid(twin_run_id)
    if run_uuid is None:
        return GradeStamp(UNTESTED, None)

    run = (await db.execute(
        select(TwinRun).where(TwinRun.id == run_uuid,
                              TwinRun.company_id == company_id)
    )).scalars().first()

    if run is None:
        logger.debug("twin run %s not found for company %s", twin_run_id, company_id)
        return GradeStamp(UNTESTED, None)
    return GradeStamp(str(run.grade), str(run.id), run.method)


async def stamp_fields(
    db: AsyncSession, company_id: uuid.UUID, twin_run_id: Any,
) -> dict[str, Any]:
    """The Proposition fields a Glasshouse run sets. Empty when ungraded.

    Returns `{}` rather than `{"honesty_grade": "untested"}` for an unreadable
    run, so a failed lookup never *overwrites* a grade the proposition already
    legitimately carries.
    """
    stamp = await read_grade(db, company_id, twin_run_id)
    if not stamp.is_tested:
        return {}
    return {"honesty_grade": stamp.honesty_grade, "twin_run_id": stamp.twin_run_id}


def _as_uuid(value: Any) -> Optional[uuid.UUID]:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None
