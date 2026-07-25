"""LEARN T2-T5 — the jobs, the read path, and the learning loop, against a real DB.

T2 (`pool_day`) is where the B10 floor meets actual rows: the pure grouping is
covered in `test_learning_pooling.py`, so what matters here is that the SQL
reads what it thinks it reads, that re-running a day replaces it rather than
doubling it, and that a below-floor group leaves **nothing** behind.

T3 (`snapshot_company` / `snapshot_all`) is the job that starts the clock. The
property worth a database is the one that looks like a bug until you know the
rule: a brand-new tenant records *absences*, not zeroes — with the one honest
exception the tests pin.

T4 (`get_kpi_history`) is the single read path four later surfaces share, so
company scoping and the shape of an empty series both matter here.

T5 (`outcomes`) is charter decision 3 in practice: the signal bus *is* the
tenant learning store, and candidates land in the shipped CORTEX lifecycle.

Self-managed committed fixtures (the `test_certified_actions_db.py` pattern) —
these jobs commit, and the tenant plane bootstraps on a different connection
than the test's, so a rollback-scoped fixture cannot clean up after them.

``needs_db``.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.tenant_schema.data_plane import schema_name_for, tenant_data_plane

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

DAY = date(2026, 3, 15)


def _db_url():
    import os

    from src.common.config import settings
    return getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")


async def _make_company(label: str) -> uuid.UUID:
    from src.common.database import AsyncSessionLocal

    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"{label}-{cid.hex[:8]}"})
        await s.commit()
    return cid


async def _drop_company(cid: uuid.UUID) -> None:
    from src.common.database import AsyncSessionLocal, engine

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name_for(cid)}" CASCADE'))
    async with AsyncSessionLocal() as s:
        # Children before parents — `ensure_sheel` (used by the candidate test)
        # creates an entity plus its loop rows, and cortex trees hang off the
        # company too. Same ordering discipline as `test_certified_actions_db`.
        await s.execute(text(
            "DELETE FROM cortex_nodes WHERE tree_id IN "
            "(SELECT id FROM cortex_trees WHERE company_id = :c)"), {"c": str(cid)})
        for tbl in ("cortex_trees", "kpi_snapshots", "routing_decisions", "signals",
                    "budget_envelopes", "loop_runtime", "execution_runs",
                    "hierarchical_entities"):
            await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"), {"c": str(cid)})
        await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
        await s.commit()


async def _decision(cid: uuid.UUID, *, task="chat", reason="auto",
                    fallback=False, at: datetime | None = None) -> None:
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO routing_decisions (id, company_id, task_type, reason, "
                 "signals, fallback_used, created_at) VALUES "
                 "(:i, :c, :t, :r, '{}'::jsonb, :f, :ts)"),
            {"i": str(uuid.uuid4()), "c": str(cid), "t": task, "r": reason,
             "f": fallback, "ts": at or datetime.combine(DAY, datetime.min.time())})
        await s.commit()


async def _pooled_rows():
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        return (await s.execute(text(
            "SELECT task_type, reason, observations, successes "
            "FROM platform_observations WHERE bucket_day = :d ORDER BY task_type"),
            {"d": DAY})).all()


@pytest_asyncio.fixture
async def companies():
    """Four unrelated tenants — enough to sit either side of a floor of three."""
    if not _db_url():
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    made = [await _make_company(f"learn-{i}") for i in range(4)]
    try:
        yield made
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM platform_observations WHERE bucket_day = :d"),
                            {"d": DAY})
            await s.commit()
        for cid in made:
            await _drop_company(cid)
        tenant_data_plane.reset_cache()


# ── T2 · pooling ─────────────────────────────────────────────────────────────

async def test_pool_day_writes_a_bucket_once_the_floor_is_met(companies):
    from src.ai.learning.pooling import pool_day
    from src.common.database import AsyncSessionLocal

    for cid in companies[:3]:
        await _decision(cid)

    async with AsyncSessionLocal() as db:
        summary = await pool_day(db, DAY, min_contributors=3)
        await db.commit()

    assert summary["decisions"] == 3
    assert summary["buckets"] == 1
    rows = await _pooled_rows()
    assert len(rows) == 1
    assert rows[0].observations == 3
    assert rows[0].successes == 3.0


async def test_a_below_floor_group_leaves_nothing_behind(companies):
    """Not a filtered read, not a parked row — the day simply has no bucket."""
    from src.ai.learning.pooling import pool_day
    from src.common.database import AsyncSessionLocal

    for _ in range(20):
        await _decision(companies[0])          # one company, twenty decisions

    async with AsyncSessionLocal() as db:
        summary = await pool_day(db, DAY, min_contributors=3)
        await db.commit()

    assert summary["decisions"] == 20
    assert summary["buckets"] == 0
    assert summary["dropped_below_floor"] == 1
    assert await _pooled_rows() == []


async def test_rerunning_a_day_replaces_it(companies):
    """Idempotence, the way this job achieves it: recompute and replace.

    An append would double every count on a retry, and a retry is the normal
    life of a cron.
    """
    from src.ai.learning.pooling import pool_day
    from src.common.database import AsyncSessionLocal

    for cid in companies[:3]:
        await _decision(cid)

    for _ in range(2):
        async with AsyncSessionLocal() as db:
            await pool_day(db, DAY, min_contributors=3)
            await db.commit()

    rows = await _pooled_rows()
    assert len(rows) == 1
    assert rows[0].observations == 3


async def test_pooling_reads_only_its_own_day(companies):
    from src.ai.learning.pooling import pool_day
    from src.common.database import AsyncSessionLocal

    other_day = datetime.combine(DAY + timedelta(days=1), datetime.min.time())
    for cid in companies[:3]:
        await _decision(cid)
        await _decision(cid, at=other_day)

    async with AsyncSessionLocal() as db:
        summary = await pool_day(db, DAY, min_contributors=3)
        await db.commit()

    assert summary["decisions"] == 3


async def test_fallbacks_reduce_successes_not_observations(companies):
    from src.ai.learning.pooling import pool_day
    from src.common.database import AsyncSessionLocal

    await _decision(companies[0])
    await _decision(companies[1])
    await _decision(companies[2], fallback=True)

    async with AsyncSessionLocal() as db:
        await pool_day(db, DAY, min_contributors=3)
        await db.commit()

    rows = await _pooled_rows()
    assert rows[0].observations == 3
    assert rows[0].successes == 2.0


# ── T3 · KPI snapshots ───────────────────────────────────────────────────────

async def test_a_new_tenant_snapshots_absences_not_zeroes(companies):
    """The rule that looks like a bug until you know it.

    A company with no business records is not "zero pipeline, zero margin" — it
    is a company whose pipeline and margin *cannot be computed*. Those store as
    NULL with a populated `missing` list, which is what later lets the series
    say when each KPI became measurable instead of showing a chart that starts
    in the middle.

    Not every KPI is an absence, though, and the distinction is the point:
    `agent_hitl_load` counts pending approvals and has no record prerequisites,
    so **zero waiting approvals is a genuine measurement** on day one. The
    invariant is the correspondence, not a blanket claim about new tenants.
    """
    from src.ai.learning.kpi_snapshot import snapshot_company
    from src.common.database import AsyncSessionLocal

    cid = companies[0]
    async with AsyncSessionLocal() as db:
        written = await snapshot_company(db, cid, on=DAY)
        await db.commit()
    assert written == 10

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(
            "SELECT kpi_key, value, measurable, missing FROM kpi_snapshots "
            "WHERE company_id = :c AND captured_on = :d"),
            {"c": str(cid), "d": DAY})).all()

    assert len(rows) == 10
    for row in rows:
        assert (row.value is None) is (not row.measurable), (
            f"{row.kpi_key}: a stored value and the measurable flag disagree")
        if not row.measurable:
            assert row.missing, f"{row.kpi_key}: an absence must say what is absent"

    absences = [r.kpi_key for r in rows if not r.measurable]
    assert len(absences) >= 8, (
        "a tenant with no records should be mostly absences, not mostly zeroes")
    measurable = {r.kpi_key for r in rows if r.measurable}
    assert measurable <= {"agent_hitl_load"}, (
        f"unexpectedly measurable for an empty tenant: {measurable} — check "
        "whether a KPI is reporting zero where it means 'cannot tell'")


async def test_snapshotting_the_same_day_twice_does_not_double_the_series(companies):
    from src.ai.learning.kpi_snapshot import snapshot_company
    from src.common.database import AsyncSessionLocal

    cid = companies[1]
    for _ in range(2):
        async with AsyncSessionLocal() as db:
            await snapshot_company(db, cid, on=DAY)
            await db.commit()

    async with AsyncSessionLocal() as db:
        count = (await db.execute(text(
            "SELECT count(*) FROM kpi_snapshots WHERE company_id = :c AND captured_on = :d"),
            {"c": str(cid), "d": DAY})).scalar()
    assert count == 10


async def test_snapshot_all_covers_every_tenant(companies):
    from src.ai.learning.kpi_snapshot import snapshot_all
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        summary = await snapshot_all(db, on=DAY)
        await db.commit()

    assert summary["companies"] >= len(companies)
    assert summary["failed"] == []

    async with AsyncSessionLocal() as db:
        for cid in companies:
            count = (await db.execute(text(
                "SELECT count(*) FROM kpi_snapshots WHERE company_id = :c AND captured_on = :d"),
                {"c": str(cid), "d": DAY})).scalar()
            assert count == 10, f"company {cid} missing from the series"


async def test_the_reaper_bounds_the_table_and_spares_the_window(companies):
    from src.ai.learning.kpi_snapshot import reap_old_snapshots, snapshot_company
    from src.common.database import AsyncSessionLocal

    cid = companies[2]
    recent, ancient = DAY, DAY - timedelta(days=500)
    async with AsyncSessionLocal() as db:
        await snapshot_company(db, cid, on=recent)
        await snapshot_company(db, cid, on=ancient)
        await db.commit()

        deleted = await reap_old_snapshots(db, retention_days=400, now=DAY)
        await db.commit()

    assert deleted == 10
    async with AsyncSessionLocal() as db:
        remaining = (await db.execute(text(
            "SELECT DISTINCT captured_on FROM kpi_snapshots WHERE company_id = :c"),
            {"c": str(cid)})).scalars().all()
    assert remaining == [recent]


# ── T4 · the history read path ───────────────────────────────────────────────

def _user(company_id: uuid.UUID):
    from types import SimpleNamespace

    return SimpleNamespace(id=uuid.uuid4(), company_id=company_id, role="admin")


async def test_history_returns_the_recorded_series_absences_included(companies):
    """Absences are part of the series, not noise filtered out of it.

    A caller drawing a trend needs to see where the line starts and why it
    could not start earlier — which is the whole reason the snapshot job
    records unmeasurable days at all.
    """
    from src.ai.kpi.api import get_kpi_history
    from src.ai.learning.kpi_snapshot import snapshot_company
    from src.common.database import AsyncSessionLocal

    cid = companies[3]
    async with AsyncSessionLocal() as db:
        for offset in range(3):
            await snapshot_company(db, cid, on=DAY - timedelta(days=offset))
        await db.commit()

    async with AsyncSessionLocal() as db:
        out = await get_kpi_history(
            keys=None, from_date=DAY - timedelta(days=7), to_date=DAY,
            current_user=_user(cid), db=db)

    assert len(out["series"]) == 10
    open_pipeline = next(s for s in out["series"] if s["key"] == "open_pipeline_value")
    assert len(open_pipeline["points"]) == 3
    assert [p["captured_on"] for p in open_pipeline["points"]] == sorted(
        p["captured_on"] for p in open_pipeline["points"]), "series must be chronological"
    assert all(p["value"] is None and not p["measurable"] for p in open_pipeline["points"])
    assert open_pipeline["first_measurable_on"] is None
    assert open_pipeline["measurable_days"] == 0

    # ...and a KPI that *is* measurable on day one reports when it became so.
    hitl = next(s for s in out["series"] if s["key"] == "agent_hitl_load")
    assert hitl["measurable_days"] == 3
    assert hitl["first_measurable_on"] == (DAY - timedelta(days=2)).isoformat()


async def test_history_is_company_scoped(companies):
    """The read is scoped by the session's company, never by a caller-supplied id."""
    from src.ai.kpi.api import get_kpi_history
    from src.ai.learning.kpi_snapshot import snapshot_company
    from src.common.database import AsyncSessionLocal

    owner, stranger = companies[0], companies[1]
    async with AsyncSessionLocal() as db:
        await snapshot_company(db, owner, on=DAY)
        await db.commit()

    async with AsyncSessionLocal() as db:
        out = await get_kpi_history(
            keys=None, from_date=DAY, to_date=DAY, current_user=_user(stranger), db=db)

    assert all(s["points"] == [] for s in out["series"])


