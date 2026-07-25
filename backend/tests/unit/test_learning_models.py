"""LEARN T1 — the B10 schema guarantee, asserted rather than promised.

Charter decision 2 says the pooled learning path must be *structurally
incapable* of carrying tenant content, and decision 8 (pooled learning is
disclosed, with no opt-out) is justified **only** by that guarantee holding.
The two stand or fall together, so the guarantee needs a test that fails when
someone repeals it — including the someone who repeals it by accident, in a
hurry, while adding a useful-looking column.

The tests below are deliberately structural. They do not check behaviour; they
check that ``platform_observations`` has no place to *put* a tenant, which is a
stronger claim than any behavioural test could make.

Design: docs/product-road-map/increment-6/01_learn.md §4.
"""
from __future__ import annotations

import pytest
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB

from src.ai.learning.models import (
    POOLED_COLUMNS,
    EntityBehaviourWeekly,
    KpiSnapshot,
    ObservationMetric,
    PlatformObservation,
    UserPreference,
)


# ── the pooled path: the guarantee ───────────────────────────────────────────

def test_pooled_table_has_no_company_column():
    """The headline claim, stated the most direct way there is.

    Not "company_id is left NULL" — decision 2 rules that out explicitly, since
    a nullable column enforced by discipline is a bug waiting for a careless
    insert. There is no column.
    """
    names = set(PlatformObservation.__table__.columns.keys())
    assert "company_id" not in names
    assert not any("company" in n for n in names)
    assert not any("tenant" in n for n in names)


def test_pooled_table_has_no_foreign_key_to_a_tenant_scoped_table():
    """Every FK out of this table must point at a *platform* catalog row.

    ``model_registry`` is the fleet catalog — the same fleet for every tenant.
    An FK to companies, users, execution_runs or hierarchical_entities would
    reintroduce the tenant by reference, which is the same leak with an extra
    join in front of it.
    """
    # ``target_fullname`` is the declared string, not the resolved Column —
    # this module is import-light on purpose (no relationship(), no consumer
    # imports), so the referenced tables are not in this metadata to resolve.
    targets = {
        fk.target_fullname.split(".")[0]
        for column in PlatformObservation.__table__.columns
        for fk in column.foreign_keys
    }
    assert targets <= {"model_registry"}, f"unexpected FK targets: {targets}"


def test_pooled_table_column_set_is_exactly_the_design():
    """A new column on this table is a decision, not a detail.

    If this test fails because a column was added: that is the test working.
    Check §4.2 of the design and, if the column is genuinely needed, update
    ``POOLED_COLUMNS`` *and* re-read decision 8 — the no-opt-out posture is
    justified by this column set and by nothing else.
    """
    assert set(PlatformObservation.__table__.columns.keys()) == POOLED_COLUMNS


def test_pooled_table_carries_no_free_form_column():
    """No JSON, no Text: the columns a business fact could hide in.

    Every remaining type is a bounded scalar — a short string from a closed
    vocabulary, a date bucket, a counter, a UUID FK. A customer's name has
    nowhere to go, so putting one here is a type error rather than a policy
    violation, which is the whole of decision 2.
    """
    allowed = (String, Integer, Float, Numeric, Date, DateTime, Boolean)
    for column in PlatformObservation.__table__.columns:
        if column.name == "id" or column.foreign_keys:
            continue                      # UUID identity / platform-catalog FK
        assert isinstance(column.type, allowed), (
            f"{column.name} is {column.type!r}; the pooled table admits only "
            "bounded scalars")
        assert not isinstance(column.type, JSONB)


@pytest.mark.parametrize("column_name,limit", [("metric", 32), ("reason", 16),
                                               ("task_type", 64)])
def test_pooled_string_columns_are_short_by_design(column_name, limit):
    """Short strings are a second line of defence, not styling.

    A ``String(32)`` cannot hold a paragraph of customer correspondence even if
    a future writer tried. The vocabulary columns are sized to their vocabulary.
    """
    assert PlatformObservation.__table__.columns[column_name].type.length == limit


def test_metric_vocabulary_is_closed():
    """An open vocabulary is a free-text column wearing a different name."""
    assert ObservationMetric.ALL == {
        "route_outcome", "model_failure", "fallback_used", "admission_score"}


def test_pooled_grain_is_unique_and_treats_no_model_as_one_value():
    """Aggregate-on-write needs one row per bucket, or the upsert is an insert.

    The grain is a unique *expression* index rather than a UniqueConstraint,
    because ``model_registry_id`` is nullable and Postgres treats NULLs as
    distinct — a plain constraint would silently permit unlimited duplicate
    "no model" buckets. `test_learning_stores_db.py` is what caught that;
    this asserts the fix stays.
    """
    idx = {i.name: i for i in PlatformObservation.__table__.indexes}
    grain = idx.get("uq_platform_observation_bucket")
    assert grain is not None and grain.unique

    rendered = [str(e) for e in grain.expressions]
    assert rendered[0].endswith("metric")
    assert "coalesce(model_registry_id" in rendered[1]
    assert [r.split(".")[-1] for r in rendered[2:]] == [
        "task_type", "reason", "bucket_day"]


# ── the tenant path: scoped the ordinary way ─────────────────────────────────

@pytest.mark.parametrize("model", [KpiSnapshot, EntityBehaviourWeekly, UserPreference])
def test_tenant_tables_are_company_scoped_not_null(model):
    """The other half of the split: these tables *must* carry a company.

    The guarantee runs in both directions. A tenant learning row without a
    company is as wrong as a pooled row with one.
    """
    company_id = model.__table__.columns["company_id"]
    assert company_id.nullable is False
    assert {fk.target_fullname for fk in company_id.foreign_keys} == {"companies.id"}


# ── the honest-absence rule, carried into storage ────────────────────────────

def test_kpi_value_is_nullable_and_measurable_is_not():
    """``value`` may be absent; whether it is absent may not be.

    A KPI whose prerequisites are unmet stores NULL and ``measurable=False``.
    Storing 0 there would turn "I cannot tell what you are owed" into "you are
    owed nothing" — the exact substitution ``kpi/compute.py`` exists to prevent,
    and the one that would do the most damage in a strategy review.
    """
    assert KpiSnapshot.__table__.columns["value"].nullable is True
    assert KpiSnapshot.__table__.columns["measurable"].nullable is False


def test_kpi_snapshot_grain_is_one_row_per_company_kpi_day():
    """Idempotency: re-running the daily job overwrites the day it re-runs."""
    uniques = {
        tuple(c.name for c in constraint.columns)
        for constraint in KpiSnapshot.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("company_id", "kpi_key", "captured_on") in uniques


def test_kpi_unit_is_stored_not_derived():
    """A definition's unit may change; a recorded reading's may not."""
    assert "unit" in KpiSnapshot.__table__.columns


# ── drift series: aggregates, never content ──────────────────────────────────

def test_behaviour_series_carries_no_content():
    """Counts and ratios only — the ``SourceTrustScore`` precedent.

    An aggregate over outcomes needs no prompt, output or record in it, and a
    drift monitor that stored them would be a second copy of tenant data with a
    different retention policy.
    """
    for column in EntityBehaviourWeekly.__table__.columns:
        assert not isinstance(column.type, JSONB), column.name
        if isinstance(column.type, String):
            pytest.fail(f"{column.name}: the behaviour series admits no strings")
