"""Inc-3 VOICE — identity, handoff and the deferred queue on a live DB.

The pure halves (the realtime profile, the live gate, the ceiling rules,
transcript summarisation) are pinned in ``tests/unit``. What needs a database
is what persists: resolving a caller to a binding, a handoff that survives for
the receiving agent to read, and the post-call queue's claim semantics.
``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.inward_auth import bindings as binding_service
from src.ai.inward_auth.models import AuthLevel, ChannelKind
from src.ai.inward_auth.sessions import elevate
from src.ai.inward_auth.tiers import Tier
from src.ai.signals.models import Signal, SignalTrust, SignalTypes
from src.ai.signals.voice_inbound import company_subscribes_voice, emit_voice_inbound
from src.ai.voice_loop.deferred import (
    MAX_ATTEMPTS,
    claim_next,
    mark_done,
    mark_failed,
    pending_count,
    queue_deferred_run,
)
from src.ai.voice_loop.handoff import HandoffContext, latest_handoff, record_handoff
from src.ai.voice_loop.identity import identify_caller, voice_tier_ceiling
from src.ai.voice_loop.models import DeferredRunStatus, VoiceDeferredRun

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def voice_tenant():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, uid = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"voice-test-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO users (id, email, full_name, hashed_password, company_id, "
                 "role, is_active, is_verified, created_at, updated_at) "
                 "VALUES (:id, :e, 'Voice Test Owner', 'x', :c, 'tenant_admin', "
                 "true, true, now(), now())"),
            {"id": str(uid), "e": f"voice-{uid.hex[:8]}@example.test", "c": str(cid)})
        await s.commit()
    try:
        yield cid, uid
    finally:
        async with AsyncSessionLocal() as s:
            for tbl in ("voice_deferred_runs", "voice_handoffs",
                        "account_manager_sessions", "channel_bindings",
                        "trigger_registry", "signals"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


async def _register_number(db, cid, uid, number):
    started = await binding_service.begin_enrollment(
        db, company_id=cid, user_id=uid,
        channel_kind=ChannelKind.VOICE, address=number)
    await binding_service.confirm_enrollment(
        db, company_id=cid, user_id=uid,
        binding_id=started.binding_id, code=started.otp)
    return started.binding_id


# --- caller identity ----------------------------------------------------------

async def test_an_unregistered_number_is_unbound(voice_tenant):
    cid, _ = voice_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        caller = await identify_caller(
            db, company_id=cid, from_number="+1 555 0199")
        await db.commit()

    assert not caller.bound
    assert caller.user_id is None
    assert caller.auth_level == AuthLevel.NONE
    # T0 still works — she answers the phone and helps generally.
    assert voice_tier_ceiling(caller, Tier.T0).allowed
    assert not voice_tier_ceiling(caller, Tier.T1).allowed


async def test_a_registered_number_resolves_to_bound_but_no_further(voice_tenant):
    cid, uid = voice_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _register_number(db, cid, uid, "+15550100")
        await db.commit()

    async with AsyncSessionLocal() as db:
        caller = await identify_caller(db, company_id=cid, from_number="+1 555 0100")
        await db.commit()

    assert caller.bound and caller.user_id == uid
    assert caller.auth_level == AuthLevel.BOUND
    assert voice_tier_ceiling(caller, Tier.T1).allowed
    # Bound is as far as a phone call goes on its own.
    assert not voice_tier_ceiling(caller, Tier.T2).allowed


async def test_an_elevation_earned_elsewhere_does_not_reach_the_phone(voice_tenant):
    """The ceiling is a channel property, not a session one — otherwise a
    console step-up would silently authorise the caller's next phone call."""
    cid, uid = voice_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _register_number(db, cid, uid, "+15550101")
        await db.commit()

    async with AsyncSessionLocal() as db:
        caller = await identify_caller(db, company_id=cid, from_number="+15550101")
        await elevate(db, caller.session, method="passkey")
        await db.commit()

        assert caller.auth_level == AuthLevel.ELEVATED
        assert not voice_tier_ceiling(caller, Tier.T2).allowed
        assert not voice_tier_ceiling(caller, Tier.T3).allowed


async def test_a_revoked_number_stops_resolving(voice_tenant):
    cid, uid = voice_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        binding_id = await _register_number(db, cid, uid, "+15550102")
        await db.commit()

    async with AsyncSessionLocal() as db:
        await binding_service.revoke_binding(db, user_id=uid, binding_id=binding_id)
        await db.commit()

    async with AsyncSessionLocal() as db:
        caller = await identify_caller(db, company_id=cid, from_number="+15550102")
        await db.commit()
    assert not caller.bound