async def test_history_of_a_tenant_with_no_snapshots_is_empty_not_an_error(companies):
    """Empty is the honest answer before the job has ever run for this tenant."""
    from src.ai.kpi.api import get_kpi_history
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        out = await get_kpi_history(
            keys=None, from_date=None, to_date=None,
            current_user=_user(companies[2]), db=db)

    assert len(out["series"]) == 10
    assert all(s["points"] == [] for s in out["series"])
    assert all(s["first_measurable_on"] is None for s in out["series"])


async def test_history_rejects_an_unknown_key(companies):
    """An empty series for a typo is indistinguishable from "no data yet"."""
    from fastapi import HTTPException

    from src.ai.kpi.api import get_kpi_history
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await get_kpi_history(
                keys="open_pipeline_value,revenue_vibes", from_date=None, to_date=None,
                current_user=_user(companies[0]), db=db)
    assert exc.value.status_code == 400
    assert "revenue_vibes" in str(exc.value.detail)


async def test_history_refuses_a_range_wider_than_retention(companies):
    """A silently truncated series is worse than a refusal."""
    from fastapi import HTTPException

    from src.ai.kpi.api import get_kpi_history
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await get_kpi_history(
                keys=None, from_date=DAY - timedelta(days=500), to_date=DAY,
                current_user=_user(companies[0]), db=db)
    assert exc.value.status_code == 400


