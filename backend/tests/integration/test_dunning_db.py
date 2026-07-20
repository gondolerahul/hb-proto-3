"""Inc 2 / TRUST — advance_dunning transitions a company + emits a signal (C5).

``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.signals.models import Signal
from src.ai.trust.dunning import SubscriptionStatus, advance_dunning
from src.auth.models import Company

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
            {"id": str(cid), "n": f"dunning-{cid.hex[:8]}"})
        await s.commit()
    try:
        yield cid
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM signals WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


async def test_advance_moves_status_and_emits_signal(company):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        status = await advance_dunning(db, company, days_past_due=10)  # → read_only
        await db.commit()
    assert status == SubscriptionStatus.READ_ONLY

    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(Company).where(Company.id == company))).scalar_one()
        assert row.subscription_status == SubscriptionStatus.READ_ONLY
        sig = (await db.execute(
            select(Signal).where(Signal.company_id == company,
                                 Signal.type == "billing.read_only"))).scalars().first()
    assert sig is not None
    assert sig.payload["days_past_due"] == 10


async def test_advance_is_idempotent(company):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await advance_dunning(db, company, days_past_due=10)
        await db.commit()
    async with AsyncSessionLocal() as db:
        again = await advance_dunning(db, company, days_past_due=10)  # same bucket
        await db.commit()
    assert again == SubscriptionStatus.READ_ONLY

    async with AsyncSessionLocal() as db:
        sigs = (await db.execute(
            select(Signal).where(Signal.company_id == company,
                                 Signal.type == "billing.read_only"))).scalars().all()
    assert len(sigs) == 1  # no duplicate transition signal


async def test_recovery_back_to_current(company):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await advance_dunning(db, company, days_past_due=10)   # read_only
        await db.commit()
    async with AsyncSessionLocal() as db:
        recovered = await advance_dunning(db, company, days_past_due=0)  # paid up
        await db.commit()
    assert recovered == SubscriptionStatus.CURRENT
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(Company).where(Company.id == company))).scalar_one()
    assert row.subscription_status == SubscriptionStatus.CURRENT
