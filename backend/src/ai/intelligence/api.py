"""intelligence/api.py — read-only admin surface for the Intelligence Engine (RTR).

The routing audit trail: which model each routed call chose, why, and over which
signals. Company-scoped through the authenticated user; read-only (decisions are
written by the router, never edited). The fleet catalog + provider opt-in
surfaces are added by FLEET.

Design: increment-5/02_router.md §8.
"""
from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.intelligence.models import CompanyProviderOptin, ModelRegistry, RoutingDecision
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/intelligence", tags=["Intelligence Engine"])


def _decision_out(d: RoutingDecision) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "run_id": str(d.run_id) if d.run_id else None,
        "task_type": d.task_type,
        "model_registry_id": str(d.model_registry_id) if d.model_registry_id else None,
        "reason": d.reason,
        "fallback_used": d.fallback_used,
        "signals": d.signals,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


@router.get("/routing-decisions")
async def list_routing_decisions(
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """The tenant's recent routing decisions — which model, why, newest first."""
    limit = max(1, min(limit, 500))
    rows = (await db.execute(
        select(RoutingDecision)
        .where(RoutingDecision.company_id == current_user.company_id)
        .order_by(RoutingDecision.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [_decision_out(d) for d in rows]


@router.get("/admissions")
async def list_admissions(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """The platform's recent model-admission + canary events (§22.3–.4 audit).
    Fleet-level (not tenant data): which models were admitted/refused and why."""
    from src.ai.signals.models import Signal, SignalTypes
    from src.auth.models import Company

    limit = max(1, min(limit, 200))
    app_id = (await db.execute(
        select(Company.id).where(Company.type == "APP").limit(1)
    )).scalar_one_or_none()
    if app_id is None:
        return []
    rows = (await db.execute(
        select(Signal)
        .where(
            Signal.company_id == app_id,
            Signal.type.in_([
                SignalTypes.MODEL_ADMISSION_EVALUATED,
                SignalTypes.MODEL_CANARY_PROMOTED,
                SignalTypes.MODEL_CANARY_ROLLED_BACK,
            ]),
        )
        .order_by(Signal.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [
        {"type": s.type, "payload": s.payload,
         "created_at": s.created_at.isoformat() if s.created_at else None}
        for s in rows
    ]


# --- FLEET / D5: provider allow-list + the auditable opt-in -----------------

class OptInRequest(BaseModel):
    """Acknowledging the current data-flow disclosure is what makes an opt-in
    informed consent — a stale version is refused."""
    disclosure_version: str


@router.get("/providers")
async def list_providers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Every catalog provider with its D5 posture and this tenant's opt-in state."""
    from src.ai.intelligence.allow_list import CURRENT_DISCLOSURE_VERSION, effective_allow

    rows = (await db.execute(select(ModelRegistry))).scalars().all()
    posture: dict[str, bool] = {}
    for r in rows:
        flow: dict[str, Any] = r.data_flow or {}
        posture[r.provider] = posture.get(r.provider, False) or bool(flow.get("default_allowed"))

    optins = {
        o.provider: o for o in (await db.execute(
            select(CompanyProviderOptin).where(
                CompanyProviderOptin.company_id == current_user.company_id)
        )).scalars().all()
    }
    allowed = await effective_allow(db, cast(UUID, current_user.company_id))

    out: list[dict[str, Any]] = []
    for provider in sorted(posture):
        o = optins.get(provider)
        out.append({
            "provider": provider,
            "default_allowed": posture[provider],
            "effective_allowed": provider in allowed,
            "opted_in": bool(o and o.revoked_at is None),
            "disclosure_version": o.disclosure_version if o else None,
            "current_disclosure_version": CURRENT_DISCLOSURE_VERSION,
            "opted_in_at": o.opted_in_at.isoformat() if o and o.opted_in_at else None,
            "revoked_at": o.revoked_at.isoformat() if o and o.revoked_at else None,
        })
    return out


@router.post("/providers/{provider}/opt-in")
async def opt_in_provider(
    provider: str,
    body: OptInRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Opt this tenant into a non-default-allowed provider (D5). Records who
    accepted which disclosure version, when."""
    from src.ai.intelligence.allow_list import DisclosureError, opt_in

    try:
        row = await opt_in(
            db, cast(UUID, current_user.company_id), provider,
            disclosure_version=body.disclosure_version, user_id=cast(UUID, current_user.id))
    except DisclosureError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"provider": row.provider, "opted_in": True,
            "disclosure_version": row.disclosure_version,
            "opted_in_at": row.opted_in_at.isoformat() if row.opted_in_at else None}


@router.post("/providers/{provider}/revoke")
async def revoke_provider(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Withdraw an opt-in — the provider drops out of routing on the next call."""
    from src.ai.intelligence.allow_list import revoke

    revoked = await revoke(db, cast(UUID, current_user.company_id), provider)
    return {"provider": provider, "revoked": revoked}