# ── T5 · outcomes on the bus, candidates in the tree ─────────────────────────

async def test_an_outcome_becomes_a_company_scoped_signal(companies):
    """Charter decision 3 in one assertion: the bus *is* the tenant store.

    And the tenant half of decision 2 comes free with it — `signals.company_id`
    is NOT NULL, so a tenant learning event cannot exist without a tenant. That
    is precisely why the pooled half needed a different table (T1).
    """
    from src.ai.learning.outcomes import Outcome, OutcomeKind, record_outcome
    from src.common.database import AsyncSessionLocal

    cid = companies[0]
    outcome = Outcome(entity_id=uuid.uuid4(), run_id=uuid.uuid4(),
                      kind=OutcomeKind.CSAT_NEGATIVE, detail="csat=-1")
    async with AsyncSessionLocal() as db:
        signal_id = await record_outcome(db, company_id=cid, outcome=outcome)
        await db.commit()
    assert signal_id is not None

    async with AsyncSessionLocal() as db:
        row = (await db.execute(text(
            "SELECT company_id, type, trust, payload FROM signals WHERE id = :i"),
            {"i": str(signal_id)})).one()
    assert row.company_id == cid
    assert row.type == "learning.outcome_observed"
    assert row.trust == "internal"
    assert row.payload["kind"] == "csat_negative"

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM signals WHERE id = :i"), {"i": str(signal_id)})
        await db.commit()