# --- the voice.inbound producer ----------------------------------------------

async def test_an_unsubscribed_tenant_keeps_its_legacy_path(voice_tenant):
    """The cutover seam: no trigger, no signal, call proceeds untouched."""
    cid, _ = voice_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        assert not await company_subscribes_voice(db, cid)
        result = await emit_voice_inbound(
            db, cid, from_number="+15550103", to_number="+15550200",
            call_sid="CA-legacy")
        await db.commit()
    assert result is None


async def test_a_subscribed_tenant_emits_a_counterparty_trust_signal(voice_tenant):
    cid, _ = voice_tenant
    from src.ai.signals.models import TriggerRegistration
    from src.ai.orm.entity import HierarchicalEntity
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        entity = HierarchicalEntity(
            company_id=cid, name="kar-01-voice-gateway",
            display_name="Voice Gateway", type="AGENT", status="ACTIVE")
        db.add(entity)
        await db.flush()
        db.add(TriggerRegistration(
            company_id=cid, process_entity_id=entity.id,
            type_pattern="voice.inbound", enabled=True))
        await db.commit()
        entity_id = entity.id

    try:
        async with AsyncSessionLocal() as db:
            assert await company_subscribes_voice(db, cid)
            signal_id = await emit_voice_inbound(
                db, cid, from_number="+1 555 0104", to_number="+15550200",
                call_sid="CA-sub-1")
        assert signal_id is not None

        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(Signal).where(Signal.id == signal_id))).scalars().one()
        # A caller's words are counterparty data, never instructions.
        assert row.trust == SignalTrust.COUNTERPARTY
        assert row.type == SignalTypes.VOICE_INBOUND
        assert row.payload["from"] == "15550104"   # digits-only, matches bindings

        # A carrier retry must not start a second conversation.
        async with AsyncSessionLocal() as db:
            again = await emit_voice_inbound(
                db, cid, from_number="+15550104", to_number="+15550200",
                call_sid="CA-sub-1")
        assert again is None
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM trigger_registry WHERE company_id = :c"),
                             {"c": str(cid)})
            await db.execute(text("DELETE FROM hierarchical_entities WHERE id = :e"),
                             {"e": str(entity_id)})
            await db.commit()


# --- handoff ------------------------------------------------------------------

async def test_a_handoff_carries_context_and_cannot_raise_the_ceiling(voice_tenant):
    cid, uid = voice_tenant
    from src.ai.orm.entity import HierarchicalEntity
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        to_entity = HierarchicalEntity(
            company_id=cid, name="agt-038-ar", display_name="AR Agent",
            type="AGENT", status="ACTIVE")
        db.add(to_entity)
        await db.commit()
        to_id = to_entity.id

    try:
        async with AsyncSessionLocal() as db:
            await record_handoff(
                db, company_id=cid,
                context=HandoffContext(
                    call_sid="CA-handoff",
                    to_entity_id=to_id,
                    reason="billing question",
                    context_summary="caller: my invoice is wrong",
                    resolved_records=[{"label": "invoice INV-42"}],
                    # Asking for more authority than the call has must not grant it.
                    tier_ceiling=Tier.T3,
                    caller_user_id=uid,
                ),
                current_ceiling=Tier.T1,
            )
            await db.commit()

        async with AsyncSessionLocal() as db:
            row = await latest_handoff(db, company_id=cid, call_sid="CA-handoff")

        assert row is not None
        assert row.tier_ceiling == "T1", "a handoff raised the tier ceiling"
        assert row.resolved_records == [{"label": "invoice INV-42"}]
        assert "invoice is wrong" in row.context_summary
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM voice_handoffs WHERE company_id = :c"),
                             {"c": str(cid)})
            await db.execute(text("DELETE FROM hierarchical_entities WHERE id = :e"),
                             {"e": str(to_id)})
            await db.commit()


# --- the deferred queue -------------------------------------------------------

def _transcript(n: int = 5):
    return [{"role": "caller" if i % 2 == 0 else "agent", "content": f"turn {i}"}
            for i in range(n)]


