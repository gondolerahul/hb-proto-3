"""Inc 4 / CONN T2 (db) — bindings persist, credentials encrypt, ACTIVE rehydrate.

Proves the write side of CONN against a real Postgres: activate upserts an
ACTIVE binding with the credential stored encrypted (never plaintext) and
write_allow defaulted from the catalog's read-only-first posture; pause flips
status; rehydrate binds ACTIVE rows into the live seam via an injected fake
resolver (no external server); a resolver failure marks the row ERROR without
sinking the others. ``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.connectors.models import BindingStatus
from src.ai.connectors.resolver import ClientResolver
from src.ai.connectors.service import (
    ConnectorNotBindable,
    ConnectorService,
    UnknownConnector,
)
from src.ai.tools.mcp.client import MCPCallResult, MCPToolDescriptor

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def company():
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
            {"id": str(cid), "n": f"conn-test-{cid.hex[:8]}"})
        await s.commit()
    try:
        yield cid
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM connector_bindings WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


class _FakeClient:
    async def list_tools(self) -> list[MCPToolDescriptor]:
        return [MCPToolDescriptor(name="get_invoice", annotations={"readOnlyHint": True})]

    async def call_tool(self, name: str, arguments: dict[str, object]) -> MCPCallResult:
        return MCPCallResult(text="{}")


class _FakeResolver:
    async def resolve(self, connector, binding, credentials) -> _FakeClient:  # type: ignore[no-untyped-def]
        return _FakeClient()


class _FailingResolver:
    async def resolve(self, connector, binding, credentials):  # type: ignore[no-untyped-def]
        raise RuntimeError("no transport here")


async def test_activate_persists_encrypted(company):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        svc = ConnectorService(db)
        binding = await svc.activate(company, "zoho_books",
                                     credentials={"access_token": "secret-tok"})
        assert binding.status == BindingStatus.ACTIVE
        assert binding.cost_sku == "mcp-zoho-books"
        # read-only-first: catalog default_write_allow flowed in
        assert "update_invoice" in binding.write_allow
        # the secret is encrypted, not the plaintext
        assert binding.encrypted_secret and "secret-tok" not in binding.encrypted_secret


async def test_get_list_and_pause(company):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        svc = ConnectorService(db)
        await svc.activate(company, "zoho_books", credentials={"k": "v"})
        assert (await svc.get_binding(company, "zoho_books")) is not None
        assert len(await svc.list_bindings(company)) == 1
        paused = await svc.pause(company, "zoho_books")
        assert paused is not None and paused.status == BindingStatus.PAUSED
        assert len(await svc.list_bindings(company, status=BindingStatus.ACTIVE)) == 0


async def test_reactivate_is_idempotent_and_clears_error(company):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        svc = ConnectorService(db)
        b1 = await svc.activate(company, "zoho_books", credentials={"k": "v"})
        b1_id = b1.id
        # simulate a prior error, then re-activate
        b1.status = BindingStatus.ERROR
        b1.last_error = "boom"
        await db.commit()
        b2 = await svc.activate(company, "zoho_books", credentials={"k": "v2"})
        assert b2.id == b1_id  # upsert, not a duplicate row
        assert b2.status == BindingStatus.ACTIVE
        assert b2.last_error is None
        assert len(await svc.list_bindings(company)) == 1


async def test_unknown_and_non_bindable_rejected(company):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        svc = ConnectorService(db)
        with pytest.raises(UnknownConnector):
            await svc.activate(company, "no_such_connector", credentials={})
        with pytest.raises(ConnectorNotBindable):
            await svc.activate(company, "tenant_data_query", credentials={})


async def test_rehydrate_binds_active(company):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        svc = ConnectorService(db)
        await svc.activate(company, "zoho_books", credentials={"access_token": "t"})
        resolver: ClientResolver = _FakeResolver()
        adapters = await svc.rehydrate(company, resolver=resolver, register=False)
        names = {a.name for a in adapters}
        assert "mcp__zoho_books__get_invoice" in names


async def test_rehydrate_failure_marks_error(company):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        svc = ConnectorService(db)
        await svc.activate(company, "zoho_books", credentials={"access_token": "t"})
        adapters = await svc.rehydrate(company, resolver=_FailingResolver(), register=False)
        assert adapters == []
        binding = await svc.get_binding(company, "zoho_books")
        assert binding is not None and binding.status == BindingStatus.ERROR
        assert "no transport here" in (binding.last_error or "")
