"""Inc 4 / SOR T4 — write-back-first mastering on a real tenant schema (§21.2).

An externally-mastered object writes to its connector *first*; the mirror is
created/updated only on confirmation, a failed write-back changes nothing
locally, and a concurrent external edit wins (sync.conflict, mirror untouched).
Driven against a fake write-back provider — the machine is proven without a live
connector (the §9 boundary). ``needs_db``.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef
from src.ai.tenant_schema.record_service import (
    SYNC_CONFLICT,
    WRITEBACK_FAILED,
    WRITTEN,
    RecordService,
)
from src.ai.tenant_schema.sor import (
    WriteBackResult,
    set_writeback_provider,
)

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
            {"id": str(cid), "n": f"sor-test-{cid.hex[:8]}"},
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


class _FakeProvider:
    """Records write-back calls; returns a configurable result."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = WriteBackResult(ok=True, external_id="EXT-1", etag="v1")

    async def write_back(self, **kw: Any) -> WriteBackResult:
        self.calls.append(kw)
        return self.result


@pytest_asyncio.fixture
async def provider():
    p = _FakeProvider()
    set_writeback_provider(p)
    try:
        yield p
    finally:
        set_writeback_provider(None)


async def _mark_external(ts, def_name: str, connector: str = "zoho_books") -> None:
    d = (await ts.execute(
        select(TenantEntityDef).where(TenantEntityDef.name == def_name)
    )).scalar_one()
    d.sor = {"master": "external", "connector_id": connector, "write_back": True}
    await ts.commit()


async def _signal_count(cid, sig_type: str) -> int:
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        return (await s.execute(
            text("SELECT count(*) FROM signals WHERE company_id = :c AND type = :t"),
            {"c": str(cid), "t": sig_type},
        )).scalar_one()


class TestExternalCreate:
    async def test_writes_back_first_then_mirrors(self, tenant_company, provider):
        async with tenant_data_plane.session(tenant_company) as ts:
            await _mark_external(ts, "Account")
            svc = RecordService(ts, tenant_company)
            res = await svc.create("Account", {"name": "Acme"})
            await ts.commit()
        assert res.status == WRITTEN
        assert len(provider.calls) == 1 and provider.calls[0]["op"] == "create"
        assert res.record.external_ref["external_id"] == "EXT-1"
        assert res.record.external_ref["etag"] == "v1"
        assert res.record.sor == {"master": "external", "connector_id": "zoho_books"}

    async def test_failed_writeback_writes_nothing(self, tenant_company, provider):
        provider.result = WriteBackResult(ok=False, error="zoho 502")
        async with tenant_data_plane.session(tenant_company) as ts:
            await _mark_external(ts, "Account")
            svc = RecordService(ts, tenant_company)
            res = await svc.create("Account", {"name": "Acme"})
            await ts.commit()
            assert res.status == WRITEBACK_FAILED
            # no local mirror was created
            assert await svc.list_records("Account") == []


class TestExternalUpdate:
    async def test_update_writes_back_and_bumps_mirror(self, tenant_company, provider):
        async with tenant_data_plane.session(tenant_company) as ts:
            await _mark_external(ts, "Account")
            svc = RecordService(ts, tenant_company)
            created = (await svc.create("Account", {"name": "Acme"})).record
            await ts.commit()
            provider.result = WriteBackResult(ok=True, external_id="EXT-1", etag="v2")
            res = await svc.update(created.id, {"name": "Acme Inc"},
                                   expected_version=created.version)
            await ts.commit()
        assert res.status == WRITTEN
        assert provider.calls[-1]["op"] == "update"
        assert res.record.data["name"] == "Acme Inc"
        assert res.record.external_ref["etag"] == "v2"      # mirror advanced
        assert res.record.version == 2

    async def test_conflict_master_wins_leaves_mirror(self, tenant_company, provider):
        async with tenant_data_plane.session(tenant_company) as ts:
            await _mark_external(ts, "Account")
            svc = RecordService(ts, tenant_company)
            created = (await svc.create("Account", {"name": "Acme"})).record
            await ts.commit()
            # the external object changed under us → master wins
            provider.result = WriteBackResult(ok=False, conflict=True)
            res = await svc.update(created.id, {"name": "Loser"},
                                   expected_version=created.version)
            await ts.commit()
        assert res.status == SYNC_CONFLICT
        # local delta NOT applied — the mirror still holds the master's value
        assert res.record.data["name"] == "Acme"
        assert await _signal_count(tenant_company, "sync.conflict") == 1


class TestHireBuddhaMasteredUnaffected:
    async def test_local_object_never_calls_provider(self, tenant_company, provider):
        # Account left HireBuddha-mastered (sor unset) — the standalone norm.
        async with tenant_data_plane.session(tenant_company) as ts:
            svc = RecordService(ts, tenant_company)
            res = await svc.create("Account", {"name": "Local"})
            await ts.commit()
        assert res.status == WRITTEN
        assert provider.calls == []
        assert res.record.external_ref is None


class TestNoProviderFailsSafe:
    async def test_external_write_without_provider_fails_safe(self, tenant_company):
        set_writeback_provider(None)  # no connector installed
        async with tenant_data_plane.session(tenant_company) as ts:
            await _mark_external(ts, "Account")
            svc = RecordService(ts, tenant_company)
            res = await svc.create("Account", {"name": "Acme"})
            await ts.commit()
            assert res.status == WRITEBACK_FAILED
            assert await svc.list_records("Account") == []
