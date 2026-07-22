"""pragya/conversation.py — what Pragya says, and the prompt she says it under.

The turn loop moved to ``runtime.py`` in Inc-4 PRAGYA-RT. What stayed here is
the part that was never orchestration: the standing refusal copy, the
per-tier refusal wording, and the assembly of a stage's system prompt.

They live in one module because they are the same concern — *how Pragya
addresses the owner when she cannot do what was asked* — and because a second
copy of a refusal is how a system ends up warm on one channel and curt on
another.

There is deliberately no turn loop here any more. Two orchestrators is the
duplication the Inc-4 seam exists to prevent, and the one that survives is
``runtime.run_turn``.
"""
from __future__ import annotations

import logging


from src.ai.inward_auth.sessions import AuthDecision
from src.ai.pragya.intents import ExtractedCommand
from src.ai.pragya.models import PragyaEngagement
from src.ai.pragya.scripts import script_for_stage
from src.ai.pragya.stages import STAGE_INFO, Stage

logger = logging.getLogger(__name__)

__all__ = ["UNBOUND_REFUSAL", "refusal_copy", "stage_system_prompt"]


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


def refusal_copy(decision: AuthDecision, command: ExtractedCommand) -> str:
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
