"""LEARN T2 + T3 — the two daily jobs, against a real database.

T2 (`pool_day`) is where the B10 floor meets actual rows: the pure grouping is
covered in `test_learning_pooling.py`, so what matters here is that the SQL
reads what it thinks it reads, that re-running a day replaces it rather than
doubling it, and that a below-floor group leaves **nothing** behind.

T3 (`snapshot_company` / `snapshot_all`) is the job that starts the clock. The
property worth a database is the one that looks like a bug until you know the
rule: a brand-new tenant produces ten rows of *recorded absence*, not zero rows
and not ten zeroes.

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
        for tbl in ("kpi_snapshots", "routing_decisions", "human_approvals_noop"):
            if tbl == "human_approvals_noop":
                continue
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
