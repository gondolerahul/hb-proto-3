"""twin/forecast.py — projecting a KPI forward, or refusing to (TWIN T7).

Reads LEARN's ``kpi_snapshots``. Two projection methods, both declared with the
result so the surface can render *how* the number was arrived at next to the
number itself:

* **seasonal-naive** — when there is at least a full week, the value repeats
  the same weekday. Business KPIs are weekly-seasonal far more often than they
  are linear, and a Monday is a better predictor of next Monday than a trend
  line through both.
* **linear** — least-squares over the series otherwise.

**A short series is refused, not widened.** Below ``TWIN_MIN_SERIES_POINTS``
this returns a refusal rather than a projection with an interval nobody reads.
A forecast the day after LEARN ships is `unknown`, and it should be — that is
the increment's own coupling made visible rather than papered over.

**The refusal says why.** "Not enough history" is a message people file under
"broken"; "8 daily points needed, 3 recorded since 2026-07-22" is one they
file under "ask me again next week". The design's honest-risks table names this
specifically, so the reason string is part of the deliverable.

``value IS NULL`` rows are **absences, not zeroes** (LEARN's C6 rule surviving
persistence). They are excluded from the series rather than read as 0 — a KPI
that was unmeasurable for a week is not a KPI that was zero for a week, and
treating it as zero would forecast a collapse that never happened.
"""
from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.twin.grading import Grade
from src.common.config import settings

__all__ = ["Projection", "Point", "project", "forecast_kpi"]

#: A full week, below which seasonal-naive has nothing to repeat.
_SEASON = 7


@dataclass(frozen=True)
class Point:
    on: date
    value: float


@dataclass(frozen=True)
class Projection:
    """A projection, or a refusal. Never both, and never neither."""

    value: Optional[float]
    low: Optional[float]
    high: Optional[float]
    method: str
    grade: str
    points_used: int
    refusal_reason: Optional[str] = None

    @property
    def refused(self) -> bool:
        return self.refusal_reason is not None


def _refuse(reason: str, points: int) -> Projection:
    return Projection(None, None, None, "none", Grade.UNKNOWN, points, reason)


def project(
    series: Sequence[Point], *, horizon_days: int = 7,
    min_points: Optional[int] = None,
) -> Projection:
    """Project a measured series forward. Pure — no IO, so it is fully testable.

    ``horizon_days`` is how far ahead; the interval widens with it, because a
    projection three weeks out is not as good as one three days out and the
    number should say so.
    """
    floor = min_points if min_points is not None else settings.TWIN_MIN_SERIES_POINTS
    usable = [p for p in series if p.value is not None]
    count = len(usable)

    if count < floor:
        oldest = min((p.on for p in usable), default=None)
        since = f" since {oldest.isoformat()}" if oldest else ""
        return _refuse(
            f"a forecast needs {floor} daily points; {count} recorded{since}. "
            f"The series starts the day KPI history began — there is no "
            f"backfill, by construction — so this becomes available with time "
            f"rather than with a setting.",
            count,
        )
    if horizon_days < 1:
        return _refuse("horizon_days must be at least 1", count)

    ordered = sorted(usable, key=lambda p: p.on)
    values = [p.value for p in ordered]

    if count >= _SEASON * 2:
        # Seasonal-naive **with drift**: the same weekday one season back, plus
        # the average week-on-week change.
        #
        # The drift term is not a refinement, it is a correctness fix. Plain
        # seasonal-naive repeats last week's value, so on any trending series it
        # projects the past and calls it the future — a business growing 10% a
        # week would be forecast flat, forever. The week-on-week differences are
        # already computed here as the residuals, and their mean is exactly the
        # drift, so this costs nothing and removes a systematic bias.
        offset = (horizon_days - 1) % _SEASON
        seasonal_differences = [
            values[i] - values[i - _SEASON] for i in range(_SEASON, count)
        ]
        drift = statistics.fmean(seasonal_differences) if seasonal_differences else 0.0
        point = values[-_SEASON + offset] + drift
        # The interval is the spread *around* the drift, not around zero:
        # a series climbing steadily by 7 a week is highly predictable, and an
        # interval built from the raw differences would call it wildly noisy.
        residuals = [d - drift for d in seasonal_differences]
        method = f"seasonal-naive with drift (weekly) over {count} daily points"
    else:
        # Least squares on the index.
        xs = list(range(count))
        mean_x = statistics.fmean(xs)
        mean_y = statistics.fmean(values)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        slope = (
            sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denominator
            if denominator
            else 0.0
        )
        intercept = mean_y - slope * mean_x
        point = intercept + slope * (count - 1 + horizon_days)
        residuals = [y - (intercept + slope * x) for x, y in zip(xs, values)]
        method = f"linear least-squares over {count} daily points"

    # A prediction interval that widens with the horizon: sqrt(h) is the random
    # walk's own growth, and claiming a constant band would overstate a
    # three-week projection exactly as much as it understates a one-day one.
    spread = statistics.pstdev(residuals) if len(residuals) > 1 else 0.0
    margin = 1.96 * spread * (horizon_days ** 0.5)

    return Projection(
        value=float(point),
        low=float(point - margin),
        high=float(point + margin),
        method=method,
        grade=Grade.FORECAST,
        points_used=count,
    )


async def forecast_kpi(
    db: AsyncSession, company_id: uuid.UUID, kpi_key: str, *,
    horizon_days: int = 7, lookback_days: int = 90,
) -> Projection:
    """Project one KPI for one company from its recorded history."""
    from datetime import timedelta

    from src.ai.learning.models import KpiSnapshot

    since = date.today() - timedelta(days=lookback_days)
    rows = (await db.execute(
        select(KpiSnapshot.captured_on, KpiSnapshot.value)
        .where(
            KpiSnapshot.company_id == company_id,
            KpiSnapshot.kpi_key == kpi_key,
            KpiSnapshot.captured_on >= since,
        )
        .order_by(KpiSnapshot.captured_on)
    )).all()

    # NULL is "not measurable", never zero — dropped rather than coerced.
    series = [Point(on, float(value)) for on, value in rows if value is not None]
    return project(series, horizon_days=horizon_days)
