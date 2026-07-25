"""SEGA T0 — a tenant may not read another tenant's tools.

The defect this pins, found while mapping SEGA against the code: both read
paths on `/api/v1/ai/tool-registry` selected `ToolRegistryEntry` with no
company filter, behind plain `get_current_user`. Any authenticated user could
therefore list and read **every other tenant's** custom and synthesized tool
entries — including the `configuration` blob, which for a synthesized tool
carries its spec, source and audit, i.e. a description of how that business
does something.

Writes were already `app_admin_only`, so this was cross-tenant *disclosure*,
not mutation. Same shape as the VG-05 approvals IDOR (a read beside a write,
scoped differently) and the same fix: scope first, 404 on a cross-tenant miss.

Handlers are called directly with a company-scoped fake user, matching
`test_certified_actions_db.py`. ``needs_db``.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


def _db_url():
    import os

    from src.common.config import settings
    return getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")


async def _make_company(label: str) -> uuid.UUID:
    from src.common.database import AsyncSessionLocal

    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"{label}-{cid.hex[:8]}"})
        await s.commit()
    return cid


async def _make_tool(company_id: uuid.UUID | None, name: str) -> uuid.UUID:
    """A synthesized tool — the worst case, because its configuration carries
    the spec and audit of how a business does something."""
    from src.common.database import AsyncSessionLocal

    tool_id = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO tool_registry_entries (id, company_id, name, "
                 "display_name, description, category, tool_type, "
                 "function_schema, is_enabled, configuration, created_at, updated_at) "
                 "VALUES (:i, :c, :n, :n, 'x', 'synthesized', 'SYNTHESIZED', "
                 "CAST(:fs AS json), false, CAST(:cfg AS json), now(), now())"),
            {"i": str(tool_id), "c": str(company_id) if company_id else None,
             "n": name, "fs": json.dumps({"name": name}),
             "cfg": json.dumps({"status": "DRAFT", "spec": {"secret_sauce": name},
                                "source": "synthesis", "audit": {}})})
        await s.commit()
    return tool_id


async def _drop(company_ids, tool_ids) -> None:
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        for tid in tool_ids:
            await s.execute(text("DELETE FROM tool_registry_entries WHERE id = :i"),
                            {"i": str(tid)})
        for cid in company_ids:
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
        await s.commit()


@pytest_asyncio.fixture
async def estate():
    """Two tenants with a synthesized tool each, plus one platform tool."""
    if not _db_url():
        pytest.skip("DATABASE_URL not set")
    from src.common.database import engine

    await engine.dispose()
    alice = await _make_company("tools-a")
    bob = await _make_company("tools-b")
    marker = uuid.uuid4().hex[:8]
    alice_tool = await _make_tool(alice, f"alice_secret_{marker}")
    bob_tool = await _make_tool(bob, f"bob_secret_{marker}")
    platform_tool = await _make_tool(None, f"platform_shared_{marker}")

    try:
        yield SimpleNamespace(
            alice=alice, bob=bob, alice_tool=alice_tool,
            bob_tool=bob_tool, platform_tool=platform_tool, marker=marker)
    finally:
        await _drop([alice, bob], [alice_tool, bob_tool, platform_tool])


def _user(company_id: uuid.UUID, role: str = "tenant_admin"):
    return SimpleNamespace(id=uuid.uuid4(), company_id=company_id, role=role)


# ── the leak, closed ─────────────────────────────────────────────────────────

async def test_a_tenant_cannot_read_another_tenants_tool(estate):
    """The headline: a valid id from another tenant is a 404, not a document."""
    from src.ai.tool_management_router import get_tool
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await get_tool(estate.bob_tool, db=db, current_user=_user(estate.alice))

    assert exc.value.status_code == 404, (
        "a cross-tenant miss must not be a 403 — a probe must not learn the id "
        "exists somewhere else")


async def test_a_tenant_cannot_list_another_tenants_tool(estate):
    """The list path leaked more than the detail path: every tenant's entry, in
    one response, `configuration` included."""
    from src.ai.tool_management_router import list_all_tools
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        listed = await list_all_tools(db=db, current_user=_user(estate.alice))

    names = {t["name"] for t in listed}
    assert f"alice_secret_{estate.marker}" in names
    assert f"bob_secret_{estate.marker}" not in names, "another tenant's tool leaked"

    blobs = json.dumps([t.get("configuration") for t in listed])
    assert f"bob_secret_{estate.marker}" not in blobs, (
        "another tenant's synthesized spec leaked through configuration")


async def test_a_tenant_still_sees_its_own_and_the_platforms(estate):
    """Scoping must not take away what a tenant is supposed to have.

    Platform tools carry `company_id IS NULL` and are shared by construction —
    over-tightening here would break every tenant's tool list, which is the
    failure mode a scoping fix most easily introduces.
    """
    from src.ai.tool_management_router import get_tool, list_all_tools
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        listed = await list_all_tools(db=db, current_user=_user(estate.alice))
        names = {t["name"] for t in listed}
        assert f"alice_secret_{estate.marker}" in names
        assert f"platform_shared_{estate.marker}" in names

        own = await get_tool(estate.alice_tool, db=db, current_user=_user(estate.alice))
        assert own.id == estate.alice_tool
        shared = await get_tool(estate.platform_tool, db=db,
                                current_user=_user(estate.alice))
        assert shared.id == estate.platform_tool


async def test_built_in_tools_survive_the_scoping(estate):
    """The merge starts from the in-memory registry, which is not company-scoped
    at all — a tenant must still get the built-in catalogue."""
    from src.ai.tool_management_router import list_all_tools
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        listed = await list_all_tools(db=db, current_user=_user(estate.alice))

    assert any(t["tool_type"] == "BUILT_IN" for t in listed)


async def test_the_platform_admin_still_sees_everything(estate):
    """The fleet is an app_admin's job, and the pre-Inc-6 behaviour is kept for
    them deliberately — this closes a tenant-to-tenant leak, not an admin
    console."""
    from src.ai.tool_management_router import get_tool, list_all_tools
    from src.common.database import AsyncSessionLocal

    admin = _user(estate.alice, role="app_admin")
    async with AsyncSessionLocal() as db:
        listed = await list_all_tools(db=db, current_user=admin)
        names = {t["name"] for t in listed}
        assert f"alice_secret_{estate.marker}" in names
        assert f"bob_secret_{estate.marker}" in names

        assert (await get_tool(estate.bob_tool, db=db, current_user=admin)).id == estate.bob_tool


async def test_the_admin_write_paths_are_unscoped_on_purpose(estate):
    """`update_tool` / `delete_tool` / `toggle_tool` load through the unrestricted
    read because they are already `app_admin_only`. Scoping them would break
    platform administration to fix a hole that is not on that path."""
    from src.ai.tool_management_service import ToolManagementService
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        entry = await ToolManagementService(db).get_tool(estate.bob_tool)
    assert entry.id == estate.bob_tool
