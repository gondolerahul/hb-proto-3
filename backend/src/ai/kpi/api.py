"""kpi/api.py — `/ai/kpi/*`, read by Pragya and the dashboards alike.

One endpoint per question, one set of numbers. If the dashboard and Pragya
computed KPIs separately they would eventually disagree, and an owner who sees
two different revenue figures stops believing both.

`/business` answers *what is true now*, computed from records. `/history`
(Inc-6 LEARN) answers *what was true then*, read from `kpi_snapshots` — and it
has to be a different source, because the records a KPI is computed from change
and yesterday's value cannot be recovered from today's data. Four consumers read
`/history`: Pragya's stage 9, TWIN's forecast engine, STRAT's mandate reviews
and (in Increment 7) the plinth trends and Seasons timeline.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.kpi.compute import compute_all
from src.ai.kpi.definitions import KPI_DEFINITIONS, definition_for, kpi_keys
from src.ai.learning.models import KpiSnapshot
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/kpi", tags=["KPIs"])


@router.get("/definitions")
async def get_definitions(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """The registry itself — formula, prerequisites, baseline, per KPI."""
    return [
        {
            "key": d.key,
            "display_name": d.display_name,
            "formula": d.formula,
            "required_objects": list(d.required_objects),
            "required_fields": list(d.required_fields),
            "baseline": d.baseline,
            "unit": d.unit,
            "cadence": d.cadence.value,
            "captured_today": d.captured_today,
            "owner_process": d.owner_process,
            "why_it_matters": d.why_it_matters,
            "caveat": d.caveat,
        }
        for d in KPI_DEFINITIONS
    ]


@router.get("/business")
async def get_business_kpis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Current readings. Unmeasurable KPIs say what is missing, never zero."""
    results = await compute_all(db, cast(uuid.UUID, current_user.company_id))
    return {
        "kpis": [r.as_dict() for r in results],
        "measurable_count": sum(1 for r in results if r.measurable),
        "total_count": len(results),
    }


#: The retention window (LEARN §6.3). A range wider than the store can hold is
#: a request that would silently return a truncated series, so it is refused.
_MAX_RANGE_DAYS = 400
_DEFAULT_RANGE_DAYS = 90


@router.get("/history")
async def get_kpi_history(
    keys: str | None = Query(None, description="Comma-separated KPI keys; omit for all"),
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The recorded series — including the days a KPI could not be measured.

    Absences are returned, not filtered out. A caller drawing a trend line
    should be able to see that the line *starts* somewhere, and `first_measurable_on`
    says when: "this became measurable in Week 5" is a different and more honest
    statement than a chart that quietly begins in the middle.

    Empty is the correct answer before the snapshot job has run — there is no
    backfill, by construction (LEARN §6.3), so a young tenant has a short series
    and that is the truth about what is known.
    """
    to_day = to_date or date.today()
    from_day = from_date or (to_day - timedelta(days=_DEFAULT_RANGE_DAYS))

    if from_day > to_day:
        raise HTTPException(status_code=400, detail="`from` is after `to`")
    if (to_day - from_day).days > _MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"range exceeds the {_MAX_RANGE_DAYS}-day retention window; "
                   "a wider range would return a silently truncated series")

    known = set(kpi_keys())
    if keys:
        wanted = [k.strip() for k in keys.split(",") if k.strip()]
        unknown = [k for k in wanted if k not in known]
        if unknown:
            # Naming an unknown key is a caller bug, and returning an empty
            # series for it would look identical to "no data yet".
            raise HTTPException(status_code=400, detail=f"unknown KPI keys: {unknown}")
    else:
        wanted = list(kpi_keys())

    rows = (await db.execute(
        select(KpiSnapshot)
        .where(
            KpiSnapshot.company_id == cast(uuid.UUID, current_user.company_id),
            KpiSnapshot.kpi_key.in_(wanted),
            KpiSnapshot.captured_on >= from_day,
            KpiSnapshot.captured_on <= to_day,
        )
        .order_by(KpiSnapshot.kpi_key, KpiSnapshot.captured_on)
    )).scalars().all()

    by_key: dict[str, list[KpiSnapshot]] = {k: [] for k in wanted}
    for row in rows:
        by_key[row.kpi_key].append(row)

    series = []
    for key in wanted:
        points = by_key[key]
        definition = definition_for(key)
        measurable_days = [p.captured_on for p in points if p.measurable]
        series.append({
            "key": key,
            "display_name": definition.display_name if definition else key,
            "unit": points[-1].unit if points else (definition.unit if definition else "count"),
            # None means "never measurable in this window" — not "never".
            "first_measurable_on": (measurable_days[0].isoformat()
                                    if measurable_days else None),
            "measurable_days": len(measurable_days),
            "points": [
                {
                    "captured_on": p.captured_on.isoformat(),
                    "value": float(p.value) if p.value is not None else None,
                    "measurable": p.measurable,
                    "missing": p.missing or [],
                    "baseline_value": (float(p.baseline_value)
                                       if p.baseline_value is not None else None),
                    "sample_size": p.sample_size,
                }
                for p in points
            ],
        })

    return {"from": from_day.isoformat(), "to": to_day.isoformat(), "series": series}
