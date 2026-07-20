"""Inc 2 / TRUST — the checkpoint SLA sweep applies the right fallback (C3).

An overdue PENDING approval is auto-denied (money), parked (comms), or escalated
(governance) per its checkpoint; a within-SLA approval is left alone.
``needs_db``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.governance.checkpoint_sla import TIMEOUT_STATUS, apply_checkpoint_timeouts
from src.ai.loop.service import ensure_sheel
from src.ai.orm.execution import HumanApproval
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def run_ctx():
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
            {"id": str(cid), "n": f"sla-test-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    async with AsyncSessionLocal() as db:
        sheel = await ensure_sheel(db, cid)
        run_id = uuid.uuid4()
        await db.execute(
            text("INSERT INTO execution_runs (id, entity_id, company_id, status, created_at) "
                 "VALUES (:r, :e, :c, 'PAUSED', now())"),
            {"r": str(run_id), "e": str(sheel.id), "c": str(cid)})
        await db.commit()
    try:
        yield cid, run_id
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            await s.execute(text(
                "DELETE FROM human_approvals WHERE run_id IN "
                "(SELECT id FROM execution_runs WHERE company_id = :c)"), {"c": str(cid)})
            for tbl in ("signals", "budget_envelopes", "loop_runtime", "execution_runs"):
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def _add_approval(db, run_id, checkpoint_key, requested_at) -> uuid.UUID:
    aid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO human_approvals "
             "(id, run_id, checkpoint_trigger, checkpoint_key, status, requested_at) "
             "VALUES (:id, :r, :t, :k, 'PENDING', :ts)"),
        {"id": str(aid), "r": str(run_id), "t": checkpoint_key, "k": checkpoint_key,
         "ts": requested_at})
    return aid


async def test_sweep_applies_per_checkpoint_fallbacks(run_ctx):
    cid, run_id = run_ctx
    from src.common.database import AsyncSessionLocal
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        # payout SLA 4h — overdue → auto_deny.
        payout = await _add_approval(
            db, run_id, "before_outbound_payout_above_band", now - timedelta(hours=5))
        # email SLA 24h — overdue → auto_park (stays PENDING).
        email = await _add_approval(
            db, run_id, "before_high_value_email_dispatch", now - timedelta(hours=25))
        # governance SLA 48h — overdue → escalate (stays PENDING).
        gov = await _add_approval(
            db, run_id, "before_autonomy_level_promotion", now - timedelta(hours=49))
        # payout, fresh — within SLA → untouched.
        fresh = await _add_approval(
            db, run_id, "before_outbound_payout_above_band", now)
        await db.commit()

    async with AsyncSessionLocal() as db:
        counts = await apply_checkpoint_timeouts(db, now=now)
        await db.commit()

    assert counts["auto_denied"] == 1
    assert counts["auto_parked"] == 1
    assert counts["escalated"] == 1

    async with AsyncSessionLocal() as db:
        by_id = {a.id: a for a in (await db.execute(
            select(HumanApproval).where(HumanApproval.run_id == run_id))).scalars().all()}
    assert by_id[payout].status == TIMEOUT_STATUS      # auto-denied, fail-safe
    assert by_id[payout].responded_at is not None
    assert by_id[email].status == "PENDING"            # parked, re-raises
    assert by_id[gov].status == "PENDING"              # escalated, still needs a human
    assert by_id[fresh].status == "PENDING"            # within SLA, untouched


async def test_auto_deny_emits_signal(run_ctx):
    cid, run_id = run_ctx
    from src.ai.signals.models import Signal
    from src.common.database import AsyncSessionLocal
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        await _add_approval(db, run_id, "before_refund_above_band", now - timedelta(hours=5))
        await db.commit()
    async with AsyncSessionLocal() as db:
        await apply_checkpoint_timeouts(db, now=now)
        await db.commit()
    async with AsyncSessionLocal() as db:
        sig = (await db.execute(
            select(Signal).where(Signal.company_id == cid,
                                 Signal.type == "approval.auto_denied"))).scalars().first()
    assert sig is not None
    assert sig.payload["checkpoint_key"] == "before_refund_above_band"
