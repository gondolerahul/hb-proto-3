"""DRIVER D3 — the bulk endpoint, mutation-testing its own gate. ``needs_db``.

``POST /ai/tenant/records/bulk`` is the seventh gated call site (a
*ceremony-only* gate in R5's table — its certified surface is the generic
step-up, D6 §7). What only this suite can prove: the gate refuses an
un-elevated session BEFORE any write happens, the same request applies
once elevated, and per-record failures are reported rather than silently
skipped. Handlers are called directly (the repo's router-test convention —
which is exactly why the gate lives in the handler body).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text

from src.ai.inward_auth.models import AuthLevel, ChannelKind
from src.ai.inward_auth.sessions import elevate, get_or_create_session
from src.ai.tenant_schema.api import BulkRequest, bulk_records
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
from src.ai.tenant_schema.record_service import RecordService

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


def _db_url():
    import os

    from src.common.config import settings
    return getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")


@pytest_asyncio.fixture
async def tenant():
    if not _db_url():
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, uid = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"bulk-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO users (id, company_id, email, full_name, hashed_password, "
                 "role, is_active, created_at, updated_at) VALUES "
                 "(:u, :c, :e, 'bulk tester', 'x', 'admin', true, now(), now())"),
            {"u": str(uid), "c": str(cid), "e": f"bulk-{uid.hex[:8]}@example.test"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    user = SimpleNamespace(company_id=cid, id=uid, role="admin")
    try:
        yield user
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            for tbl in ("account_manager_sessions", "signals"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM users WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def _seed_leads(cid: uuid.UUID, n: int) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    async with tenant_data_plane.session(cid) as ts:
        svc = RecordService(ts, cid)
        for i in range(n):
            res = await svc.create("Lead", {"display_name": f"Lead {i}", "status": "new"})
            assert res.record is not None
            ids.append(res.record.id)
        await ts.commit()
    return ids


async def _elevate_console(user) -> None:
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        session = await get_or_create_session(
            db, company_id=user.company_id, user_id=user.id,
            channel_kind=ChannelKind.CONSOLE)
        await elevate(db, session, method="passkey", level=AuthLevel.OOB_CONFIRMED)
        await db.commit()


async def test_bulk_refuses_an_unelevated_session_before_any_write(tenant):
    from src.common.database import AsyncSessionLocal

    ids = await _seed_leads(tenant.company_id, 3)
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await bulk_records(
                BulkRequest(def_name="Lead", op="update", record_ids=ids,
                            data={"status": "qualified"}),
                db, tenant)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "step_up_required"
    assert exc.value.detail["tier"] == "T2"

    # The gate ran before the loop: nothing changed.
    async with tenant_data_plane.session(tenant.company_id) as ts:
        svc = RecordService(ts, tenant.company_id)
        for rid in ids:
            rec = await svc.get(rid)
            assert rec is not None and rec.data["status"] == "new"


async def test_the_same_bulk_applies_once_elevated(tenant):
    from src.common.database import AsyncSessionLocal

    ids = await _seed_leads(tenant.company_id, 3)
    await _elevate_console(tenant)
    async with AsyncSessionLocal() as db:
        out = await bulk_records(
            BulkRequest(def_name="Lead", op="update", record_ids=ids,
                        data={"status": "qualified"}),
            db, tenant)
    assert out["applied"] == 3
    async with tenant_data_plane.session(tenant.company_id) as ts:
        svc = RecordService(ts, tenant.company_id)
        for rid in ids:
            rec = await svc.get(rid)
            assert rec is not None and rec.data["status"] == "qualified"


async def test_a_missing_record_is_reported_not_silently_skipped(tenant):
    from src.common.database import AsyncSessionLocal

    ids = await _seed_leads(tenant.company_id, 2)
    ghost = uuid.uuid4()
    await _elevate_console(tenant)
    async with AsyncSessionLocal() as db:
        out = await bulk_records(
            BulkRequest(def_name="Lead", op="delete",
                        record_ids=[*ids, ghost]),
            db, tenant)
    assert out["applied"] == 2
    statuses = {r["id"]: r["status"] for r in out["results"]}
    assert statuses[str(ghost)] in ("not_found", "error")
