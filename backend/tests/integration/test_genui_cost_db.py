"""DRIVER D2 — the cost estimator over real rows. ``needs_db``.

What only the database can prove: the **company scope** (no platform-wide
fallback — the design's named violation), the trailing **window**, the
**post-approval** placement of spend, and the tray composer picking the
estimate up for an amountless gate.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.genui.cost import observed_decision_cost, reset_cost_cache
from src.ai.genui.trays import tray_list
from src.ai.orm.execution import ExecutionRun, HumanApproval
from src.ai.solo_pack.activation import activate_slice
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

CHECKPOINT = "before_external_communication"
NOW = datetime.utcnow()


async def _make_company(s, tag: str) -> uuid.UUID:
    cid = uuid.uuid4()
    await s.execute(
        text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
             "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
        {"id": str(cid), "n": f"cost-{tag}-{cid.hex[:8]}"})
    return cid


async def _cleanup_company(engine, AsyncSessionLocal, cid: uuid.UUID) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
    async with AsyncSessionLocal() as s:
        await s.execute(text(
            "DELETE FROM usage_logs WHERE company_id = :c"), {"c": str(cid)})
        await s.execute(text(
            "DELETE FROM human_approvals WHERE run_id IN "
            "(SELECT id FROM execution_runs WHERE company_id = :c)"), {"c": str(cid)})
        for tbl in ("integration_registry", "execution_runs", "signals",
                    "trigger_registry", "budget_envelopes", "loop_runtime"):
            await s.execute(
                text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
        await s.execute(
            text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
            {"c": str(cid)})
        await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
        await s.commit()


@pytest_asyncio.fixture
async def two_tenants():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    reset_cost_cache()
    async with AsyncSessionLocal() as s:
        cid_a = await _make_company(s, "a")
        cid_b = await _make_company(s, "b")
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid_a)
    await tenant_data_plane.ensure_ready(cid_b)
    try:
        yield cid_a, cid_b
    finally:
        for cid in (cid_a, cid_b):
            await _cleanup_company(engine, AsyncSessionLocal, cid)
        tenant_data_plane.reset_cache()
        reset_cost_cache()


async def _seed_sku(s, cid: uuid.UUID) -> uuid.UUID:
    sku_id = uuid.uuid4()
    await s.execute(text(
        "INSERT INTO integration_registry (id, company_id, provider_name, model_name, "
        "service_sku, service_category, component_type, internal_cost, cost_unit, status, "
        "created_at, updated_at) VALUES (:id, :c, 'testprov', 'm', :sku, 'LLM', "
        "'input_token', 0.002, '1k tokens', 'active', now(), now())"),
        {"id": str(sku_id), "c": str(cid), "sku": f"cost-sku-{sku_id.hex[:6]}"})
    return sku_id


async def _approved_with_spend(
    db, cid: uuid.UUID, agent_id: uuid.UUID, sku_id: uuid.UUID,
    *, spend: Decimal | None, responded_at: datetime,
    spend_at_offset_s: int = 60,
) -> None:
    """One APPROVED approval and (optionally) its post-approval usage row."""
    run = ExecutionRun(entity_id=agent_id, company_id=cid, status="COMPLETED")
    db.add(run)
    await db.flush()
    approval = HumanApproval(
        run_id=run.id, checkpoint_trigger="policy:comm",
        checkpoint_key=CHECKPOINT, status="APPROVED",
        requested_at=responded_at - timedelta(minutes=5),
        responded_at=responded_at,
        context_snapshot={"category": "email_dispatch", "reason": "r"})
    db.add(approval)
    await db.flush()
    if spend is not None:
        await db.execute(text(
            "INSERT INTO usage_logs (id, timestamp, company_id, run_id, sku_id, "
            "raw_quantity, calculated_cost, attribution) VALUES "
            "(:id, :ts, :c, :r, :sku, 1, :cost, 'tool')"),
            {"id": str(uuid.uuid4()),
             "ts": responded_at + timedelta(seconds=spend_at_offset_s),
             "c": str(cid), "r": str(run.id), "sku": str(sku_id),
             "cost": str(spend)})


class TestObservedDecisionCost:
    async def test_the_median_over_post_approval_spend_with_the_floor(self, two_tenants):
        from src.common.database import AsyncSessionLocal
        cid, _ = two_tenants
        async with AsyncSessionLocal() as db:
            result = await activate_slice(db, cid)
            agent_id = uuid.UUID(result["agt-015-proposal-quote"])
            sku = await _seed_sku(db, cid)
            for spend in (Decimal(2), Decimal(3), Decimal(4)):
                await _approved_with_spend(
                    db, cid, agent_id, sku, spend=spend,
                    responded_at=NOW - timedelta(days=1))
            await db.commit()

        async with AsyncSessionLocal() as db:
            # Four observations (three spends + none yet) is below the floor.
            await _approved_with_spend(
                db, cid, agent_id, sku, spend=None,
                responded_at=NOW - timedelta(days=2))
            await db.commit()
        reset_cost_cache()
        async with AsyncSessionLocal() as db:
            assert await observed_decision_cost(db, cid, CHECKPOINT, now=NOW) is None

        async with AsyncSessionLocal() as db:
            # The fifth observation crosses the floor; the zero-spend
            # approval is IN the sample (2, 3, 4, 0, 100 → median 3).
            await _approved_with_spend(
                db, cid, agent_id, sku, spend=Decimal(100),
                responded_at=NOW - timedelta(days=3))
            await db.commit()
        reset_cost_cache()
        async with AsyncSessionLocal() as db:
            estimate = await observed_decision_cost(db, cid, CHECKPOINT, now=NOW)
        assert estimate is not None
        assert estimate["amount"] == 3.0
        assert "5 similar decisions" in estimate["basis"]
        assert estimate["currency"] is None

    async def test_company_scoped_never_pooled_and_windowed(self, two_tenants):
        from src.common.database import AsyncSessionLocal
        cid_a, cid_b = two_tenants
        async with AsyncSessionLocal() as db:
            result_b = await activate_slice(db, cid_b)
            agent_b = uuid.UUID(result_b["agt-015-proposal-quote"])
            sku_b = await _seed_sku(db, cid_b)
            # Company B has plenty of history at this checkpoint…
            for _ in range(6):
                await _approved_with_spend(
                    db, cid_b, agent_b, sku_b, spend=Decimal(10),
                    responded_at=NOW - timedelta(days=1))
            # …and company A has plenty too, but all outside the window.
            result_a = await activate_slice(db, cid_a)
            agent_a = uuid.UUID(result_a["agt-015-proposal-quote"])
            sku_a = await _seed_sku(db, cid_a)
            for _ in range(6):
                await _approved_with_spend(
                    db, cid_a, agent_a, sku_a, spend=Decimal(10),
                    responded_at=NOW - timedelta(days=120))
            await db.commit()
        reset_cost_cache()
        async with AsyncSessionLocal() as db:
            # No platform-wide fallback: B's history must not answer for A,
            # and A's own stale history is outside the trailing window.
            assert await observed_decision_cost(db, cid_a, CHECKPOINT, now=NOW) is None
            estimate_b = await observed_decision_cost(db, cid_b, CHECKPOINT, now=NOW)
            assert estimate_b is not None and estimate_b["amount"] == 10.0

    async def test_spend_before_the_approval_is_not_its_consequence(self, two_tenants):
        from src.common.database import AsyncSessionLocal
        cid, _ = two_tenants
        async with AsyncSessionLocal() as db:
            result = await activate_slice(db, cid)
            agent_id = uuid.UUID(result["agt-015-proposal-quote"])
            sku = await _seed_sku(db, cid)
            for _ in range(5):
                # Usage stamped BEFORE responded_at: the run's spend up to
                # the gate, not the cost of saying yes.
                await _approved_with_spend(
                    db, cid, agent_id, sku, spend=Decimal(50),
                    responded_at=NOW - timedelta(days=1),
                    spend_at_offset_s=-600)
            await db.commit()
        reset_cost_cache()
        async with AsyncSessionLocal() as db:
            estimate = await observed_decision_cost(db, cid, CHECKPOINT, now=NOW)
        # Five observations, every one of them zero post-approval spend.
        assert estimate is not None
        assert estimate["amount"] == 0.0

    async def test_an_amountless_pending_tray_carries_the_estimate(self, two_tenants):
        from src.common.database import AsyncSessionLocal
        cid, _ = two_tenants
        async with AsyncSessionLocal() as db:
            result = await activate_slice(db, cid)
            agent_id = uuid.UUID(result["agt-015-proposal-quote"])
            sku = await _seed_sku(db, cid)
            for spend in (Decimal(1), Decimal(2), Decimal(3), Decimal(4), Decimal(5)):
                await _approved_with_spend(
                    db, cid, agent_id, sku, spend=spend,
                    responded_at=NOW - timedelta(days=1))
            run = ExecutionRun(entity_id=agent_id, company_id=cid, status="RUNNING")
            db.add(run)
            await db.flush()
            db.add(HumanApproval(
                run_id=run.id, checkpoint_trigger="policy:comm",
                checkpoint_key=CHECKPOINT, status="PENDING",
                requested_at=NOW,
                context_snapshot={"category": "email_dispatch", "reason": "send it?"}))
            await db.commit()
        reset_cost_cache()
        async with AsyncSessionLocal() as db:
            trays = await tray_list(db, cid, now=NOW)
        assert len(trays) == 1
        approve = next(p for p in trays[0]["paths"] if p["key"] == "approve")
        assert approve["cost"] is not None
        assert approve["cost"]["amount"] == 3.0
        assert "observed" in approve["cost"]["basis"]
