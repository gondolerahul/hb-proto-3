"""learning/api.py — `/ai/learning/preferences` (LEARN T8).

The only HTTP surface LEARN has, and it is deliberately narrow: a person reads
and writes their *own* preferences. Everything else this workstream produces —
pooled observations, KPI history, drift — is read through paths that already
exist (`/ai/kpi/history`) or is not read by anyone yet.

Scoping is by the session's user, never by a supplied id. There is no
"preferences for user X" endpoint, so there is no id for a caller to change.

Design: docs/product-road-map/increment-6/01_learn.md §9.
"""
from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.learning.preferences import (
    InvalidPreferenceKey,
    get_preferences,
    observe_density,
    set_preference,
)
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/learning", tags=["Learning"])


class PreferenceWrite(BaseModel):
    key: str
    value: Any


class DensityObservation(BaseModel):
    surface: str
    density: str


@router.get("/preferences")
async def read_preferences(
    prefix: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """This user's preferences, each flagged stated-or-learned."""
    prefs = await get_preferences(
        db, cast(uuid.UUID, current_user.id), prefix=prefix)
    return {"preferences": prefs}


@router.put("/preferences")
async def write_preference(
    body: PreferenceWrite,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """State a preference by hand. Clears any learned value for the key.

    Not a certified action: choosing how dense your own dashboard is confers no
    capability, moves no money and touches no one else's data. Gating it would
    be the kind of ceremony that teaches people to click through ceremonies.
    """
    try:
        row = await set_preference(
            db,
            user_id=cast(uuid.UUID, current_user.id),
            company_id=cast(uuid.UUID, current_user.company_id),
            key=body.key, value=body.value)
    except InvalidPreferenceKey as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await db.commit()
    return {"key": row.key, "value": row.value, "learned": row.learned}


@router.post("/preferences/observe-density")
async def post_density_observation(
    body: DensityObservation,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record that this person chose a density — an observation, not a setting."""
    signal_id = await observe_density(
        db,
        user_id=cast(uuid.UUID, current_user.id),
        company_id=cast(uuid.UUID, current_user.company_id),
        surface=body.surface, density=body.density)
    await db.commit()
    return {"observed": signal_id is not None}