async def test_a_finished_call_queues_the_deferred_stages(voice_tenant):
    cid, _ = voice_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        row = await queue_deferred_run(
            db, company_id=cid, call_sid="CA-defer-1", transcript=_transcript())
        await db.commit()

    assert row is not None
    # The stages the live turn could not run — corrected in Inc-4. Strategize
    # and Decide are gone: you cannot plan or decide about a call that ended.
    assert set(row.stages) == {"pre_critic", "post_critic", "reflect"}
    assert "strategize" not in row.stages
    assert "decide" not in row.stages
    assert "policy_gate" not in row.stages, "governance ran inline; nothing to defer"
    assert "act" not in row.stages


async def test_a_call_too_short_to_reflect_on_is_not_queued(voice_tenant):
    """A wrong number or a hangup on the greeting must not spend a model call."""
    cid, _ = voice_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        row = await queue_deferred_run(
            db, company_id=cid, call_sid="CA-short", transcript=_transcript(1))
        await db.commit()
    assert row is None


async def test_a_repeated_end_of_call_webhook_does_not_double_queue(voice_tenant):
    cid, _ = voice_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        assert await queue_deferred_run(
            db, company_id=cid, call_sid="CA-dupe", transcript=_transcript())
        await db.commit()

    async with AsyncSessionLocal() as db:
        again = await queue_deferred_run(
            db, company_id=cid, call_sid="CA-dupe", transcript=_transcript())
        await db.commit()
    assert again is None


async def test_claim_marks_running_and_completes(voice_tenant):
    cid, _ = voice_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await queue_deferred_run(
            db, company_id=cid, call_sid="CA-claim", transcript=_transcript())
        await db.commit()

    async with AsyncSessionLocal() as db:
        claimed = await claim_next(db, company_id=cid)
        assert claimed is not None
        assert claimed.status == DeferredRunStatus.RUNNING
        await mark_done(db, claimed)
        await db.commit()

    async with AsyncSessionLocal() as db:
        assert await pending_count(db, cid) == 0
        assert await claim_next(db, company_id=cid) is None


async def test_a_failing_run_retries_then_gives_up_without_blocking(voice_tenant):
    """Bounded: a transcript that cannot be reflected on will not become
    reflectable, and it must not be retried forever."""
    cid, _ = voice_tenant
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await queue_deferred_run(
            db, company_id=cid, call_sid="CA-fail", transcript=_transcript())
        await db.commit()

    for _ in range(MAX_ATTEMPTS):
        async with AsyncSessionLocal() as db:
            claimed = await claim_next(db, company_id=cid)
            assert claimed is not None
            await mark_failed(db, claimed, "model unavailable")
            await db.commit()

    async with AsyncSessionLocal() as db:
        assert await claim_next(db, company_id=cid) is None
        row = (await db.execute(
            select(VoiceDeferredRun)
            .where(VoiceDeferredRun.call_sid == "CA-fail"))).scalars().one()
    assert row.status == DeferredRunStatus.FAILED
    assert row.error == "model unavailable"


# --- draining and reaping (Inc-4 PRAGYA-RT T6) -------------------------------

async def test_the_reaper_bounds_the_table(voice_tenant):
    """Inc-3 left this queue filling with nothing to empty it. Draining alone
    would only convert an unbounded queue into an unbounded archive."""
    from datetime import datetime, timedelta

    from src.ai.voice_loop.deferred_runner import queue_depth, reap_finished
    from src.common.database import AsyncSessionLocal

    cid, _ = voice_tenant
    async with AsyncSessionLocal() as db:
        row = await queue_deferred_run(
            db, company_id=cid, call_sid="CA-reap", transcript=_transcript())
        assert row is not None
        row.status = DeferredRunStatus.DONE
        row.completed_at = datetime.utcnow() - timedelta(days=60)
        await db.commit()

    async with AsyncSessionLocal() as db:
        before = await queue_depth(db)
        reaped = await reap_finished(db)
        await db.commit()
        after = await queue_depth(db)

    assert reaped >= 1
    assert after < before


async def test_the_reaper_leaves_unfinished_work_alone(voice_tenant):
    """However old a pending row looks, it has not been reflected on yet."""
    from datetime import datetime, timedelta

    from src.ai.voice_loop.deferred_runner import reap_finished
    from src.common.database import AsyncSessionLocal

    cid, _ = voice_tenant
    async with AsyncSessionLocal() as db:
        row = await queue_deferred_run(
            db, company_id=cid, call_sid="CA-old-pending",
            transcript=_transcript())
        assert row is not None
        row.created_at = datetime.utcnow() - timedelta(days=90)
        await db.commit()

    async with AsyncSessionLocal() as db:
        await reap_finished(db)
        await db.commit()

    async with AsyncSessionLocal() as db:
        survivor = (await db.execute(
            select(VoiceDeferredRun).where(
                VoiceDeferredRun.call_sid == "CA-old-pending"))).scalars().first()
    assert survivor is not None
    assert survivor.status == DeferredRunStatus.PENDING


