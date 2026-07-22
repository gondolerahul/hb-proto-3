"""Inc 3 / AUTH — bindings, elevation, lockout and the T3 leg against a live DB.

The pure policy is pinned in ``tests/unit/test_inward_auth_{tiers,sessions}.py``;
what needs a database is everything that persists: the enrollment handshake,
the OTP burn, the lockout write plus its fan-out alerts, and the both-legs-or-
nothing out-of-band flow. ``needs_db``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.inward_auth import bindings as binding_service
from src.ai.inward_auth import oob as oob_service
from src.ai.inward_auth import step_up as totp_service
from src.ai.inward_auth.models import (
    AuthLevel,
    ChannelKind,
    normalise_address,
)
from src.ai.inward_auth.sessions import (
    effective_level,
    elevate,
    get_or_create_session,
    is_locked,
    record_failed_stepup,
    require_tier,
)
from src.ai.inward_auth.tiers import Tier
from src.ai.signals.models import Signal, SignalTypes
from src.common.config import settings

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def authn_tenant():
    """A company with two users' worth of nothing — just the FK targets."""
    import os

    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, uid = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"authn-test-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO users (id, email, full_name, hashed_password, company_id, "
                 "role, is_active, is_verified, created_at, updated_at) "
                 "VALUES (:id, :e, 'AUTH Test Owner', 'x', :c, 'tenant_admin', "
                 "true, true, now(), now())"),
            {"id": str(uid), "e": f"authn-{uid.hex[:8]}@example.test", "c": str(cid)})
        await s.commit()
    try:
        yield cid, uid
    finally:
        async with AsyncSessionLocal() as s:
            for tbl in ("oob_confirmations", "webauthn_challenges",
                        "webauthn_credentials", "totp_secrets"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE user_id = :u"), {"u": str(uid)})
            for tbl in ("account_manager_sessions", "channel_bindings", "signals"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


# ── channel bindings (T5) ─────────────────────────────────────────────────────

async def test_enrollment_handshake_binds_only_after_the_code_is_proved(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        started = await binding_service.begin_enrollment(
            db, company_id=cid, user_id=uid,
            channel_kind=ChannelKind.WHATSAPP, address="+91 98765 43210")
        await db.commit()

    assert started.ok and started.otp is not None

    # Until the code is proved the address must not resolve — an unverified
    # row is a claim, not a binding.
    async with AsyncSessionLocal() as db:
        assert await binding_service.resolve_inbound(
            db, company_id=cid, channel_kind=ChannelKind.WHATSAPP,
            address="+919876543210") is None

    async with AsyncSessionLocal() as db:
        bad = await binding_service.confirm_enrollment(
            db, company_id=cid, user_id=uid,
            binding_id=started.binding_id, code="000000")
        await db.commit()
    assert not bad.ok

    async with AsyncSessionLocal() as db:
        good = await binding_service.confirm_enrollment(
            db, company_id=cid, user_id=uid,
            binding_id=started.binding_id, code=started.otp)
        await db.commit()
    assert good.ok

    # Now it resolves, and formatting noise does not matter.
    async with AsyncSessionLocal() as db:
        resolved = await binding_service.resolve_inbound(
            db, company_id=cid, channel_kind=ChannelKind.WHATSAPP,
            address="+919876543210")
        await db.commit()
    assert resolved is not None and resolved.user_id == uid

    # ...but a different dialling format is a different address, on purpose:
    # equating them means guessing a country code, and a wrong guess binds
    # someone else's number to this account.
    async with AsyncSessionLocal() as db:
        assert await binding_service.resolve_inbound(
            db, company_id=cid, channel_kind=ChannelKind.WHATSAPP,
            address="09876543210") is None


async def test_the_otp_is_burned_on_use(authn_tenant):
    """A code that still works after it worked is a replayable second factor."""
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        started = await binding_service.begin_enrollment(
            db, company_id=cid, user_id=uid,
            channel_kind=ChannelKind.EMAIL, address="Owner@Example.Test")
        await db.commit()

    async with AsyncSessionLocal() as db:
        assert (await binding_service.confirm_enrollment(
            db, company_id=cid, user_id=uid,
            binding_id=started.binding_id, code=started.otp)).ok
        await db.commit()

    async with AsyncSessionLocal() as db:
        replay = await binding_service.confirm_enrollment(
            db, company_id=cid, user_id=uid,
            binding_id=started.binding_id, code=started.otp)
        await db.commit()
    assert not replay.ok


async def test_enrollment_emits_the_otp_over_the_signal_seam(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await binding_service.begin_enrollment(
            db, company_id=cid, user_id=uid,
            channel_kind=ChannelKind.EMAIL, address="owner@example.test")
        await db.commit()

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Signal).where(
                Signal.company_id == cid,
                Signal.type == SignalTypes.AUTHN_CHANNEL_OTP))).scalars().all()
    assert len(rows) == 1
    assert rows[0].payload["address"] == "owner@example.test"


async def test_revoked_binding_stops_resolving(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        started = await binding_service.begin_enrollment(
            db, company_id=cid, user_id=uid,
            channel_kind=ChannelKind.VOICE, address="+1 555 0100")
        await binding_service.confirm_enrollment(
            db, company_id=cid, user_id=uid,
            binding_id=started.binding_id, code=started.otp)
        await db.commit()

    async with AsyncSessionLocal() as db:
        assert await binding_service.revoke_binding(
            db, user_id=uid, binding_id=started.binding_id)
        await db.commit()

    async with AsyncSessionLocal() as db:
        assert await binding_service.resolve_inbound(
            db, company_id=cid, channel_kind=ChannelKind.VOICE,
            address="+15550100") is None


async def test_console_channel_cannot_be_enrolled(authn_tenant):
    """The console is bound by login; an OTP handshake there means nothing."""
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await binding_service.begin_enrollment(
            db, company_id=cid, user_id=uid,
            channel_kind=ChannelKind.CONSOLE, address="console")
        await db.rollback()
    assert not result.ok


# ── sessions, elevation, lockout (T3) ─────────────────────────────────────────

async def test_console_session_is_born_bound_and_other_channels_are_not(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        console = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        whatsapp = await get_or_create_session(
            db, company_id=cid, channel_kind=ChannelKind.WHATSAPP,
            channel_address="+15550111")
        await db.commit()

        assert effective_level(console) == AuthLevel.BOUND
        assert effective_level(whatsapp) == AuthLevel.NONE
        # An unbound channel cannot even read tenant state.
        assert not require_tier(whatsapp, Tier.T1).allowed


async def test_get_or_create_session_is_idempotent(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        first = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await db.commit()
        first_id = first.id

    async with AsyncSessionLocal() as db:
        second = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await db.commit()
    assert second.id == first_id


async def test_elevation_persists_and_then_expires(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="totp")
        await db.commit()

    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        assert require_tier(session, Tier.T2).allowed
        # Past the window the same stored row no longer authorises anything.
        later = datetime.utcnow() + timedelta(
            minutes=settings.INWARD_AUTH_ELEVATION_MINUTES + 1)
        assert not require_tier(session, Tier.T2, later).allowed
        await db.commit()


async def test_lockout_after_repeated_failures_alerts_every_channel(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    # Two verified channels so the fan-out has somewhere to go.
    async with AsyncSessionLocal() as db:
        for kind, addr in ((ChannelKind.EMAIL, "owner@example.test"),
                           (ChannelKind.WHATSAPP, "+15550122")):
            started = await binding_service.begin_enrollment(
                db, company_id=cid, user_id=uid, channel_kind=kind, address=addr)
            await binding_service.confirm_enrollment(
                db, company_id=cid, user_id=uid,
                binding_id=started.binding_id, code=started.otp)
        await db.commit()

    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="totp")

        locked = False
        for _ in range(settings.INWARD_AUTH_MAX_FAILED_STEPUPS):
            locked = await record_failed_stepup(db, session)
        assert locked and is_locked(session)

        # The lock must also drop the elevation it was holding.
        assert effective_level(session) == AuthLevel.BOUND
        assert not require_tier(session, Tier.T2).allowed
        # ...but reads still work, so the owner can see what happened.
        assert require_tier(session, Tier.T1).allowed

        alerted = await binding_service.alert_all_channels(
            db, company_id=cid, user_id=uid,
            event="step_up_lockout", detail="test lockout")
        await db.commit()

    assert alerted == 2
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Signal).where(
                Signal.company_id == cid,
                Signal.type == SignalTypes.AUTHN_SECURITY_ALERT))).scalars().all()
    assert len(rows) == 2


# ── TOTP (T3) ─────────────────────────────────────────────────────────────────

async def test_totp_enroll_confirm_and_verify(authn_tenant):
    import pyotp

    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        assert not await totp_service.has_totp(db, uid)
        enrollment = await totp_service.begin_totp_enrollment(
            db, user_id=uid, account_label="owner@example.test")
        await db.commit()

    totp = pyotp.TOTP(enrollment.secret)

    # An unconfirmed authenticator is not a factor yet.
    async with AsyncSessionLocal() as db:
        assert not await totp_service.has_totp(db, uid)
        assert not (await totp_service.verify_totp(db, user_id=uid, code=totp.now())).ok
        await db.commit()

    async with AsyncSessionLocal() as db:
        assert (await totp_service.confirm_totp_enrollment(
            db, user_id=uid, code=totp.now())).ok
        await db.commit()

    async with AsyncSessionLocal() as db:
        assert await totp_service.has_totp(db, uid)
        # Confirmation consumed the current slot, so verify from a later one.
        future = datetime.utcnow().timestamp() + 2 * totp_service.TOTP_PERIOD_SECONDS
        assert (await totp_service.verify_totp(
            db, user_id=uid, code=totp.at(int(future)), at=future)).ok
        await db.commit()


async def test_totp_code_cannot_be_replayed_in_a_later_slot(authn_tenant):
    """The drift window would otherwise let a captured code work twice."""
    import pyotp

    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        enrollment = await totp_service.begin_totp_enrollment(
            db, user_id=uid, account_label="owner@example.test")
        await db.commit()

    totp = pyotp.TOTP(enrollment.secret)
    base = datetime.utcnow().timestamp()

    async with AsyncSessionLocal() as db:
        await totp_service.confirm_totp_enrollment(db, user_id=uid, code=totp.at(int(base)))
        await db.commit()

    # The very code just used, presented one slot later — still inside the
    # drift window, and it must be refused.
    replay_at = base + totp_service.TOTP_PERIOD_SECONDS
    async with AsyncSessionLocal() as db:
        result = await totp_service.verify_totp(
            db, user_id=uid, code=totp.at(int(base)), at=replay_at)
        await db.commit()
    assert not result.ok and "replay" in result.reason


# ── T3 out-of-band leg (T6) ───────────────────────────────────────────────────

async def _verified_binding(db, cid, uid, kind, address):
    started = await binding_service.begin_enrollment(
        db, company_id=cid, user_id=uid, channel_kind=kind, address=address)
    await binding_service.confirm_enrollment(
        db, company_id=cid, user_id=uid,
        binding_id=started.binding_id, code=started.otp)
    return started.binding_id


async def test_oob_fails_closed_without_a_second_channel(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="passkey")
        challenge = await oob_service.issue_challenge(
            db, session, command_ref="loop.kill_switch")
        await db.rollback()

    assert not challenge.ok
    assert "no second registered channel" in challenge.reason


async def test_oob_requires_the_step_up_leg_first(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _verified_binding(db, cid, uid, ChannelKind.WHATSAPP, "+15550133")
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        challenge = await oob_service.issue_challenge(
            db, session, command_ref="loop.kill_switch")
        await db.rollback()

    assert not challenge.ok
    assert "step-up" in challenge.reason


async def test_oob_both_legs_confirm_and_reach_t3(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _verified_binding(db, cid, uid, ChannelKind.WHATSAPP, "+15550144")
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="passkey")
        # Elevated alone is not enough for T3.
        assert not require_tier(session, Tier.T3).allowed

        challenge = await oob_service.issue_challenge(
            db, session, command_ref="loop.kill_switch")
        await db.commit()

    assert challenge.ok and challenge.channel_kind == ChannelKind.WHATSAPP

    async with AsyncSessionLocal() as db:
        # A nonce issued for one command must not authorise another.
        wrong = await oob_service.confirm(
            db, company_id=cid, user_id=uid, challenge_id=challenge.challenge_id,
            command_ref="payout.release", nonce=challenge.nonce)
        assert not wrong.ok and "different command" in wrong.reason

        result = await oob_service.confirm(
            db, company_id=cid, user_id=uid, challenge_id=challenge.challenge_id,
            command_ref="loop.kill_switch", nonce=challenge.nonce)
        await db.commit()
    assert result.ok

    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        assert effective_level(session) == AuthLevel.OOB_CONFIRMED
        assert require_tier(session, Tier.T3).allowed
        await db.commit()


async def test_oob_nonce_is_single_use(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _verified_binding(db, cid, uid, ChannelKind.WHATSAPP, "+15550155")
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="passkey")
        challenge = await oob_service.issue_challenge(
            db, session, command_ref="loop.kill_switch")
        await db.commit()

    async with AsyncSessionLocal() as db:
        assert (await oob_service.confirm(
            db, company_id=cid, user_id=uid, challenge_id=challenge.challenge_id,
            command_ref="loop.kill_switch", nonce=challenge.nonce)).ok
        await db.commit()

    async with AsyncSessionLocal() as db:
        again = await oob_service.confirm(
            db, company_id=cid, user_id=uid, challenge_id=challenge.challenge_id,
            command_ref="loop.kill_switch", nonce=challenge.nonce)
        await db.commit()
    assert not again.ok and "already used" in again.reason


async def test_oob_is_emitted_to_the_second_channel_not_the_issuing_one(authn_tenant):
    cid, uid = authn_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _verified_binding(db, cid, uid, ChannelKind.EMAIL, "owner@example.test")
        session = await get_or_create_session(
            db, company_id=cid, user_id=uid, channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="passkey")
        challenge = await oob_service.issue_challenge(
            db, session, command_ref="payout.release")
        await db.commit()

    assert challenge.ok
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Signal).where(
                Signal.company_id == cid,
                Signal.type == SignalTypes.AUTHN_OOB_CONFIRM))).scalars().all()
    assert len(rows) == 1
    payload = rows[0].payload
    assert payload["channel_kind"] == ChannelKind.EMAIL
    assert payload["channel_kind"] != ChannelKind.CONSOLE
    assert payload["command_ref"] == "payout.release"


def test_address_normalisation_strips_formatting_but_not_dialling_context():
    assert normalise_address(ChannelKind.EMAIL, " Owner@Example.Test ") == "owner@example.test"
    assert normalise_address(ChannelKind.WHATSAPP, "+91 98765 43210") == "919876543210"
    assert normalise_address(ChannelKind.WHATSAPP, "91-98765-43210") == "919876543210"
    assert normalise_address(ChannelKind.VOICE, "(555) 010-0") == "5550100"
    # National and E.164 forms stay distinct — see normalise_address.
    assert (normalise_address(ChannelKind.WHATSAPP, "09876543210")
            != normalise_address(ChannelKind.WHATSAPP, "+919876543210"))
