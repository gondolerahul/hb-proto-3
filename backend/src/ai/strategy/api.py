"""strategy/api.py — the pipeline's HTTP surface (STRAT T8).

Narrow on purpose. The eight Planning objects are ordinary HBS records, so the
**shipped record API already reads and writes them** — re-exposing CRUD here
would create a second write path with its own scoping bugs, which is exactly
the mistake decision 1 avoided by not making these control-plane tables.

What is left is the two things the record API cannot do:

* **`POST /ai/strategy/adopt`** — adopting a Proposition into a Resolution is a
  **T2 certified act** (`enforce_kind`, in the handler body). It is one act
  spanning two records, and the certification belongs to the act rather than to
  either write.
* **`GET /ai/strategy/mandates/{id}/realized`** — predicted-vs-realized, which
  needs the control plane (`kpi_snapshots`) and the tenant plane (the records)
  in one answer and so belongs to neither plane's CRUD.

`GET /ai/strategy/reviews-due` is the third, and it exists because the sweep
emits a signal a surface may have missed.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.guard import enforce_kind
from src.ai.inward_auth.tiers import IntentKind
from src.ai.strategy.pipeline import may_adopt
from src.ai.strategy.realized import compute_realized
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/strategy", tags=["Strategy"])


class AdoptRequest(BaseModel):
    proposition_id: uuid.UUID
    title: str
    decision: str
    adopted_on: Optional[date] = None
    concerns_module: Optional[str] = None


@router.post("/adopt")
async def adopt_proposition(
    body: AdoptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Adopt a tabled Proposition into an active Resolution. **T2 certified.**

    The `enforce_kind` call is in the handler body, not a `Depends` — this
    repo's router tests invoke handlers directly, so a declarative gate would
    be invisible to every test claiming to cover this route and could be
    deleted without failing one (the VG-05 lesson).
    """
    from src.ai.tenant_schema.data_plane import tenant_data_plane
    from src.ai.tenant_schema.record_service import REFUSED, RecordService

    company_id = cast(uuid.UUID, current_user.company_id)

    async with tenant_data_plane.session(company_id) as ts:
        svc = RecordService(ts, company_id)
        proposition = await svc.get(body.proposition_id)
        # Loaded through its company scope *before* the human is asked to prove
        # anything, and 404 on a miss rather than 403 — a probe must not learn
        # that an id exists in another tenant ("scope first, then gate").
        if proposition is None:
            raise HTTPException(status_code=404, detail="Proposition not found")
        data = dict(proposition.data or {})

        verdict = may_adopt(data)
        if not verdict:
            raise HTTPException(status_code=409, detail=verdict.reason)

    await enforce_kind(
        db, current_user, IntentKind.STRATEGY_RESOLUTION,
        command_ref=f"strategy.adopt:{body.proposition_id}",
        command_summary=f"Adopt the proposition {data.get('title') or ''!r} "
                        f"as a resolution",
    )

    async with tenant_data_plane.session(company_id) as ts:
        svc = RecordService(ts, company_id)
        resolution = await svc.create("Resolution", {
            "title": body.title,
            "decision": body.decision,
            "adopted_on": (body.adopted_on or date.today()).isoformat(),
            "concerns_module": body.concerns_module,
            "status": "active",
            "proposition": str(body.proposition_id),
        })
        if resolution.status == REFUSED:
            raise HTTPException(status_code=409, detail=resolution.reason)

        current = await svc.get(body.proposition_id)
        if current is not None:
            await svc.update(body.proposition_id, {"status": "adopted"},
                             expected_version=current.version)
        await ts.commit()

    return {
        "resolution_id": str(resolution.record.id) if resolution.record else None,
        "proposition_id": str(body.proposition_id),
        "status": resolution.status,
    }


@router.get("/mandates/{mandate_id}/realized")
async def read_realized(
    mandate_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Predicted vs realized for one mandate — including "we cannot tell".

    `not_measurable` is a legitimate outcome and comes back with a populated
    `missing`, never a zero.
    """
    from src.ai.tenant_schema.data_plane import tenant_data_plane
    from src.ai.tenant_schema.record_service import RecordService

    company_id = cast(uuid.UUID, current_user.company_id)

    async with tenant_data_plane.session(company_id) as ts:
        svc = RecordService(ts, company_id)
        mandate_row = await svc.get(mandate_id)
        if mandate_row is None:
            raise HTTPException(status_code=404, detail="Mandate not found")
        mandate = dict(mandate_row.data or {})
        target = await _linked(svc, mandate.get("target"))
        resolution = await _linked(svc, mandate.get("resolution"))
        proposition = await _linked(svc, (resolution or {}).get("proposition"))
        forecast = await _forecast_for(svc, mandate.get("target"))

    result = await compute_realized(
        db, company_id, mandate,
        target=target, forecast=forecast, proposition=proposition)

    return {
        "mandate_id": str(mandate_id),
        "kpi_key": result.kpi_key,
        "predicted_value": result.predicted_value,
        "predicted_from": result.predicted_from,
        "realized_value": result.realized_value,
        "measurable": result.measurable,
        "missing": result.missing,
        "verdict": result.verdict,
        "direction": result.direction,
        # Carried beside the verdict deliberately: a missed mandate whose
        # proposition was graded `replay` is a different failure from one that
        # was never tested at all.
        "honesty_grade": result.honesty_grade,
        "twin_run_id": result.twin_run_id,
        "review_fields": result.as_review_fields(),
    }


@router.get("/reviews-due")
async def reviews_due(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Mandates whose review is due. The same read the 02:20 sweep makes.

    Exists because the sweep emits a signal a surface may have missed, and a
    tray that can only be populated by a cron is a tray that is empty after
    every deploy.
    """
    from src.ai.strategy.review_sweep import due_mandates
    from src.ai.tenant_schema.data_plane import tenant_data_plane

    company_id = cast(uuid.UUID, current_user.company_id)
    async with tenant_data_plane.session(company_id) as ts:
        mandates = await due_mandates(ts, company_id)
    return {"mandates": mandates, "count": len(mandates)}


async def _linked(svc: Any, record_id: Any) -> Optional[dict[str, Any]]:
    """Load a referenced record's data, or None. Scoped by `RecordService.get`."""
    if not record_id:
        return None
    try:
        row = await svc.get(uuid.UUID(str(record_id)))
    except (ValueError, AttributeError, TypeError):
        return None
    return dict(row.data or {}) if row is not None else None


async def _forecast_for(svc: Any, target_id: Any) -> Optional[dict[str, Any]]:
    """The most recent Forecast attached to this Target, if any."""
    if not target_id:
        return None
    for row in await svc.list_records("Forecast", limit=100):
        data = dict(row.data or {})
        if str(data.get("target") or "") == str(target_id):
            return data
    return None
