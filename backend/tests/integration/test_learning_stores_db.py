"""LEARN T1 — the stores exist in the database, and the pooled one is bare.

``test_learning_models.py`` asserts the guarantee against the SQLAlchemy
metadata. This suite asserts it against **the database Postgres actually has**,
because those can differ: a hand-written migration is not generated from the
models, so a column could reach the table without reaching the class (or the
reverse). The B10 guarantee is about the physical table, so it is worth
checking the physical table.

Also pins the two properties the later tasks depend on: the pooled grain is
unique (T2 upserts into it) and a KPI snapshot may record an absence (T3 writes
one every day for every unmeasurable KPI).

``needs_db``.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


async def _columns(db, table: str) -> dict[str, str]:
    rows = (await db.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = :t"), {"t": table})).all()
    return {name: dtype for name, dtype in rows}


async def _fk_targets(db, table: str) -> set[str]:
    rows = (await db.execute(text("""
        SELECT ccu.table_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
        WHERE tc.table_name = :t AND tc.constraint_type = 'FOREIGN KEY'
    """), {"t": table})).all()
    return {r[0] for r in rows}


# ── the guarantee, at the database ───────────────────────────────────────────

async def test_pooled_table_exists_and_has_no_tenant_column(db):
    cols = await _columns(db, "platform_observations")
    assert cols, "platform_observations missing — learn001 not applied"
    assert "company_id" not in cols
    assert not any("company" in c or "tenant" in c for c in cols)


async def test_pooled_table_has_no_json_or_text_column(db):
    """The physical types, not the declared ones.

    ``jsonb`` and ``text`` are where a business fact would hide. Everything the
    pooled table holds is a bounded scalar, so there is nowhere for one to go.
    """
    cols = await _columns(db, "platform_observations")
    offenders = {n: t for n, t in cols.items() if t in ("jsonb", "json", "text")}
    assert not offenders, f"free-form columns on the pooled table: {offenders}"


async def test_pooled_table_references_only_the_platform_catalog(db):
    targets = await _fk_targets(db, "platform_observations")
    assert targets <= {"model_registry"}, f"unexpected FK targets: {targets}"


async def test_pooled_grain_rejects_a_duplicate_bucket(db):
    """T2 upserts on this constraint; without it the job appends forever.

    The second insert runs inside a nested transaction so its failure does not
    poison the enclosing one — the `db` fixture rolls everything back anyway.
    """
    insert = text(
        "INSERT INTO platform_observations "
        "(id, metric, task_type, reason, bucket_day, observations) "
        "VALUES (:id, :m, :t, 'auto', :d, 1)")
    shared = {"m": "route_outcome", "t": f"test_{uuid.uuid4().hex[:8]}",
              "d": date(2026, 1, 1)}

    await db.execute(insert, {**shared, "id": str(uuid.uuid4())})
    await db.flush()

    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(insert, {**shared, "id": str(uuid.uuid4())})


# ── the tenant path ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("table", ["kpi_snapshots", "entity_behaviour_weekly",
                                   "user_preferences"])
async def test_tenant_tables_require_a_company(db, table):
    cols = (await db.execute(text(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = 'company_id'"), {"t": table})).all()
    assert cols, f"{table}.company_id missing"
    assert cols[0][0] == "NO"


async def test_a_kpi_snapshot_can_record_an_absence(db, test_company_id):
    """NULL value + measurable=false is a legitimate row, not a constraint error.

    This is the C6 honest-absence rule surviving persistence. If the column were
    NOT NULL the daily job would have to skip unmeasurable KPIs, and the series
    would silently begin on the day a KPI became computable — which is exactly
    the chart that starts in the middle.
    """
    row_id = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO kpi_snapshots (id, company_id, kpi_key, captured_on, "
        "value, measurable, missing, unit) VALUES "
        "(:i, :c, 'gross_margin', :d, NULL, false, "
        "'[\"Invoice.due_date\"]'::jsonb, 'percent')"),
        {"i": str(row_id), "c": str(test_company_id), "d": date(2026, 1, 1)})
    await db.flush()

    stored = (await db.execute(text(
        "SELECT value, measurable, missing FROM kpi_snapshots WHERE id = :i"),
        {"i": str(row_id)})).one()
    assert stored[0] is None
    assert stored[1] is False
    assert stored[2] == ["Invoice.due_date"]
