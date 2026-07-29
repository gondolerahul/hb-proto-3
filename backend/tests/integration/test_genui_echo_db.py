"""SEAM T6 — the echo bus over real rows. ``needs_db``.

The load-bearing test is the reaper-in-producer one: writing an echo sweeps
this company's expired rows in the same transaction, so retention cannot
outlive its producer or run without one (the LIB T3 lesson, restated as a
property).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text

import src.auth.models  # noqa: F401 — registers users/companies for the FK metadata
from src.ai.genui.echo import install_echo_fanout, record_echo
from src.ai.genui.models import UiEcho

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
            {"id": str(cid), "n": f"echo-test-{cid.hex[:8]}"})
        await s.commit()
    try:
        yield cid
    finally:
        install_echo_fanout(None)
        async with AsyncSessionLocal() as s:
            await s.execute(
                text("DELETE FROM ui_echoes WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(
                text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


def _payload() -> dict:
    return {
        "sentence": "filtered Invoices to overdue",
        "action_ref": {"kind": "register.filter", "surface_id": "hall.accounting",
                       "params": {"filter": "overdue"}},
        "manifest_hash": "sha256:abc",
        "component_id": "c4",
    }


class TestEchoBus:
    async def test_an_echo_persists_with_its_audit_pair(self, company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            echo = await record_echo(db, company, None, _payload())
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(UiEcho).where(UiEcho.id == echo.id))).scalar_one()
        assert row.sentence == "filtered Invoices to overdue"
        assert row.action_ref["kind"] == "register.filter"
        assert row.manifest_hash == "sha256:abc"
        assert row.component_id == "c4"

    async def test_writing_an_echo_reaps_this_companys_expired_rows(self, company):
        from src.common.database import AsyncSessionLocal
        now = datetime.utcnow()
        async with AsyncSessionLocal() as db:
            stale = UiEcho(
                company_id=company, sentence="old act",
                action_ref={"kind": "x"}, occurred_at=now - timedelta(days=120),
                created_at=now - timedelta(days=120))
            fresh = UiEcho(
                company_id=company, sentence="recent act",
                action_ref={"kind": "x"}, occurred_at=now - timedelta(days=5),
                created_at=now - timedelta(days=5))
            db.add_all([stale, fresh])
            await db.commit()

        async with AsyncSessionLocal() as db:
            await record_echo(db, company, None, _payload(), now=now)

        async with AsyncSessionLocal() as db:
            sentences = {
                r.sentence for r in (await db.execute(
                    select(UiEcho).where(UiEcho.company_id == company))).scalars()}
        assert "old act" not in sentences
        assert {"recent act", "filtered Invoices to overdue"} <= sentences

    async def test_the_fanout_seam_fires_when_installed(self, company):
        from src.common.database import AsyncSessionLocal
        seen: list[str] = []

        async def listener(echo: UiEcho) -> None:
            seen.append(echo.sentence)

        install_echo_fanout(listener)
        try:
            async with AsyncSessionLocal() as db:
                await record_echo(db, company, None, _payload())
        finally:
            install_echo_fanout(None)
        assert seen == ["filtered Invoices to overdue"]