async def test_the_same_run_is_never_counted_twice(companies):
    """A run has one ending. A re-processed run must not inflate a threshold —
    the dedupe is what stops a replay from manufacturing a pattern."""
    from src.ai.learning.outcomes import Outcome, OutcomeKind, record_outcome
    from src.common.database import AsyncSessionLocal

    cid = companies[1]
    outcome = Outcome(entity_id=uuid.uuid4(), run_id=uuid.uuid4(),
                      kind=OutcomeKind.RUN_FAILED)
    async with AsyncSessionLocal() as db:
        first = await record_outcome(db, company_id=cid, outcome=outcome)
        await db.commit()
        second = await record_outcome(db, company_id=cid, outcome=outcome)
        await db.commit()

    assert first is not None
    assert second is None, "a duplicate outcome must be dropped, not re-emitted"

    async with AsyncSessionLocal() as db:
        count = (await db.execute(text(
            "SELECT count(*) FROM signals WHERE company_id = :c AND type = :t"),
            {"c": str(cid), "t": "learning.outcome_observed"})).scalar()
        assert count == 1
        await db.execute(text("DELETE FROM signals WHERE company_id = :c"), {"c": str(cid)})
        await db.commit()


async def test_outcomes_read_back_from_the_bus_and_distil(companies):
    """The round trip: emit → read → distil. No intermediate store anywhere."""
    from src.ai.learning.outcomes import (
        Outcome, OutcomeKind, distil, observed_outcomes, record_outcome,
    )
    from src.common.database import AsyncSessionLocal

    cid = companies[2]
    entity = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        for _ in range(3):
            await record_outcome(db, company_id=cid, outcome=Outcome(
                entity_id=entity, run_id=uuid.uuid4(),
                kind=OutcomeKind.APPROVAL_REJECTED))
        await db.commit()

    async with AsyncSessionLocal() as db:
        outcomes = await observed_outcomes(db, cid)
    assert len(outcomes) == 3

    candidates = distil(outcomes)
    assert len(candidates) == 1
    assert candidates[0].entity_id == entity
    assert candidates[0].observations == 3

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM signals WHERE company_id = :c"), {"c": str(cid)})
        await db.commit()


