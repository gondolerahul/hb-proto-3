"""strategy/realized.py — did that decision work? (STRAT T7)

The forward walk: `Resolution → Mandate → Review → the measured KPI series`.
This module computes the Review's numbers; a human writes the Review.

**Rule 4 is the one that matters.** `realized_value` is `None` with
`measurable=False` and `missing` populated whenever the KPI cannot be read —
never zero, never a guess. C6's honest-absence rule (`kpi/compute.py`) exists
because *a fabricated KPI prompts a decision while a missing one prompts a
question*, and a strategy review is precisely where a fabricated number would
do the most damage. `not_measurable` is a first-class verdict.

It will also be the **most common** verdict for the first months after deploy,
because `kpi_snapshots` began collecting on the day LEARN shipped with no
backfill by construction. That is honest and it will still look like a broken
feature, which is why `missing` says *why* rather than only *that*.

**The originating grade travels with the verdict.** "This bet was graded
`forecast` when it was made" is what separates an honest track record from a
flattering one — a missed mandate whose proposition was graded `replay` is a
different failure from one that was never tested at all.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "Verdict",
    "RealizedResult",
    "decide_verdict",
    "compute_realized",
]


class Verdict:
    ON_TRACK = "on_track"
    OFF_TRACK = "off_track"
    MET = "met"
    MISSED = "missed"
    NOT_MEASURABLE = "not_measurable"


@dataclass(frozen=True)
class RealizedResult:
    """What a Review should record. Shaped like `KpiResult` on purpose."""

    kpi_key: Optional[str] = None
    predicted_value: Optional[float] = None
    realized_value: Optional[float] = None
    measurable: bool = False
    #: Why it could not be read, in words a person can act on.
    missing: list[str] = field(default_factory=list)
    verdict: str = Verdict.NOT_MEASURABLE
    direction: Optional[str] = None
    #: The originating proposition's grade, carried through unchanged.
    honesty_grade: Optional[str] = None
    twin_run_id: Optional[str] = None
    #: Where `predicted_value` came from — "target" or "forecast".
    predicted_from: Optional[str] = None

    def as_review_fields(self) -> dict[str, Any]:
        """The subset a `Review` record actually stores."""
        return {
            "predicted_value": self.predicted_value,
            "realized_value": self.realized_value,
            "measurable": self.measurable,
            "missing": "; ".join(self.missing),
            "verdict": self.verdict,
        }


def decide_verdict(
    *, predicted: Optional[float], realized: Optional[float],
    direction: Optional[str], window_closed: bool,
) -> str:
    """Met / missed / on-track / off-track / not-measurable.

    `direction` is load-bearing and not decoration: for a days-outstanding or
    time-to-respond style metric, improving means going **down**, so a
    comparison that assumed "higher is better" would report a genuine success
    as a miss. `hold` is neither — it asks the number to stay where it is, so
    nothing here can call it met and the honest answer is on/off track against
    the target as a level.

    No KPI key is named anywhere in this package, deliberately: `direction`
    comes off the tenant's own Target record and the key is a value flowing
    through, never a literal in platform code (LEARN §7 mechanism 1).
    """
    if realized is None or predicted is None:
        return Verdict.NOT_MEASURABLE

    if direction == "decrease":
        hit = realized <= predicted
    elif direction == "hold":
        # No "met" for a hold — holding is a state you are still in, not one
        # you reach. Reporting `met` would claim a finish line that does not
        # exist.
        return Verdict.ON_TRACK if realized == predicted else Verdict.OFF_TRACK
    else:
        hit = realized >= predicted

    if window_closed:
        return Verdict.MET if hit else Verdict.MISSED
    return Verdict.ON_TRACK if hit else Verdict.OFF_TRACK


async def _kpi_at(
    db: AsyncSession, company_id: uuid.UUID, kpi_key: str, on_or_before: date,
) -> tuple[Optional[float], list[str]]:
    """The KPI reading nearest on or before a date, from LEARN's history.

    Returns `(value, missing_reasons)`. A snapshot that recorded an *absence*
    (LEARN stores unmeasurable KPIs as rows with `measurable=False` rather than
    skipping them) is reported as absent with its own reason — which is the
    whole reason that decision was taken: "we looked and could not measure" and
    "we never looked" are different facts.
    """
    from src.ai.learning.models import KpiSnapshot

    row = (await db.execute(
        select(KpiSnapshot)
        .where(KpiSnapshot.company_id == company_id,
               KpiSnapshot.kpi_key == kpi_key,
               KpiSnapshot.captured_on <= on_or_before)
        .order_by(KpiSnapshot.captured_on.desc())
        .limit(1)
    )).scalars().first()

    if row is None:
        return None, [
            f"no KPI snapshot for {kpi_key!r} on or before "
            f"{on_or_before.isoformat()} — the history starts the day LEARN "
            "deployed and is not backfilled"]
    if not row.measurable or row.value is None:
        reasons = list(row.missing or []) if isinstance(row.missing, list) else []
        return None, reasons or [
            f"{kpi_key!r} was recorded as unmeasurable on "
            f"{row.captured_on.isoformat()}"]
    return float(row.value), []


async def compute_realized(
    db: AsyncSession, company_id: uuid.UUID, mandate: dict[str, Any], *,
    target: Optional[dict[str, Any]] = None,
    forecast: Optional[dict[str, Any]] = None,
    proposition: Optional[dict[str, Any]] = None,
    today: Optional[date] = None,
) -> RealizedResult:
    """Predicted vs realized for one mandate, honest about what it cannot read.

    The records are passed in rather than fetched: they live in the tenant
    plane and `db` is the control plane (that is where `kpi_snapshots` is), and
    pretending one session could reach both is how cross-plane bugs start.
    """
    at = today or datetime.utcnow().date()
    missing: list[str] = []

    if not target:
        return RealizedResult(
            missing=["this mandate names no Target, so there is no number to "
                     "compare against"],
            verdict=Verdict.NOT_MEASURABLE,
            honesty_grade=(proposition or {}).get("honesty_grade"),
            twin_run_id=(proposition or {}).get("twin_run_id"),
        )

    kpi_key = target.get("kpi_key")
    direction = target.get("direction")

    # Rule 3: the Forecast's value where one is attached, else the Target's.
    # A forecast is what the business actually expected; the target is what it
    # asked for, and reviewing against the ask when a forecast exists would
    # grade the plan rather than the decision.
    predicted, predicted_from = _predicted(target, forecast)
    if predicted is None:
        missing.append("neither the Target nor the Forecast carries a value")

    if not kpi_key:
        missing.append("the Target names no kpi_key, so nothing can be read")
        return RealizedResult(
            predicted_value=predicted, predicted_from=predicted_from,
            missing=missing, verdict=Verdict.NOT_MEASURABLE, direction=direction,
            honesty_grade=(proposition or {}).get("honesty_grade"),
            twin_run_id=(proposition or {}).get("twin_run_id"))

    review_due = _as_date(mandate.get("review_due"))
    read_at = min(review_due, at) if review_due else at
    realized, kpi_missing = await _kpi_at(db, company_id, kpi_key, read_at)
    missing.extend(kpi_missing)

    window_closed = bool(review_due and at >= review_due)
    verdict = decide_verdict(predicted=predicted, realized=realized,
                             direction=direction, window_closed=window_closed)

    return RealizedResult(
        kpi_key=kpi_key,
        predicted_value=predicted,
        predicted_from=predicted_from,
        realized_value=realized,
        measurable=realized is not None,
        missing=missing,
        verdict=verdict,
        direction=direction,
        honesty_grade=(proposition or {}).get("honesty_grade"),
        twin_run_id=(proposition or {}).get("twin_run_id"),
    )


def _predicted(
    target: dict[str, Any], forecast: Optional[dict[str, Any]],
) -> tuple[Optional[float], Optional[str]]:
    if forecast and forecast.get("value") is not None:
        return _as_float(forecast["value"]), "forecast"
    if target.get("target_value") is not None:
        return _as_float(target["target_value"]), "target"
    return None, None


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None