async def test_a_drained_run_records_the_corrected_stage_set(voice_tenant, monkeypatch):
    """Post-Critic and Reflect only — Strategize and Decide were an Inc-3
    error and running them post-hoc would be theatre."""
    import src.ai.voice_loop.deferred_runner as runner
    from src.common.database import AsyncSessionLocal

    cid, _ = voice_tenant

    async def _fake_run(db, row):
        return {"stages": ["post_critic", "reflect"],
                "summary": "caller asked about an invoice", "outcome": "resolved"}

    monkeypatch.setattr(runner, "run_deferred", _fake_run)

    async with AsyncSessionLocal() as db:
        await queue_deferred_run(
            db, company_id=cid, call_sid="CA-drain", transcript=_transcript())
        await db.commit()

    async with AsyncSessionLocal() as db:
        stats = await runner.drain_batch(db, limit=5)

    assert stats["done"] >= 1
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(VoiceDeferredRun).where(
                VoiceDeferredRun.call_sid == "CA-drain"))).scalars().one()
    assert row.status == DeferredRunStatus.DONE
    assert set(row.stages) == {"post_critic", "reflect"}
    assert "strategize" not in row.stages
    assert "decide" not in row.stages


async def test_a_failing_drain_does_not_invalidate_the_call(voice_tenant, monkeypatch):
    """The conversation happened and was governed inline. Reflection failing
    afterwards costs learning, not correctness."""
    import src.ai.voice_loop.deferred_runner as runner
    from src.common.database import AsyncSessionLocal

    cid, _ = voice_tenant

    async def _boom(db, row):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(runner, "run_deferred", _boom)

    async with AsyncSessionLocal() as db:
        await queue_deferred_run(
            db, company_id=cid, call_sid="CA-drain-fail",
            transcript=_transcript())
        await db.commit()

    async with AsyncSessionLocal() as db:
        stats = await runner.drain_batch(db, limit=3)
    assert stats["failed"] >= 1

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(VoiceDeferredRun).where(
                VoiceDeferredRun.call_sid == "CA-drain-fail"))).scalars().one()
    # Retried, not abandoned on the first failure.
    assert row.status in (DeferredRunStatus.PENDING, DeferredRunStatus.FAILED)
    assert "model unavailable" in (row.error or "")


# --- the number is the routing discriminator (Inc-4 T5, decision 5) ----------

async def test_a_number_assigned_to_pragya_routes_to_the_inward_face(voice_tenant):
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.pragya.channels.routing import (
        VoiceFace,
        assign_pragya_number,
        route_for_number,
    )
    from src.common.database import AsyncSessionLocal
    from src.voice.phone_pool_models import PhoneNumber

    cid, _ = voice_tenant
    async with AsyncSessionLocal() as db:
        db.add(HierarchicalEntity(
            company_id=cid, name="pragya", display_name="Pragya",
            type="AGENT", status="ACTIVE"))
        db.add(PhoneNumber(
            phone_number="+919900000001", provider="twilio",
            country_code="+91", status="available", is_active=True))
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            await assign_pragya_number(
                db, company_id=cid, phone_number="+919900000001")
            await db.commit()

        async with AsyncSessionLocal() as db:
            # Carrier format differences must not change the routing decision.
            for dialled in ("+919900000001", "919900000001", "+91 9900-000001"):
                route = await route_for_number(db, dialled)
                assert route.face is VoiceFace.PRAGYA, dialled
                assert route.company_id == cid
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM phone_numbers WHERE phone_number = :p"),
                             {"p": "+919900000001"})
            await db.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                             {"c": str(cid)})
            await db.commit()