async def test_one_tenants_outcomes_are_invisible_to_another(companies):
    """Tenant learning stays per-tenant — the other half of the B10 split."""
    from src.ai.learning.outcomes import Outcome, OutcomeKind, observed_outcomes, record_outcome
    from src.common.database import AsyncSessionLocal

    owner, stranger = companies[0], companies[3]
    async with AsyncSessionLocal() as db:
        await record_outcome(db, company_id=owner, outcome=Outcome(
            entity_id=uuid.uuid4(), run_id=uuid.uuid4(), kind=OutcomeKind.RUN_FAILED))
        await db.commit()

    async with AsyncSessionLocal() as db:
        assert await observed_outcomes(db, stranger) == []
        await db.execute(text("DELETE FROM signals WHERE company_id = :c"), {"c": str(owner)})
        await db.commit()


async def test_a_candidate_for_an_unknown_entity_writes_nothing(companies):
    """Scope first, then write — the VG-05 lesson, applied to a payload reader.

    The entity id arrives in a signal, and `get_or_create_intelligence_tree`
    will *create* a tree for any id it is handed. Without the ownership check
    a malformed or foreign id would mint an orphan tree attributed to this
    company, and a learning loop must never break the work it learns from, so
    it declines quietly rather than raising.
    """
    from src.ai.learning.outcomes import CandidateRule, OutcomeKind, write_candidate
    from src.common.database import AsyncSessionLocal

    candidate = CandidateRule(entity_id=uuid.uuid4(), kind=OutcomeKind.RUN_FAILED,
                              observations=3, statement="3 runs failed.")
    async with AsyncSessionLocal() as db:
        assert await write_candidate(db, company_id=companies[0], candidate=candidate) is None
        await db.rollback()

    async with AsyncSessionLocal() as db:
        trees = (await db.execute(text(
            "SELECT count(*) FROM cortex_trees WHERE company_id = :c"),
            {"c": str(companies[0])})).scalar()
    assert trees == 0, "an unknown entity must not mint a tree"


async def test_a_candidate_for_a_real_entity_lands_with_its_provenance(companies):
    """Two producers write candidates into the same tree now (the reflector and
    this loop), so `kind` has to say which — otherwise a debugger asking *which
    loop taught the agent this* has no way to find out."""
    from src.ai.learning.outcomes import CandidateRule, OutcomeKind, write_candidate
    from src.ai.loop.service import ensure_sheel
    from src.common.database import AsyncSessionLocal

    cid = companies[1]
    async with AsyncSessionLocal() as db:
        sheel = await ensure_sheel(db, cid)
        await db.commit()
        entity_id = sheel.id

    candidate = CandidateRule(entity_id=entity_id, kind=OutcomeKind.CSAT_NEGATIVE,
                              observations=4, statement="Rated poorly 4 times.")
    async with AsyncSessionLocal() as db:
        node_id = await write_candidate(db, company_id=cid, candidate=candidate)
        await db.commit()

    assert node_id is not None
    async with AsyncSessionLocal() as db:
        row = (await db.execute(text(
            "SELECT source_ref, content FROM cortex_nodes WHERE id = :i"),
            {"i": str(node_id)})).one()
    assert row.source_ref["status"] == "candidate", (
        "it must enter the shipped lifecycle as a candidate, not as a confirmed rule")
    assert row.source_ref["kind"] == "outcome_candidate"
    assert row.source_ref["observations"] == 4
    assert "4 times" in row.content

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM cortex_nodes WHERE tree_id IN "
                              "(SELECT id FROM cortex_trees WHERE company_id = :c)"),
                         {"c": str(cid)})
        await db.execute(text("DELETE FROM cortex_trees WHERE company_id = :c"),
                         {"c": str(cid)})
        await db.commit()
