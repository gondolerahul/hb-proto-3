"""Inc 2 / TRUST — the platform-initiated envelope + admission (B13).

A tenant's platform envelope is a separate row from its Loop envelope, with its
own cap and no reserve; admission parks platform work at that cap while the Loop
envelope (tenant work) is untouched. ``needs_db``.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.loop.envelopes import ensure_loop_envelope
from src.ai.loop.models import BUDGET_CLASS_PLATFORM, BUDGET_CLASS_TENANT
from src.ai.loop.platform_budget import (
    default_platform_envelope_usd,
    ensure_platform_envelope,
    platform_spend_admitted,
    platform_work_admitted,
)
from src.ai.loop.service import ensure_sheel
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def tenant():
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
            {"id": str(cid), "n": f"b13-test-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    try:
        yield cid
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            for tbl in ("budget_envelopes", "loop_runtime", "signals", "execution_runs"):
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def test_platform_envelope_is_separate_from_the_loop(tenant):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        sheel = await ensure_sheel(db, tenant)
        loop_env = await ensure_loop_envelope(db, tenant, sheel.id)
        plat_env = await ensure_platform_envelope(db, tenant, sheel.id)
        await db.commit()
    # Two distinct envelopes on the same Loop, different class + cap.
    assert loop_env.id != plat_env.id
    assert loop_env.budget_class == BUDGET_CLASS_TENANT
    assert plat_env.budget_class == BUDGET_CLASS_PLATFORM
    assert Decimal(str(plat_env.envelope_usd)) == default_platform_envelope_usd()
    assert Decimal(str(plat_env.reserved_usd)) == Decimal("0")  # no reserve

    # ensure_loop_envelope still returns the tenant one (not the platform row).
    async with AsyncSessionLocal() as db:
        again = await ensure_loop_envelope(db, tenant, sheel.id)
    assert again.id == loop_env.id


async def test_admission_parks_at_cap(tenant):
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        sheel = await ensure_sheel(db, tenant)
        cap = default_platform_envelope_usd()
        # No platform spend yet → a request under the cap is admitted…
        under = await platform_spend_admitted(db, tenant, sheel.id, cap - Decimal("1"))
        # …one over the cap is parked (never tenant work).
        over = await platform_spend_admitted(db, tenant, sheel.id, cap + Decimal("1"))
        await db.commit()
    assert under is True
    assert over is False


async def test_work_admitted_resolves_the_loop_itself(tenant):
    """The call-site helper platform-initiated runners use — no Loop id needed."""
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await ensure_sheel(db, tenant)
        await db.commit()
    async with AsyncSessionLocal() as db:
        assert await platform_work_admitted(db, tenant) is True
        # Over the cap → the runner must park its platform work.
        over = await platform_work_admitted(
            db, tenant, default_platform_envelope_usd() + Decimal("1"))
        await db.commit()
    assert over is False


async def test_work_admitted_fails_open_without_a_loop(tenant):
    """No seeded Sheel = no envelope. Missing infra must not disable platform work."""
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        assert await platform_work_admitted(db, tenant) is True


async def test_admission_is_idempotent_on_envelope(tenant):
    # Repeated admission checks reuse one platform envelope, not many.
    from sqlalchemy import select

    from src.ai.loop.models import BudgetEnvelope
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        sheel = await ensure_sheel(db, tenant)
        await platform_spend_admitted(db, tenant, sheel.id, Decimal("1"))
        await platform_spend_admitted(db, tenant, sheel.id, Decimal("1"))
        await db.commit()
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(BudgetEnvelope).where(
                BudgetEnvelope.company_id == tenant,
                BudgetEnvelope.budget_class == BUDGET_CLASS_PLATFORM))).scalars().all()
    assert len(rows) == 1
