"""Inc 2 / SLICE — activation seeds the pack onto the Inc-1 substrate (§18, §23).

Activating the slice for a tenant creates the 4 entities with the right
parentage, resolves the HBS owner_process_code → the P03 entity id in the
tenant data plane, and registers the trigger subscriptions — idempotently.
``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.orm.entity import HierarchicalEntity
from src.ai.signals.models import TriggerRegistration
from src.ai.solo_pack.activation import activate_slice
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef

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
            {"id": str(cid), "n": f"pack-test-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    try:
        yield cid
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            for tbl in ("trigger_registry", "budget_envelopes", "loop_runtime", "signals"):
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


class TestActivation:
    async def test_seeds_entities_with_parentage(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await activate_slice(db, tenant)
        assert set(result.keys()) == {
            "kar-02-email-gateway", "p03-cold-to-closed-acquisition",
            "agt-013-inbound-deal-closer", "agt-015-proposal-quote"}

        async with AsyncSessionLocal() as db:
            ents = {e.name: e for e in (await db.execute(
                select(HierarchicalEntity).where(HierarchicalEntity.company_id == tenant)
            )).scalars().all()}
            sheel = ents["Sheel"]
            assert ents["p03-cold-to-closed-acquisition"].parent_id == sheel.id
            assert ents["kar-02-email-gateway"].parent_id == sheel.id
            p03_id = ents["p03-cold-to-closed-acquisition"].id
            assert ents["agt-013-inbound-deal-closer"].parent_id == p03_id
            assert ents["agt-015-proposal-quote"].parent_id == p03_id
            assert ents["p03-cold-to-closed-acquisition"].type == "PROCESS"

    async def test_resolves_owner_process_id(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await activate_slice(db, tenant)
        p03_id = uuid.UUID(result["p03-cold-to-closed-acquisition"])

        async with tenant_data_plane.session(tenant) as ts:
            for obj in ("Lead", "Opportunity", "Quote"):
                d = (await ts.execute(
                    select(TenantEntityDef).where(
                        TenantEntityDef.company_id == tenant, TenantEntityDef.name == obj)
                )).scalar_one()
                assert d.owner_process_id == p03_id, obj
            # A non-P03 object keeps its unresolved owner.
            vendor = (await ts.execute(
                select(TenantEntityDef).where(
                    TenantEntityDef.company_id == tenant, TenantEntityDef.name == "Vendor")
            )).scalar_one()
            assert vendor.owner_process_id is None

    async def test_registers_triggers(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await activate_slice(db, tenant)
            regs = (await db.execute(
                select(TriggerRegistration).where(TriggerRegistration.company_id == tenant)
            )).scalars().all()
        by_pattern = {r.type_pattern: r.process_entity_id for r in regs}
        assert by_pattern["email.inbound"] == uuid.UUID(result["kar-02-email-gateway"])
        assert by_pattern["lead.inbound"] == uuid.UUID(result["p03-cold-to-closed-acquisition"])

    async def test_idempotent(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            first = await activate_slice(db, tenant)
        async with AsyncSessionLocal() as db:
            second = await activate_slice(db, tenant)
            n_ent = (await db.execute(
                select(HierarchicalEntity).where(HierarchicalEntity.company_id == tenant)
            )).scalars().all()
            n_trig = (await db.execute(
                select(TriggerRegistration).where(TriggerRegistration.company_id == tenant)
            )).scalars().all()
        assert first == second                      # same ids
        assert len([e for e in n_ent if e.name != "Sheel"]) == 4   # no duplicate entities
        assert len(n_trig) == 3                      # no duplicate triggers
