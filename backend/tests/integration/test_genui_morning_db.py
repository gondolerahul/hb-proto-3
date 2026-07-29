"""LINE L1+L2 — the morning over real rows. ``needs_db``.

What only the database can prove: the generated story is stored and the
endpoint serves the stored telling (audio aligned); an empty wallet
degrades to text and says so; the WhatsApp summary reaches only a
verified binding; and the reaper clears past retention in the producing
job's own path.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

import src.auth.models  # noqa: F401 — registers users/companies for FK metadata
from src.ai.genui import morning_job as mj
from src.ai.genui.models import MorningStory
from src.ai.genui.morning import morning_story
from src.ai.orm.execution import ExecutionRun
from src.ai.solo_pack.activation import activate_slice
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


class FakeSpeaker:
    def stream(self, text_):
        async def _run():
            yield b"\x00\x01\x02\x03"
        return _run()


class RecordingTransport:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def __call__(self, to: str, message: str) -> bool:
        self.sent.append((to, message))
        return True


@pytest_asyncio.fixture
async def tenant():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, uid = uuid.uuid4(), uuid.uuid4()
    # One address belongs to at most one tenant, globally (iauth002) — a
    # fixed number would collide across fixture instances and dev data.
    address = f"91{uid.int % 10**10:010d}"
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"morning-test-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO users (id, email, full_name, hashed_password, "
                 "company_id, role, is_active, created_at, updated_at) "
                 "VALUES (:id, :e, 'Morning Owner', 'x', :c, 'tenant_admin', "
                 "true, now(), now())"),
            {"id": str(uid), "e": f"morning-{uid.hex[:10]}@test.local", "c": str(cid)})
        await s.execute(
            text("INSERT INTO channel_bindings (id, company_id, user_id, "
                 "channel_kind, address, verified_at, created_at) "
                 "VALUES (:id, :c, :u, 'whatsapp', :a, now(), now())"),
            {"id": str(uuid.uuid4()), "c": str(cid), "u": str(uid), "a": address})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    try:
        yield cid, uid, address
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            for tbl in ("morning_stories", "channel_bindings",
                        "tray_deliveries", "tray_recommendations"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text(
                "DELETE FROM human_approvals WHERE run_id IN "
                "(SELECT id FROM execution_runs WHERE company_id = :c)"), {"c": str(cid)})
            for tbl in ("execution_runs", "signals", "trigger_registry",
                        "budget_envelopes", "loop_runtime", "credit_wallets"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(
                text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                {"c": str(cid)})
            await s.execute(
                text("DELETE FROM users WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(
                text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def _seed_work(db, cid) -> None:
    result = await activate_slice(db, cid)
    agent_id = uuid.UUID(result["agt-015-proposal-quote"])
    run = ExecutionRun(entity_id=agent_id, company_id=cid, status="COMPLETED")
    db.add(run)
    await db.commit()


class TestMorning:
    async def test_the_generated_story_is_stored_voiced_and_summarized(
            self, tenant):
        cid, _uid, address = tenant
        from src.common.database import AsyncSessionLocal

        transport = RecordingTransport()
        async with AsyncSessionLocal() as db:
            await _seed_work(db, cid)
        async with AsyncSessionLocal() as db:
            summary = await mj.generate_for_company(
                db, cid, speaker=FakeSpeaker(), mirror_transport=transport)
        assert summary["cards"] > 0
        assert summary["voiced"] == summary["cards"]
        assert summary["degraded"] is None
        assert summary["summarized"] == 1
        assert transport.sent[0][0] == f"+{address}"
        assert transport.sent[0][1].startswith("Good morning. ")

        # The endpoint now serves the STORED telling, audio aligned.
        async with AsyncSessionLocal() as db:
            story = await morning_story(db, cid)
        assert story["generated_at"] is not None
        assert story["degraded_reason"] is None
        assert all(card["audio"] is not None for card in story["cards"])

    async def test_an_empty_wallet_degrades_to_text_and_says_so(self, tenant):
        cid, _uid, address = tenant
        from src.common.database import AsyncSessionLocal

        async def no_wallet(db, company_id):
            return False

        async with AsyncSessionLocal() as db:
            await _seed_work(db, cid)
        async with AsyncSessionLocal() as db:
            summary = await mj.generate_for_company(
                db, cid, speaker=FakeSpeaker(),
                mirror_transport=RecordingTransport(),
                wallet_allows=no_wallet)
        assert summary["voiced"] == 0
        assert summary["degraded"] == "wallet"
        async with AsyncSessionLocal() as db:
            story = await morning_story(db, cid)
        assert story["degraded_reason"] == "wallet"
        assert all(card["audio"] is None for card in story["cards"])

    async def test_the_reaper_clears_past_retention_in_the_producers_job(
            self, tenant):
        cid, _uid, address = tenant
        from src.common.database import AsyncSessionLocal

        old_date = (datetime.utcnow() - timedelta(
            days=mj.RETENTION_DAYS + 5)).date()
        async with AsyncSessionLocal() as db:
            db.add(MorningStory(
                company_id=cid, story_date=old_date, cards=[],
                generated_at=datetime.utcnow()))
            await db.commit()
        async with AsyncSessionLocal() as db:
            reaped = await mj.reap_old_stories(db)
        assert reaped >= 1
        async with AsyncSessionLocal() as db:
            assert await db.get(MorningStory, (cid, old_date)) is None
