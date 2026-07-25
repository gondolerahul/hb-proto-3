"""LEARN T9 — letting observation correct a declaration, but only so far.

`model_registry.capability_profile` is what a model's vendor (or our own
catalog author) *claims*. The pooled store is what the fleet was *seen* doing.
This is the arithmetic that reconciles them, and every test here is about the
reconciliation staying modest: an unbounded correction would let a quiet
fortnight promote a bad model and a noisy one demote a good one, which is the
opposite of what a learning loop is for.

The load-bearing property is non-inferiority: with no pooled data — the state
of every deployment on day one — routing must behave *exactly* as it did
before. `tests/parity` is the canary for the rest of it.

Design: docs/product-road-map/increment-6/01_learn.md §4.4.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.intelligence.scoring import Candidate, blend_reliability, capability_fit, utility
from src.ai.intelligence.types import RoutingSignals

WEIGHT = 0.2


# ── the blend ────────────────────────────────────────────────────────────────

def test_no_observation_leaves_the_declaration_untouched():
    """The day-one state, and the one that must not change anything.

    An absent observation is not evidence against a declaration; it is the
    absence of evidence, and the declaration is real information.
    """
    assert blend_reliability(0.9, None, weight=WEIGHT) == 0.9


def test_a_zero_weight_disables_the_correction_entirely():
    """`LEARN_OBSERVATION_WEIGHT = 0.0` is the off switch, and it is exact."""
    assert blend_reliability(0.9, 0.1, weight=0.0) == 0.9


def test_a_worse_observation_marks_a_model_down():
    """The motivating case: advertised 0.9, observed 0.6."""
    assert blend_reliability(0.9, 0.6, weight=WEIGHT) == pytest.approx(0.7)


def test_a_better_observation_marks_a_model_up():
    """Correction runs both ways — a model that quietly outperforms its sheet
    should stop being passed over."""
    assert blend_reliability(0.5, 0.9, weight=WEIGHT) == pytest.approx(0.7)


def test_the_correction_is_clamped_at_the_weight():
    """However bad the fortnight was, the declaration moves at most `weight`.

    Without the clamp a model observed at 0.0 would score as 0.0 and vanish
    from routing — a removal decision, made silently, by an instrument that was
    only ever meant to express a preference. Removal is EVX's job.
    """
    assert blend_reliability(0.9, 0.0, weight=WEIGHT) == pytest.approx(0.7)
    assert blend_reliability(0.1, 1.0, weight=WEIGHT) == pytest.approx(0.3)


@pytest.mark.parametrize("declared,observed", [(1.0, 1.0), (0.0, 0.0), (0.05, 0.0)])
def test_the_result_stays_on_the_unit_interval(declared, observed):
    result = blend_reliability(declared, observed, weight=WEIGHT)
    assert 0.0 <= result <= 1.0


# ── capability_fit ───────────────────────────────────────────────────────────

_PROFILE = {"reasoning_strength": 0.9, "tool_reliability": 0.9}


def test_capability_fit_is_unchanged_by_default():
    """Every pre-existing caller passes neither new argument and must get the
    identical number back — this is the non-inferiority claim in one line."""
    assert capability_fit(_PROFILE, 0.5, True) == capability_fit(
        _PROFILE, 0.5, True, observed_reliability=None, observation_weight=WEIGHT)


def test_observation_only_touches_the_tool_axis():
    """Reasoning strength is not what the pooled data measures.

    A fallback rate says whether a call had to be re-routed; it says nothing
    about how well the model reasons. Correcting `reasoning_strength` from it
    would be inventing evidence.
    """
    no_tools = capability_fit(_PROFILE, 0.5, False,
                              observed_reliability=0.1, observation_weight=WEIGHT)
    assert no_tools == capability_fit(_PROFILE, 0.5, False)


def test_a_badly_observed_model_fits_worse_when_tools_are_needed():
    good = capability_fit(_PROFILE, 0.5, True,
                          observed_reliability=0.9, observation_weight=WEIGHT)
    bad = capability_fit(_PROFILE, 0.5, True,
                         observed_reliability=0.3, observation_weight=WEIGHT)
    assert bad < good


# ── utility ──────────────────────────────────────────────────────────────────

def _candidate(model_registry_id: uuid.UUID, *, cost: float = 0.001) -> Candidate:
    return Candidate(
        integration_id=uuid.uuid4(), model_name="m", provider="p",
        model_registry_id=model_registry_id,
        capability_profile=dict(_PROFILE), cost_proxy=cost)


def test_utility_is_unchanged_when_no_observations_are_supplied():
    signals = RoutingSignals(task_type="chat", needs_tools=True, complexity=0.5)
    candidate = _candidate(uuid.uuid4())
    assert utility(candidate, 0.5, signals) == utility(
        candidate, 0.5, signals, observed={}, observation_weight=WEIGHT)


def test_an_observation_for_another_model_does_not_apply():
    """Corrections are keyed by catalog row. A mismatched key must be a no-op,
    not a default."""
    signals = RoutingSignals(task_type="chat", needs_tools=True, complexity=0.5)
    candidate = _candidate(uuid.uuid4())
    stranger = {uuid.uuid4(): 0.1}
    assert utility(candidate, 0.5, signals,
                   observed=stranger, observation_weight=WEIGHT) == utility(
        candidate, 0.5, signals)


def test_a_poorly_observed_model_can_lose_a_close_race():
    """What the whole task is for: two models the catalog rates identically,
    one of which keeps having to be re-routed off."""
    signals = RoutingSignals(task_type="chat", needs_tools=True, complexity=0.5)
    reliable_id, flaky_id = uuid.uuid4(), uuid.uuid4()
    reliable, flaky = _candidate(reliable_id), _candidate(flaky_id)
    observed = {reliable_id: 0.95, flaky_id: 0.40}

    assert utility(reliable, 0.5, signals) == utility(flaky, 0.5, signals)
    assert (utility(reliable, 0.5, signals, observed=observed, observation_weight=WEIGHT)
            > utility(flaky, 0.5, signals, observed=observed, observation_weight=WEIGHT))


def test_observation_cannot_beat_a_large_capability_gap():
    """The bound, expressed as a routing outcome rather than as arithmetic.

    A weak model observed perfectly must not out-score a strong model observed
    poorly — otherwise a fortnight of luck would be enough to route hard work
    to a model that cannot do it.
    """
    signals = RoutingSignals(task_type="chat", needs_tools=True, complexity=0.9)
    strong_id, weak_id = uuid.uuid4(), uuid.uuid4()
    strong = _candidate(strong_id)
    weak = Candidate(
        integration_id=uuid.uuid4(), model_name="w", provider="p",
        model_registry_id=weak_id,
        capability_profile={"reasoning_strength": 0.3, "tool_reliability": 0.3},
        cost_proxy=0.001)
    observed = {strong_id: 0.0, weak_id: 1.0}

    assert (utility(strong, 0.9, signals, observed=observed, observation_weight=WEIGHT)
            > utility(weak, 0.9, signals, observed=observed, observation_weight=WEIGHT))
