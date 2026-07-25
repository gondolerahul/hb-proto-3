"""SEGA T2 — every entity write leaves a version behind (VG-17).

The property worth a database: the ledger row and the entity change land in the
**same transaction**, so there is no state where an entity has moved and its
history has not. Plus the two directions the Gallery and the Glasshouse need —
read the history, and put an entity back.

``needs_db``.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


def _db_url():
    import os

    from src.common.config import settings
    return getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")


async def _make_company() -> uuid.UUID:
    from src.common.database import AsyncSessionLocal

    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"ledger-{cid.hex[:8]}"})
        await s.commit()
    return cid


async def _make_entity(cid: uuid.UUID) -> uuid.UUID:
    import json

    from src.common.database import AsyncSessionLocal

    eid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO hierarchical_entities (id, company_id, version, type, "
                 "status, name, display_name, goal, governance, created_at, updated_at) "
                 "VALUES (:i, :c, '1.0.0', 'AGENT', 'ACTIVE', :n, :n, 'original goal', "
                 "CAST(:g AS json), now(), now())"),
            {"i": str(eid), "c": str(cid), "n": f"ledger-agent-{eid.hex[:6]}",
             "g": json.dumps({"autonomy_level": "A1"})})
        await s.commit()
    return eid


@pytest_asyncio.fixture
async def tenant():
    if not _db_url():
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid = await _make_company()
    eid = await _make_entity(cid)
    try:
        yield SimpleNamespace(company_id=cid, entity_id=eid)
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM entity_versions WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


# ── the hookup ───────────────────────────────────────────────────────────────

async def test_a_human_edit_writes_a_ledger_row(tenant):
    """Human edits are recorded too. A ledger of only automated changes cannot
    answer "what did this agent look like last Tuesday"."""
    from src.ai.schemas.entity import HierarchicalEntityUpdate
    from src.ai.service import AIService
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await AIService(db).update_entity(
            tenant.entity_id, HierarchicalEntityUpdate(goal="a better goal"),
            tenant.company_id)

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(
            "SELECT version, change_kind, snapshot, status FROM entity_versions "
            "WHERE entity_id = :e"), {"e": str(tenant.entity_id)})).all()

    assert len(rows) == 1
    assert rows[0].change_kind == "human"
    assert rows[0].status == "ga"
    assert rows[0].snapshot["goal"] == "a better goal"


async def test_the_entity_version_moves_with_the_ledger(tenant):
    """The row's version and the entity's must agree, or "which version is
    live" has two answers."""
    from src.ai.schemas.entity import HierarchicalEntityUpdate
    from src.ai.service import AIService
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        updated = await AIService(db).update_entity(
            tenant.entity_id, HierarchicalEntityUpdate(goal="v2"), tenant.company_id)
        assert updated.version == "1.0.1"

    async with AsyncSessionLocal() as db:
        recorded = (await db.execute(text(
            "SELECT version FROM entity_versions WHERE entity_id = :e"),
            {"e": str(tenant.entity_id)})).scalar()
    assert recorded == "1.0.1"


async def test_successive_edits_accumulate_history(tenant):
    from src.ai.schemas.entity import HierarchicalEntityUpdate
    from src.ai.service import AIService
    from src.ai.evolution.ledger import version_history
    from src.common.database import AsyncSessionLocal

    for goal in ("first", "second", "third"):
        async with AsyncSessionLocal() as db:
            await AIService(db).update_entity(
                tenant.entity_id, HierarchicalEntityUpdate(goal=goal), tenant.company_id)

    async with AsyncSessionLocal() as db:
        history = await version_history(db, tenant.entity_id)

    assert [h.version for h in history] == ["1.0.3", "1.0.2", "1.0.1"], (
        "history is newest-first — what the Gallery renders")
    assert history[-1].snapshot["goal"] == "first"


async def test_the_snapshot_records_governance_even_though_it_is_never_self_modified(tenant):
    """The ledger records what happened; blast_radius decides what may happen.
    A human raising a band must still appear in the history."""
    from src.ai.schemas.entity import HierarchicalEntityUpdate
    from src.ai.service import AIService
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await AIService(db).update_entity(
            tenant.entity_id,
            HierarchicalEntityUpdate(governance={"autonomy_level": "A2"}),
            tenant.company_id)

    async with AsyncSessionLocal() as db:
        snapshot = (await db.execute(text(
            "SELECT snapshot FROM entity_versions WHERE entity_id = :e"),
            {"e": str(tenant.entity_id)})).scalar()

    assert snapshot["governance"]["autonomy_level"] == "A2"


# ── rollback ─────────────────────────────────────────────────────────────────

async def test_a_restore_puts_the_entity_back_and_records_that_it_did(tenant):
    """A rollback is a change like any other and gets its own row, so the
    history reads forward — "it was tuned, then rolled back" — rather than
    appearing never to have happened."""
    from src.ai.evolution.ledger import restore, version_history
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.schemas.entity import HierarchicalEntityUpdate
    from src.ai.service import AIService
    from src.common.database import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        await AIService(db).update_entity(
            tenant.entity_id, HierarchicalEntityUpdate(goal="the good goal"),
            tenant.company_id)
        await AIService(db).update_entity(
            tenant.entity_id, HierarchicalEntityUpdate(goal="the regrettable goal"),
            tenant.company_id)

    async with AsyncSessionLocal() as db:
        history = await version_history(db, tenant.entity_id)
        good = next(h for h in history if h.snapshot["goal"] == "the good goal")
        entity = (await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.id == tenant.entity_id))).scalar_one()

        row = await restore(db, entity, good, company_id=tenant.company_id)
        await db.commit()
        assert row is not None

    async with AsyncSessionLocal() as db:
        entity = (await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.id == tenant.entity_id))).scalar_one()
        assert entity.goal == "the good goal"

        history = await version_history(db, tenant.entity_id)
        assert history[0].change_kind == "rollback"
        assert good.version in {h.version for h in history}
        rolled = next(h for h in history if h.version == good.version)
        assert rolled.status == "rolled_back"


async def test_a_restore_refuses_across_tenants(tenant):
    """Exempt from the rate cap and the kill switch, never from scope."""
    from src.ai.evolution.ledger import restore, version_history
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.schemas.entity import HierarchicalEntityUpdate
    from src.ai.service import AIService
    from src.common.database import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        await AIService(db).update_entity(
            tenant.entity_id, HierarchicalEntityUpdate(goal="mine"), tenant.company_id)

    async with AsyncSessionLocal() as db:
        target = (await version_history(db, tenant.entity_id))[0]
        entity = (await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.id == tenant.entity_id))).scalar_one()

        assert await restore(db, entity, target, company_id=uuid.uuid4()) is None
        await db.rollback()
