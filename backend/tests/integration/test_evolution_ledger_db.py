"""SEGA T2 — every entity write leaves a version behind (VG-17).

The property worth a database: the ledger row and the entity change land in the
**same transaction**, so there is no state where an entity has moved and its
history has not. Plus the two directions the Gallery and the Glasshouse need —
read the history, and put an entity back.

``needs_db``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
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
            # Children before parents — the canary tests hang runs and signals
            # off the entity, and `execution_runs.entity_id` is a real FK.
            for tbl in ("by_run", "signals", "execution_runs",
                        "entity_versions", "hierarchical_entities"):
                if tbl == "by_run":
                    # Approvals and tool logs hang off runs, not off the
                    # company — they need the join, and they go first.
                    for child in ("human_approvals", "tool_interaction_logs"):
                        await s.execute(text(
                            f"DELETE FROM {child} WHERE run_id IN "
                            "(SELECT id FROM execution_runs WHERE company_id = :c)"),
                            {"c": str(cid)})
                    continue
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"),
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


# ── T3/T4 · the canary, against real telemetry ───────────────────────────────

async def _version(cid: uuid.UUID, eid: uuid.UUID, *, version: str, status: str) -> uuid.UUID:
    import json

    from src.common.database import AsyncSessionLocal

    vid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO entity_versions (id, entity_id, company_id, version, "
                 "snapshot, change_kind, status, created_at) VALUES "
                 "(:i, :e, :c, :v, CAST(:snap AS jsonb), 'charter_tune', :st, now())"),
            {"i": str(vid), "e": str(eid), "c": str(cid), "v": version,
             "snap": json.dumps({"goal": f"goal at {version}"}), "st": status})
        await s.commit()
    return vid


async def _run_at(cid: uuid.UUID, eid: uuid.UUID, version_id: uuid.UUID, *,
                  status="COMPLETED", cost="0.10") -> uuid.UUID:
    from src.common.database import AsyncSessionLocal

    rid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO execution_runs (id, entity_id, company_id, status, "
                 "total_cost_usd, entity_version_id, created_at) VALUES "
                 "(:i, :e, :c, :s, :cost, :v, now())"),
            {"i": str(rid), "e": str(eid), "c": str(cid), "s": status,
             "cost": cost, "v": str(version_id)})
        await s.commit()
    return rid


async def test_health_is_measured_per_version(tenant):
    """The reason sega002 stores the assignment: a verdict compares one
    version's runs against another's, which needs the runs attributed."""
    from src.ai.evolution.entity_canary import measure_version
    from src.common.database import AsyncSessionLocal

    ga = await _version(tenant.company_id, tenant.entity_id, version="1.0.1", status="ga")
    canary = await _version(tenant.company_id, tenant.entity_id,
                            version="1.0.2", status="canary")

    for _ in range(12):
        await _run_at(tenant.company_id, tenant.entity_id, ga)
    for _ in range(11):
        await _run_at(tenant.company_id, tenant.entity_id, canary, status="FAILED")

    async with AsyncSessionLocal() as db:
        incumbent = await measure_version(db, ga)
        candidate = await measure_version(db, canary)

    assert incumbent.runs == 12 and incumbent.failures == 0
    assert candidate.runs == 11 and candidate.failures == 11

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM execution_runs WHERE company_id = :c"),
                         {"c": str(tenant.company_id)})
        await db.commit()


async def test_a_regressing_canary_is_rolled_back_and_the_entity_restored(tenant):
    """End to end: measure → assess → roll back → the entity is back where it
    was, and the ledger says so."""
    from src.ai.evolution.entity_canary import assess, measure_version, roll_back
    from src.ai.evolution.models import EntityVersion
    from src.ai.orm.entity import HierarchicalEntity
    from src.common.database import AsyncSessionLocal
    from sqlalchemy import select

    ga = await _version(tenant.company_id, tenant.entity_id, version="1.0.1", status="ga")
    canary = await _version(tenant.company_id, tenant.entity_id,
                            version="1.0.2", status="canary")
    for _ in range(12):
        await _run_at(tenant.company_id, tenant.entity_id, ga)
    for _ in range(12):
        await _run_at(tenant.company_id, tenant.entity_id, canary, status="FAILED")

    async with AsyncSessionLocal() as db:
        verdict = assess(await measure_version(db, canary),
                         await measure_version(db, ga))
        assert verdict.action == "roll_back"

        entity = (await db.execute(select(HierarchicalEntity).where(
            HierarchicalEntity.id == tenant.entity_id))).scalar_one()
        version = (await db.execute(select(EntityVersion).where(
            EntityVersion.id == canary))).scalar_one()

        await roll_back(db, entity, version, company_id=tenant.company_id)
        await db.commit()

    async with AsyncSessionLocal() as db:
        entity = (await db.execute(select(HierarchicalEntity).where(
            HierarchicalEntity.id == tenant.entity_id))).scalar_one()
        assert entity.goal == "goal at 1.0.1"

        statuses = dict((await db.execute(text(
            "SELECT version, status FROM entity_versions WHERE entity_id = :e"),
            {"e": str(tenant.entity_id)})).all())
        assert statuses["1.0.2"] == "rolled_back"

        emitted = (await db.execute(text(
            "SELECT type FROM signals WHERE company_id = :c"),
            {"c": str(tenant.company_id)})).scalars().all()
        assert "governance.entity_rolled_back" in emitted

        await db.execute(text("DELETE FROM signals WHERE company_id = :c"),
                         {"c": str(tenant.company_id)})
        await db.execute(text("DELETE FROM execution_runs WHERE company_id = :c"),
                         {"c": str(tenant.company_id)})
        await db.commit()


async def test_promotion_refuses_a_change_no_independent_suite_backs(tenant):
    """T4 — the exam predates the student, and this entity sat no exam.

    The refusal is inside `promote`, before the status flip, so a new caller
    cannot forget it (the `RegistryService.activate` precedent).
    """
    from src.ai.evolution.entity_canary import promote
    from src.ai.evolution.models import EntityVersion
    from src.ai.intelligence.admission import AdmissionError, SuiteSet
    from src.common.database import AsyncSessionLocal
    from sqlalchemy import select

    canary = await _version(tenant.company_id, tenant.entity_id,
                            version="1.0.5", status="canary")

    async with AsyncSessionLocal() as db:
        version = (await db.execute(select(EntityVersion).where(
            EntityVersion.id == canary))).scalar_one()
        with pytest.raises(AdmissionError):
            await promote(db, version,
                          suites=SuiteSet(incumbent_golden=True, platform_curated=False))
        await db.rollback()

    async with AsyncSessionLocal() as db:
        status = (await db.execute(text(
            "SELECT status FROM entity_versions WHERE id = :i"), {"i": str(canary)})).scalar()
    assert status == "canary", "a refused promotion must not have moved the version"


async def test_a_backed_promotion_supersedes_the_previous_ga(tenant):
    """One GA at a time, or "which version is live" has two answers."""
    from src.ai.evolution.entity_canary import promote
    from src.ai.evolution.models import EntityVersion
    from src.ai.intelligence.admission import SuiteSet
    from src.common.database import AsyncSessionLocal
    from sqlalchemy import select

    old_ga = await _version(tenant.company_id, tenant.entity_id,
                            version="1.0.6", status="ga")
    canary = await _version(tenant.company_id, tenant.entity_id,
                            version="1.0.7", status="canary")

    async with AsyncSessionLocal() as db:
        version = (await db.execute(select(EntityVersion).where(
            EntityVersion.id == canary))).scalar_one()
        await promote(db, version,
                      suites=SuiteSet(incumbent_golden=True, platform_curated=True))
        await db.commit()

    async with AsyncSessionLocal() as db:
        statuses = dict((await db.execute(text(
            "SELECT id::text, status FROM entity_versions WHERE entity_id = :e"),
            {"e": str(tenant.entity_id)})).all())
    assert statuses[str(canary)] == "ga"
    assert statuses[str(old_ga)] == "superseded"

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM signals WHERE company_id = :c"),
                         {"c": str(tenant.company_id)})
        await db.commit()


async def test_stamping_prefers_the_incumbent_when_there_is_no_canary(tenant):
    """Ordinary life: no experiment running, every run attributed to GA."""
    from src.ai.evolution.entity_canary import stamp_run_version
    from src.common.database import AsyncSessionLocal

    ga = await _version(tenant.company_id, tenant.entity_id, version="1.0.8", status="ga")
    async with AsyncSessionLocal() as db:
        assigned = await stamp_run_version(
            db, entity_id=tenant.entity_id, cohort_key=str(uuid.uuid4()), fraction=0.25)
    assert assigned == ga


async def test_stamping_splits_traffic_when_a_canary_exists(tenant):
    """Both sides get served, and neither gets all of it."""
    from src.ai.evolution.entity_canary import stamp_run_version
    from src.common.database import AsyncSessionLocal

    ga = await _version(tenant.company_id, tenant.entity_id, version="1.0.9", status="ga")
    canary = await _version(tenant.company_id, tenant.entity_id,
                            version="1.1.0", status="canary")

    async with AsyncSessionLocal() as db:
        assignments = [
            await stamp_run_version(db, entity_id=tenant.entity_id,
                                    cohort_key=str(uuid.uuid4()), fraction=0.5)
            for _ in range(40)
        ]

    assert set(assignments) == {ga, canary}


async def test_an_entity_with_no_ledger_history_stamps_nothing(tenant):
    """NULL means "not attributed", never "the incumbent" — a run from an
    unstamped path must not be counted as evidence for either side."""
    from src.ai.evolution.entity_canary import stamp_run_version
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        assert await stamp_run_version(
            db, entity_id=uuid.uuid4(), cohort_key="k", fraction=0.25) is None


# ── T5 · the sweep ───────────────────────────────────────────────────────────

async def test_sweep_promotes_a_healthy_backed_canary(tenant):
    """A Solo Pack entity with a clean canary and a track record is promoted."""
    from src.ai.evolution.sweep import sweep_company
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        await s.execute(text(
            "UPDATE hierarchical_entities SET tags = CAST(:t AS json) WHERE id = :e"),
            {"t": '["solo_pack"]', "e": str(tenant.entity_id)})
        await s.commit()

    ga = await _version(tenant.company_id, tenant.entity_id, version="2.0.1", status="ga")
    canary = await _version(tenant.company_id, tenant.entity_id,
                            version="2.0.2", status="canary")
    for _ in range(12):
        await _run_at(tenant.company_id, tenant.entity_id, ga)
        await _run_at(tenant.company_id, tenant.entity_id, canary)

    async with AsyncSessionLocal() as db:
        summary = await sweep_company(db, tenant.company_id)
        await db.commit()

    assert summary["promoted"] == 1
    async with AsyncSessionLocal() as db:
        status = (await db.execute(text(
            "SELECT status FROM entity_versions WHERE id = :i"), {"i": str(canary)})).scalar()
    assert status == "ga"


async def test_sweep_leaves_a_healthy_but_unbacked_canary_alone(tenant):
    """Healthy evidence, no independent suite: left in place, not promoted on
    its own say-so and not discarded for doing nothing wrong. A human decides.
    """
    from src.ai.evolution.sweep import sweep_company
    from src.common.database import AsyncSessionLocal

    ga = await _version(tenant.company_id, tenant.entity_id, version="2.1.1", status="ga")
    canary = await _version(tenant.company_id, tenant.entity_id,
                            version="2.1.2", status="canary")
    for _ in range(12):
        await _run_at(tenant.company_id, tenant.entity_id, ga)
        await _run_at(tenant.company_id, tenant.entity_id, canary)

    async with AsyncSessionLocal() as db:
        summary = await sweep_company(db, tenant.company_id)
        await db.commit()

    assert summary["unpromotable"] == 1
    assert summary["promoted"] == 0
    async with AsyncSessionLocal() as db:
        status = (await db.execute(text(
            "SELECT status FROM entity_versions WHERE id = :i"), {"i": str(canary)})).scalar()
    assert status == "canary"


async def test_sweep_keeps_observing_a_thin_canary(tenant):
    """A low-traffic entity sits in canary, and that is a state not a delay."""
    from src.ai.evolution.sweep import sweep_company
    from src.common.database import AsyncSessionLocal

    ga = await _version(tenant.company_id, tenant.entity_id, version="2.2.1", status="ga")
    canary = await _version(tenant.company_id, tenant.entity_id,
                            version="2.2.2", status="canary")
    await _run_at(tenant.company_id, tenant.entity_id, ga)
    await _run_at(tenant.company_id, tenant.entity_id, canary)

    async with AsyncSessionLocal() as db:
        summary = await sweep_company(db, tenant.company_id)
        await db.commit()

    assert summary["observed"] == 1
    assert summary["promoted"] == summary["rolled_back"] == 0


async def test_an_undecided_canary_eventually_expires(tenant):
    """An experiment with no end date is not an experiment.

    Rolled back rather than promoted: the change failed to show it was an
    improvement, and the burden of proof sits with the change.
    """
    from src.ai.evolution.sweep import sweep_company
    from src.common.database import AsyncSessionLocal

    await _version(tenant.company_id, tenant.entity_id, version="2.3.1", status="ga")
    canary = await _version(tenant.company_id, tenant.entity_id,
                            version="2.3.2", status="canary")

    async with AsyncSessionLocal() as db:
        summary = await sweep_company(
            db, tenant.company_id, now=datetime.utcnow() + timedelta(days=30))
        await db.commit()

    assert summary["expired"] == 1
    async with AsyncSessionLocal() as db:
        status = (await db.execute(text(
            "SELECT status FROM entity_versions WHERE id = :i"), {"i": str(canary)})).scalar()
    assert status == "rolled_back"


# ── T6 · taint descends from what the run actually read ──────────────────────

async def test_a_run_that_scraped_the_web_is_no_longer_internal(tenant):
    """D3's core case, and the one Increment 1 could not see.

    The triggering signal said `internal`; the run then called a scraper. The
    gate must judge it on what it has read, not on how it started.
    """
    from src.ai.evolution.taint import resolve_run_taint
    from src.common.database import AsyncSessionLocal

    version = await _version(tenant.company_id, tenant.entity_id,
                             version="3.0.1", status="ga")
    run_id = await _run_at(tenant.company_id, tenant.entity_id, version)

    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO tool_interaction_logs (id, run_id, tool_id, tool_name, "
            "success, created_at) VALUES (:i, :r, 'scraper_tool', 'scraper_tool', "
            "true, now())"),
            {"i": str(uuid.uuid4()), "r": str(run_id)})
        await db.commit()

        assert await resolve_run_taint(db, run_id, seed="internal") == "counterparty"


async def test_a_run_that_read_nothing_external_keeps_its_seed(tenant):
    from src.ai.evolution.taint import resolve_run_taint
    from src.common.database import AsyncSessionLocal

    version = await _version(tenant.company_id, tenant.entity_id,
                             version="3.1.1", status="ga")
    run_id = await _run_at(tenant.company_id, tenant.entity_id, version)

    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO tool_interaction_logs (id, run_id, tool_id, tool_name, "
            "success, created_at) VALUES (:i, :r, 'calculator', 'calculator', "
            "true, now())"),
            {"i": str(uuid.uuid4()), "r": str(run_id)})
        await db.commit()

        assert await resolve_run_taint(db, run_id, seed="internal") == "internal"


async def test_the_resolved_taint_is_stamped_on_the_run(tenant):
    """A column, because `context_state` is rewritten wholesale and "what did
    this run know when it asked?" is an incident-review question."""
    from src.ai.evolution.taint import record_run_taint, resolve_run_taint
    from src.common.database import AsyncSessionLocal

    version = await _version(tenant.company_id, tenant.entity_id,
                             version="3.2.1", status="ga")
    run_id = await _run_at(tenant.company_id, tenant.entity_id, version)

    async with AsyncSessionLocal() as db:
        level = await resolve_run_taint(db, run_id, seed="counterparty")
        await record_run_taint(db, run_id, level)
        await db.commit()

    async with AsyncSessionLocal() as db:
        stamped = (await db.execute(text(
            "SELECT taint_level FROM execution_runs WHERE id = :i"),
            {"i": str(run_id)})).scalar()
    assert stamped == "counterparty"
