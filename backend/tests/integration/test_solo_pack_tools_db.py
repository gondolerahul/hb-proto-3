"""Inc 2 / SLICE — the Solo Pack agent tools bridge to the Inc-1 substrate.

``tenant_record_write`` creates a Lead in the tenant data plane; ``emit_business_
signal`` emits a control-plane signal — the two calls KAR-02 makes to turn an
inbound email into ``lead.inbound``. The LLM-driven orchestration itself is
proven in the T6 end-to-end (MockLLM). ``needs_db``.
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.solo_pack.tools import EmitBusinessSignalTool, TenantRecordWriteTool
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
from src.ai.tenant_schema.models import TenantRecord, TenantEntityDef

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def tenant():
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
            {"id": str(cid), "n": f"tool-test-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    try:
        yield cid
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM signals WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


class TestRecordWriteTool:
    async def test_creates_a_lead(self, tenant):
        tool = TenantRecordWriteTool()
        out = json.loads(await tool.run_with_context(
            json.dumps({"def_name": "Lead", "data": {
                "display_name": "Jo Buyer", "email": "jo@acme.com", "source": "inbound_email"}}),
            {"company_id": str(tenant)},
        ))
        assert out["status"] == "written"
        assert out["record_id"]

        async with tenant_data_plane.session(tenant) as ts:
            lead_def = (await ts.execute(select(TenantEntityDef).where(
                TenantEntityDef.company_id == tenant, TenantEntityDef.name == "Lead"))).scalar_one()
            rows = (await ts.execute(select(TenantRecord).where(
                TenantRecord.company_id == tenant,
                TenantRecord.entity_def_id == lead_def.id))).scalars().all()
            assert len(rows) == 1
            assert rows[0].data["display_name"] == "Jo Buyer"

    async def test_validation_error_returns_cleanly(self, tenant):
        tool = TenantRecordWriteTool()
        out = json.loads(await tool.run_with_context(
            json.dumps({"def_name": "Lead", "data": {"email": "no@name.com"}}),  # missing required display_name
            {"company_id": str(tenant)},
        ))
        assert out.get("error_code") == "validation_error"

    async def test_no_company_context(self):
        tool = TenantRecordWriteTool()
        out = json.loads(await tool.run_with_context(
            json.dumps({"def_name": "Lead", "data": {"display_name": "x"}}), {}))
        assert "error" in out


class TestSignalTool:
    async def test_emits_lead_inbound(self, tenant):
        tool = EmitBusinessSignalTool()
        out = json.loads(await tool.run_with_context(
            json.dumps({"type": "lead.inbound", "payload": {"lead_id": "abc"}}),
            {"company_id": str(tenant)},
        ))
        assert out["signal_id"]

        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                text("SELECT type, source, trust FROM signals WHERE company_id = :c"),
                {"c": str(tenant)})).first()
            assert row is not None
            assert row[0] == "lead.inbound"
            assert row[1] == "agent"
