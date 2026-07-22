"""Inc 2 / TRUST — free-credit abuse controls against a live DB (E2).

Covers the two queries: the per-IP signup throttle counting recent companies by
their stamped ``onboarding_metadata.signup_ip``, and the daily-credit
eligibility gate (active + paying + has a verified user).

``needs_db``.
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.trust.abuse_controls import (
    SIGNUP_IP_KEY,
    daily_credit_eligibility,
    signup_allowed,
)
from src.ai.trust.dunning import SubscriptionStatus
from src.common.config import settings

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

TEST_IP = "198.51.100.77"


@pytest_asyncio.fixture
async def tracker():
    """Creates companies/users on demand and cleans every one up afterwards."""
    import os

    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    created: list[uuid.UUID] = []

    async def make_company(*, ip: str | None = None, status: str = "active",
                           subscription_status: str = SubscriptionStatus.CURRENT) -> uuid.UUID:
        cid = uuid.uuid4()
        metadata = {SIGNUP_IP_KEY: ip} if ip else {}
        async with AsyncSessionLocal() as s:
            await s.execute(
                text("INSERT INTO companies "
                     "(id, name, type, status, subscription_status, onboarding_metadata, "
                     " created_at, updated_at) "
                     "VALUES (:id, :n, 'TENANT', :st, :sub, CAST(:md AS jsonb), now(), now())"),
                {"id": str(cid), "n": f"abuse-{cid.hex[:8]}", "st": status,
                 "sub": subscription_status, "md": json.dumps(metadata)})
            await s.commit()
        created.append(cid)
        return cid

    async def make_user(company_id: uuid.UUID, *, verified: bool) -> None:
        async with AsyncSessionLocal() as s:
            await s.execute(
                text("INSERT INTO users (id, email, full_name, hashed_password, "
                     " company_id, role, is_active, is_verified, created_at, updated_at) "
                     "VALUES (:id, :e, 'T', 'x', :c, 'tenant_admin', true, :v, now(), now())"),
                {"id": str(uuid.uuid4()), "e": f"{uuid.uuid4().hex[:12]}@example.test",
                 "c": str(company_id), "v": verified})
            await s.commit()

    try:
        yield make_company, make_user
    finally:
        async with AsyncSessionLocal() as s:
            for cid in created:
                await s.execute(text("DELETE FROM users WHERE company_id = :c"), {"c": str(cid)})
                await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


class TestSignupThrottle:
    async def test_under_the_cap_is_allowed(self, tracker):
        from src.common.database import AsyncSessionLocal
        make_company, _ = tracker
        await make_company(ip=TEST_IP)
        async with AsyncSessionLocal() as db:
            assert await signup_allowed(db, TEST_IP) is True

    async def test_at_the_cap_is_blocked(self, tracker):
        from src.common.database import AsyncSessionLocal
        make_company, _ = tracker
        for _ in range(settings.TRUST_SIGNUP_MAX_PER_IP_PER_DAY):
            await make_company(ip=TEST_IP)
        async with AsyncSessionLocal() as db:
            assert await signup_allowed(db, TEST_IP) is False

    async def test_a_different_ip_is_unaffected(self, tracker):
        from src.common.database import AsyncSessionLocal
        make_company, _ = tracker
        for _ in range(settings.TRUST_SIGNUP_MAX_PER_IP_PER_DAY):
            await make_company(ip=TEST_IP)
        async with AsyncSessionLocal() as db:
            assert await signup_allowed(db, "203.0.113.200") is True

    async def test_absent_ip_is_never_throttled(self, tracker):
        """Admin/internal creation has no origin header and must not be blocked."""
        from src.common.database import AsyncSessionLocal
        make_company, _ = tracker
        for _ in range(settings.TRUST_SIGNUP_MAX_PER_IP_PER_DAY + 2):
            await make_company(ip=TEST_IP)
        async with AsyncSessionLocal() as db:
            assert await signup_allowed(db, None) is True


class TestDailyCreditEligibility:
    async def test_verified_active_company_is_eligible(self, tracker):
        from src.common.database import AsyncSessionLocal
        make_company, make_user = tracker
        cid = await make_company()
        await make_user(cid, verified=True)
        async with AsyncSessionLocal() as db:
            assert bool(await daily_credit_eligibility(db, cid))

    async def test_unverified_company_is_withheld(self, tracker):
        from src.common.database import AsyncSessionLocal
        make_company, make_user = tracker
        cid = await make_company()
        await make_user(cid, verified=False)
        async with AsyncSessionLocal() as db:
            result = await daily_credit_eligibility(db, cid)
        assert not result
        assert "verified" in result.reason

    async def test_read_only_company_is_withheld(self, tracker):
        """Past the paying states, free credits stop — that IS the dunning point."""
        from src.common.database import AsyncSessionLocal
        make_company, make_user = tracker
        cid = await make_company(subscription_status=SubscriptionStatus.READ_ONLY)
        await make_user(cid, verified=True)
        async with AsyncSessionLocal() as db:
            result = await daily_credit_eligibility(db, cid)
        assert not result
        assert SubscriptionStatus.READ_ONLY in result.reason

    async def test_grace_company_still_gets_credits(self, tracker):
        """Grace is full-function (C5 decision 1) — credits keep flowing."""
        from src.common.database import AsyncSessionLocal
        make_company, make_user = tracker
        cid = await make_company(subscription_status=SubscriptionStatus.GRACE)
        await make_user(cid, verified=True)
        async with AsyncSessionLocal() as db:
            assert bool(await daily_credit_eligibility(db, cid))

    async def test_inactive_company_is_withheld(self, tracker):
        from src.common.database import AsyncSessionLocal
        make_company, make_user = tracker
        cid = await make_company(status="suspended")
        await make_user(cid, verified=True)
        async with AsyncSessionLocal() as db:
            assert not await daily_credit_eligibility(db, cid)

    async def test_unknown_company_is_withheld(self, tracker):
        # Takes `tracker` purely for its engine.dispose() — pytest-asyncio gives
        # each test its own loop and asyncpg can't share pooled connections.
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await daily_credit_eligibility(db, uuid.uuid4())
        assert not result
        assert "not found" in result.reason
