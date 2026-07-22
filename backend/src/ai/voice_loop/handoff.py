"""voice_loop/handoff.py — agent-to-agent transfer inside a live call (B7).

B7's second question. The naive reading of "warm transfer" is telephony:
bridge the call to another number. That is the wrong mechanism for
agent-to-agent handoff — it involves the carrier, drops the media session, and
loses context at exactly the moment context matters most.

**The call never moves.** What changes is which entity's system prompt, tools
and governance are driving the realtime model. Everything the caller has
already established travels with them:

* the transcript, *summarised* — a replay would consume the realtime context
  window and buy nothing;
* the records already identified, so nobody is asked their invoice number twice;
* their authenticated identity and **tier ceiling**.

That last one carries rather than being recomputed, and the direction matters:
a handoff can only ever *lower* the ceiling, never raise it. If transfer could
raise it, transfer would be an escalation path — ask to be put through to the
agent with more authority, and the spoofed caller gains what the spoofed
number could not give them.

The receiving agent's own governance applies from the moment of handoff; the
originating gateway's does not carry over. Governance belongs to the entity
doing the acting.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.tiers import Tier
from src.ai.voice_loop.models import VoiceHandoff

__all__ = [
    "HandoffContext",
    "TRANSCRIPT_SUMMARY_CHARS",
    "summarise_transcript",
    "record_handoff",
    "latest_handoff",
    "opening_line",
]

#: The gist, not the call. Realtime context windows are small and the
#: receiving agent needs room to actually converse.
TRANSCRIPT_SUMMARY_CHARS = 1200


@dataclass(frozen=True)
class HandoffContext:
    """What the receiving agent is handed."""

    call_sid: str
    to_entity_id: uuid.UUID
    reason: str
    context_summary: str = ""
    resolved_records: list[dict[str, Any]] = field(default_factory=list)
    tier_ceiling: Tier = Tier.T1
    caller_user_id: uuid.UUID | None = None
    from_entity_id: uuid.UUID | None = None


def summarise_transcript(
    turns: list[dict[str, Any]], limit: int = TRANSCRIPT_SUMMARY_CHARS,
) -> str:
    """Condense a call transcript to the tail that still matters.

    Deliberately the *most recent* turns rather than the first: what the
    caller just said is what the receiving agent has to respond to. Older
    context that mattered should already be in ``resolved_records``, which is
    structured and does not compete for the same space.
    """
    lines: list[str] = []
    total = 0
    for turn in reversed(turns):
        speaker = str(turn.get("role") or turn.get("speaker") or "caller")
        text = str(turn.get("content") or turn.get("text") or "").strip()
        if not text:
            continue
        line = f"{speaker}: {text}"
        if total + len(line) > limit:
            break
        lines.append(line)
        total += len(line)
    return "\n".join(reversed(lines))


def _clamp_ceiling(requested: Tier, current: Tier) -> Tier:
    """A handoff may lower the ceiling; it may never raise it."""
    return Tier(min(int(requested), int(current)))


async def record_handoff(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    context: HandoffContext,
    current_ceiling: Tier = Tier.T1,
) -> VoiceHandoff:
    """Persist the handoff and return the row the receiving agent reads."""
    ceiling = _clamp_ceiling(context.tier_ceiling, current_ceiling)

    row = VoiceHandoff(
        company_id=company_id,
        call_sid=context.call_sid,
        from_entity_id=context.from_entity_id,
        to_entity_id=context.to_entity_id,
        reason=context.reason,
        context_summary=context.context_summary[:TRANSCRIPT_SUMMARY_CHARS],
        resolved_records=list(context.resolved_records),
        tier_ceiling=ceiling.name,
        caller_user_id=context.caller_user_id,
    )
    db.add(row)
    await db.flush()
    return row


async def latest_handoff(
    db: AsyncSession, *, company_id: uuid.UUID, call_sid: str,
) -> VoiceHandoff | None:
    """The most recent handoff on a call — the receiving agent's context."""
    return (await db.execute(
        select(VoiceHandoff)
        .where(
            VoiceHandoff.company_id == company_id,
            VoiceHandoff.call_sid == call_sid,
        )
        .order_by(VoiceHandoff.created_at.desc())
        .limit(1)
    )).scalars().first()


def opening_line(handoff: VoiceHandoff) -> str:
    """How the receiving agent opens.

    It must demonstrate continuity in the first sentence. A handoff the caller
    has to repeat themselves through has failed, however cleanly it executed —
    from their side, being transferred and then re-interrogated is worse than
    not being transferred at all.
    """
    records = handoff.resolved_records or []
    if records:
        described = ", ".join(
            str(r.get("label") or r.get("type") or "record") for r in records[:2])
        return (f"Right, I've got {described} in front of me and I'm caught up "
                f"on what you've told my colleague — no need to go over it again.")
    return ("Right, I'm caught up on what you've told my colleague — no need "
            "to go over it again.")
