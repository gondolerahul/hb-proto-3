"""Inc 4 / SOR T7 — ownership migration (§21.4): propose, confirm, apply.

Flipping an object's master is explicit and one-directional: external→hirebuddha
promotes mirrors to native records (sor/external_ref cleared, data kept);
hirebuddha→external re-declares the object. Every applied flip audits itself with
governance.sor_migrated. Invalid transitions are refused. ``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.connectors.sor_migration import (
    MigrationError,
    apply_migration,
    propose_migration,
)
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef
from src.ai.tenant_schema.record_service import RecordService
from src.ai.tenant_schema.sor import sor_of

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


def _db_url():
    import os

    from src.common.config import settings
    return getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")


@pytest_asyncio.fixture
async def tenant_company():
    url = _db_url()
    if not url:
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"migr-{cid.hex[:8]}"},
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


async def _mark_external(cid, def_name: str, connector: str = "zoho_books") -> None:
    async with tenant_data_plane.session(cid) as ts:
        d = (await ts.execute(
            select(TenantEntityDef).where(TenantEntityDef.name == def_name)
        )).scalar_one()
        d.sor = {"master": "external", "connector_id": connector, "write_back": True}
        await ts.commit()


async def _def_master(cid, def_name: str) -> str:
    async with tenant_data_plane.session(cid) as ts:
        d = (await ts.execute(
            select(TenantEntityDef).where(TenantEntityDef.name == def_name)
        )).scalar_one()
        return sor_of(d.sor).master


async def _signal_count(cid, sig_type: str) -> int:
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        return (await s.execute(
            text("SELECT count(*) FROM signals WHERE company_id = :c AND type = :t"),
            {"c": str(cid), "t": sig_type},
        )).scalar_one()


class TestExternalToHireBuddha:
    async def test_promotes_mirrors_to_native(self, tenant_company):
        await _mark_external(tenant_company, "Account")
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            await svc.sync_mirror("Account", "EXT-1", {"name": "A"}, connector_id="zoho_books")
            await svc.sync_mirror("Account", "EXT-2", {"name": "B"}, connector_id="zoho_books")
            await ts.commit()

        plan = await propose_migration(tenant_company, "Account", "hirebuddha")
        assert plan.from_master == "external" and plan.records_to_promote == 2

        result = await apply_migration(tenant_company, "Account", "hirebuddha")
        assert result.records_affected == 2
        assert await _def_master(tenant_company, "Account") == "hirebuddha"

        # the mirrors are now native — sor + external_ref cleared, data kept
        async with tenant_data_plane.session(tenant_company) as ts:
            recs = await RecordService(ts, tenant_company).list_records("Account")
        assert len(recs) == 2
        assert all(r.sor is None and r.external_ref is None for r in recs)
        assert await _signal_count(tenant_company, "governance.sor_migrated") == 1


class TestHireBuddhaToExternal:
    async def test_redeclares_object_external(self, tenant_company):
        # Account is HireBuddha-mastered by default
        result = await apply_migration(
            tenant_company, "Account", "external", connector_id="zoho_books")
        assert result.from_master == "hirebuddha" and result.to_master == "external"
        assert await _def_master(tenant_company, "Account") == "external"
        assert await _signal_count(tenant_company, "governance.sor_migrated") == 1


class TestRefusals:
    async def test_external_without_connector_is_refused(self, tenant_company):
        with pytest.raises(MigrationError):
            await propose_migration(tenant_company, "Account", "external")

    async def test_bad_master_is_refused(self, tenant_company):
        with pytest.raises(MigrationError):
            await propose_migration(tenant_company, "Account", "sideways")

    async def test_no_op_is_refused(self, tenant_company):
        with pytest.raises(MigrationError):
            await propose_migration(tenant_company, "Account", "hirebuddha")  # already HB
