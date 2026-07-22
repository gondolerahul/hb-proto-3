"""pragya/api.py — the console chat surface (`/ai/pragya/*`).

Company-scoped over the shipped JWT session, which is the console channel's
bound identity. The route layer stays deliberately thin: it moves turns in and
out and reports what the conversation layer decided. Every authorisation
question is answered in `runtime.run_turn`, so there is one place a
reviewer has to read to know what Pragya may do.

The SSE endpoint streams the *same* `run_turn` result rather than a second
code path. Streaming a turn that skipped authorisation because it went through
a different function is exactly the sort of divergence that makes a security
review meaningless.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator, cast

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.models import ChannelKind
from src.ai.pragya.runtime import TurnOutcome, TurnRequest, run_turn
from src.ai.pragya.deployment import (
    integration_readiness,
    operating_report,
    propose_blueprint,
)
from src.ai.pragya.advancement import evaluate_eligibility, needs_owner_confirmation
from src.ai.pragya.engagement import (
    advance,
    current_stage,
    engagement_summary,
    get_or_create_engagement,
    recent_turns,
)
from src.ai.pragya.stages import STAGE_INFO, Stage
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/pragya", tags=["Pragya"])


class ChatRequest(BaseModel):
    message: str


def _turn_payload(result: TurnOutcome) -> dict[str, Any]:
    """The wire shape of a completed turn.

    ``needs_step_up`` / ``needs_oob`` are surfaced so the console can open the
    right ceremony — the frontend never re-derives the tier itself.
    """
    return {
        "reply": result.reply,
        "stage": int(result.stage),
        "stage_name": STAGE_INFO[result.stage].name,
        "auth_level": result.auth_level,
        "tier": result.tier,
        "raised_approval": result.raised_approval,
        "needs_step_up": result.needs_step_up,
        "needs_oob": result.needs_oob,
        "command_ref": result.command_ref,
        "command_summary": result.command.summary if result.command else None,
        "cost_usd": result.cost_usd,
    }


@router.get("/engagement")
async def get_engagement(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Where the nine-stage engagement stands — drives the console stage rail."""
    engagement = await get_or_create_engagement(
        db, cast(uuid.UUID, current_user.company_id))
    await db.commit()
    summary = engagement_summary(engagement)
    summary["stages"] = [
        {
            "stage": int(stage),
            "name": info.name,
            "summary": info.summary,
            "scripted": info.scripted,
        }
        for stage, info in STAGE_INFO.items()
    ]
    return summary


@router.post("/advance")
async def post_advance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The owner confirming a stage is done — stages 2 and 5 only.

    An explicit action, deliberately not inferred from the conversation.
    These two stages exist because the owner's *agreement* is the deliverable
    (which assumptions were struck; which priority was chosen), and reading
    agreement out of "yeah, that sounds about right" is precisely the failure
    they guard against.
    """
    engagement = await get_or_create_engagement(
        db, cast(uuid.UUID, current_user.company_id))
    stage = current_stage(engagement)

    if not needs_owner_confirmation(stage):
        raise HTTPException(
            status_code=400,
            detail=f"{STAGE_INFO[stage].name} does not wait on confirmation — "
                   f"it advances once its artifacts are complete")

    eligibility = evaluate_eligibility(stage, engagement.artifacts)
    if not eligibility.eligible:
        # Confirming an unfinished stage would carry a half-formed hypothesis
        # into the configuration that stage 6 builds from.
        raise HTTPException(status_code=409, detail=eligibility.reason)

    await advance(db, engagement, reason="owner confirmed the stage")
    await db.commit()

    moved = current_stage(engagement)
    return {
        "ok": True,
        "stage": int(moved),
        "stage_name": STAGE_INFO[moved].name,
    }


@router.get("/history")
async def get_history(
    limit: int = 40,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    turns = await recent_turns(
        db, cast(uuid.UUID, current_user.company_id), limit=min(limit, 200))
    return [
        {
            "role": t.role,
            "content": t.content,
            "stage": t.stage,
            "tier": t.tier,
            "outcome": t.outcome,
            "at": t.created_at.isoformat(),
        }
        for t in turns
    ]


@router.get("/blueprint")
async def get_blueprint(
    bundle: str = "solo_pack",
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Stage 6: what would activate and where it would stop for a human."""
    return await propose_blueprint(bundle)


@router.get("/readiness")
async def get_readiness(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Stage 7: which channels are connected, and which are still missing."""
    return await integration_readiness(
        db, cast(uuid.UUID, current_user.company_id))


@router.get("/report")
async def get_report(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Stage 9: the standing operational picture, KPIs included.

    KPIs come from the C6 registry, so an unmeasurable one reports what is
    missing rather than a plausible number.
    """
    return await operating_report(db, cast(uuid.UUID, current_user.company_id))


@router.post("/chat")
async def post_chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One turn of conversation."""
    result = await run_turn(db, TurnRequest(
        company_id=cast(uuid.UUID, current_user.company_id),
        user_id=cast(uuid.UUID, current_user.id),
        text=body.message,
        channel_kind=ChannelKind.CONSOLE,
    ))
    await db.commit()
    return _turn_payload(result)


@router.post("/chat/stream")
async def post_chat_stream(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """The same turn, delivered as SSE for the console.

    The turn is resolved first and then streamed. Chunking the reply after the
    fact rather than streaming generation directly keeps a single authorisation
    path — a refusal must never be able to arrive mid-sentence because tokens
    were already on the wire before the tier was checked.
    """
    result = await run_turn(db, TurnRequest(
        company_id=cast(uuid.UUID, current_user.company_id),
        user_id=cast(uuid.UUID, current_user.id),
        text=body.message,
        channel_kind=ChannelKind.CONSOLE,
    ))
    await db.commit()

    async def events() -> AsyncIterator[str]:
        words = result.reply.split(" ")
        for i in range(0, len(words), 8):
            chunk = " ".join(words[i:i + 8])
            yield f"event: token\ndata: {json.dumps({'text': chunk + ' '})}\n\n"
        yield f"event: done\ndata: {json.dumps(_turn_payload(result))}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
