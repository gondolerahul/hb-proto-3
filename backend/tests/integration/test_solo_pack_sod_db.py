"""Inc 2 / PACK — segregation of duties holds at runtime (§9.4, §23.1).

The finance slice is split across two owners on purpose: P08's Accounts
Receivable is the **maker** (owns Invoice/Payment), P10's Bookkeeping &
Reconciliation is the **checker** (owns Ledger Entry). This proves the
separation is structural, not a label:

* the RecordService ownership gate makes a cross-owner write **propose**
  (``object.change_proposed``), never mutate;
* the ``tenant_record_write`` tool, run *as* the reconciliation agent, proposes
  on the maker's Invoice, while the maker writes it directly;
* the gateway (no process ancestor) still originates front-door.

``needs_db``.
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.signals.models import Signal
from src.ai.solo_pack.activation import activate_solo_pack
from src.ai.solo_pack.tools import TenantRecordWriteTool
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
from src.ai.tenant_schema.record_service import RecordService

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def pack_tenant():
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
            {"id": str(cid), "n": f"sod-test-{cid.hex[:8]}"})
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


class TestOwnershipGate:
    """The RecordService seam: a cross-owner write proposes, the owner writes."""

    async def test_checker_proposes_on_makers_invoice(self, pack_tenant):
        cid, _ = pack_tenant
        async with tenant_data_plane.session(cid) as ts:
            svc = RecordService(ts, cid)
            # P10 (reconciliation, checker) may not create an Invoice — P08 owns it.
            res = await svc.create("Invoice", {"note": "x"}, actor_process_code="P10")
            assert res.status == "proposed"
            assert res.record is None
            assert res.signal_id is not None  # object.change_proposed emitted

    async def test_owner_writes_its_own_invoice(self, pack_tenant):
        cid, _ = pack_tenant
        async with tenant_data_plane.session(cid) as ts:
            svc = RecordService(ts, cid)
            acc = (await svc.create("Account", {"name": "Acme SoD"})).record
            # P08 (AR, maker) owns Invoice — a direct write.
            res = await svc.create(
                "Invoice", {"account": str(acc.id)}, actor_process_code="P08")
            assert res.status == "written"
            assert res.record is not None
            await ts.commit()

    async def test_change_proposed_signal_names_actor_and_owner(self, pack_tenant):
        cid, _ = pack_tenant
        async with tenant_data_plane.session(cid) as ts:
            svc = RecordService(ts, cid)
            await svc.create("Invoice", {"note": "y"}, actor_process_code="P10")
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            sig = (await db.execute(
                select(Signal).where(Signal.company_id == cid,
                                     Signal.type == "object.change_proposed")
            )).scalars().first()
        assert sig is not None
        assert sig.payload.get("actor") == "P10"
        assert sig.payload.get("owner") == "P08"


class TestToolActorResolution:
    """The tool resolves the acting process from agent_id and gates on it."""

    async def test_reconciler_tool_proposes_on_invoice(self, pack_tenant):
        cid, ids = pack_tenant
        tool = TenantRecordWriteTool()
        out = json.loads(await tool.run_with_context(
            json.dumps({"def_name": "Invoice", "data": {"note": "z"}}),
            {"company_id": str(cid), "agent_id": ids["agt-046-bookkeeping-reconciliation"]}))
        assert out["status"] == "proposed"
        assert out["record_id"] is None

    async def test_maker_tool_writes_invoice(self, pack_tenant):
        cid, ids = pack_tenant
        async with tenant_data_plane.session(cid) as ts:
            acc = (await RecordService(ts, cid).create("Account", {"name": "Acme Tool"})).record
            await ts.commit()
        tool = TenantRecordWriteTool()
        out = json.loads(await tool.run_with_context(
            json.dumps({"def_name": "Invoice", "data": {"account": str(acc.id)}}),
            {"company_id": str(cid), "agent_id": ids["agt-038-accounts-receivable"]}))
        assert out["status"] == "written"
        assert out["record_id"]

    async def test_gateway_originates_front_door(self, pack_tenant):
        cid, ids = pack_tenant
        tool = TenantRecordWriteTool()
        # KAR-02 has no PROCESS ancestor → front-door origination (the Lead it
        # makes is owned by P03, but origination is not a cross-owner mutation).
        out = json.loads(await tool.run_with_context(
            json.dumps({"def_name": "Lead", "data": {"display_name": "Origin",
                                                      "source": "inbound_email"}}),
            {"company_id": str(cid), "agent_id": ids["kar-02-email-gateway"]}))
        assert out["status"] == "written"

    async def test_no_agent_id_is_front_door(self, pack_tenant):
        cid, _ = pack_tenant
        tool = TenantRecordWriteTool()
        out = json.loads(await tool.run_with_context(
            json.dumps({"def_name": "Lead", "data": {"display_name": "Admin",
                                                      "source": "manual"}}),
            {"company_id": str(cid)}))
        assert out["status"] == "written"
