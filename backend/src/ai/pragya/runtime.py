"""pragya/runtime.py — Pragya's own turn loop (Inc-4 PRAGYA-RT T1).

The fork. The shipped eight-stage loop is a **task** engine — perceive,
strategize, act, observe, reflect over bounded work. Pragya's unit of work is
a months-long relationship, and Increment 3's four recorded gaps (stage
advancement, artifact extraction, drainable reflection, script goldens) were
four symptoms of that one mismatch.

Eight steps here too, but they are *conversation* steps, and **exactly one
model call sits on the latency path** against the task loop's four (planner,
pre-critic, post-critic, reflector). That difference is the whole reason the
orchestration forks.

What does **not** fork (the Inc-4 §3 seam, locked): governance, tiers,
metering, memory, tool execution, the signal bus, the Meta-Agent, HITL. This
module *calls* those; it does not wrap or shadow them. Two orchestrators are
only safe while there is one PolicyGate, one wallet, and one audit trail.

Ordering is a safety property carried from Increment 3: classify and authorise
**before** generating. A model that has already promised to pause a process
and only then discovers it may not has to be corrected in front of the owner.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.models import AccountManagerSession, ChannelKind
from src.ai.inward_auth.sessions import AuthDecision, get_or_create_session, require_tier
from src.ai.inward_auth.tiers import Tier
from src.ai.llm.router import LLMRouter
from src.ai.loop.wallet_holds import available_for_spend
from src.ai.pragya.acting import ActOutcome, ProposedCall, ToolTurnResult, run_tool_calls
from src.ai.pragya.advancement import (
    AUTO_ADVANCE_STAGES,
    advancement_prompt,
    evaluate_eligibility,
)
from src.ai.pragya.artifacts import (
    ARTIFACT_TOOL_NAME,
    artifact_schema_for,
    extraction_prompt,
    parse_extraction,
)
from src.ai.pragya.delegation import (
    mark_reported,
    report_copy,
    unreported_for,
)
from src.ai.pragya.conversation import (
    UNBOUND_REFUSAL,
    refusal_copy,
    stage_system_prompt,
)
from src.ai.pragya.engagement import (
    advance,
    current_stage,
    get_or_create_engagement,
    recent_turns,
    record_artifacts,
    record_turn,
)
from src.ai.pragya.intents import INTENT_SCHEMA, ExtractedCommand, classify_turn
from src.ai.pragya.scripts import script_for_stage
from src.ai.pragya.stages import Stage
from src.ai.schemas.governance import AutonomyLevel, Governance
from src.ai.services.cost_attribution import CostAttribution
from src.ai.usage_service import UsageService

logger = logging.getLogger(__name__)

__all__ = ["TurnRequest", "TurnOutcome", "run_turn", "PRAGYA_MODEL_SKU",
           "MIN_TURN_BALANCE_USD", "OUT_OF_CREDIT"]


#: The SKU a conversational turn meters against.
PRAGYA_MODEL_SKU = "pragya-conversation"

#: A turn will not start below this. Small — a turn costs cents — but not zero:
#: an account with nothing left should be told, not silently served until the
#: wallet goes negative.
MIN_TURN_BALANCE_USD = Decimal("0.02")

OUT_OF_CREDIT = (
    "I've run out of credit on your account, so I can't reply properly right "
    "now — everything we've discussed is saved and I'll pick up exactly where "
    "we left off once it's topped up. You can do that from Billing."
)


@dataclass
class TurnRequest:
    """One inbound turn, normalised by whichever channel adapter received it."""

    company_id: uuid.UUID
    text: str
    user_id: uuid.UUID | None = None
    channel_kind: str = ChannelKind.CONSOLE
    channel_address: str | None = None
    #: Set by the voice adapter so a call and its console session share state.
    session: AccountManagerSession | None = None


@dataclass
class TurnOutcome:
    """Everything one turn produced. Channel adapters render this."""

    reply: str
    stage: Stage
    auth_level: str
    tier: str | None = None
    command: ExtractedCommand | None = None
    decision: AuthDecision | None = None
    tool_results: list[ToolTurnResult] = field(default_factory=list)
    needs_step_up: bool = False
    needs_oob: bool = False
    command_ref: str | None = None
    #: True when a tool raised a HITL card this turn.
    raised_approval: bool = False
    cost_usd: float = 0.0
    #: Artifact keys this turn established.
    artifacts_written: list[str] = field(default_factory=list)
    #: Set when the turn moved the engagement on.
    advanced_to: Stage | None = None
    #: Set when the stage is complete but waiting on the owner to say so.
    awaiting_confirmation: bool = False
    #: Promises closed on this turn.
    reported_delegations: list[str] = field(default_factory=list)


#: Pragya's own governance. She is a conversational surface, not a worker
#: agent: she holds no monetary authority of her own, so any categorised act
#: she proposes raises a card rather than resolving against a band. Declared
#: here rather than seeded as an entity because she is platform-provided and
#: identical for every tenant.
PRAGYA_GOVERNANCE = Governance(
    autonomy_level=AutonomyLevel.A1,
    authority=None,
)


def _tool_schemas() -> list[dict[str, Any]]:
    """Tools Pragya may propose. Empty until T4 wires the delegation set.

    Deliberately not "every registered tool": her reach is curated, because a
    conversational surface with the full catalogue is a very large attack
    surface for anything that talks its way past the tier classifier.
    """
    return []


async def _meter_turn(
    db: AsyncSession, company_id: uuid.UUID, *, tokens: int, stage: Stage,
) -> float:
    """Write the turn's usage row. Metering is a launch blocker, not a follow-up.

    A turn that writes no ``usage_logs`` is free compute the wallet cannot
    see — the seam makes billing shared precisely so this cannot be skipped.
    Failures are logged, never raised: a metering problem must not cost the
    owner their reply.
    """
    try:
        row = await UsageService(db).log_usage(
            company_id=company_id,
            service_sku=PRAGYA_MODEL_SKU,
            raw_quantity=float(tokens),
            metadata={"surface": "pragya", "stage": int(stage)},
            attribution=CostAttribution.PRAGYA_TURN.value,
        )
        return float(row.calculated_cost or 0)
    except Exception as exc:  # noqa: BLE001
        logger.error("pragya turn metering failed (company=%s): %s", company_id, exc)
        return 0.0


async def _extract_command(
    router: LLMRouter, text: str,
) -> dict[str, Any] | None:
    """Ask the model what the turn is asking for. Failure is not a pass-through.

    ``classify_turn`` treats a missing reading as ``UNKNOWN``, which the
    classifier floors at T3 — so an extraction outage makes Pragya *more*
    cautious, never less.
    """
    try:
        screening = await router.call_llm(
            task_type="text_generation",
            system_prompt=("Classify the owner's message using the "
                           "classify_owner_turn tool. Do not reply "
                           "conversationally."),
            user_prompt=text,
            tools=[INTENT_SCHEMA],
            temperature=0.0,
        )
        for call in screening.function_calls:
            if call.get("name") == INTENT_SCHEMA["name"]:
                return dict(call.get("args") or {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("pragya intent extraction failed: %s", exc)
    return None


async def _extract_artifacts(
    db: AsyncSession, router: LLMRouter, engagement: Any, stage: Stage,
    turns: list[Any],
) -> list[str]:
    """Read the conversation for what this stage has established.

    A second, cheap model call *off* the reply path — the owner has already
    been answered by the time this runs, so its latency is invisible and its
    failure costs state, not a response.
    """
    script = script_for_stage(int(stage))
    schema = artifact_schema_for(stage)
    if script is None or schema is None:
        return []

    transcript = "\n".join(f"{t.role}: {t.content}" for t in turns[-12:])
    try:
        response = await router.call_llm(
            task_type="text_generation",
            system_prompt=extraction_prompt(script),
            user_prompt=f"=== CONVERSATION ===\n{transcript}\n=== END ===",
            tools=[schema],
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("pragya artifact extraction failed at stage %s: %s",
                       int(stage), exc)
        return []

    for call in response.function_calls:
        if call.get("name") != ARTIFACT_TOOL_NAME:
            continue
        extracted = parse_extraction(stage, dict(call.get("args") or {}))
        if extracted:
            await record_artifacts(db, engagement, extracted)
            return sorted(extracted)
    return []


async def run_turn(db: AsyncSession, request: TurnRequest) -> TurnOutcome:
    """Process one turn through Pragya's loop.

    Steps, in the order the docstring's safety argument requires:
      1. resolve session + engagement
      2. assemble context
      3. classify intent → tier
      4. authorise
      5. LLM turn (the one model call on the path) + gated tool calls
      6. record
      7. meter
    """
    engagement = await get_or_create_engagement(db, request.company_id)
    stage = current_stage(engagement)

    session = request.session or await get_or_create_session(
        db,
        company_id=request.company_id,
        user_id=request.user_id,
        channel_kind=request.channel_kind,
        channel_address=request.channel_address,
    )

    await record_turn(db, company_id=request.company_id, stage=stage,
                      role="user", content=request.text, user_id=request.user_id)

    # An unresolved channel never reaches extraction: nothing about this
    # tenant should be computed for someone we cannot identify.
    unresolved = require_tier(session, Tier.T1)
    if not unresolved.allowed and unresolved.current_level == "none":
        await record_turn(db, company_id=request.company_id, stage=stage,
                          role="pragya", content=UNBOUND_REFUSAL,
                          outcome="refused_unbound")
        return TurnOutcome(reply=UNBOUND_REFUSAL, stage=stage,
                           auth_level=unresolved.current_level,
                           decision=unresolved)

    # Admission. Checked before the model call, not after — spending first and
    # discovering insolvency second is how a wallet goes negative.
    if await available_for_spend(db, request.company_id) < MIN_TURN_BALANCE_USD:
        await record_turn(db, company_id=request.company_id, stage=stage,
                          role="pragya", content=OUT_OF_CREDIT,
                          outcome="refused_no_credit")
        return TurnOutcome(reply=OUT_OF_CREDIT, stage=stage,
                           auth_level=unresolved.current_level)

    router = LLMRouter(db=db, company_id=request.company_id)

    extracted = await _extract_command(router, request.text)
    command = classify_turn(request.text, extracted)
    decision = require_tier(session, command.tier)
    command_ref = f"{command.kind}:{uuid.uuid4().hex[:12]}"

    if not decision.allowed:
        reply = refusal_copy(decision, command)
        await record_turn(
            db, company_id=request.company_id, stage=stage, role="pragya",
            content=reply, intent_kind=command.kind, tier=command.tier.name,
            outcome="refused_needs_stepup" if decision.needs_step_up else "refused")
        return TurnOutcome(
            reply=reply, stage=stage, auth_level=decision.current_level,
            tier=command.tier.name, command=command, decision=decision,
            needs_step_up=decision.needs_step_up, needs_oob=decision.needs_oob,
            command_ref=command_ref)

    history = [
        {"role": "user" if t.role == "user" else "model",
         "parts": [{"text": t.content}]}
        for t in await recent_turns(db, request.company_id, limit=20)
    ]

    response = await router.call_llm(
        task_type="text_generation",
        system_prompt=stage_system_prompt(stage, engagement),
        user_prompt=request.text,
        history=history,
        tools=_tool_schemas() or None,
        temperature=0.6,
    )

    # Gated acts. Every proposal passes the shared PolicyGate before the
    # shared executor; a governed one raises a card and does not complete.
    tool_results: list[ToolTurnResult] = []
    if response.function_calls:
        tool_results = await run_tool_calls(
            [ProposedCall(name=str(c.get("name")), args=dict(c.get("args") or {}))
             for c in response.function_calls],
            PRAGYA_GOVERNANCE,
            company_id=request.company_id,
            user_id=request.user_id,
        )

    reply = (response.output or "").strip()

    # Close any loop Pragya opened. Done first and prefixed to the reply: work
    # that finished and was never mentioned again is the specific failure the
    # delegation table exists to make visible, so the report leads.
    finished = await unreported_for(db, request.company_id)
    reported: list[str] = []
    if finished:
        reply = "\n\n".join([*(report_copy(d) for d in finished), reply]).strip()
        reported = [str(d.kind) for d in finished]
        await mark_reported(db, finished)

    raised = [r for r in tool_results if r.outcome == ActOutcome.RAISED]
    if raised and not reply:
        reply = ("I've raised that for approval — it's waiting at the Judgment "
                 "Desk. I'll confirm once it's signed off.")

    tokens = int(getattr(response, "prompt_tokens", 0) or 0) + int(
        getattr(response, "completion_tokens", 0) or 0)
    cost = await _meter_turn(db, request.company_id, tokens=tokens, stage=stage)

    await record_turn(
        db, company_id=request.company_id, stage=stage, role="pragya",
        content=reply, intent_kind=command.kind, tier=command.tier.name,
        outcome="raised" if raised else "answered")

    # 6. Read the conversation for what this stage established, then
    # 7. move on if it is done. Both run after the reply is fixed, so neither
    # can delay the owner's answer or change what she was told.
    written = await _extract_artifacts(
        db, router, engagement, stage,
        await recent_turns(db, request.company_id, limit=20))

    advanced_to: Stage | None = None
    awaiting = False
    eligibility = evaluate_eligibility(stage, engagement.artifacts)
    if eligibility.eligible:
        if stage in AUTO_ADVANCE_STAGES:
            # Gathering stages advance on their own: nothing was agreed, so
            # there is nothing to ask the owner to agree to.
            await advance(db, engagement,
                          reason=f"stage {int(stage)} artifacts complete")
            advanced_to = current_stage(engagement)
        elif eligibility.needs_confirmation:
            # The owner's decision *is* this stage's deliverable, so Pragya
            # asks rather than announces — see advancement.CONFIRM_STAGES.
            awaiting = True
            reply = f"{reply}\n\n{advancement_prompt(stage)}".strip()

    return TurnOutcome(
        reply=reply, stage=stage, auth_level=decision.current_level,
        tier=command.tier.name, command=command, decision=decision,
        tool_results=tool_results, command_ref=command_ref,
        raised_approval=bool(raised), cost_usd=cost,
        artifacts_written=written, advanced_to=advanced_to,
        awaiting_confirmation=awaiting, reported_delegations=reported)
