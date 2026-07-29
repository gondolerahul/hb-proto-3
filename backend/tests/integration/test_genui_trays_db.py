"""SEAM T5 — the tray composer over real rows. ``needs_db``.

What only the database can prove: the company-scoped join (a tray never
crosses tenants), the SLA read off the seeded checkpoint defs, and the
probe shape — an unknown id and a foreign id answer identically.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.genui.trays import tray_detail, tray_list
from src.ai.orm.execution import ExecutionRun, HumanApproval
from src.ai.solo_pack.activation import activate_slice
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
            {"id": str(cid), "n": f"tray-test-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    try:
        yield cid
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            await s.execute(text(
                "DELETE FROM human_approvals WHERE run_id IN "
                "(SELECT id FROM execution_runs WHERE company_id = :c)"), {"c": str(cid)})
            for tbl in ("execution_runs", "signals", "trigger_registry",
                        "budget_envelopes", "loop_runtime"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(
                text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                {"c": str(cid)})
            await s.execute(
                text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def _raise_payout_approval(db, cid) -> uuid.UUID:
    result = await activate_slice(db, cid)
    agent_id = uuid.UUID(result["agt-015-proposal-quote"])
    run = ExecutionRun(entity_id=agent_id, company_id=cid, status="RUNNING")
    db.add(run)
    await db.flush()
    approval = HumanApproval(
        run_id=run.id, checkpoint_trigger="policy:outbound_payout",
        checkpoint_key="before_outbound_payout_above_band", status="PENDING",
        requested_at=datetime.utcnow(),
        context_snapshot={
            "category": "outbound_payout", "reason": "Payout above the A2 band",
            "band": 2, "amount": 84200.0,
        })
    db.add(approval)
    await db.commit()
    return approval.id


class TestTrays:
    async def test_a_payout_approval_composes_a_certified_payment_tray(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            approval_id = await _raise_payout_approval(db, tenant)

        async with AsyncSessionLocal() as db:
            trays = await tray_list(db, tenant)

        assert len(trays) == 1
        tray = trays[0]
        assert tray["approval_id"] == str(approval_id)
        assert tray["certified"]["component"] == "certified.payment@1"
        assert tray["certified"]["props"]["amount"] == 84200.0
        assert tray["prepared_by"]["name"]
        # The seeded checkpoint def carries the SLA (trust002) — composed,
        # not copied from the approval row.
        assert tray["sla"]["seconds_left"] is not None
        assert tray["sla"]["on_timeout"] is not None

    async def test_a_foreign_tray_answers_like_an_unknown_one(self, tenant):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            approval_id = await _raise_payout_approval(db, tenant)

        other = uuid.uuid4()
        async with AsyncSessionLocal() as s:
            await s.execute(
                text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                     "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
                {"id": str(other), "n": f"tray-probe-{other.hex[:8]}"})
            await s.commit()
        try:
            async with AsyncSessionLocal() as db:
                own = await tray_detail(db, tenant, approval_id)
                foreign = await tray_detail(db, other, approval_id)
                unknown = await tray_detail(db, tenant, uuid.uuid4())
            assert own is not None
            assert foreign is None and unknown is None
        finally:
            async with AsyncSessionLocal() as s:
                await s.execute(
                    text("DELETE FROM companies WHERE id = :c"), {"c": str(other)})
                await s.commit()
