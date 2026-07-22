"""voice_loop/live_gate.py — governance on a live voice turn.

The enforcement half of the realtime profile. It reuses
``governance.policy_gate.evaluate_policy`` **unchanged** — that function was
already pure, which is the property that makes governed realtime voice
possible at all. There is no voice-specific policy here, and there must never
be one: a second authority matrix that only applies to phone calls is a second
thing to keep correct and an obvious place for the two to drift.

What this module adds is the *voice-shaped consequence* of a decision:

* ``PASS`` → the tool runs live and the agent speaks the result.
* ``RAISE_HITL`` → the card is raised **during** the call, and the agent
  **promises**. It does not wait, it does not ask the caller to approve, and it
  does not complete the action.
* ``BLOCK`` → the agent declines plainly.

The promise path is the interesting one. A caller cannot approve their own
request over the phone (standing rule 2, and the channel is the most spoofable
one the platform accepts), so the honest response is the one a competent
assistant would give: *"I've put that through for approval."*
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.ai.governance.policy_gate import (
    BLOCK,
    PASS,
    RAISE_HITL,
    ActIntent,
    GateDecision,
    evaluate_policy,
)
from src.ai.schemas.governance import Governance
from src.ai.voice_loop.profile import LIVE_COMPLETION_RULE

__all__ = [
    "LiveOutcome",
    "VoiceActDecision",
    "gate_voice_act",
    "PROMISE_TEMPLATE",
    "DECLINE_TEMPLATE",
]


#: What the agent says when the gate raised a card. Deliberately concrete
#: about *what* is pending — "I'll look into it" is how a caller ends up
#: believing something happened that did not.
PROMISE_TEMPLATE = (
    "I can't put that through on my own — it needs {who} to sign off. "
    "I've raised it now with everything we've discussed, so it's waiting for "
    "them rather than for me. You'll get confirmation once it's approved."
)

DECLINE_TEMPLATE = (
    "That one's outside what I'm allowed to do at all, so I'd be misleading "
    "you if I said I'd try. {reason} The person who can authorise it will "
    "need to do it directly."
)


class LiveOutcome(str, Enum):
    """What actually happens to the act on this turn."""

    COMPLETED = "completed"    # ran live, result available to speak
    PROMISED = "promised"      # HITL card raised; settles after the call
    DECLINED = "declined"      # hard-blocked; nothing raised


@dataclass(frozen=True)
class VoiceActDecision:
    """The gate's verdict plus what the agent should say about it."""

    outcome: LiveOutcome
    gate: GateDecision
    #: What the agent says. Empty for COMPLETED — the tool result is the reply.
    spoken: str = ""
    checkpoint_key: str | None = None

    @property
    def may_execute_live(self) -> bool:
        """The single question the caller of this module is asking."""
        return self.outcome is LiveOutcome.COMPLETED


def gate_voice_act(
    intent: ActIntent,
    gov: Governance,
    *,
    approver: str = "someone on your side",
) -> VoiceActDecision:
    """Decide what a voice turn may do with ``intent``.

    Pure, and deliberately so — it runs on the latency path. The only work is
    the shipped gate plus a branch, which is what lets governance stay inline
    at conversational speed (see ``profile.REALTIME_PROFILE``).
    """
    decision = evaluate_policy(intent, gov)

    if decision.decision == PASS:
        return VoiceActDecision(LiveOutcome.COMPLETED, decision)

    if decision.decision == RAISE_HITL:
        # The card is raised by the caller (it needs a DB write); this module
        # decides only that the act does *not* complete on the turn.
        return VoiceActDecision(
            LiveOutcome.PROMISED, decision,
            spoken=PROMISE_TEMPLATE.format(who=approver),
            checkpoint_key=decision.checkpoint_key,
        )

    if decision.decision == BLOCK:
        reason = decision.reason.strip()
        return VoiceActDecision(
            LiveOutcome.DECLINED, decision,
            spoken=DECLINE_TEMPLATE.format(
                reason=(reason + ".") if reason and not reason.endswith(".") else reason),
            checkpoint_key=decision.checkpoint_key,
        )

    # An unrecognised decision string is not a pass. Fail closed, loudly.
    return VoiceActDecision(
        LiveOutcome.DECLINED, decision,
        spoken=DECLINE_TEMPLATE.format(
            reason="I couldn't confirm I'm allowed to do that."),
    )


def profile_note() -> str:
    """The normative limit, for embedding in the gateway's system prompt.

    Kept as a function over ``profile.LIVE_COMPLETION_RULE`` so the agent's own
    instructions and the code that enforces them cannot state different rules.
    """
    return LIVE_COMPLETION_RULE
