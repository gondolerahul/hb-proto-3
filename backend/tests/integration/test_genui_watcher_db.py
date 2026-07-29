"""STEWARD S1 — the sweep over real rows. ``needs_db``.

What only the database can prove: the ledger's (approval, user) grain —
reached once, never twice; appearing later, still told — and that the
recommendation is written exactly once, before anyone has been reached,
and never after.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, text

import src.auth.models  # noqa: F401 — registers users/companies for FK metadata
from src.ai.genui import channel as ch
from src.ai.genui import watcher as w
from src.ai.genui.models import TrayDelivery, TrayRecommendation
from src.ai.genui.push import subscribe
from src.ai.orm.execution import ExecutionRun, HumanApproval
from src.ai.solo_pack.activation import activate_slice
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


class FakeSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, data):
        self.sent.append(data)


@pytest.fixture()
def hub(monkeypatch):
    fresh = ch.ChannelHub()
    monkeypatch.setattr(ch, "_hub", fresh)
    return fresh


@pytest.fixture(autouse=True)
def _no_installed_recommender():
    w.install_recommender(None)
    yield
    w.install_recommender(None)


@pytest_asyncio.fixture
async def tenant():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, u1, u2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"watcher-test-{cid.hex[:8]}"})
        for uid, label in ((u1, "one"), (u2, "two")):
            await s.execute(
                text("INSERT INTO users (id, email, full_name, hashed_password, "
                     "company_id, role, is_active, created_at, updated_at) "
                     "VALUES (:id, :e, :n, 'x', :c, 'tenant_admin', "
                     "true, now(), now())"),
                {"id": str(uid), "e": f"watcher-{label}-{uid.hex[:10]}@test.local",
                 "n": f"Watcher {label}", "c": str(cid)})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    try:
        yield cid, u1, u2
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            for tbl in ("tray_deliveries", "tray_recommendations",
                        "push_subscriptions"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text(
                "DELETE FROM human_approvals WHERE run_id IN "
                "(SELECT id FROM execution_runs WHERE company_id = :c)"), {"c": str(cid)})
            for tbl in ("execution_runs", "signals", "trigger_registry",
                        "budget_envelopes", "loop_runtime"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(
                text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                {"c": str(cid)})
            await s.execute(
                text("DELETE FROM users WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(
                text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def _activate(db, cid) -> uuid.UUID:
    result = await activate_slice(db, cid)
    return uuid.UUID(result["agt-015-proposal-quote"])


async def _raise_approval(db, cid, agent_id) -> uuid.UUID:
    run = ExecutionRun(entity_id=agent_id, company_id=cid, status="RUNNING")
    db.add(run)
    await db.flush()
    approval = HumanApproval(
        run_id=run.id, checkpoint_trigger="policy:outbound_payout",
        checkpoint_key="before_outbound_payout_above_band", status="PENDING",
        requested_at=datetime.utcnow(),
        context_snapshot={
            "category": "outbound_payout", "reason": "Payout above the A2 band",
            "band": 2, "amount": 84200.0,
        })
    db.add(approval)
    await db.commit()
    return approval.id


async def _ledger(db, approval_id) -> list[TrayDelivery]:
    return list((
        await db.execute(
            select(TrayDelivery)
            .where(TrayDelivery.approval_id == approval_id)
            .order_by(TrayDelivery.delivered_at))
    ).scalars().all())


class TestSweep:
    async def test_a_listening_user_gets_the_tray_once_and_only_once(
            self, tenant, hub):
        cid, u1, _ = tenant
        from src.common.database import AsyncSessionLocal

        socket = FakeSocket()
        hub.join(uuid.uuid4(), cid, u1, socket)

        async with AsyncSessionLocal() as db:
            agent_id = await _activate(db, cid)
            approval_id = await _raise_approval(db, cid, agent_id)
        async with AsyncSessionLocal() as db:
            written = await w.sweep_once(db)
        assert [(r.approval_id, r.user_id, r.via) for r in written] == [
            (approval_id, u1, "socket")]
        delivered = [m for m in socket.sent if m.get("type") == "deliver_tray"]
        assert len(delivered) == 1
        assert delivered[0]["tray"]["approval_id"] == str(approval_id)

        # The second sweep finds the pair in the ledger and stays quiet.
        async with AsyncSessionLocal() as db:
            assert await w.sweep_once(db) == []
        assert len(
            [m for m in socket.sent if m.get("type") == "deliver_tray"]) == 1

    async def test_a_user_appearing_later_still_hears_about_a_pending_card(
            self, tenant, hub):
        cid, u1, u2 = tenant
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            agent_id = await _activate(db, cid)
            approval_id = await _raise_approval(db, cid, agent_id)

        # Nobody is reachable: no ledger row, not "nowhere and forgotten".
        async with AsyncSessionLocal() as db:
            assert await w.sweep_once(db) == []

        first, late = FakeSocket(), FakeSocket()
        hub.join(uuid.uuid4(), cid, u1, first)
        async with AsyncSessionLocal() as db:
            written = await w.sweep_once(db)
        assert [(r.user_id, r.via) for r in written] == [(u1, "socket")]

        hub.join(uuid.uuid4(), cid, u2, late)
        async with AsyncSessionLocal() as db:
            written = await w.sweep_once(db)
        assert [(r.user_id, r.via) for r in written] == [(u2, "socket")]
        async with AsyncSessionLocal() as db:
            rows = await _ledger(db, approval_id)
        assert {(r.user_id, r.via) for r in rows} == {
            (u1, "socket"), (u2, "socket")}

    async def test_a_push_subscriber_is_reached_through_the_one_door(
            self, tenant, hub):
        cid, u1, _ = tenant
        from src.common.database import AsyncSessionLocal

        pushed: list[str] = []

        def transport(endpoint, keys, payload, key, claims) -> int:
            pushed.append(payload)
            return 201

        async with AsyncSessionLocal() as db:
            await subscribe(
                db, cid, u1, endpoint=f"https://push.test/{uuid.uuid4().hex}",
                p256dh="k", auth="a")
            agent_id = await _activate(db, cid)
            approval_id = await _raise_approval(db, cid, agent_id)
        async with AsyncSessionLocal() as db:
            written = await w.sweep_once(db, push_transport=transport)
        assert [(r.user_id, r.via) for r in written] == [(u1, "push")]
        assert len(pushed) == 1
        assert str(approval_id) in pushed[0]

    async def test_a_responded_approval_is_not_delivered(self, tenant, hub):
        cid, u1, _ = tenant
        from src.common.database import AsyncSessionLocal

        hub.join(uuid.uuid4(), cid, u1, FakeSocket())
        async with AsyncSessionLocal() as db:
            agent_id = await _activate(db, cid)
            approval_id = await _raise_approval(db, cid, agent_id)
            approval = await db.get(HumanApproval, approval_id)
            approval.status = "APPROVED"
            await db.commit()
        async with AsyncSessionLocal() as db:
            assert await w.sweep_once(db) == []

    async def test_the_recommendation_is_written_at_first_delivery_and_never_after(
            self, tenant, hub):
        cid, u1, u2 = tenant
        from src.common.database import AsyncSessionLocal

        # First delivery goes out with NO writer installed — the tray ships
        # without advice, and that is final for this card.
        hub.join(uuid.uuid4(), cid, u1, FakeSocket())
        async with AsyncSessionLocal() as db:
            agent_id = await _activate(db, cid)
            approval_id = await _raise_approval(db, cid, agent_id)
        async with AsyncSessionLocal() as db:
            await w.sweep_once(db)

        async def writer(db, company_id, tray):
            return w.RecommendationDraft(sentence="late advice")

        w.install_recommender(writer)
        late = FakeSocket()
        hub.join(uuid.uuid4(), cid, u2, late)
        async with AsyncSessionLocal() as db:
            written = await w.sweep_once(db)
        assert [(r.user_id) for r in written] == [u2]
        async with AsyncSessionLocal() as db:
            stored = await db.get(TrayRecommendation, approval_id)
        assert stored is None
        delivered = [m for m in late.sent if m.get("type") == "deliver_tray"]
        assert delivered[0]["tray"]["recommendation"] is None

        # A fresh card with the writer installed gets its sentence — once,
        # stored, and identical for every recipient.
        async with AsyncSessionLocal() as db:
            second_id = await _raise_approval(db, cid, agent_id)
        async with AsyncSessionLocal() as db:
            await w.sweep_once(db)
        async with AsyncSessionLocal() as db:
            stored = await db.get(TrayRecommendation, second_id)
        assert stored is not None and stored.sentence == "late advice"
