"""voice_loop/identity.py — who is on the phone, and how far that gets them.

Caller ID is the most spoofable identity the platform accepts. Anyone can
present any number, and the carrier will deliver it. So the AUTH rules bind
hardest here, and this module exists to make one thing structurally
impossible:

> **A voice channel can never reach ``ELEVATED`` by voice alone.**

No spoken passphrase, no DTMF PIN, no voice print as a sole factor (§11.3).
Those are all things an attacker who already spoofed the number can also
supply — a recording, a shoulder-surfed PIN, a synthesised voice. Step-up is a
console ceremony reached by a link sent to a *separately registered* channel,
and ``voice_tier_ceiling`` refuses anything above T1 that has not been through
one.

T3 is unavailable on voice at all. It requires step-up plus out-of-band
confirmation on a second channel; originating that chain from the most
spoofable channel available is not a sensible place to start it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.bindings import resolve_inbound
from src.ai.inward_auth.models import AccountManagerSession, AuthLevel, ChannelKind
from src.ai.inward_auth.sessions import AuthDecision, effective_level, get_or_create_session
from src.ai.inward_auth.tiers import Tier

__all__ = [
    "VOICE_TIER_CEILING",
    "VoiceCaller",
    "identify_caller",
    "voice_tier_ceiling",
    "UNKNOWN_CALLER_GREETING",
    "STEP_UP_REDIRECT",
    "T3_UNAVAILABLE",
]


#: The highest tier a voice session may reach on its own. Everything above
#: needs a ceremony that does not happen on this channel.
VOICE_TIER_CEILING = Tier.T1


UNKNOWN_CALLER_GREETING = (
    "Thanks for calling. I don't recognise this number, so I can't go into "
    "anything specific about an account — I've no way to be sure who I'm "
    "talking to, and I'd rather be careful than convenient. I can answer "
    "general questions, or if this is your account, you can register this "
    "number from Settings then call back."
)

STEP_UP_REDIRECT = (
    "That's a sensitive change, so I can't take it on a phone call — a number "
    "is too easy to fake for me to act on one alone. I've sent a link to your "
    "registered {channel}; approve it there and I'll have it done in seconds."
)

T3_UNAVAILABLE = (
    "That one I can't do over the phone at all, even with verification — it's "
    "in the can't-be-undone category, and those need confirming from two "
    "places that aren't this call. Sign in to the console and I'll walk you "
    "through it."
)


@dataclass(frozen=True)
class VoiceCaller:
    """The resolved (or unresolved) identity behind an inbound call."""

    session: AccountManagerSession
    user_id: uuid.UUID | None
    bound: bool
    #: The binding the number resolved to, when it did.
    binding_id: uuid.UUID | None = None

    @property
    def auth_level(self) -> str:
        return effective_level(self.session)


async def identify_caller(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    from_number: str,
) -> VoiceCaller:
    """Resolve a calling number to a user, or return an unbound caller.

    Unbound is a routing outcome, not an error: the agent still answers, it
    just cannot discuss the account. Note it never *confirms* whether the
    number is unknown to this tenant specifically — a caller learning "yes,
    that number is registered to Acme" has already learned something worth
    having.
    """
    binding = await resolve_inbound(
        db, company_id=company_id, channel_kind=ChannelKind.VOICE,
        address=from_number)

    session = await get_or_create_session(
        db,
        company_id=company_id,
        user_id=binding.user_id if binding else None,
        channel_kind=ChannelKind.VOICE,
        channel_address=from_number,
    )

    # A resolved binding makes the session bound — but only bound. The voice
    # channel is not born elevated and cannot become so here.
    if binding is not None and session.auth_level == AuthLevel.NONE:
        session.auth_level = AuthLevel.BOUND
        await db.flush()

    return VoiceCaller(
        session=session,
        user_id=binding.user_id if binding else None,
        bound=binding is not None,
        binding_id=binding.id if binding else None,
    )


def voice_tier_ceiling(
    caller: VoiceCaller, tier: Tier,
) -> AuthDecision:
    """Whether a command of ``tier`` may run on this *voice* session.

    Applies the channel ceiling **before** the ordinary session check, so no
    amount of session state can talk a voice call above T1. That ordering is
    the point: if the ceiling were checked second, a session elevated through
    some other path would carry its elevation onto the phone.
    """
    current = caller.auth_level

    if tier >= Tier.T3:
        return AuthDecision(
            allowed=False, tier=tier, current_level=current,
            required_level=AuthLevel.OOB_CONFIRMED,
            reason=("T3 is not available on the voice channel: it needs "
                    "out-of-band confirmation on a second channel, and this "
                    "one is the most spoofable"),
            needs_step_up=False, needs_oob=False,
        )

    if tier > VOICE_TIER_CEILING:
        return AuthDecision(
            allowed=False, tier=tier, current_level=current,
            required_level=AuthLevel.ELEVATED,
            reason=("voice cannot self-elevate: step-up is a console ceremony "
                    "reached from a separately registered channel"),
            # The step-up is *offered*, but it happens elsewhere — the console
            # link is the mechanism, not a prompt on this call.
            needs_step_up=caller.bound,
            needs_oob=False,
        )

    if not caller.bound:
        return AuthDecision(
            allowed=tier <= Tier.T0, tier=tier, current_level=current,
            required_level=AuthLevel.BOUND,
            reason=("this number is not registered to anyone on the account"
                    if tier > Tier.T0 else "general question, no identity needed"),
        )

    return AuthDecision(
        allowed=True, tier=tier, current_level=current,
        required_level=AuthLevel.BOUND,
        reason=f"registered caller, {tier.name} within the voice ceiling",
    )
