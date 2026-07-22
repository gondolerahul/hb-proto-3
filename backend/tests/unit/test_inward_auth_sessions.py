"""Elevation, expiry and ``require_tier`` (Inc-3 AUTH T3).

These drive ``AccountManagerSession`` instances constructed in memory — the
predicate is pure over the row plus the clock, and keeping it testable without
a database is the reason it was written that way. The DB-backed half
(enrollment, persistence, lockout writes) is in
``tests/integration/test_inward_auth_db.py``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from src.ai.inward_auth.models import AccountManagerSession, AuthLevel, ChannelKind
from src.ai.inward_auth.sessions import (
    AuthDecision,
    effective_level,
    is_locked,
    require_tier,
)
from src.ai.inward_auth.tiers import Tier

NOW = datetime(2026, 7, 22, 12, 0, 0)


def _session(
    *,
    level: str = AuthLevel.BOUND,
    elevated_until: datetime | None = None,
    locked_until: datetime | None = None,
    user_id: uuid.UUID | None = None,
    channel_kind: str = ChannelKind.CONSOLE,
) -> AccountManagerSession:
    return AccountManagerSession(
        company_id=uuid.uuid4(),
        user_id=uuid.uuid4() if user_id is None else user_id,
        channel_kind=channel_kind,
        auth_level=level,
        elevated_until=elevated_until,
        locked_until=locked_until,
        failed_stepups=0,
    )


# --- elevation is time-boxed --------------------------------------------------

def test_elevation_holds_inside_its_window() -> None:
    s = _session(level=AuthLevel.ELEVATED, elevated_until=NOW + timedelta(minutes=5))
    assert effective_level(s, NOW) == AuthLevel.ELEVATED


def test_expired_elevation_demotes_to_bound_silently() -> None:
    """No sweeper demotes a session — the clock does, on read."""
    s = _session(level=AuthLevel.ELEVATED, elevated_until=NOW - timedelta(seconds=1))
    assert effective_level(s, NOW) == AuthLevel.BOUND


def test_elevation_with_no_expiry_is_not_trusted() -> None:
    """A stored ELEVATED without a window is corrupt state, not a free pass."""
    s = _session(level=AuthLevel.ELEVATED, elevated_until=None)
    assert effective_level(s, NOW) == AuthLevel.BOUND


def test_expired_elevation_on_an_unbound_session_falls_to_none() -> None:
    s = AccountManagerSession(
        company_id=uuid.uuid4(), user_id=None, channel_kind=ChannelKind.WHATSAPP,
        auth_level=AuthLevel.ELEVATED, elevated_until=NOW - timedelta(minutes=1),
        failed_stepups=0)
    assert effective_level(s, NOW) == AuthLevel.NONE


# --- require_tier: the §11.3 verification column ------------------------------

def test_t0_passes_even_unauthenticated() -> None:
    s = AccountManagerSession(
        company_id=uuid.uuid4(), user_id=None, channel_kind=ChannelKind.VOICE,
        auth_level=AuthLevel.NONE, failed_stepups=0)
    assert require_tier(s, Tier.T0, NOW).allowed


def test_t1_needs_a_bound_identity() -> None:
    unbound = AccountManagerSession(
        company_id=uuid.uuid4(), user_id=None, channel_kind=ChannelKind.WHATSAPP,
        auth_level=AuthLevel.NONE, failed_stepups=0)
    decision = require_tier(unbound, Tier.T1, NOW)
    assert not decision.allowed
    assert "not bound" in decision.reason
    # An unbound channel has no user to prove, so a step-up modal is the wrong
    # offer — enrollment is.
    assert not decision.needs_step_up

    assert require_tier(_session(level=AuthLevel.BOUND), Tier.T1, NOW).allowed


def test_t2_needs_a_live_elevation_and_asks_for_a_step_up() -> None:
    bound = _session(level=AuthLevel.BOUND)
    decision = require_tier(bound, Tier.T2, NOW)
    assert not decision.allowed
    assert decision.needs_step_up and not decision.needs_oob

    elevated = _session(level=AuthLevel.ELEVATED,
                        elevated_until=NOW + timedelta(minutes=5))
    assert require_tier(elevated, Tier.T2, NOW).allowed


def test_t2_denied_once_the_elevation_lapses() -> None:
    """The exit-demo guarantee: re-checked at execution, not classification."""
    s = _session(level=AuthLevel.ELEVATED, elevated_until=NOW + timedelta(minutes=10))
    assert require_tier(s, Tier.T2, NOW).allowed
    assert not require_tier(s, Tier.T2, NOW + timedelta(minutes=11)).allowed


def test_t3_needs_out_of_band_confirmation_not_merely_a_step_up() -> None:
    elevated = _session(level=AuthLevel.ELEVATED,
                        elevated_until=NOW + timedelta(minutes=5))
    decision = require_tier(elevated, Tier.T3, NOW)
    assert not decision.allowed
    assert decision.needs_oob

    confirmed = _session(level=AuthLevel.OOB_CONFIRMED,
                         elevated_until=NOW + timedelta(minutes=5))
    assert require_tier(confirmed, Tier.T3, NOW).allowed


def test_oob_confirmation_also_satisfies_t2() -> None:
    """Levels are ranked, so the stronger proof covers the weaker demand."""
    s = _session(level=AuthLevel.OOB_CONFIRMED,
                 elevated_until=NOW + timedelta(minutes=5))
    assert require_tier(s, Tier.T2, NOW).allowed


# --- lockout ------------------------------------------------------------------

def test_lockout_blocks_t2_and_above_but_not_reads() -> None:
    """A locked-out owner must still be able to find out what happened."""
    s = _session(level=AuthLevel.ELEVATED,
                 elevated_until=NOW + timedelta(minutes=5),
                 locked_until=NOW + timedelta(minutes=10))
    assert is_locked(s, NOW)

    assert require_tier(s, Tier.T0, NOW).allowed
    assert require_tier(s, Tier.T1, NOW).allowed

    for tier in (Tier.T2, Tier.T3):
        decision = require_tier(s, tier, NOW)
        assert not decision.allowed and decision.locked, tier


def test_lockout_releases_when_it_expires() -> None:
    s = _session(level=AuthLevel.ELEVATED,
                 elevated_until=NOW + timedelta(minutes=30),
                 locked_until=NOW + timedelta(minutes=10))
    later = NOW + timedelta(minutes=11)
    assert not is_locked(s, later)
    assert require_tier(s, Tier.T2, later).allowed


def test_decision_always_explains_itself() -> None:
    s = _session(level=AuthLevel.BOUND)
    for tier in Tier:
        decision: AuthDecision = require_tier(s, tier, NOW)
        assert decision.reason.strip()
        assert decision.tier is tier
