"""Inc 6 / GATE T6 — the broadcast.inbound producer + the publish audit. ``needs_db``.

Written against the same properties `test_whatsapp_inbound_db.py` pins, because
the producer is deliberately the same shape: subscription-gated, deduped on the
platform's own id, ``trust: counterparty``, and it reaches the KAR-05 gateway
through the ordinary trigger machinery rather than a path of its own.

No live platform call is made (GATE decision 5) — the producer takes
already-fetched items, and fetching them is an injected transport.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.signals.broadcast_inbound import (
    emit_broadcast_inbound,
    emit_broadcast_published,
)
from src.ai.signals.models import Signal, SignalTrust, SignalTypes

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def bare_company():
    """A tenant with no Solo Pack — so no `broadcast.inbound` trigger."""
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
            {"id": str(cid), "n": f"gate-bare-{cid.hex[:8]}"})
        await s.commit()
    try:
        yield cid
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM signals WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


@pytest_asyncio.fixture
async def company():
    """A tenant with the Solo Pack activated.

    Activated rather than hand-seeded on purpose: the trigger that feeds KAR-05
    has to come from activation, so this fixture is also the proof that adding
    the gateway to ``GATEWAYS`` actually wires it for a real tenant.
    """
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.ai.solo_pack.activation import activate_solo_pack
    from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"gate-bcast-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    async with AsyncSessionLocal() as db:
        await activate_solo_pack(db, cid)
    try:
        yield cid
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            for tbl in ("trigger_registry", "budget_envelopes", "loop_runtime",
                        "wallet_holds", "signals", "execution_runs"):
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"),
                                {"c": str(cid)})
            await s.execute(
                text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


class TestSubscriptionGate:
    async def test_unsubscribed_tenant_emits_nothing(self, bare_company):
        """A tenant that has not asked for social routing must not have its
        comments quietly turned into leads."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            sid = await emit_broadcast_inbound(
                db, bare_company, platform="linkedin", item_id="c1", body="hello")
        assert sid is None

    async def test_activation_is_what_subscribes_a_tenant(self, company):
        """Adding KAR-05 to GATEWAYS has to actually wire it — otherwise the
        gateway exists as data and is fed by nothing."""
        from src.ai.signals.whatsapp_inbound import company_subscribes
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            assert await company_subscribes(
                db, company, SignalTypes.BROADCAST_INBOUND) is True

    async def test_subscribed_tenant_emits(self, company):
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            sid = await emit_broadcast_inbound(
                db, company, platform="linkedin", item_id="c1",
                body="do you do enterprise pricing?", author_handle="@someone")
        assert sid is not None

        async with AsyncSessionLocal() as db:
            sig = (await db.execute(
                select(Signal).where(Signal.id == sid))).scalar_one()
        assert sig.type == SignalTypes.BROADCAST_INBOUND
        # Every Karuna channel is counterparty-trust. A public comment is the
        # cheapest hostile input there is.
        assert sig.trust == SignalTrust.COUNTERPARTY
        assert sig.payload["platform"] == "linkedin"
        assert sig.payload["body"] == "do you do enterprise pricing?"


class TestDedupe:
    async def test_the_same_item_emits_once(self, company):
        """Polling re-reads the same window constantly; without dedupe the same
        comment becomes a lead every cycle."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            first = await emit_broadcast_inbound(
                db, company, platform="linkedin", item_id="c1", body="hi")
        async with AsyncSessionLocal() as db:
            second = await emit_broadcast_inbound(
                db, company, platform="linkedin", item_id="c1", body="hi")
        assert first is not None
        assert second is None

    async def test_the_same_id_on_two_platforms_is_two_items(self, company):
        """Two platforms can and do issue the same numeric id, so the dedupe
        key is scoped by platform."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            a = await emit_broadcast_inbound(
                db, company, platform="linkedin", item_id="12345", body="hi")
        async with AsyncSessionLocal() as db:
            b = await emit_broadcast_inbound(
                db, company, platform="reddit", item_id="12345", body="hi")
        assert a is not None and b is not None and a != b


class TestInteractionKind:
    async def test_an_unknown_kind_falls_back_rather_than_storing_junk(self, company):
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            sid = await emit_broadcast_inbound(
                db, company, platform="linkedin", item_id="c9", body="x",
                kind="something_new")
        async with AsyncSessionLocal() as db:
            sig = (await db.execute(select(Signal).where(Signal.id == sid))).scalar_one()
        assert sig.payload["kind"] == "comment"

    async def test_a_dm_is_recorded_as_a_dm(self, company):
        """A reply to a public comment is visible to everyone; answering a DM
        is not. The gateway needs to be able to tell them apart."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            sid = await emit_broadcast_inbound(
                db, company, platform="instagram", item_id="d1", body="x",
                kind="direct_message")
        async with AsyncSessionLocal() as db:
            sig = (await db.execute(select(Signal).where(Signal.id == sid))).scalar_one()
        assert sig.payload["kind"] == "direct_message"


class TestPublishAudit:
    async def test_a_publish_lands_on_the_bus(self, company):
        """Until GATE a public post left no trace at all, so "what did our
        agents say in public last week" had no answer."""
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            sid = await emit_broadcast_published(
                db, company, platform="linkedin", tool_name="linkedin_create_post",
                item_id="urn:li:share:1")
        assert sid is not None

        async with AsyncSessionLocal() as db:
            sig = (await db.execute(select(Signal).where(Signal.id == sid))).scalar_one()
        assert sig.type == SignalTypes.BROADCAST_PUBLISHED
        assert sig.trust == SignalTrust.INTERNAL
        assert sig.payload["tool"] == "linkedin_create_post"

    async def test_the_audit_is_not_subscription_gated(self, bare_company):
        """Deliberately unlike the inbound half. An audit record of something
        the platform actually did is not a routing decision — a tenant must not
        be able to end up with agents publishing and no record of it.

        This company has no trigger registered at all.
        """
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            sid = await emit_broadcast_published(
                db, bare_company, platform="tiktok", tool_name="tiktok_publish_video")
        assert sid is not None

    async def test_the_suppressed_count_travels(self, company):
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            sid = await emit_broadcast_published(
                db, company, platform="meta_ads",
                tool_name="meta_ads_manage_audiences", suppressed_count=3)
        async with AsyncSessionLocal() as db:
            sig = (await db.execute(select(Signal).where(Signal.id == sid))).scalar_one()
        assert sig.payload["audience_suppressed"] == 3


class TestReachesTheGateway:
    async def test_the_kar05_trigger_pattern_matches_the_signal(self, company):
        """The gateway is reached through the ordinary trigger machinery, not a
        path of its own — so if this pattern stops matching, the gateway simply
        stops being fed and nothing else breaks loudly."""
        from src.ai.signals.triggers import pattern_matches
        from src.ai.solo_pack.templates.gateways import KAR_05_BROADCAST

        for pattern in KAR_05_BROADCAST["metadata_extensions"]["trigger_patterns"]:
            assert pattern_matches(pattern, SignalTypes.BROADCAST_INBOUND)
