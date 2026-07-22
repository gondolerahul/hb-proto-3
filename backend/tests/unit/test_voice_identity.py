"""Voice identity and the elevation ceiling (Inc-3 VOICE V3).

Caller ID is the most spoofable identity the platform accepts. These pin the
structural consequence: **a voice channel can never reach ELEVATED by voice
alone**, and T3 is unavailable on the channel entirely.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.inward_auth.models import AccountManagerSession, AuthLevel, ChannelKind
from src.ai.inward_auth.tiers import Tier
from src.ai.voice_loop.identity import (
    T3_UNAVAILABLE,
    UNKNOWN_CALLER_GREETING,
    VOICE_TIER_CEILING,
    VoiceCaller,
    voice_tier_ceiling,
)


def _caller(*, bound: bool, level: str = AuthLevel.BOUND) -> VoiceCaller:
    session = AccountManagerSession(
        company_id=uuid.uuid4(),
        user_id=uuid.uuid4() if bound else None,
        channel_kind=ChannelKind.VOICE,
        channel_address="15550100",
        auth_level=level if bound else AuthLevel.NONE,
        failed_stepups=0,
    )
    return VoiceCaller(
        session=session,
        user_id=session.user_id,
        bound=bound,
    )


# --- the ceiling --------------------------------------------------------------

def test_the_voice_ceiling_is_t1() -> None:
    assert VOICE_TIER_CEILING is Tier.T1


def test_a_registered_caller_reaches_t1() -> None:
    decision = voice_tier_ceiling(_caller(bound=True), Tier.T1)
    assert decision.allowed


def test_t0_works_even_for_an_unknown_number() -> None:
    """General questions need no identity — she still answers the phone."""
    assert voice_tier_ceiling(_caller(bound=False), Tier.T0).allowed


def test_an_unregistered_number_cannot_reach_t1() -> None:
    decision = voice_tier_ceiling(_caller(bound=False), Tier.T1)
    assert not decision.allowed
    assert "not registered" in decision.reason


def test_voice_cannot_self_elevate_to_t2() -> None:
    """The load-bearing rule: no spoken passphrase, PIN, or voice print."""
    decision = voice_tier_ceiling(_caller(bound=True), Tier.T2)
    assert not decision.allowed
    assert "cannot self-elevate" in decision.reason


@pytest.mark.parametrize("level", [AuthLevel.ELEVATED, AuthLevel.OOB_CONFIRMED])
def test_no_session_state_can_lift_a_voice_call_above_the_ceiling(level: str) -> None:
    """The ceiling is checked *before* the session, so an elevation obtained
    elsewhere cannot be carried onto the phone."""
    decision = voice_tier_ceiling(_caller(bound=True, level=level), Tier.T2)
    assert not decision.allowed


def test_t3_is_unavailable_on_voice_at_any_level() -> None:
    for level in (AuthLevel.BOUND, AuthLevel.ELEVATED, AuthLevel.OOB_CONFIRMED):
        decision = voice_tier_ceiling(_caller(bound=True, level=level), Tier.T3)
        assert not decision.allowed, level
        assert "not available on the voice channel" in decision.reason
        # Nothing is offered — there is no path, so offering one would lie.
        assert not decision.needs_step_up
        assert not decision.needs_oob


def test_a_t2_refusal_offers_the_console_ceremony_to_a_known_caller() -> None:
    decision = voice_tier_ceiling(_caller(bound=True), Tier.T2)
    assert decision.needs_step_up


def test_an_unbound_caller_is_not_offered_a_step_up() -> None:
    """There is no user to prove — enrollment is the path, not a ceremony."""
    decision = voice_tier_ceiling(_caller(bound=False), Tier.T2)
    assert not decision.allowed
    assert not decision.needs_step_up


# --- what she actually says ---------------------------------------------------

def test_the_unknown_caller_greeting_does_not_confirm_the_account() -> None:
    """A caller learning 'yes, that's Acme's number' has learned something."""
    text = UNKNOWN_CALLER_GREETING.lower()
    assert "don't recognise this number" in text
    assert "register" in text
    # It must not name or confirm a tenant.
    assert "acme" not in text


def test_the_t3_refusal_explains_rather_than_stonewalls() -> None:
    assert "two places" in T3_UNAVAILABLE
    assert "console" in T3_UNAVAILABLE
