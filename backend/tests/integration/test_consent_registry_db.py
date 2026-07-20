"""Inc 2 / TRUST — the consent registry enforces the tenant's posture (D6).

DNC, unsubscribe, and explicit-denial each block; absent any of those a send is
allowed (tenant-managed default, decision 8). End-to-end: with the registry
installed, KAR's ``check_outbound_consent`` seam honours a DNC entry.
``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.solo_pack.consent import check_outbound_consent, set_consent_checker
from src.ai.trust.consent_registry import (
    add_dnc,
    evaluate_consent,
    install_consent_registry,
    record_unsubscribe,
    set_consent,
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
            {"id": str(cid), "n": f"consent-test-{cid.hex[:8]}"})
        await s.commit()
    try:
        yield cid
    finally:
        async with AsyncSessionLocal() as s:
            for tbl in ("consent_records", "dnc_entries", "unsubscribe_log"):
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


class TestEvaluate:
    async def test_default_allows(self, company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            d = await evaluate_consent(db, company, "email", "new@lead.com",
                                       ConsentPurpose.TRANSACTIONAL)
        assert d.allowed is True

    async def test_dnc_blocks_any_purpose(self, company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await add_dnc(db, company, "whatsapp", "+1 (555) 111-2222", reason="asked to stop")
            await db.commit()
        async with AsyncSessionLocal() as db:
            # Different formatting of the same number still matches (normalised).
            d = await evaluate_consent(db, company, "whatsapp", "whatsapp:+15551112222",
                                       ConsentPurpose.MARKETING)
        assert d.allowed is False
        assert "do-not-contact" in d.reason

    async def test_unsubscribe_blocks_only_that_purpose(self, company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await record_unsubscribe(db, company, "email", "jo@x.com", ConsentPurpose.MARKETING)
            await db.commit()
        async with AsyncSessionLocal() as db:
            marketing = await evaluate_consent(db, company, "email", "jo@x.com",
                                               ConsentPurpose.MARKETING)
            transactional = await evaluate_consent(db, company, "email", "jo@x.com",
                                                   ConsentPurpose.TRANSACTIONAL)
        assert marketing.allowed is False
        assert transactional.allowed is True  # unsubscribe was purpose-scoped

    async def test_explicit_denial_blocks(self, company):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await set_consent(db, company, "email", "no@x.com", ConsentPurpose.MARKETING,
                              ConsentStatus.DENIED)
            await db.commit()
        async with AsyncSessionLocal() as db:
            d = await evaluate_consent(db, company, "email", "no@x.com", ConsentPurpose.MARKETING)
        assert d.allowed is False


async def test_seam_honours_registry_end_to_end(company):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await add_dnc(db, company, "whatsapp", "+15559998888")
        await db.commit()
    install_consent_registry()  # tenant-managed provider → the KAR seam
    try:
        blocked = await check_outbound_consent(company, "whatsapp", "+15559998888",
                                               ConsentPurpose.MARKETING)
        allowed = await check_outbound_consent(company, "whatsapp", "+15550000000",
                                               ConsentPurpose.TRANSACTIONAL)
        assert blocked.allowed is False
        assert allowed.allowed is True
    finally:
        set_consent_checker(None)
