"""Inc 1 / SIG — DB-backed signal-bus behavior (technical doc §18).

Covers the properties the design promises:
  * outbox atomicity — an uncommitted emit leaves no row;
  * producer idempotency — dedupe_key double-emit yields one row;
  * claim/consume — trigger resolution spawns exactly one run;
  * parked lifecycle — no trigger → PARKED → (3 reviews) → ESCALATED,
    and a trigger registered while parked consumes on review;
  * failure path — attempts/backoff, DEAD + incident.governance at max;
  * completion audit — ``*.completed`` with no subscriber self-consumes;
  * SKIP LOCKED — two racing claimants, one winner (own connections).

All tests: ``needs_db`` (skip without Postgres).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest

from src.ai.signals.dispatcher import (
    claim_pending_batch,
    process_claimed_signal,
)
from src.ai.signals.models import (
    MAX_DISPATCH_ATTEMPTS,
    MAX_PARK_REVIEWS,
    Signal,
    SignalStatus,
    TriggerRegistration,
)
from src.ai.signals.service import emit_signal
from src.ai.signals.sweeper import review_parked
from src.ai.signals.triggers import resolve_owner

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


async def _make_entity(db, company_id: uuid.UUID, name: str = "sig-test-process"):
    from src.ai.orm.entity import HierarchicalEntity

    entity = HierarchicalEntity(
        company_id=company_id, type="PROCESS", name=name, status="ACTIVE",
    )
    db.add(entity)
    await db.flush()
    return entity


async def _make_trigger(db, company_id, entity, pattern="lead.*", priority=100):
    reg = TriggerRegistration(
        company_id=company_id,
        process_entity_id=entity.id,
        type_pattern=pattern,
        priority=priority,
    )
    db.add(reg)
    await db.flush()
    return reg


async def _emit(db, company_id, **kw):
    defaults = dict(source="connector", type="lead.inbound", trust="counterparty")
    defaults.update(kw)
    return await emit_signal(db, company_id=company_id, **defaults)


class TestOutboxAndDedupe:
    async def test_emit_lives_in_caller_transaction(self, db, test_company_id):
        sid = await _emit(db, test_company_id)
        assert sid is not None
        await db.rollback()  # caller's business transaction fails
        found = await db.get(Signal, sid)
        assert found is None, "outbox row must vanish with the caller's rollback"

    async def test_dedupe_key_is_idempotent(self, db, test_company_id):
        first = await _emit(db, test_company_id, dedupe_key="evt-123")
        second = await _emit(db, test_company_id, dedupe_key="evt-123")
        assert first is not None
        assert second is None, "duplicate external event must not create a second row"

    async def test_dedupe_scoped_per_company(self, db, test_company_id):
        from sqlalchemy import text

        other = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                "VALUES (:id, :name, 'TENANT', 'active', now(), now())"
            ),
            {"id": str(other), "name": f"sig-other-{other.hex[:8]}"},
        )
        first = await _emit(db, test_company_id, dedupe_key="evt-xyz")
        second = await _emit(db, other, dedupe_key="evt-xyz")
        assert first is not None and second is not None

    async def test_null_dedupe_keys_never_collide(self, db, test_company_id):
        assert await _emit(db, test_company_id) is not None
        assert await _emit(db, test_company_id) is not None


class TestDispatchConsume:
    async def test_signal_spawns_run_for_owning_process(self, db, test_company_id):
        from src.ai.orm.execution import ExecutionRun

        entity = await _make_entity(db, test_company_id)
        await _make_trigger(db, test_company_id, entity, "lead.*")
        sid = await _emit(db, test_company_id, payload={"subject": "hot lead"})
        await db.flush()

        signal = await db.get(Signal, sid)
        outcome = await process_claimed_signal(db, None, signal)
        assert outcome == "consumed"
        assert signal.status == SignalStatus.CONSUMED
        assert signal.owner_process_id == entity.id
        assert signal.consumed_by_run_id is not None
        assert signal.consumed_at is not None

        run = await db.get(ExecutionRun, signal.consumed_by_run_id)
        assert run is not None
        assert run.entity_id == entity.id
        assert run.input_data["signal_id"] == str(signal.id)
        assert run.input_data["signal_type"] == "lead.inbound"
        assert run.input_data["signal"]["trust"] == "counterparty"

    async def test_no_trigger_parks_with_review_timer(self, db, test_company_id):
        sid = await _emit(db, test_company_id, type="orphan.event")
        signal = await db.get(Signal, sid)
        outcome = await process_claimed_signal(db, None, signal)
        assert outcome == "parked"
        assert signal.status == SignalStatus.PARKED
        assert signal.park_review_at is not None

    async def test_archived_owner_parks(self, db, test_company_id):
        entity = await _make_entity(db, test_company_id)
        await _make_trigger(db, test_company_id, entity, "lead.*")
        entity.status = "ARCHIVED"
        await db.flush()
        sid = await _emit(db, test_company_id)
        signal = await db.get(Signal, sid)
        assert await process_claimed_signal(db, None, signal) == "parked"

    async def test_unsubscribed_completion_signal_self_consumes(self, db, test_company_id):
        sid = await _emit(db, test_company_id, type="lead.inbound.completed",
                          source="agent", trust="platform")
        signal = await db.get(Signal, sid)
        outcome = await process_claimed_signal(db, None, signal)
        assert outcome == "audited"
        assert signal.status == SignalStatus.CONSUMED
        assert signal.consumed_by_run_id is None

    async def test_resolution_priority_and_tiebreak(self, db, test_company_id):
        low = await _make_entity(db, test_company_id, "low-prio")
        high = await _make_entity(db, test_company_id, "high-prio")
        await _make_trigger(db, test_company_id, low, "lead.*", priority=10)
        await _make_trigger(db, test_company_id, high, "lead.inbound", priority=200)
        reg = await resolve_owner(db, test_company_id, "lead.inbound")
        assert reg is not None and reg.process_entity_id == high.id


class TestParkedLifecycle:
    async def test_three_unresolved_reviews_escalate(self, db, test_company_id):
        sid = await _emit(db, test_company_id, type="orphan.event")
        signal = await db.get(Signal, sid)
        await process_claimed_signal(db, None, signal)
        assert signal.status == SignalStatus.PARKED

        now = datetime.utcnow()
        for review in range(1, MAX_PARK_REVIEWS + 1):
            now = now + timedelta(seconds=1000)  # past the 15-min timer
            stats = await review_parked(db, None, now=now, company_id=test_company_id)
            if review < MAX_PARK_REVIEWS:
                assert stats["parked_repark"] == 1
        await db.refresh(signal)
        assert signal.status == SignalStatus.ESCALATED
        assert signal.attempts == MAX_PARK_REVIEWS

    async def test_late_registered_trigger_consumes_on_review(self, db, test_company_id):
        sid = await _emit(db, test_company_id, type="orphan.event")
        signal = await db.get(Signal, sid)
        await process_claimed_signal(db, None, signal)
        assert signal.status == SignalStatus.PARKED

        entity = await _make_entity(db, test_company_id)
        await _make_trigger(db, test_company_id, entity, "orphan.*")
        stats = await review_parked(
            db, None, now=datetime.utcnow() + timedelta(seconds=1000),
            company_id=test_company_id,
        )
        assert stats["parked_consumed"] == 1
        await db.refresh(signal)
        assert signal.status == SignalStatus.CONSUMED
        assert signal.owner_process_id == entity.id


class TestFailurePath:
    async def test_dispatch_failure_backs_off_then_dies(
        self, db, test_company_id, monkeypatch,
    ):
        from sqlalchemy import select as _select
        import src.ai.signals.dispatcher as dispatcher_mod

        async def _boom(*_a, **_k):
            raise RuntimeError("resolver exploded")

        monkeypatch.setattr(dispatcher_mod, "resolve_owner", _boom)

        sid = await _emit(db, test_company_id)
        # Commit the producer's transaction (savepoint-release under the test
        # fixture) so the dispatcher's failure rollback — which only spans the
        # dispatch transaction in production — can't unwind the emit itself.
        await db.commit()
        for attempt in range(1, MAX_DISPATCH_ATTEMPTS + 1):
            signal = (await db.execute(
                _select(Signal).where(Signal.id == sid)
            )).scalar_one()
            signal.park_review_at = None  # make it due despite backoff
            await db.commit()
            outcome = await process_claimed_signal(db, None, signal)
            if attempt < MAX_DISPATCH_ATTEMPTS:
                assert outcome == "retry_scheduled"

        signal = (await db.execute(
            _select(Signal).where(Signal.id == sid)
        )).scalar_one()
        assert signal.status == SignalStatus.DEAD
        assert signal.attempts == MAX_DISPATCH_ATTEMPTS
        assert "resolver exploded" in (signal.last_error or "")

        notice = (await db.execute(
            _select(Signal).where(
                Signal.company_id == test_company_id,
                Signal.type == "incident.governance",
            )
        )).scalar_one_or_none()
        assert notice is not None, "DEAD must emit incident.governance"
        assert notice.payload["signal_id"] == str(sid)

    async def test_backoff_defers_claim(self, db, test_company_id):
        sid = await _emit(db, test_company_id)
        signal = await db.get(Signal, sid)
        signal.park_review_at = datetime.utcnow() + timedelta(seconds=600)
        await db.flush()
        claimed = await claim_pending_batch(db, limit=10, company_id=test_company_id)
        assert all(s.id != sid for s in claimed), "backed-off signal must not be claimable yet"


class TestCriticalOrdering:
    async def test_critical_claims_ahead_of_older_normal(self, db, test_company_id):
        older = await _emit(db, test_company_id, type="a.normal")
        newer = await _emit(db, test_company_id, type="b.critical", urgency="critical")
        assert older is not None and newer is not None
        claimed = await claim_pending_batch(db, limit=1, company_id=test_company_id)
        assert len(claimed) == 1 and claimed[0].id == newer


@pytest.mark.slow
class TestSkipLockedRace:
    async def test_concurrent_claimants_each_signal_consumed_once(self, _engine):
        """Two workers on separate connections race over 20 signals; every
        signal is consumed exactly once (SKIP LOCKED, §18.3). Uses real
        commits, so it provisions and deletes its own rows.
        """
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession

        company_id = uuid.uuid4()
        entity_id = None
        signal_ids: list[uuid.UUID] = []
        try:
            async with AsyncSession(bind=_engine, expire_on_commit=False) as setup:
                await setup.execute(
                    text(
                        "INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                        "VALUES (:id, :name, 'TENANT', 'active', now(), now())"
                    ),
                    {"id": str(company_id), "name": f"sig-race-{company_id.hex[:8]}"},
                )
                entity = await _make_entity(setup, company_id, "race-process")
                entity_id = entity.id
                await _make_trigger(setup, company_id, entity, "race.*")
                for i in range(20):
                    sid = await emit_signal(
                        setup, company_id=company_id, source="connector",
                        type="race.event", trust="internal",
                        dedupe_key=f"race-{company_id.hex[:8]}-{i}",
                    )
                    assert sid is not None
                    signal_ids.append(sid)
                await setup.commit()

            async def worker() -> int:
                consumed = 0
                async with AsyncSession(bind=_engine, expire_on_commit=False) as s:
                    while True:
                        batch = await claim_pending_batch(s, limit=1, company_id=company_id)
                        if not batch:
                            await s.rollback()
                            break
                        outcome = await process_claimed_signal(s, None, batch[0])
                        if outcome == "consumed":
                            consumed += 1
                return consumed

            results = await asyncio.gather(worker(), worker())
            assert sum(results) == 20, f"expected 20 total consumptions, got {results}"

            async with AsyncSession(bind=_engine, expire_on_commit=False) as check:
                rows = (await check.execute(
                    text("SELECT status, consumed_by_run_id FROM signals WHERE company_id = :c"),
                    {"c": str(company_id)},
                )).all()
                assert len(rows) == 20
                assert all(r[0] == SignalStatus.CONSUMED for r in rows)
                run_ids = [r[1] for r in rows]
                assert len(set(run_ids)) == 20, "each signal must map to its own run"
        finally:
            async with AsyncSession(bind=_engine, expire_on_commit=False) as cleanup:
                await cleanup.execute(
                    text("DELETE FROM signals WHERE company_id = :c"),
                    {"c": str(company_id)},
                )
                await cleanup.execute(
                    text("DELETE FROM execution_runs WHERE company_id = :c"),
                    {"c": str(company_id)},
                )
                await cleanup.execute(
                    text("DELETE FROM trigger_registry WHERE company_id = :c"),
                    {"c": str(company_id)},
                )
                if entity_id is not None:
                    await cleanup.execute(
                        text("DELETE FROM hierarchical_entities WHERE id = :e"),
                        {"e": str(entity_id)},
                    )
                await cleanup.execute(
                    text("DELETE FROM companies WHERE id = :c"),
                    {"c": str(company_id)},
                )
                await cleanup.commit()


class TestEmailPoll:
    async def test_poll_emits_and_dedupes(self, db, test_company_id, monkeypatch):
        """Two UNSEEN mails → two email.inbound signals; a re-poll of the
        same mailbox (IMAP re-delivery) emits nothing new (Message-ID dedupe)."""
        from types import SimpleNamespace

        import src.ai.signals.email_poll as poll_mod
        from src.ai.signals.email_poll import _poll_one_connection

        fake_mail = [
            poll_mod._InboundEmail(
                uid="1", message_id="<m1@example.com>", from_addr="a@x.com",
                to_addr="us@co.com", subject="Need a quote", date="d1", body="hi",
            ),
            poll_mod._InboundEmail(
                uid="2", message_id="<m2@example.com>", from_addr="b@y.com",
                to_addr="us@co.com", subject="Invoice query", date="d2", body="yo",
            ),
        ]
        monkeypatch.setattr(poll_mod, "_fetch_unseen_messages",
                            lambda *a, **k: fake_mail)
        import src.common.security as security_mod
        monkeypatch.setattr(security_mod, "decrypt_api_key", lambda _v: "pw")

        conn = SimpleNamespace(
            id=uuid.uuid4(), company_id=test_company_id,
            imap_host="imap.test", imap_port=993,
            email_address="us@co.com", encrypted_app_password="enc",
            last_connected_at=None,
        )
        emitted, deduped = await _poll_one_connection(db, None, conn)
        assert (emitted, deduped) == (2, 0)
        emitted2, deduped2 = await _poll_one_connection(db, None, conn)
        assert (emitted2, deduped2) == (0, 2), "re-poll must dedupe on Message-ID"

        from sqlalchemy import select as _select
        rows = (await db.execute(
            _select(Signal).where(
                Signal.company_id == test_company_id,
                Signal.type == "email.inbound",
            )
        )).scalars().all()
        assert len(rows) == 2
        assert all(r.trust == "counterparty" and r.source == "connector" for r in rows)
        assert {r.dedupe_key for r in rows} == {"<m1@example.com>", "<m2@example.com>"}
