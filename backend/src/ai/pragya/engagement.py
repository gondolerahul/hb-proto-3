"""pragya/engagement.py — reading and moving the engagement.

The thin persistence layer over ``stages.py``'s rules. Everything that decides
*whether* a move is legal lives in that pure module; this one only performs
legal moves and records them.

Artifacts merge rather than replace. A stage that re-runs — and stages 4–6 are
explicitly re-enterable — must not silently erase what an earlier pass
learned, because the re-entry exists to *add* evidence, not to start over.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.pragya.models import PragyaEngagement, PragyaTurn
from src.ai.pragya.stages import (
    STAGE_INFO,
    Stage,
    next_stage,
    validate_transition,
)

__all__ = [
    "get_or_create_engagement",
    "current_stage",
    "set_stage",
    "advance",
    "record_artifacts",
    "record_turn",
    "recent_turns",
    "engagement_summary",
]


async def get_or_create_engagement(
    db: AsyncSession, company_id: uuid.UUID
) -> PragyaEngagement:
    """The company's engagement row, created at stage 1 on first contact."""
    existing = (await db.execute(
        select(PragyaEngagement)
        .where(PragyaEngagement.company_id == company_id).limit(1)
    )).scalars().first()
    if existing is not None:
        return existing

    now = datetime.utcnow()
    engagement = PragyaEngagement(
        company_id=company_id,
        stage=int(Stage.BASELINE),
        artifacts={},
        stage_history=[{"stage": int(Stage.BASELINE), "at": now.isoformat(),
                        "reason": "engagement opened"}],
    )
    db.add(engagement)
    await db.flush()
    return engagement


def current_stage(engagement: PragyaEngagement) -> Stage:
    return Stage(engagement.stage)


async def set_stage(
    db: AsyncSession,
    engagement: PragyaEngagement,
    target: Stage,
    *,
    reason: str,
) -> PragyaEngagement:
    """Move to ``target``, or raise ``TransitionError``.

    The reason is required and recorded. A stage move with no stated cause is
    unexplainable to the owner three months later, and stage 9's reporting is
    supposed to be able to say why the engagement went back to analysis.
    """
    validate_transition(current_stage(engagement), target)
    if target == current_stage(engagement):
        return engagement

    history = list(engagement.stage_history or [])
    history.append({
        "stage": int(target),
        "from": engagement.stage,
        "at": datetime.utcnow().isoformat(),
        "reason": reason,
    })
    engagement.stage = int(target)
    engagement.stage_history = history
    await db.flush()
    return engagement


async def advance(
    db: AsyncSession, engagement: PragyaEngagement, *, reason: str
) -> PragyaEngagement:
    """Move forward exactly one stage. No-op at OPERATE."""
    following = next_stage(current_stage(engagement))
    if following is None:
        return engagement
    return await set_stage(db, engagement, following, reason=reason)


async def record_artifacts(
    db: AsyncSession, engagement: PragyaEngagement, artifacts: dict[str, Any],
) -> PragyaEngagement:
    """Merge artifacts into the bag.

    Shallow merge by key: a re-entered stage overwrites its own artifacts with
    the newer pass but leaves every other stage's alone. Deep-merging would
    make a corrected assumption list impossible to actually correct.
    """
    merged = dict(engagement.artifacts or {})
    merged.update(artifacts)
    engagement.artifacts = merged
    await db.flush()
    return engagement


async def record_turn(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    stage: Stage,
    role: str,
    content: str,
    user_id: uuid.UUID | None = None,
    intent_kind: str | None = None,
    tier: str | None = None,
    outcome: str | None = None,
) -> PragyaTurn:
    """Append a conversation turn."""
    turn = PragyaTurn(
        company_id=company_id, user_id=user_id, stage=int(stage), role=role,
        content=content, intent_kind=intent_kind, tier=tier, outcome=outcome,
    )
    db.add(turn)
    await db.flush()
    return turn


async def recent_turns(
    db: AsyncSession, company_id: uuid.UUID, limit: int = 20,
) -> list[PragyaTurn]:
    """The last ``limit`` turns, oldest first (conversation order)."""
    rows = (await db.execute(
        select(PragyaTurn)
        .where(PragyaTurn.company_id == company_id)
        .order_by(PragyaTurn.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return list(reversed(rows))


def engagement_summary(engagement: PragyaEngagement) -> dict[str, Any]:
    """A display view of where the engagement stands."""
    stage = current_stage(engagement)
    info = STAGE_INFO[stage]
    return {
        "stage": int(stage),
        "stage_name": info.name,
        "stage_summary": info.summary,
        "scripted": info.scripted,
        "artifact_keys": sorted((engagement.artifacts or {}).keys()),
        "history": list(engagement.stage_history or []),
    }
