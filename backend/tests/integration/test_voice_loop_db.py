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
    # Exactly the stages the live turn could not run.
    assert set(row.stages) == {"strategize", "pre_critic", "post_critic",
                               "reflect", "decide"}
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
