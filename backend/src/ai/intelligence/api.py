"""intelligence/api.py — read-only admin surface for the Intelligence Engine (RTR).

The routing audit trail: which model each routed call chose, why, and over which
signals. Company-scoped through the authenticated user; read-only (decisions are
written by the router, never edited). The fleet catalog + provider opt-in
surfaces are added by FLEET.

Design: increment-5/02_router.md §8.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.intelligence.models import RoutingDecision
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
