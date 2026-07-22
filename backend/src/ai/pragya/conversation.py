"""pragya/conversation.py — one turn of the engagement.

The orchestration seam. A turn does four things in a fixed order, and the
order is the safety property:

1. **Resolve the session** (AUTH). An unbound channel gets a conversation, not
   an account — she is helpful about the product and declines everything
   tenant-specific.
2. **Classify the intent** *before* generating any prose, so that what she
   says is constrained by what she is allowed to do rather than the reverse.
   Generating first invites a model that has already promised to pause a
   process to then discover it may not.
3. **Authorise** via ``require_tier``, at execution time.
4. **Generate** the reply, told plainly what it may and may not claim.

Execution of the command itself is separate (``commands.py``): a turn decides
*whether*, the executor decides *how*.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.models import AccountManagerSession, ChannelKind
from src.ai.inward_auth.sessions import AuthDecision, get_or_create_session, require_tier
from src.ai.inward_auth.tiers import Tier
from src.ai.llm.router import LLMRouter
from src.ai.pragya.engagement import (
    current_stage,
    get_or_create_engagement,
    recent_turns,
    record_turn,
)
from src.ai.pragya.commands import execute_command
from src.ai.pragya.intents import INTENT_SCHEMA, ExtractedCommand, classify_turn
from src.ai.pragya.models import PragyaEngagement
from src.ai.pragya.scripts import script_for_stage
from src.ai.pragya.stages import STAGE_INFO, Stage

logger = logging.getLogger(__name__)

__all__ = ["TurnResult", "handle_turn", "UNBOUND_REFUSAL", "stage_system_prompt"]


#: What an unresolved channel gets. Deliberately warm and useless: it must not
#: confirm whether the company exists, who the owner is, or what is configured
#: — an unauthenticated caller learning "yes, that's the right number for
#: Acme's account manager" has already learned something worth having.
UNBOUND_REFUSAL = (
    "I can't discuss a specific account with this number — I've no way to know "
    "it's really you, and I'd rather be careful than convenient. If it's your "
    "account, you can register this channel from Settings → Security in the "
    "web console, and then we can pick this up properly. Happy to answer "
    "general questions in the meantime."
)


@dataclass
class TurnResult:
    """Everything one turn produced."""

    reply: str
    stage: Stage
    auth_level: str
    tier: str | None = None
    command: ExtractedCommand | None = None
    decision: AuthDecision | None = None
    executed: bool = False
    #: Set when the console must open a ceremony before this can proceed.
    needs_step_up: bool = False
    needs_oob: bool = False
    command_ref: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)


def stage_system_prompt(stage: Stage, engagement: PragyaEngagement) -> str:
    """The prompt for the current stage: its script, or the operating brief.

    Stages 6–9 have no script by design — they are mechanical — so they get a
    short standing brief instead, carrying the same global guardrails the
    scripted stages assemble.
    """
    script = script_for_stage(int(stage))
    if script is not None:
        return script.render_prompt()

    info = STAGE_INFO[stage]
    from src.ai.pragya.scripts import GLOBAL_GUARDRAILS

    rules = "\n".join(f"- {rule}" for rule in GLOBAL_GUARDRAILS)
    known = ", ".join(sorted((engagement.artifacts or {}).keys())) or "nothing yet"
    return (
        f"You are Pragya, this company's account manager. You are in stage "
        f"{int(stage)} — {info.name}. {info.summary}\n\n"
        f"What you already know about this business is recorded under: {known}. "
        f"Use it; do not re-ask for it.\n\n"
        f"## Rules that always apply\n{rules}\n"
    )


def _refusal_copy(decision: AuthDecision, command: ExtractedCommand) -> str:
    """What Pragya says when the session has not proved enough.

    A refusal names the action, the reason, and the way forward. "I can't do
    that" without a path is the response that makes people find a way around
    the system rather than through it.
    """
    if decision.locked:
        return (
            f"I can't act on \"{command.summary}\" right now — there have been "
            "several failed verification attempts on this account, so sensitive "
            "actions are locked for a short while. I've alerted every channel "
            "you've registered. If that wasn't you, it's worth a look."
        )
    if decision.current_level == "none":
        return UNBOUND_REFUSAL
    if decision.needs_oob:
        return (
            f"\"{command.summary}\" can't be undone, so it needs two "
            "confirmations: your passkey here, then a code I'll send to your "
            "other registered channel. Shall I start?"
        )
    return (
        f"Happy to do that — \"{command.summary}\" is a sensitive change, so "
        "I need you to confirm it's you first. One tap with your passkey."
    )


async def handle_turn(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    text: str,
    user_id: uuid.UUID | None = None,
    channel_kind: str = ChannelKind.CONSOLE,
    channel_address: str | None = None,
    session: AccountManagerSession | None = None,
) -> TurnResult:
    """Process one owner turn end to end."""
    engagement = await get_or_create_engagement(db, company_id)
    stage = current_stage(engagement)

    if session is None:
        session = await get_or_create_session(
            db, company_id=company_id, user_id=user_id,
            channel_kind=channel_kind, channel_address=channel_address)

    await record_turn(db, company_id=company_id, stage=stage, role="user",
                      content=text, user_id=user_id)

    # An unresolved channel never reaches intent extraction. Nothing about
    # this tenant should be computed for a caller we cannot identify.
    unresolved = require_tier(session, Tier.T1)
    if not unresolved.allowed and unresolved.current_level == "none":
        await record_turn(db, company_id=company_id, stage=stage, role="pragya",
                          content=UNBOUND_REFUSAL, outcome="refused_unbound")
        return TurnResult(
            reply=UNBOUND_REFUSAL, stage=stage,
            auth_level=unresolved.current_level, decision=unresolved,
        )

    router = LLMRouter(db=db, company_id=company_id)
    history = [
        {"role": "user" if t.role == "user" else "model",
         "parts": [{"text": t.content}]}
        for t in await recent_turns(db, company_id, limit=20)
    ]
    system_prompt = stage_system_prompt(stage, engagement)

    # 2. Classify before generating. What she may do constrains what she says.
    extracted: dict[str, Any] | None = None
    try:
        screening = await router.call_llm(
            task_type="text_generation",
            system_prompt=(
                "Classify the owner's message using the classify_owner_turn "
                "tool. Do not reply conversationally."
            ),
            user_prompt=text,
            tools=[INTENT_SCHEMA],
            temperature=0.0,
        )
        for call in screening.function_calls:
            if call.get("name") == INTENT_SCHEMA["name"]:
                extracted = dict(call.get("args") or {})
                break
    except Exception as exc:
        # Extraction failure must not become a pass-through: classify_turn
        # treats a missing reading as UNKNOWN, which fails up to T3.
        logger.warning("pragya intent extraction failed: %s", exc)

    command = classify_turn(text, extracted)
    decision = require_tier(session, command.tier)
    command_ref = f"{command.kind}:{uuid.uuid4().hex[:12]}"

    # 3. Authorise. A refusal is final for this turn — no prose is generated
    # that could soften or contradict it.
    if not decision.allowed:
        reply = _refusal_copy(decision, command)
        await record_turn(
            db, company_id=company_id, stage=stage, role="pragya", content=reply,
            intent_kind=command.kind, tier=command.tier.name,
            outcome="refused_needs_stepup" if decision.needs_step_up else "refused")
        return TurnResult(
            reply=reply, stage=stage, auth_level=decision.current_level,
            tier=command.tier.name, command=command, decision=decision,
            needs_step_up=decision.needs_step_up, needs_oob=decision.needs_oob,
            command_ref=command_ref,
        )

    # 4a. An authorised command executes before any prose is written, so that
    # what she reports is what actually happened rather than what she intended.
    if command.tier >= Tier.T2:
        outcome = await execute_command(
            db, session, command, company_id=company_id)
        await record_turn(
            db, company_id=company_id, stage=stage, role="pragya",
            content=outcome.message, intent_kind=command.kind,
            tier=command.tier.name,
            outcome="executed" if outcome.executed else "execution_failed")
        return TurnResult(
            reply=outcome.message, stage=stage,
            auth_level=decision.current_level, tier=command.tier.name,
            command=command, decision=decision, executed=outcome.executed,
            command_ref=command_ref,
        )

    # 4b. Generate, having established what is permitted.
    response = await router.call_llm(
        task_type="text_generation",
        system_prompt=system_prompt,
        user_prompt=text,
        history=history,
        temperature=0.6,
    )
    reply = response.output.strip()

    await record_turn(
        db, company_id=company_id, stage=stage, role="pragya", content=reply,
        intent_kind=command.kind, tier=command.tier.name, outcome="answered")

    return TurnResult(
        reply=reply, stage=stage, auth_level=decision.current_level,
        tier=command.tier.name, command=command, decision=decision,
        command_ref=command_ref,
    )
