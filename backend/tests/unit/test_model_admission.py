"""Inc 5 / EVX — the admission gate's pure logic (unit, no DB).

Non-inferiority, the cost budget, and the independent-suite rule (§22.2, §22.4).
The failing-candidate fixtures are the proof the gate bites.
"""
from __future__ import annotations

import pytest

from src.ai.intelligence.admission import (
    AdmissionError,
    SuiteSet,
    non_inferior,
    require_independent_suites,
    within_cost_budget,
)
from tests.eval.routing_corpus import (
    EXPENSIVE_CANDIDATE,
    FULL_SUITES,
    GOOD_CANDIDATE,
    INCUMBENT_EVAL,
    REGRESSED_CANDIDATE,
    SELF_GENERATED_ONLY,
)


def test_non_inferior_allows_small_regression_within_tolerance() -> None:
    assert non_inferior(GOOD_CANDIDATE.quality, INCUMBENT_EVAL.quality)      # 0.91 vs 0.90
    assert non_inferior(0.89, 0.90, tolerance=0.02)                         # just inside
    assert not non_inferior(REGRESSED_CANDIDATE.quality, INCUMBENT_EVAL.quality)  # 0.80 vs 0.90


def test_cost_budget_lets_cheaper_pass_and_caps_pricier() -> None:
    assert within_cost_budget(GOOD_CANDIDATE.cost, INCUMBENT_EVAL.cost)      # cheaper → pass
    assert within_cost_budget(0.014, 0.010, ratio=1.5)                      # 1.4× → within
    assert not within_cost_budget(EXPENSIVE_CANDIDATE.cost, INCUMBENT_EVAL.cost)  # 3× → refuse


def test_independent_suite_rule_requires_incumbent_and_curated() -> None:
    require_independent_suites(FULL_SUITES)   # both present → no raise
    # The exam must predate the student — self-generated-only is refused.
    with pytest.raises(AdmissionError):
        require_independent_suites(SELF_GENERATED_ONLY)
    # A curated suite alone (no incumbent golden) is also refused.
    with pytest.raises(AdmissionError):
        require_independent_suites(SuiteSet(incumbent_golden=False, platform_curated=True))
    # An incumbent golden without a platform curated suite is refused too.
    with pytest.raises(AdmissionError):
        require_independent_suites(SuiteSet(incumbent_golden=True, platform_curated=False))


def test_model_admission_spend_is_platform_initiated() -> None:
    """B13 (§5 convention): eval-harness admission runs must never draw from a
    tenant wallet — the attribution has to be classified platform-initiated."""
    from src.ai.services.cost_attribution import (
        PLATFORM_INITIATED_ATTRIBUTIONS,
        CostAttribution,
    )
    assert CostAttribution.MODEL_ADMISSION.value in PLATFORM_INITIATED_ATTRIBUTIONS
