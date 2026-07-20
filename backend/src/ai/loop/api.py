"""loop/api.py — read-only budget-envelope view (Inc 2 ONBOARD admin surface).

Increment 1 shipped envelopes as data only; ONBOARD's operator UI needs to see
Sheel's envelope — utilization, the protected reserve, and whether it has
downshifted or capped. Company-scoped through the authenticated user; read-only
(the envelope is managed by the Loop heartbeat, not edited by hand).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.loop.envelopes import is_capped, is_downshift, utilization_pct
from src.ai.loop.models import BudgetEnvelope
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/loop", tags=["Loop Budget"])


def envelope_out(env: BudgetEnvelope) -> dict[str, Any]:
    """Serialise an envelope with its derived utilization / downshift / cap state."""
    return {
        "id": str(env.id),
        "entity_id": str(env.entity_id),
        "cycle": env.cycle,
        "envelope_usd": float(env.envelope_usd),
        "reserved_usd": float(env.reserved_usd),
        "spent_usd": float(env.spent_usd),
        "utilization_pct": round(utilization_pct(env), 2),
        "downshift_at_pct": env.downshift_at_pct,
        "downshift": is_downshift(env),
        "capped": is_capped(env),
        "refreshed_at": env.refreshed_at.isoformat() if env.refreshed_at else None,
    }


@router.get("/envelope")
async def get_envelopes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """The tenant's budget envelope(s): utilization, reserve, downshift/cap state."""
    rows = (await db.execute(
        select(BudgetEnvelope).where(BudgetEnvelope.company_id == current_user.company_id)
    )).scalars().all()
    return [envelope_out(env) for env in rows]
