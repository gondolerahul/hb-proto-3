"""LEARN T7 — detecting a step change without crying wolf.

Drift catches an agent that is becoming *different*, which is a weaker and
noisier signal than an agent that is failing. That makes the interesting tests
the ones about **restraint**: a short baseline, a metric that never varied, an
agent whose normal is unusual. Each is a way to fire on nothing, and an alert
nobody believes is worse than no alert.

Design: docs/product-road-map/increment-6/01_learn.md §8.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from src.ai.learning.drift import (
    MIN_BASELINE_WEEKS,
    TRACKED_METRICS,
    detect_drift,
    week_start_of,
)
from src.ai.learning.models import EntityBehaviourWeekly

ENTITY = uuid.uuid4()


def _week(n: int, **metrics) -> EntityBehaviourWeekly:
    """A measured week; unnamed metrics are absent, not zero."""
    return EntityBehaviourWeekly(
        company_id=uuid.uuid4(), entity_id=ENTITY,
        week_start=date(2026, 1, 5) + timedelta(weeks=n), runs=10, **metrics)


# ── the week grain ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("day,expected", [
    (date(2026, 3, 15), date(2026, 3, 9)),    # a Sunday → the Monday before
    (date(2026, 3, 9), date(2026, 3, 9)),     # a Monday → itself
    (date(2026, 3, 13), date(2026, 3, 9)),    # a Friday → that Monday
])
def test_weeks_start_on_monday(day, expected):
    assert week_start_of(day) == expected


# ── restraint ────────────────────────────────────────────────────────────────

def test_a_short_baseline_detects_nothing():
    """There is nothing to be different *from* yet.

    A new agent's second week is not a step change, and treating it as one
    would make every newly activated colleague look like it was drifting.
    """
    history = [_week(i, approval_rate=0.5) for i in range(MIN_BASELINE_WEEKS - 1)]
    assert detect_drift(history, _week(9, approval_rate=1.0)) == []


def test_a_metric_that_never_varied_gives_no_scale():
    """Zero variance would make any change infinitely many sigmas away.

    That is arithmetic, not evidence — an agent whose approval rate has been
    exactly 1.0 for six weeks and is 0.99 this week has not drifted.
    """
    history = [_week(i, approval_rate=1.0) for i in range(6)]
    assert detect_drift(history, _week(9, approval_rate=0.99)) == []


def test_an_unusual_agent_is_compared_against_itself():
    """A meticulous agent that always escalates is not drifting; it is itself.

    The only meaningful baseline for "has this changed" is what *this* agent
    used to do — never a fleet average, which would flag every specialist.
    """
    history = [_week(i, escalation_rate=0.80 + (i % 2) * 0.01) for i in range(6)]
    assert detect_drift(history, _week(9, escalation_rate=0.81)) == []


def test_an_absent_metric_this_week_is_not_a_drop_to_zero():
    """An agent that raised no approvals has no approval rate.

    Reading absence as 0.0 would fire drift every quiet week, and then fire it
    again when the agent resumed — the honest-absence rule, in a second place
    that needs it.
    """
    history = [_week(i, approval_rate=0.9 + (i % 3) * 0.01) for i in range(6)]
    assert detect_drift(history, _week(9)) == []


def test_normal_variation_is_not_drift():
    history = [_week(i, mean_steps=4.0 + (i % 3) * 0.5) for i in range(8)]
    assert detect_drift(history, _week(9, mean_steps=4.5)) == []


# ── detection ────────────────────────────────────────────────────────────────

def test_a_real_step_change_is_detected():
    history = [_week(i, rejection_rate=0.05 + (i % 3) * 0.01) for i in range(8)]
    findings = detect_drift(history, _week(9, rejection_rate=0.60))
    assert len(findings) == 1
    assert findings[0].metric == "rejection_rate"
    assert findings[0].direction == "up"


def test_a_drop_is_drift_too():
    """Becoming quieter is a change. An agent that stopped escalating may have
    stopped noticing, which is the more dangerous direction."""
    history = [_week(i, escalation_rate=0.40 + (i % 3) * 0.02) for i in range(8)]
    findings = detect_drift(history, _week(9, escalation_rate=0.0))
    assert len(findings) == 1
    assert findings[0].direction == "down"


def test_a_finding_carries_the_numbers_behind_the_claim():
    """A human reads this. "Drifted" alone is an assertion; the baseline and
    the spread are the evidence."""
    history = [_week(i, mean_csat=0.9 + (i % 3) * 0.02) for i in range(8)]
    finding = detect_drift(history, _week(9, mean_csat=-1.0))[0]
    assert finding.baseline_sigma > 0
    assert "baseline" in finding.as_sentence()
    assert f"{finding.current:.2f}" in finding.as_sentence()


def test_several_metrics_can_drift_at_once():
    history = [_week(i, rejection_rate=0.05, mean_steps=4.0 + (i % 3) * 0.1)
               for i in range(8)]
    findings = detect_drift(history, _week(9, rejection_rate=0.05, mean_steps=40.0))
    assert {f.metric for f in findings} == {"mean_steps"}


def test_the_sigma_threshold_is_honoured():
    history = [_week(i, approval_rate=0.50 + (i % 2) * 0.10) for i in range(8)]
    lenient = detect_drift(history, _week(9, approval_rate=0.70), sigma=1.0)
    strict = detect_drift(history, _week(9, approval_rate=0.70), sigma=6.0)
    assert lenient and not strict


def test_the_tracked_set_stays_small():
    """Every axis added is another way for the sweep to cry wolf."""
    assert set(TRACKED_METRICS) == {
        "approval_rate", "rejection_rate", "escalation_rate", "mean_steps", "mean_csat"}


def test_detection_never_demotes():
    """LEARN observes; C4 decides. A finding is a dataclass with no authority —
    there is deliberately no `demote` field for a caller to act on directly."""
    history = [_week(i, rejection_rate=0.05) for i in range(8)]
    finding = detect_drift(history, _week(9, rejection_rate=0.9))
    assert not hasattr(finding[0] if finding else object(), "demote")
