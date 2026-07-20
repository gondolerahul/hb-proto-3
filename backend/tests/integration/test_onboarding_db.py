"""Inc 2 / ONBOARD — the wizard activate + status steps against a live tenant.

Step 4 (activate) seeds the pack via PACK's activation; step 5 (status) reports
what's live. ``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.solo_pack.onboarding import activate_for_company, onboarding_status
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def onboard_tenant():
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
            {"id": str(cid), "n": f"onboard-test-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    try:
        yield cid
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            for tbl in ("trigger_registry", "budget_envelopes", "loop_runtime",
                        "wallet_holds", "signals", "execution_runs"):
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def test_status_before_and_after_activation(onboard_tenant):
    cid = onboard_tenant
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        before = await onboarding_status(db, cid)
    assert before["activated"] is False
    assert before["entity_count"] == 0

    async with AsyncSessionLocal() as db:
        result = await activate_for_company(db, cid, "solo_pack")
    assert len(result) == 18

    async with AsyncSessionLocal() as db:
        after = await onboarding_status(db, cid)
    assert after["activated"] is True
    assert after["entity_count"] == 18       # solo_pack-tagged entities (not Sheel)
    assert after["trigger_count"] == 16
    assert after["console_path"] == "/app/approvals"
    assert "kar-03-whatsapp-gateway" in after["entities"]


async def test_activate_a_single_bundle(onboard_tenant):
    cid = onboard_tenant
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await activate_for_company(db, cid, "compliance")
    # Compliance seeds P14 + its agent (+ the shared gateways).
    assert "p14-continuous-guardrails" in result
    assert "agt-068-regulatory-watchdog" in result

    async with AsyncSessionLocal() as db:
        status = await onboarding_status(db, cid)
    assert status["activated"] is True
    assert "p14-continuous-guardrails" in status["entities"]
    # A finance process is NOT part of the compliance bundle.
    assert "p08-order-to-cash" not in status["entities"]


async def test_envelope_view_after_activation(onboard_tenant):
    # The admin envelope surface: activation ensures Sheel + its budget envelope.
    cid = onboard_tenant
    from sqlalchemy import select

    from src.ai.loop.api import envelope_out
    from src.ai.loop.models import BudgetEnvelope
    from src.common.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await activate_for_company(db, cid, "solo_pack")
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(BudgetEnvelope).where(BudgetEnvelope.company_id == cid))).scalars().all()
    assert len(rows) >= 1
    view = envelope_out(rows[0])
    assert view["utilization_pct"] >= 0.0
    assert view["reserved_usd"] > 0.0            # the protected reserve is carved out
    assert view["downshift"] in (True, False)
    assert view["capped"] in (True, False)
