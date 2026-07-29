"""talent/router.py — the termination endpoint (DRIVER D7, VG-18).

A **plain governed act** by owner decision (11_driver.md §2.3): stopping
a colleague must never be harder than hiring one, so there is no
``enforce_*`` call here — deliberately, and R5's correspondence test
would fail if one appeared without a certified surface.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.talent.termination import terminate_colleague
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/talent", tags=["Talent"])


@router.get("/colleagues-past")
async def colleagues_past(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """The Gallery's roster (D6 §11): terminated colleagues, from the
    stamp termination wrote — a query, never a new table."""
    from sqlalchemy import select

    from src.ai.orm.entity import HierarchicalEntity

    rows = (
        await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.company_id
                == uuid.UUID(str(current_user.company_id)),
                HierarchicalEntity.status == "DELETED",
                HierarchicalEntity.type == "AGENT",
            ))
    ).scalars().all()
    past: list[dict[str, Any]] = []
    for entity in rows:
        extensions = entity.metadata_extensions or {}
        stamp = extensions.get("termination") if isinstance(extensions, dict) else None
        if not isinstance(stamp, dict):
            continue  # soft-deleted without the ceremony — not a Gallery record
        past.append({
            "entity_id": str(entity.id),
            "name": entity.display_name or entity.name,
            "art_name": entity.name,
            "terminated_at": stamp.get("terminated_at"),
            "runs_total": stamp.get("runs_total"),
            "runs_completed": stamp.get("runs_completed"),
            "memo_artifact_id": stamp.get("memo_artifact_id"),
        })
    return past


@router.post("/colleagues/{entity_id}/terminate")
async def terminate(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    outcome = await terminate_colleague(
        db, uuid.UUID(str(current_user.company_id)), entity_id)
    if outcome.status == "not_found":
        raise HTTPException(404, "Colleague not found")
    if outcome.status == "refused":
        raise HTTPException(409, {
            "error": "termination_refused",
            "reason": outcome.reason,
            "running_run_ids": outcome.running_run_ids,
        })
    assert outcome.summary is not None
    return {
        "status": outcome.status,
        "memo_artifact_id": outcome.memo_artifact_id,
        "summary": {
            "name": outcome.summary.name,
            "runs_total": outcome.summary.runs_total,
            "runs_completed": outcome.summary.runs_completed,
            "pending_approvals": outcome.summary.pending_approvals,
        },
    }
