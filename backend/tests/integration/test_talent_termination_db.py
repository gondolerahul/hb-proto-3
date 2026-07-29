"""DRIVER D7 — termination over real rows (VG-18). ``needs_db``.

What only the database can prove: the refusal over live runs (nothing is
stranded silently), the memo artifact row + file, the Gallery stamp
preceding the soft-delete, pending approvals surviving the colleague,
and the probe rule (unknown id ≡ foreign id).
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.orm.entity import HierarchicalEntity
from src.ai.orm.execution import ExecutionRun, HumanApproval
from src.ai.solo_pack.activation import activate_slice
from src.ai.talent.termination import terminate_colleague
from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def tenant(tmp_path):
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
            {"id": str(cid), "n": f"term-{cid.hex[:8]}"})
        await s.commit()
    tenant_data_plane.reset_cache()
    await tenant_data_plane.ensure_ready(cid)
    try:
        yield cid, tmp_path
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
        async with AsyncSessionLocal() as s:
            await s.execute(text(
                "DELETE FROM human_approvals WHERE run_id IN "
                "(SELECT id FROM execution_runs WHERE company_id = :c)"), {"c": str(cid)})
            for tbl in ("artifacts", "execution_runs", "signals", "trigger_registry",
                        "budget_envelopes", "loop_runtime"):
                await s.execute(
                    text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
            await s.execute(
                text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()
        tenant_data_plane.reset_cache()


async def _hire(db, cid):
    result = await activate_slice(db, cid)
    return uuid.UUID(result["agt-015-proposal-quote"])


async def test_a_live_run_refuses_the_termination(tenant):
    from src.common.database import AsyncSessionLocal
    cid, tmp = tenant
    async with AsyncSessionLocal() as db:
        agent_id = await _hire(db, cid)
        db.add(ExecutionRun(entity_id=agent_id, company_id=cid, status="RUNNING"))
        await db.commit()

    async with AsyncSessionLocal() as db:
        outcome = await terminate_colleague(db, cid, agent_id, artifacts_root=tmp)
    assert outcome.status == "refused"
    assert outcome.running_run_ids
    # Nothing changed: the colleague still stands.
    async with AsyncSessionLocal() as db:
        entity = (await db.execute(
            select(HierarchicalEntity).where(HierarchicalEntity.id == agent_id))
        ).scalar_one()
        assert entity.status != "DELETED"


async def test_termination_files_the_memo_stamps_and_soft_deletes(tenant):
    from src.common.database import AsyncSessionLocal
    cid, tmp = tenant
    async with AsyncSessionLocal() as db:
        agent_id = await _hire(db, cid)
        run = ExecutionRun(entity_id=agent_id, company_id=cid, status="COMPLETED")
        db.add(run)
        await db.flush()
        db.add(HumanApproval(
            run_id=run.id, checkpoint_trigger="policy:x",
            checkpoint_key="before_external_communication", status="PENDING",
            requested_at=datetime.utcnow(),
            context_snapshot={"category": "email_dispatch", "reason": "r"}))
        await db.commit()

    async with AsyncSessionLocal() as db:
        outcome = await terminate_colleague(db, cid, agent_id, artifacts_root=tmp)
    assert outcome.status == "terminated"
    assert outcome.memo_artifact_id is not None
    assert outcome.summary is not None and outcome.summary.pending_approvals == 1

    async with AsyncSessionLocal() as db:
        entity = (await db.execute(
            select(HierarchicalEntity).where(HierarchicalEntity.id == agent_id))
        ).scalar_one()
        assert entity.status == "DELETED"
        assert entity.deleted_at is not None
        stamp = (entity.metadata_extensions or {}).get("termination")
        assert stamp is not None
        assert stamp["memo_artifact_id"] == outcome.memo_artifact_id

        # The memo is a real artifact row pointing at a real file.
        row = (await db.execute(text(
            "SELECT file_path FROM artifacts WHERE id = :a"),
            {"a": outcome.memo_artifact_id})).scalar_one()
        from pathlib import Path
        memo = Path(row).read_text(encoding="utf-8")
        assert "Handover memo" in memo
        assert "1 approval(s) still waiting" in memo

        # The approval survived the colleague — it belongs to the human.
        pending = (await db.execute(text(
            "SELECT count(*) FROM human_approvals ha JOIN execution_runs er "
            "ON ha.run_id = er.id WHERE er.company_id = :c AND ha.status = 'PENDING'"),
            {"c": str(cid)})).scalar_one()
        assert pending == 1


async def test_an_unknown_id_and_a_foreign_id_answer_alike(tenant):
    from src.common.database import AsyncSessionLocal
    cid, tmp = tenant
    async with AsyncSessionLocal() as db:
        unknown = await terminate_colleague(db, cid, uuid.uuid4(), artifacts_root=tmp)
    assert unknown.status == "not_found"


async def test_a_process_is_not_terminable(tenant):
    from src.common.database import AsyncSessionLocal
    cid, tmp = tenant
    async with AsyncSessionLocal() as db:
        agent_id = await _hire(db, cid)
        agent = (await db.execute(
            select(HierarchicalEntity).where(HierarchicalEntity.id == agent_id))
        ).scalar_one()
        process_id = agent.parent_id
        assert process_id is not None
        outcome = await terminate_colleague(db, cid, process_id, artifacts_root=tmp)
    assert outcome.status == "refused"
    assert outcome.reason is not None and "decommissioned" in outcome.reason
