"""Inc 4 / CONN T6 (db) — the write-back bridge resolves a binding + delegates.

Proves ConnectorWriteBackProvider (installed into the SOR seam) resolves the
company's ACTIVE binding, hands off to the connector's write_back, and reflects
the result into the mirror — the full CONN→SOR path through the record service.
With no binding it fails safe. Uses a fake SoR connector on Account so the bridge
is tested apart from any one vendor's schema. ``needs_db``.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.connectors.service import ConnectorService
from src.ai.connectors.sync import SyncEvent
from src.ai.connectors.writeback import install_connector_writeback
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef
from src.ai.tenant_schema.record_service import WRITEBACK_FAILED, WRITTEN, RecordService
from src.ai.tenant_schema.sor import WriteBackResult, set_writeback_provider

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
            {"id": str(cid), "n": f"wbridge-{cid.hex[:8]}"},
        )
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    try:
        yield cid
    finally:
        set_writeback_provider(None)
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM connector_bindings WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM signals WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


class _FakeConn:
    """A SoR connector on Account (structurally satisfies SorConnector)."""

    def __init__(self) -> None:
        self.result = WriteBackResult(ok=True, external_id="EXT-1", etag="v1")
        self.calls: list[str] = []

    async def write_back(self, *, op: str, object_name: str, data: dict[str, Any],
                         external_ref: Optional[dict[str, Any]]) -> WriteBackResult:
        self.calls.append(op)
        return self.result

    async def fetch_changes(self, object_name: str, since: Optional[str]) -> list[SyncEvent]:
        return []


class _FakeResolver:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn

    async def resolve(self, connector, binding, credentials) -> _FakeConn:  # type: ignore[no-untyped-def]
        return self.conn


async def _mark_external(cid, def_name: str, connector: str) -> None:
    async with tenant_data_plane.session(cid) as ts:
        d = (await ts.execute(
            select(TenantEntityDef).where(TenantEntityDef.name == def_name)
        )).scalar_one()
        d.sor = {"master": "external", "connector_id": connector, "write_back": True}
        await ts.commit()


async def test_bridge_resolves_binding_and_delegates(tenant_company):
    from src.common.database import AsyncSessionLocal

    conn = _FakeConn()
    install_connector_writeback(_FakeResolver(conn))
    async with AsyncSessionLocal() as db:
        await ConnectorService(db).activate(tenant_company, "zoho_books",
                                            credentials={"access_token": "t"})
    await _mark_external(tenant_company, "Account", "zoho_books")

    async with tenant_data_plane.session(tenant_company) as ts:
        res = await RecordService(ts, tenant_company).create("Account", {"name": "Acme"})
        await ts.commit()
    assert res.status == WRITTEN
    assert conn.calls == ["create"]
    assert res.record.external_ref["external_id"] == "EXT-1"


async def test_no_binding_fails_safe(tenant_company):
    # provider installed, object external, but no binding activated → fail safe
    install_connector_writeback(_FakeResolver(_FakeConn()))
    await _mark_external(tenant_company, "Account", "zoho_books")
    async with tenant_data_plane.session(tenant_company) as ts:
        svc = RecordService(ts, tenant_company)
        res = await svc.create("Account", {"name": "Acme"})
        await ts.commit()
        assert res.status == WRITEBACK_FAILED
        assert await svc.list_records("Account") == []
