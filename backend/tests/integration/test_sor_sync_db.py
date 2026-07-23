"""Inc 4 / SOR T5 — sync-in: external changes → mirror + object.synced (§21.2).

An external change reflects into the mirror and announces itself as object.synced,
deduped on the external event id; the scheduled sweep drives the same ingest
across a connector's mastered objects. Driven against fakes (no live connector —
the §9 boundary). ``needs_db``.
"""
from __future__ import annotations

import uuid
from typing import Optional

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.connectors.catalog import ConnectorBackend, ConnectorDef
from src.ai.connectors.sync import (
    SyncEvent,
    ingest_external_change,
    sweep_connector,
)
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef
from src.ai.tenant_schema.record_service import RecordService

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
            {"id": str(cid), "n": f"sync-test-{cid.hex[:8]}"},
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


async def _signal_count(cid, sig_type: str) -> int:
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        return (await s.execute(
            text("SELECT count(*) FROM signals WHERE company_id = :c AND type = :t"),
            {"c": str(cid), "t": sig_type},
        )).scalar_one()


async def _accounts(cid):
    async with tenant_data_plane.session(cid) as ts:
        return await RecordService(ts, cid).list_records("Account")


class TestIngest:
    async def test_creates_mirror_and_emits(self, tenant_company):
        await _mark_external(tenant_company, "Account")
        event = SyncEvent("Account", "EXT-9", {"name": "Synced Co"}, etag="e1", event_id="evt-1")
        sig = await ingest_external_change(tenant_company, "zoho_books", event)
        assert sig is not None
        recs = await _accounts(tenant_company)
        assert len(recs) == 1
        assert recs[0].external_ref["external_id"] == "EXT-9"
        assert recs[0].data["name"] == "Synced Co"
        assert await _signal_count(tenant_company, "object.synced") == 1

    async def test_duplicate_event_is_deduped(self, tenant_company):
        await _mark_external(tenant_company, "Account")
        event = SyncEvent("Account", "EXT-9", {"name": "Synced Co"}, etag="e1", event_id="evt-1")
        await ingest_external_change(tenant_company, "zoho_books", event)
        # same event id again → the announce is deduped
        sig2 = await ingest_external_change(tenant_company, "zoho_books", event)
        assert sig2 is None
        assert await _signal_count(tenant_company, "object.synced") == 1
        assert len(await _accounts(tenant_company)) == 1  # still one mirror

    async def test_new_change_updates_mirror_in_place(self, tenant_company):
        await _mark_external(tenant_company, "Account")
        await ingest_external_change(
            tenant_company, "zoho_books",
            SyncEvent("Account", "EXT-9", {"name": "Old"}, etag="e1", event_id="evt-1"))
        await ingest_external_change(
            tenant_company, "zoho_books",
            SyncEvent("Account", "EXT-9", {"name": "New"}, etag="e2", event_id="evt-2"))
        recs = await _accounts(tenant_company)
        assert len(recs) == 1                       # upsert by external_id
        assert recs[0].data["name"] == "New"
        assert recs[0].external_ref["etag"] == "e2"
        assert await _signal_count(tenant_company, "object.synced") == 2


class _FakeSource:
    def __init__(self, events: list[SyncEvent]) -> None:
        self.events = events

    async def fetch_changes(self, object_name: str, since: Optional[str]) -> list[SyncEvent]:
        return [e for e in self.events if e.object_name == object_name]


class TestSweep:
    async def test_sweep_ingests_all_changes(self, tenant_company):
        await _mark_external(tenant_company, "Account", connector="test_conn")
        connector = ConnectorDef("test_conn", "finance", "Test", ConnectorBackend.OWN_ADAPTER,
                                 masters=("Account",), adapter="x", cost_sku="s")
        source = _FakeSource([
            SyncEvent("Account", "A1", {"name": "One"}, event_id="s1"),
            SyncEvent("Account", "A2", {"name": "Two"}, event_id="s2"),
        ])
        count = await sweep_connector(tenant_company, connector, source)
        assert count == 2
        assert len(await _accounts(tenant_company)) == 2
        assert await _signal_count(tenant_company, "object.synced") == 2
