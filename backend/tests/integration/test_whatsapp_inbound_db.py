"""Inc 2 / KAR — the WhatsApp producer puts inbound messages on the bus (§18.2).

Mirrors the email producer: an inbound WhatsApp message becomes a
``message.inbound`` signal (``trust: counterparty``, SID-deduped) — but only for
a SIG-subscribed tenant (the Solo Pack activated). Dispatching it spawns the
KAR-03 gateway. A tenant not on SIG gets nothing (the caller keeps its legacy
path). ``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.orm.execution import ExecutionRun
from src.ai.signals.dispatcher import process_claimed_signal
from src.ai.signals.models import Signal, SignalStatus, SignalTrust
from src.ai.signals.whatsapp_inbound import company_subscribes, emit_whatsapp_inbound
from src.ai.solo_pack.activation import activate_solo_pack
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def kar_tenant():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"kar-test-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    async with AsyncSessionLocal() as db:
        ids = await activate_solo_pack(db, cid)
    try:
        yield cid, ids
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            for tbl in ("trigger_registry", "budget_envelopes", "loop_runtime",
                        "wallet_holds", "signals", "execution_runs"):
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def test_emits_message_inbound_when_subscribed(kar_tenant):
    cid, _ = kar_tenant
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        assert await company_subscribes(db, cid, "message.inbound") is True
        sig_id = await emit_whatsapp_inbound(
            db, cid, from_number="whatsapp:+15551234567", to_number="+15559876543",
            body="Hi, do you sell widgets?", message_sid="SM_abc")
        assert sig_id is not None
    async with AsyncSessionLocal() as db:
        sig = (await db.execute(select(Signal).where(Signal.id == sig_id))).scalar_one()
    assert sig.type == "message.inbound"
    assert sig.trust == SignalTrust.COUNTERPARTY  # world-facing input, not trusted
    assert sig.payload["channel"] == "whatsapp"
    assert sig.payload["from"] == "15551234567"  # normalised (no whatsapp:/+)


async def test_dedupes_on_message_sid(kar_tenant):
    cid, _ = kar_tenant
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        first = await emit_whatsapp_inbound(
            db, cid, from_number="+1999", to_number="+1888",
            body="hello", message_sid="SM_dupe")
    async with AsyncSessionLocal() as db:
        second = await emit_whatsapp_inbound(
            db, cid, from_number="+1999", to_number="+1888",
            body="hello", message_sid="SM_dupe")
    assert first is not None
    assert second is None  # webhook retry deduped on the SID


async def test_no_signal_when_not_subscribed():
    # A tenant with no triggers (Solo Pack not activated) never enters the bus —
    # the caller keeps its legacy path. No fixture / tenant schema needed.
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine
    await engine.dispose()  # this test has no fixture; own the pool for this loop
    async with AsyncSessionLocal() as db:
        out = await emit_whatsapp_inbound(
            db, uuid.uuid4(), from_number="+1", to_number="+2",
            body="hi", message_sid="SM_x")
    assert out is None


async def test_dispatch_spawns_kar03(kar_tenant):
    cid, ids = kar_tenant
    kar03_id = uuid.UUID(ids["kar-03-whatsapp-gateway"])
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        sig_id = await emit_whatsapp_inbound(
            db, cid, from_number="+15551112222", to_number="+15553334444",
            body="need support with my order", message_sid="SM_route")
        sig = (await db.execute(
            select(Signal).where(Signal.id == sig_id, Signal.status == SignalStatus.PENDING)
            .with_for_update(skip_locked=True))).scalar_one()
        outcome = await process_claimed_signal(db, None, sig)
        assert outcome == "consumed"
        run = (await db.execute(
            select(ExecutionRun).where(ExecutionRun.company_id == cid,
                                       ExecutionRun.entity_id == kar03_id))).scalar_one()
        assert run is not None  # the WhatsApp gateway was fired by the trigger
