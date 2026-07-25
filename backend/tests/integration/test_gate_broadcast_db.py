"""Inc 6 / GATE T3+T4 — channel posture against real registry rows. ``needs_db``.

The unit tests exercise the policy through an injected checker. This exercises
the storage decision: a channel-wide posture is a ``consent_records`` /
``dnc_entries`` row under a sentinel identity, which is what let GATE add the
posture with no migration. The risk that buys is collision — one counterparty
address normalising onto the sentinel would silently mute a tenant's entire
channel — so that is what most of this file is about.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.solo_pack.consent import check_channel_posture, set_channel_posture_checker
from src.ai.trust.consent_registry import (
    CHANNEL_POSTURE_IDENTITY,
    add_dnc,
    evaluate_channel_posture,
    evaluate_consent,
    install_consent_registry,
    normalise_identity,
    set_channel_posture,
)
from src.ai.trust.models import ConsentPurpose, ConsentStatus

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
            {"id": str(cid), "n": f"gate-test-{cid.hex[:8]}"})
        await s.commit()
    try:
        yield cid
    finally:
        set_channel_posture_checker(None)
        async with AsyncSessionLocal() as s:
            for tbl in ("consent_records", "dnc_entries", "unsubscribe_log"):
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"),
                                {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


class TestChannelPosture:
    async def test_absent_posture_allows(self, company):
        """Inc-2 decision 8 — permissive until the tenant configures it."""
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            d = await evaluate_channel_posture(db, company, "linkedin")
        assert d.allowed is True
        assert "governed by band alone" in d.reason

    async def test_denied_record_blocks_that_purpose_only(self, company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await set_channel_posture(
                db, company, "linkedin", ConsentPurpose.MARKETING, ConsentStatus.DENIED)
            await db.commit()
        async with AsyncSessionLocal() as db:
            marketing = await evaluate_channel_posture(
                db, company, "linkedin", ConsentPurpose.MARKETING)
            transactional = await evaluate_channel_posture(
                db, company, "linkedin", ConsentPurpose.TRANSACTIONAL)
        assert marketing.allowed is False
        # A tenant that refuses marketing on a channel keeps its support replies.
        assert transactional.allowed is True

    async def test_dnc_on_the_sentinel_switches_the_whole_channel_off(self, company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await add_dnc(db, company, "linkedin", CHANNEL_POSTURE_IDENTITY,
                          reason="regulated out of public statements")
            await db.commit()
        async with AsyncSessionLocal() as db:
            for purpose in (ConsentPurpose.MARKETING, ConsentPurpose.TRANSACTIONAL):
                d = await evaluate_channel_posture(db, company, "linkedin", purpose)
                assert d.allowed is False, purpose

    async def test_posture_is_per_channel(self, company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await set_channel_posture(
                db, company, "linkedin", ConsentPurpose.MARKETING, ConsentStatus.DENIED)
            await db.commit()
        async with AsyncSessionLocal() as db:
            assert (await evaluate_channel_posture(
                db, company, "linkedin", ConsentPurpose.MARKETING)).allowed is False
            assert (await evaluate_channel_posture(
                db, company, "tiktok", ConsentPurpose.MARKETING)).allowed is True

    async def test_setting_posture_twice_updates_rather_than_duplicates(self, company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await set_channel_posture(
                db, company, "linkedin", ConsentPurpose.MARKETING, ConsentStatus.DENIED)
            await set_channel_posture(
                db, company, "linkedin", ConsentPurpose.MARKETING, ConsentStatus.GRANTED)
            await db.commit()
        async with AsyncSessionLocal() as db:
            count = (await db.execute(
                text("SELECT count(*) FROM consent_records WHERE company_id = :c"),
                {"c": str(company)})).scalar()
            d = await evaluate_channel_posture(
                db, company, "linkedin", ConsentPurpose.MARKETING)
        assert count == 1
        assert d.allowed is True


class TestSentinelIsolation:
    """The sentinel must not be reachable from a real counterparty address."""

    def test_normalisation_cannot_produce_the_sentinel(self):
        """The only function that could map some other string onto the posture
        key. On phone channels it strips to digits; on the rest it lowercases —
        neither can synthesise the sentinel from a well-formed address."""
        for channel in ("linkedin", "email", "whatsapp", "voice", "sms"):
            for address in (
                "someone@example.com", "SOMEONE@EXAMPLE.COM", "+1 555 111 2222",
                "  spaced@example.com  ", "Channel", "__CHANNEL__",
            ):
                normalised = normalise_identity(channel, address)
                if normalised == CHANNEL_POSTURE_IDENTITY:
                    # The one string that survives lowercasing unchanged is the
                    # sentinel itself, which is not a valid address anywhere.
                    assert address.lower() == CHANNEL_POSTURE_IDENTITY

    async def test_channel_posture_does_not_leak_into_person_consent(self, company):
        """Switching a channel off must not put anybody on the DNC list."""
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await add_dnc(db, company, "linkedin", CHANNEL_POSTURE_IDENTITY)
            await db.commit()
        async with AsyncSessionLocal() as db:
            person = await evaluate_consent(
                db, company, "linkedin", "someone@example.com",
                ConsentPurpose.MARKETING)
        assert person.allowed is True

    async def test_person_dnc_does_not_leak_into_channel_posture(self, company):
        """And the reverse: one unsubscribed person must not mute the channel.

        This is the failure the sentinel choice exists to prevent, so it is
        asserted rather than assumed.
        """
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await add_dnc(db, company, "linkedin", "someone@example.com")
            await db.commit()
        async with AsyncSessionLocal() as db:
            posture = await evaluate_channel_posture(db, company, "linkedin")
        assert posture.allowed is True


class TestSeamInstallation:
    async def test_install_wires_both_seams(self, company):
        """Installing consent must not leave broadcast posture permissive —
        a deployment with one enforced and the other silently open is exactly
        the failure this workstream is fixing."""
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await set_channel_posture(
                db, company, "linkedin", ConsentPurpose.MARKETING, ConsentStatus.DENIED)
            await db.commit()

        install_consent_registry()
        try:
            decision = await check_channel_posture(company, "linkedin", "marketing")
        finally:
            set_channel_posture_checker(None)
        assert decision.allowed is False
