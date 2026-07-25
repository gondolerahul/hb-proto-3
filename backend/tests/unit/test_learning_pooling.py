"""LEARN T2 — the k-anonymity floor, where it is decidable without a database.

The pooled table cannot hold a tenant (T1 proved that structurally). This suite
is about the second, subtler leak: a bucket that names nobody is still
attributable if only one tenant could have produced it. The floor is what
closes that, and the property it must have is that it counts **distinct
companies, not rows** — a floor that a single chatty tenant can clear protects
nobody while looking like it protects everybody.

Design: docs/product-road-map/increment-6/01_learn.md §4.3.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from src.ai.learning.pooling import Bucket, DecisionRow, bucket_decisions

MODEL_A = uuid.uuid4()
MODEL_B = uuid.uuid4()


def _row(company: uuid.UUID, *, model=MODEL_A, task="chat", reason="auto",
         fallback=False, latency=100, cost="0.01") -> DecisionRow:
    return DecisionRow(
        company_id=company, task_type=task, model_registry_id=model,
        reason=reason, fallback_used=fallback, latency_ms=latency,
        cost_usd=Decimal(cost))


def _companies(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


# ── the floor ────────────────────────────────────────────────────────────────

def test_one_tenant_with_many_rows_never_clears_the_floor():
    """The load-bearing test in this file.

    A thousand decisions from one company is one contributor. If the floor
    counted rows, a single-tenant bucket would sail through it and the pooled
    table would carry a fact about exactly one identifiable business.
    """
    only = uuid.uuid4()
    rows = [_row(only) for _ in range(1000)]
    assert bucket_decisions(rows, min_contributors=3) == []


def test_a_group_at_the_floor_is_kept():
    rows = [_row(c) for c in _companies(3)]
    buckets = bucket_decisions(rows, min_contributors=3)
    assert len(buckets) == 1
    assert buckets[0].contributors == 3
    assert buckets[0].observations == 3


def test_a_group_below_the_floor_is_dropped_not_deferred():
    """Dropped means gone: no residue, no queue, nothing held for later.

    Deferring would mean keeping company-attributable rows somewhere until more
    tenants arrived, which is the exact exposure the floor exists to prevent.
    """
    rows = [_row(c) for c in _companies(2)]
    assert bucket_decisions(rows, min_contributors=3) == []


def test_the_floor_is_per_group_not_global():
    """A popular group must not carry a rare one through with it."""
    popular = [_row(c, task="chat") for c in _companies(4)]
    rare = [_row(uuid.uuid4(), task="realtime_audio")]

    buckets = bucket_decisions(popular + rare, min_contributors=3)
    assert [b.task_type for b in buckets] == ["chat"]


def test_a_floor_of_one_keeps_everything():
    """The setting is a floor, not a policy branch — 1 disables it cleanly."""
    rows = [_row(uuid.uuid4())]
    assert len(bucket_decisions(rows, min_contributors=1)) == 1


# ── grouping ─────────────────────────────────────────────────────────────────

def test_groups_split_on_model_task_and_reason():
    companies = _companies(3)
    rows = (
        [_row(c, model=MODEL_A, task="chat", reason="auto") for c in companies]
        + [_row(c, model=MODEL_B, task="chat", reason="auto") for c in companies]
        + [_row(c, model=MODEL_A, task="extract", reason="auto") for c in companies]
        + [_row(c, model=MODEL_A, task="chat", reason="downshift") for c in companies]
    )
    buckets = bucket_decisions(rows, min_contributors=3)
    assert len(buckets) == 4
    assert all(b.observations == 3 for b in buckets)


def test_decisions_with_no_bound_model_group_together():
    """`model_registry_id` is nullable, so "no model" must be one group.

    This is the same fact the grain's `coalesce` index encodes at the database:
    if these split, the job would emit rows the unique index then rejects.
    """
    companies = _companies(3)
    rows = [_row(c, model=None) for c in companies]
    buckets = bucket_decisions(rows, min_contributors=3)
    assert len(buckets) == 1
    assert buckets[0].model_registry_id is None


# ── the counts ───────────────────────────────────────────────────────────────

def test_success_means_did_not_fall_back():
    """The canary's SLO proxy, reused deliberately (and limited the same way)."""
    companies = _companies(4)
    rows = [_row(companies[0]), _row(companies[1]),
            _row(companies[2], fallback=True), _row(companies[3], fallback=True)]
    bucket = bucket_decisions(rows, min_contributors=3)[0]
    assert bucket.observations == 4
    assert bucket.successes == 2.0


def test_latency_and_cost_are_summed_not_averaged():
    """Sums keep the bucket mergeable; a mean would need its own denominator."""
    companies = _companies(3)
    rows = [_row(companies[0], latency=100, cost="0.01"),
            _row(companies[1], latency=250, cost="0.02"),
            _row(companies[2], latency=50, cost="0.03")]
    bucket = bucket_decisions(rows, min_contributors=3)[0]
    assert bucket.latency_ms_sum == 400
    assert bucket.cost_usd_sum == Decimal("0.06")


def test_empty_input_is_not_an_error():
    """A quiet day pools nothing and says so — it does not raise."""
    assert bucket_decisions([], min_contributors=3) == []


def test_bucket_carries_no_company_field():
    """The output shape has nowhere to leak a tenant either.

    `contributors` is a count, and it is deliberately not written to the table
    (§4.3) — a distinct-company count is itself a small fact about tenants.
    """
    fields = set(Bucket.__dataclass_fields__)
    assert "company_id" not in fields
    assert not any("company" in f for f in fields - {"contributors"})


@pytest.mark.parametrize("floor", [2, 3, 5])
def test_the_floor_is_honoured_exactly(floor):
    """Off-by-one at a privacy boundary is a privacy bug."""
    below = [_row(c) for c in _companies(floor - 1)]
    at = [_row(c) for c in _companies(floor)]
    assert bucket_decisions(below, min_contributors=floor) == []
    assert len(bucket_decisions(at, min_contributors=floor)) == 1
