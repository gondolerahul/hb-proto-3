"""kpi/api.py — `/ai/kpi/business`, read by Pragya and the dashboards alike.

One endpoint, one set of numbers. If the dashboard and Pragya computed KPIs
separately they would eventually disagree, and an owner who sees two different
revenue figures stops believing both.
"""
from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.kpi.compute import compute_all
from src.ai.kpi.definitions import KPI_DEFINITIONS
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
