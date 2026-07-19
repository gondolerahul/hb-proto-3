"""Inc 1 / SCH — record service against the schema backend (§19, §23).

Ref materialisation, CAS versioning + write-conflict signal, owner-writes/
others-propose, the Signal→Lead→Opportunity chain, and soft delete — all on a
real per-tenant Postgres schema. Self-managed committed fixtures (the record
service emits control-plane signals on its own connection), cleaned up after.
``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
from src.ai.tenant_schema.models import TenantRecordLink
from src.ai.tenant_schema.record_service import CONFLICT, PROPOSED, WRITTEN, RecordService
from src.ai.tenant_schema.validation import ValidationError

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


def _db_url():
    import os

    from src.common.config import settings
    return getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")


@pytest_asyncio.fixture
async def tenant_company():
    """A committed company + provisioned tenant schema; dropped on teardown."""
    url = _db_url()
    if not url:
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    # pytest-asyncio gives each test its own event loop; the process-global
    # control engine (used by the data plane + record-service signal emits)
    # pools asyncpg connections bound to whatever loop first touched them.
    # Dispose so this test's first use rebuilds the pool on the current loop.
    await engine.dispose()

    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"sch-test-{cid.hex[:8]}"},
        )
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


async def _new_account(svc, name="Acme"):
    res = await svc.create("Account", {"name": name})
    return res.record


class TestCreateAndValidate:
    async def test_create_seeded_object(self, tenant_company):
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            res = await svc.create("Account", {"name": "Acme", "type": "customer"})
            await ts.commit()
            assert res.status == WRITTEN
            assert res.record.version == 1
            assert res.record.data["type"] == "customer"

    async def test_missing_required_rejected(self, tenant_company):
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            with pytest.raises(ValidationError):
                await svc.create("Account", {"type": "customer"})  # no name


class TestRefMaterialisation:
    async def test_belongs_to_link_created_atomically(self, tenant_company):
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            acc = await _new_account(svc)
            await ts.commit()
            res = await svc.create("Contact", {"first_name": "Jo", "account": str(acc.id)})
            await ts.commit()
            assert res.status == WRITTEN
            links = (await ts.execute(
                TenantRecordLink.__table__.select().where(
                    TenantRecordLink.src_record_id == res.record.id)
            )).all()
            assert len(links) == 1
            assert links[0].rel_type == "belongs_to"
            assert links[0].dst_record_id == acc.id

    async def test_ref_to_wrong_target_rejected(self, tenant_company):
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            acc = await _new_account(svc)
            await ts.commit()
            # Contact.account must point at an Account; point it at itself-as-ticket
            with pytest.raises(ValidationError):
                await svc.create("Contact", {"first_name": "Jo",
                                             "account": str(uuid.uuid4())})  # missing target


class TestChain:
    async def test_signal_lead_opportunity_chain(self, tenant_company):
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            acc = await _new_account(svc)
            sig = (await svc.create("Signal", {"title": "hot inbound"})).record
            await ts.commit()
            lead = (await svc.create("Lead", {"display_name": "Jo",
                                              "source_signal": str(sig.id)})).record
            await ts.commit()
            opp = (await svc.create("Opportunity", {
                "name": "Big deal", "account": str(acc.id), "lead": str(lead.id),
            })).record
            await ts.commit()

            # Signal → Lead (converted_to, direction "in" so src=signal)
            chain = await svc.traverse(sig.id, rel_type="converted_to", depth=3)
            dsts = {c["dst"] for c in chain}
            assert str(lead.id) in dsts
            # Lead → Opportunity
            lead_chain = await svc.traverse(lead.id, rel_type="converted_to")
            assert str(opp.id) in {c["dst"] for c in lead_chain}


class TestCAS:
    async def test_stale_version_conflicts_and_signals(self, tenant_company):
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            acc = await _new_account(svc)
            await ts.commit()
            # Write with a stale expected_version (record is at 1).
            res = await svc.update(acc.id, {"industry": "tech"}, expected_version=99)
            await ts.commit()
            assert res.status == CONFLICT
            assert res.signal_id is not None

        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as cp:
            row = (await cp.execute(
                text("SELECT type FROM signals WHERE company_id = :c AND type = :t"),
                {"c": str(tenant_company), "t": "object.write_conflict"},
            )).first()
            assert row is not None

    async def test_happy_update_bumps_version(self, tenant_company):
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            acc = await _new_account(svc)
            await ts.commit()
            res = await svc.update(acc.id, {"industry": "tech"}, expected_version=1)
            await ts.commit()
            assert res.status == WRITTEN
            assert res.record.version == 2
            assert res.record.data["industry"] == "tech"


class TestOwnership:
    async def test_non_owner_agent_proposes(self, tenant_company):
        """SoD: an AR agent (P08) cannot edit a Vendor (owned by P09) — it can
        only propose, and the proposal is an auditable object.change_proposed."""
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            vendor = (await svc.create("Vendor", {"name": "Supplier Co"})).record
            await ts.commit()
            res = await svc.update(
                vendor.id, {"category": "hardware"}, expected_version=1,
                actor_process_code="P08",   # Order-to-Cash, not the P09 owner
            )
            await ts.commit()
            assert res.status == PROPOSED
            assert res.signal_id is not None
            # The record was NOT mutated.
            fresh = await svc.get(vendor.id)
            assert "category" not in (fresh.data or {})

    async def test_owner_agent_writes_direct(self, tenant_company):
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            vendor = (await svc.create("Vendor", {"name": "Supplier Co"})).record
            await ts.commit()
            res = await svc.update(
                vendor.id, {"category": "hardware"}, expected_version=1,
                actor_process_code="P09",   # the owner
            )
            await ts.commit()
            assert res.status == WRITTEN
            assert res.record.data["category"] == "hardware"


class TestSoftDelete:
    async def test_soft_delete_hides_record(self, tenant_company):
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            acc = await _new_account(svc)
            await ts.commit()
            await svc.soft_delete(acc.id)
            await ts.commit()
            assert await svc.get(acc.id) is None
            assert await svc.get(acc.id, include_deleted=True) is not None


class TestExport:
    async def test_export_bundle_includes_tenant_and_control_plane(self, tenant_company):
        from src.ai.tenant_schema.export_service import export_tenant
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            await svc.create("Account", {"name": "Acme"})
            await ts.commit()
        bundle = await export_tenant(tenant_company)
        assert bundle["manifest"]["company_id"] == str(tenant_company)
        # Tenant DB: 27 seeded defs + our 1 record.
        assert len(bundle["tenant_db"]["entity_defs"]) == 27
        assert len(bundle["tenant_db"]["records"]) == 1
        # v3.0.6 rider: the control-plane KB/memory travels in the bundle.
        assert "kb_documents" in bundle["control_plane"]
        assert "memory_manifest" in bundle["control_plane"]
        assert "control_plane_kb" in bundle["manifest"]["includes"]


class TestEvolution:
    async def test_def_version_upgrades_lazily_on_write(self, tenant_company):
        from src.ai.tenant_schema.models import TenantEntityDef
        from sqlalchemy import select as _select
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            acc = (await svc.create("Account", {"name": "Acme"})).record
            await ts.commit()
            assert acc.def_version == 1

            # Evolve the Account def: bump version + add an alias for `industry`.
            d = (await ts.execute(
                _select(TenantEntityDef).where(
                    TenantEntityDef.company_id == tenant_company,
                    TenantEntityDef.name == "Account")
            )).scalar_one()
            new_fields = []
            for f in d.fields:
                if f["name"] == "industry":
                    f = {**f, "aliases": ["sector"]}
                new_fields.append(f)
            d.fields = new_fields
            d.version = 2
            await ts.commit()

            # Write via the ALIAS key — normalises to `industry`; def_version upgrades.
            res = await svc.update(acc.id, {"sector": "tech"}, expected_version=1)
            await ts.commit()
            assert res.status == WRITTEN
            assert res.record.def_version == 2
            assert res.record.data["industry"] == "tech"
            assert "sector" not in res.record.data
