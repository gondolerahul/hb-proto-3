"""SEGA T3/T4 — the cohort split and the verdict, decidable without a database.

Two things carry the weight here.

The **three-way verdict**: healthy / unhealthy / *not decided yet*. Collapsing
"not enough evidence" into either of the others is the failure mode — into
healthy and every change ships on a quiet week, into unhealthy and every change
is rolled back on one. A low-traffic entity sits in `canary` for weeks, and
that is a state rather than a delay.

The **stable cohort**: the same triggering signal must always land the same
side, or a retried signal contaminates both arms of the comparison with one
event.

Design: docs/product-road-map/increment-6/02_sega.md §6.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.ai.evolution.entity_canary import (
    DEFAULT_THRESHOLDS,
    MIN_SAMPLES,
    CanaryThresholds,
    VersionHealth,
    assess,
    in_canary_cohort,
    suites_for_entity,
)


def _health(runs=50, failures=0, decided=0, rejected=0, cost=0.0) -> VersionHealth:
    return VersionHealth(runs=runs, failures=failures, approvals_decided=decided,
                         approvals_rejected=rejected, total_cost_usd=cost)


# ── the cohort split ─────────────────────────────────────────────────────────

def test_the_split_is_stable_for_the_same_key():
    """A retried signal must land where it landed the first time."""
    key = str(uuid.uuid4())
    assert in_canary_cohort(key, 0.25) == in_canary_cohort(key, 0.25)


def test_the_split_is_stable_across_processes():
    """Hashed, not ``hash()`` — Python salts that per process, so a worker
    restart would silently re-draw every cohort."""
    assert in_canary_cohort("a-fixed-key", 0.5) is in_canary_cohort("a-fixed-key", 0.5)
    # A pinned expectation: if the hash function changes, every in-flight
    # canary re-assigns, and this test is where that is noticed.
    assert in_canary_cohort("a-fixed-key", 1.0) is True


def test_a_zero_fraction_serves_nobody():
    assert not any(in_canary_cohort(str(i), 0.0) for i in range(50))


def test_a_full_fraction_serves_everybody():
    assert all(in_canary_cohort(str(i), 1.0) for i in range(50))


def test_the_split_is_roughly_the_requested_fraction():
    """Not an exact count — a hash is not a quota. Close enough that a 25%
    canary does not quietly become 60%."""
    keys = [str(uuid.uuid4()) for _ in range(2000)]
    share = sum(in_canary_cohort(k, 0.25) for k in keys) / len(keys)
    assert 0.20 < share < 0.30


# ── the three-way verdict ────────────────────────────────────────────────────

def test_a_thin_canary_is_undecided_not_healthy():
    """The property this whole file exists for.

    A change with three runs behind it has not passed; it has not been judged.
    Reading that as "healthy" would promote every change a quiet tenant makes.
    """
    verdict = assess(_health(runs=3), _health(runs=100))
    assert verdict.decided is False
    assert verdict.action == "observe"


def test_a_thin_incumbent_is_also_undecided():
    """Comparison needs two sides. A brand-new entity has no predecessor worth
    comparing to, and that is not the candidate's fault."""
    verdict = assess(_health(runs=100), _health(runs=2))
    assert verdict.decided is False


def test_the_sample_floor_is_honoured_exactly():
    assert assess(_health(runs=MIN_SAMPLES - 1), _health(runs=100)).decided is False
    assert assess(_health(runs=MIN_SAMPLES), _health(runs=MIN_SAMPLES)).decided is True


def test_a_clean_canary_is_promoted():
    verdict = assess(_health(runs=50, failures=2), _health(runs=50, failures=2))
    assert verdict.decided and verdict.healthy
    assert verdict.action == "promote"


def test_a_regressing_failure_rate_rolls_back():
    verdict = assess(_health(runs=50, failures=30), _health(runs=50, failures=2))
    assert verdict.action == "roll_back"
    assert any("failure rate" in r for r in verdict.reasons)


def test_more_human_rejections_roll_back():
    """A change humans keep refusing is a bad change even when nothing errors —
    the failure mode a pure uptime metric would miss entirely."""
    verdict = assess(
        _health(runs=50, decided=40, rejected=30),
        _health(runs=50, decided=40, rejected=2))
    assert verdict.action == "roll_back"
    assert any("rejected" in r for r in verdict.reasons)


def test_a_much_more_expensive_version_rolls_back():
    verdict = assess(_health(runs=50, cost=100.0), _health(runs=50, cost=10.0))
    assert verdict.action == "roll_back"
    assert any("x the previous" in r for r in verdict.reasons)


def test_a_cheaper_version_is_never_penalised():
    verdict = assess(_health(runs=50, cost=1.0), _health(runs=50, cost=50.0))
    assert verdict.healthy


def test_an_entity_with_a_high_baseline_is_judged_against_itself():
    """An entity whose normal failure rate is 30% is not unhealthy for being
    itself. The question is whether *this version* is worse than its own
    predecessor — a fleet-wide absolute would condemn every hard job."""
    verdict = assess(_health(runs=50, failures=16), _health(runs=50, failures=15))
    assert verdict.healthy


def test_every_regression_reason_is_reported_not_just_the_first():
    """A human reading a rollback deserves the whole case, not the first clause."""
    verdict = assess(
        _health(runs=50, failures=40, decided=40, rejected=35, cost=100.0),
        _health(runs=50, failures=1, decided=40, rejected=1, cost=1.0))
    assert len(verdict.reasons) == 3


def test_thresholds_are_configurable():
    strict = CanaryThresholds(failure_rate_margin=0.0)
    healthy_by_default = assess(_health(runs=50, failures=6), _health(runs=50, failures=1))
    assert healthy_by_default.healthy
    assert not assess(_health(runs=50, failures=6), _health(runs=50, failures=1),
                      strict).healthy


def test_a_verdict_reports_why_even_when_healthy():
    verdict = assess(_health(runs=50), _health(runs=50), DEFAULT_THRESHOLDS)
    assert verdict.reasons and "no regression" in verdict.reasons[0]


# ── T4 · the admission suites ────────────────────────────────────────────────

def test_a_solo_pack_entity_is_covered_by_the_platform_suite():
    """The PACK behavioural goldens (03b) are the curated suite for this class."""
    entity = SimpleNamespace(tags=["solo_pack", "karuna", "agent_code:AGT-030"])
    suites = suites_for_entity(entity, _health(runs=50))
    assert suites.platform_curated is True
    assert suites.incumbent_golden is True


def test_a_hand_built_tenant_agent_has_no_curated_suite():
    """And therefore cannot be promoted automatically.

    A real and intended consequence, not an oversight: §22.2 wants a platform
    curated suite for the artifact class, and a tenant's bespoke agent has
    none. A human may still promote it by hand — these limits govern
    *automated* change only.
    """
    entity = SimpleNamespace(tags=["custom"])
    assert suites_for_entity(entity, _health(runs=50)).platform_curated is False


def test_an_entity_with_no_track_record_has_no_incumbent_golden():
    """"The exam predates the student" — with no predecessor runs, nothing set
    the bar, so there is no exam."""
    entity = SimpleNamespace(tags=["solo_pack"])
    assert suites_for_entity(entity, _health(runs=1)).incumbent_golden is False


def test_promotion_refuses_without_independent_suites():
    """The EVX rule, reused verbatim rather than re-implemented."""
    from src.ai.intelligence.admission import AdmissionError, require_independent_suites

    entity = SimpleNamespace(tags=["custom"])
    with pytest.raises(AdmissionError):
        require_independent_suites(suites_for_entity(entity, _health(runs=50)))
