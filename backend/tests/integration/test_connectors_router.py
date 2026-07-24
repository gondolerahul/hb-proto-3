"""Inc 4 / CONN T8 — the /ai/connectors admin API (endpoint functions).

Exercised by calling the route handlers directly with a fake company-scoped user
(the auth dependency is the shipped get_current_user, tested elsewhere): the
catalog lists bindable connectors, bind→status→pause round-trips a binding
without ever leaking the secret, unknown/non-bindable are rejected, and the
ownership-migration two-step runs. ``needs_db``.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text

from src.ai.connectors.router import (
    BindRequest,
    MigrateRequest,
    apply_master_migration,
    bind,
    connector_status,
    get_bindings,
    get_catalog,
    pause,
    propose_master_migration,
)
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


def _db_url():
    import os

    from src.common.config import settings
    return getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")


async def _elevate(user) -> None:
    """Stamp a live T2+ ceremony on the console session, as a passkey would."""
    from src.ai.inward_auth.models import AuthLevel, ChannelKind
    from src.ai.inward_auth.sessions import elevate, get_or_create_session
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=user.company_id, user_id=user.id,
            channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="passkey", level=AuthLevel.OOB_CONFIRMED)
        await db.commit()


@pytest_asyncio.fixture
async def user():
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
            {"id": str(cid), "n": f"crouter-{cid.hex[:8]}"},
        )
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    # VG-05: binding a connector is now a T2 certified act, so the fixture needs
    # a real user (the session row FKs to it) holding a live ceremony. The
    # *refusal* path is covered in test_certified_actions_db.py; here we care
    # about the connector behaviour on the other side of the gate.
    uid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO users (id, company_id, email, full_name, hashed_password, "
                 "role, is_active, created_at, updated_at) VALUES "
                 "(:u, :c, :e, 'connector tester', 'x', 'admin', true, now(), now())"),
            {"u": str(uid), "c": str(cid), "e": f"crouter-{uid.hex[:8]}@example.test"})
        await s.commit()
    user_ns = SimpleNamespace(id=uid, company_id=cid, role="admin")
    await _elevate(user_ns)
    try:
        yield user_ns
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM connector_bindings WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM signals WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM account_manager_sessions WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM users WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def test_catalog_lists_connectors(user):
    catalog = await get_catalog(current_user=user)
    by_id = {c["connector_id"]: c for c in catalog}
    assert by_id["zoho_books"]["bindable"] is True
    assert "Invoice" in by_id["zoho_books"]["masters"]
    assert by_id["tenant_data_query"]["bindable"] is False   # platform-internal


async def test_bind_status_pause_roundtrip(user):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        view = await bind("zoho_books", BindRequest(credentials={"access_token": "s3cr3t"}),
                          current_user=user, db=db)
    assert view["status"] == "active" and view["has_credential"] is True
    assert "s3cr3t" not in str(view)               # the secret never leaves the server
    assert "encrypted_secret" not in view

    async with AsyncSessionLocal() as db:
        assert len(await get_bindings(current_user=user, db=db)) == 1
    async with AsyncSessionLocal() as db:
        assert (await connector_status("zoho_books", current_user=user, db=db))["status"] == "active"
    async with AsyncSessionLocal() as db:
        assert (await pause("zoho_books", current_user=user, db=db))["status"] == "paused"


async def test_bind_rejects_unknown_and_internal(user):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as ei:
            await bind("nope", BindRequest(), current_user=user, db=db)
        assert ei.value.status_code == 404
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as ei:
            await bind("tenant_data_query", BindRequest(), current_user=user, db=db)
        assert ei.value.status_code == 400


async def test_status_404_when_unbound(user):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as ei:
            await connector_status("zoho_books", current_user=user, db=db)
        assert ei.value.status_code == 404


async def test_ownership_migration_two_step(user):
    # Account is HireBuddha-mastered → propose then apply the flip to external.
    plan = await propose_master_migration(
        "Account", MigrateRequest(to_master="external", connector_id="zoho_books"),
        current_user=user)
    assert plan["from_master"] == "hirebuddha" and plan["to_master"] == "external"

    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await apply_master_migration(
            "Account", MigrateRequest(to_master="external", connector_id="zoho_books"),
            current_user=user, db=db)
    assert result["to_master"] == "external"


async def test_migration_bad_request(user):
    with pytest.raises(HTTPException) as ei:
        await propose_master_migration(
            "Account", MigrateRequest(to_master="external"), current_user=user)  # no connector
    assert ei.value.status_code == 400
