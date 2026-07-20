"""solo_pack/onboarding_router.py — the setup-wizard step API (Inc 2 ONBOARD).

A thin, company-scoped router over ``solo_pack.onboarding`` — the wizard steps
authored as Pragya's Inc-3 stage APIs (decision 4). The React wizard + admin
surfaces are a separate frontend track; this is the contract they call.
"""
from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.solo_pack.bundles import SOLO_PACK
from src.ai.solo_pack.onboarding import (
    activate_for_company,
    governance_preview,
    list_bundles,
    onboarding_status,
)
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/onboarding", tags=["Solo Pack Onboarding"])


class ActivateRequest(BaseModel):
    bundle_key: str = SOLO_PACK


@router.get("/bundles")
async def get_bundles(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Step 4 picker: the Solo Pack + starter bundles and what each activates now."""
    return list_bundles()


@router.get("/governance-preview")
async def get_governance_preview(
    bundle: str = SOLO_PACK,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Step 3: the A1 governance the chosen bundle would seed, for the owner to confirm."""
    try:
        return governance_preview(bundle)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/activate")
async def post_activate(
    body: ActivateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Step 4: activate the chosen bundle for the tenant (over PACK activation)."""
    try:
        result = await activate_for_company(
            db, cast(uuid.UUID, current_user.company_id), body.bundle_key,
            user_id=cast(uuid.UUID, current_user.id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"activated": True, "bundle": body.bundle_key, "entities": dict(result)}


@router.get("/status")
async def get_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Step 5: what's live for the tenant + where HITL cards land."""
    return await onboarding_status(db, cast(uuid.UUID, current_user.company_id))