async def test_a_business_number_routes_to_the_outward_gateway(voice_tenant):
    """KAR-01 keeps realtime (decision 4) — the two faces must never collide."""
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.pragya.channels.routing import VoiceFace, route_for_number
    from src.common.database import AsyncSessionLocal
    from src.voice.phone_pool_models import PhoneNumber

    cid, _ = voice_tenant
    async with AsyncSessionLocal() as db:
        gateway = HierarchicalEntity(
            company_id=cid, name="kar-01-voice-gateway",
            display_name="Voice Gateway", type="AGENT", status="ACTIVE")
        db.add(gateway)
        db.add(HierarchicalEntity(
            company_id=cid, name="pragya", display_name="Pragya",
            type="AGENT", status="ACTIVE"))
        await db.flush()
        db.add(PhoneNumber(
            phone_number="+919900000002", provider="twilio",
            country_code="+91", status="assigned", is_active=True,
            company_id=cid, agent_id=gateway.id))
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            route = await route_for_number(db, "+919900000002")
        assert route.face is VoiceFace.GATEWAY
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM phone_numbers WHERE phone_number = :p"),
                             {"p": "+919900000002"})
            await db.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                             {"c": str(cid)})
            await db.commit()


async def test_an_unassigned_number_routes_to_neither_face(voice_tenant):
    """Answering an unowned line as an account manager would offer a tenant
    conversation on a number nobody holds."""
    from src.ai.pragya.channels.routing import VoiceFace, route_for_number
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        route = await route_for_number(db, "+919900009999")
    assert route.face is VoiceFace.UNKNOWN
    assert route.company_id is None


async def test_assigning_pragyas_number_refuses_without_a_pragya_entity(voice_tenant):
    """A number routed inward with nothing behind it answers and then cannot
    hold a conversation."""
    from src.ai.pragya.channels.routing import assign_pragya_number
    from src.common.database import AsyncSessionLocal
    from src.voice.phone_pool_models import PhoneNumber

    cid, _ = voice_tenant
    async with AsyncSessionLocal() as db:
        db.add(PhoneNumber(
            phone_number="+919900000003", provider="twilio",
            country_code="+91", status="available", is_active=True))
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            with pytest.raises(ValueError, match="Pragya entity"):
                await assign_pragya_number(
                    db, company_id=cid, phone_number="+919900000003")
            await db.rollback()
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM phone_numbers WHERE phone_number = :p"),
                             {"p": "+919900000003"})
            await db.commit()


async def test_voice_is_refused_when_the_speech_skus_are_unconfigured(
        voice_tenant, monkeypatch):
    """Checked before answering, not discovered mid-call.

    The missing SKU is **injected**, not assumed from an empty database. This
    test used to call `voice_ready` on a bare tenant and assert it refused —
    which passed only while no speech rows existed *anywhere*, because
    `_resolve` deliberately falls back to the platform company's row. It broke
    the day voice was actually configured, i.e. the day the feature started
    working, which is the worst possible time for a test to fail.

    A test that asserts the absence of global configuration is testing the
    environment. This one tests the logic.
    """
    import src.ai.pragya.channels.speech as speech
    from src.ai.pragya.channels.speech import SpeechConfigError, voice_ready
    from src.common.database import AsyncSessionLocal

    cid, _ = voice_tenant

    async def _missing(db, company_id, sku):
        raise SpeechConfigError(f"no active {sku!r} entry")

    monkeypatch.setattr(speech, "_resolve", _missing)

    async with AsyncSessionLocal() as db:
        ready, why = await voice_ready(db, cid)

    assert not ready
    assert "not configured" in why
    # Every missing SKU is named, so an operator is told what to add rather
    # than that something is wrong.
    for sku in (speech.ASR_SKU, speech.TTS_SKU_IN, speech.TTS_SKU_OUT):
        assert sku in why, sku


@pytest.mark.asyncio
async def test_a_half_configured_tenant_is_refused_not_half_accepted(
        voice_tenant, monkeypatch):
    """The `-in` row missing is *misconfigured*, not partially configured.

    Gemini TTS bills per token both ways. A tenant with only the output row
    would still synthesise speech and would still be billed — just not metered
    on the prompt side, silently and only in the direction that favours nobody.
    """
    import src.ai.pragya.channels.speech as speech
    from src.ai.pragya.channels.speech import SpeechConfigError, voice_ready
    from src.common.database import AsyncSessionLocal

    cid, _ = voice_tenant

    async def _only_in_missing(db, company_id, sku):
        if sku == speech.TTS_SKU_IN:
            raise SpeechConfigError(f"no active {sku!r} entry")
        return object()

    monkeypatch.setattr(speech, "_resolve", _only_in_missing)

    async with AsyncSessionLocal() as db:
        ready, why = await voice_ready(db, cid)

    assert not ready
    assert speech.TTS_SKU_IN in why
    assert speech.TTS_SKU_OUT not in why
