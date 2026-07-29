"""SEAM T7 — push subscriptions over real rows. ``needs_db``.

The wire is a fake transport throughout (no test may reach a live push
service). What the database proves: endpoint idempotency, the probe-shaped
unsubscribe, and the 410 revocation — a device the push service forgot must
not stay "active" forever.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

import src.auth.models  # noqa: F401 — registers users/companies for FK metadata
from src.ai.genui.models import PushSubscription
from src.ai.genui.push import send_tray_push, subscribe, unsubscribe

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def tenant_user():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, uid = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"push-test-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO users (id, email, full_name, hashed_password, "
                 "company_id, role, is_active, created_at, updated_at) "
                 "VALUES (:id, :e, 'Push Tester', 'x', :c, 'tenant_admin', "
                 "true, now(), now())"),
            {"id": str(uid), "e": f"push-{uid.hex[:10]}@test.local", "c": str(cid)})
        await s.commit()
    try:
        yield cid, uid
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(
                text("DELETE FROM push_subscriptions WHERE company_id = :c"),
                {"c": str(cid)})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


class TestPushSubscriptions:
    async def test_resubscribing_revives_the_same_endpoint(self, tenant_user):
        cid, uid = tenant_user
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            first = await subscribe(
                db, cid, uid, endpoint="https://push.example/abc",
                p256dh="k1", auth="a1")
            await unsubscribe(db, cid, uid, first.id)
            second = await subscribe(
                db, cid, uid, endpoint="https://push.example/abc",
                p256dh="k2", auth="a2")
        assert second.id == first.id
        assert second.revoked_at is None
        assert second.p256dh == "k2"

    async def test_unsubscribe_answers_foreign_and_unknown_alike(self, tenant_user):
        cid, uid = tenant_user
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            row = await subscribe(
                db, cid, uid, endpoint="https://push.example/mine",
                p256dh="k", auth="a")
            stranger = uuid.uuid4()
            assert await unsubscribe(db, cid, stranger, row.id) is False
            assert await unsubscribe(db, cid, uid, uuid.uuid4()) is False
            assert await unsubscribe(db, cid, uid, row.id) is True

    async def test_a_send_reaches_live_devices_and_revokes_dead_ones(self, tenant_user):
        cid, uid = tenant_user
        from src.common.database import AsyncSessionLocal

        sent: list[tuple[str, str]] = []

        def transport(endpoint, keys, payload, key, claims) -> int:
            sent.append((endpoint, payload))
            return 410 if "dead" in endpoint else 201

        async with AsyncSessionLocal() as db:
            await subscribe(db, cid, uid, endpoint="https://push.example/live",
                            p256dh="k", auth="a")
            await subscribe(db, cid, uid, endpoint="https://push.example/dead",
                            p256dh="k", auth="a")
            delivered = await send_tray_push(
                db, cid, uid, tray_id="t1",
                one_sentence="A payout needs you.", transport=transport)

        assert delivered == 1
        assert all('"tray_id": "t1"' in payload for _, payload in sent)
        async with AsyncSessionLocal() as db:
            dead = (await db.execute(
                select(PushSubscription).where(
                    PushSubscription.endpoint == "https://push.example/dead"))
            ).scalar_one()
        assert dead.revoked_at is not None
