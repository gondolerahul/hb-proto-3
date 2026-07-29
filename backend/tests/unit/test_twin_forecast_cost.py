"""Increment 6 / TWIN T7 + T8 + T10 + T11 — forecast, cost, promotion, people.

The forecast tests care mostly about the *refusal*: §12 says "forecast is empty
at launch. Correct, and it will look broken. The refusal message must say why
it cannot forecast yet, not just that it cannot." So the message is asserted,
not only the absence of a number.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from src.ai.twin.counterparties import (
    SIMULATED_MARKER,
    build_counterparty,
    disclose,
    is_simulated,
)
from src.ai.twin.forecast import Point, project
from src.ai.twin.grading import Grade
from src.ai.twin.materialise import Scope, ScopeRefused
from src.ai.twin.promotion import EvidenceTooWeak, evidence_for


def _series(values: list[float], start: date | None = None) -> list[Point]:
    origin = start or (date.today() - timedelta(days=len(values)))
    return [Point(origin + timedelta(days=i), v) for i, v in enumerate(values)]


# ── T7: forecast ─────────────────────────────────────────────────────


def test_a_short_series_is_refused_not_widened() -> None:
    result = project(_series([1.0, 2.0, 3.0]), min_points=8)
    assert result.refused
    assert result.value is None
    assert result.grade == Grade.UNKNOWN


def test_the_refusal_says_why_it_cannot_forecast_yet() -> None:
    """"Not enough history" is a message people file under "broken". A message
    naming the floor, the count and the reason is one they file under "ask me
    again next week"."""
    result = project(_series([1.0, 2.0, 3.0]), min_points=8)
    assert "8" in result.refusal_reason
    assert "3" in result.refusal_reason
    assert "backfill" in result.refusal_reason


def test_a_long_enough_series_projects_and_says_how() -> None:
    result = project(_series([10.0] * 10), min_points=8)
    assert not result.refused
    assert result.grade == Grade.FORECAST
    assert result.value == pytest.approx(10.0, abs=0.5)
    # The method is declared with the result — §5.3.
    assert "points" in result.method


def test_a_flat_series_has_a_tight_interval() -> None:
    result = project(_series([10.0] * 20), min_points=8)
    assert result.high - result.low == pytest.approx(0.0, abs=0.001)


def test_a_noisy_series_has_a_wider_one() -> None:
    noisy = project(_series([0.0, 20.0] * 10), min_points=8)
    flat = project(_series([10.0] * 20), min_points=8)
    assert (noisy.high - noisy.low) > (flat.high - flat.low)


def test_the_interval_widens_with_the_horizon() -> None:
    """A projection three weeks out is not as good as one three days out, and
    the number should say so."""
    series = _series([float(i % 5) for i in range(20)])
    near = project(series, horizon_days=1, min_points=8)
    far = project(series, horizon_days=21, min_points=8)
    assert (far.high - far.low) > (near.high - near.low)


def test_a_long_series_uses_seasonal_naive() -> None:
    """Business KPIs are weekly-seasonal far more often than they are linear."""
    result = project(_series([float(i % 7) for i in range(30)]), min_points=8)
    assert "seasonal-naive" in result.method


def test_a_short_but_sufficient_series_uses_linear() -> None:
    result = project(_series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]),
                     min_points=8)
    assert "linear" in result.method


def test_a_rising_line_projects_upward() -> None:
    result = project(_series([float(i) for i in range(20)]), horizon_days=1,
                     min_points=8)
    assert result.value > 19.0


# ── T8: scope bounds ─────────────────────────────────────────────────


def test_a_window_past_the_cap_is_refused() -> None:
    """§6.1 — a refusal, not a truncation. Silently shrinking a window would
    make two runs incomparable without saying so."""
    with pytest.raises(ScopeRefused) as caught:
        Scope(objects=("Invoice",), window_days=365).validate()
    assert "incomparable" in str(caught.value)


def test_a_window_at_the_cap_is_allowed() -> None:
    from src.common.config import settings

    Scope(objects=("Invoice",), window_days=settings.TWIN_MAX_WINDOW_DAYS).validate()


def test_a_zero_window_is_refused() -> None:
    with pytest.raises(ScopeRefused):
        Scope(objects=("Invoice",), window_days=0).validate()


def test_an_empty_object_list_is_legitimate() -> None:
    """Schema-only: a scenario varying a charter or a roster needs the shape
    but no history."""
    Scope(objects=(), window_days=7).validate()


def test_the_cap_message_teaches_the_rule_not_just_the_bound() -> None:
    with pytest.raises(ScopeRefused) as caught:
        Scope(window_days=999).validate()
    assert "refusal rather than a truncation" in str(caught.value)


# ── T10: promotion evidence ──────────────────────────────────────────


class _Run:
    def __init__(self, grade: str, refusal: str | None = None):
        self.id = uuid.uuid4()
        self.scenario_id = uuid.uuid4()
        self.company_id = uuid.uuid4()
        self.grade = grade
        self.method = "replayed 63 signals"
        self.metrics = {"revenue": 100}
        self.entity_version_id = None
        self.refusal_reason = refusal


def test_the_card_carries_the_grade_and_what_it_means() -> None:
    """A T2 ceremony asks someone to accept a change on this evidence. Hiding
    the grade behind a number would make the ceremony worse than none, since it
    would launder a guess as proof."""
    card = evidence_for(_Run(Grade.REPLAY)).as_card()
    assert card["grade"] == Grade.REPLAY
    assert card["grade_means"]
    assert "argument, not an authorisation" in card["caveat"]


@pytest.mark.asyncio
async def test_an_unknown_graded_run_is_refused_as_evidence() -> None:
    """Putting an illustration in front of an owner as though it were evidence
    trains them to click through the ceremony, which is how a gate stops
    working."""
    from src.ai.twin.promotion import propose_promotion

    with pytest.raises(EvidenceTooWeak) as caught:
        await propose_promotion(None, _Run(Grade.UNKNOWN))
    assert "illustration" in str(caught.value)


@pytest.mark.asyncio
async def test_a_refused_run_is_refused_as_evidence() -> None:
    from src.ai.twin.promotion import propose_promotion

    with pytest.raises(EvidenceTooWeak):
        await propose_promotion(None, _Run(Grade.REPLAY, refusal="over the cap"))


def test_twin_owns_no_canary() -> None:
    """Decision 5. A second blast-radius implementation is the one duplication
    B11 cannot survive — a limit enforced in two places is enforced in neither,
    because the next change only updates one of them.

    **Structural, not a string match** (corrected in GLASS X4). The first
    version forbade the *substring* ``BlastRadius`` anywhere under
    ``twin/``, which cannot tell "defines its own" from "imports SEGA's" —
    so the first module to do exactly what the rule demands, `import
    BlastRadiusError from evolution`, failed it. The guarantee is about
    **definitions**, so the test now reads definitions. Verified still to
    fire: adding ``class BlastRadiusLimits`` under ``twin/`` fails it.
    """
    import ast
    import pathlib

    twin = pathlib.Path(__file__).resolve().parents[2] / "src" / "ai" / "twin"
    forbidden_defs = {"CanaryThresholds", "assess"}
    for path in twin.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in forbidden_defs, (
                    f"{path.name} defines its own {node.name!r} — "
                    "TWIN must call SEGA's")
                assert "BlastRadius" not in node.name, (
                    f"{path.name} defines its own {node.name!r} — "
                    "the blast-radius limits live in SEGA and only in SEGA")


# ── T11: simulated people ────────────────────────────────────────────


def test_a_simulated_counterparty_says_so_in_its_record() -> None:
    record = build_counterparty(uuid.uuid4(), 0).as_record()
    assert record[SIMULATED_MARKER] is True
    assert is_simulated(record)
    # And in the name, for a human skimming a result.
    assert "[simulated]" in record["name"]


def test_the_same_scenario_faces_the_same_cast() -> None:
    """Two runs that differ only because the imaginary customers were re-rolled
    are not comparable, and comparability is most of what this is for."""
    scenario = uuid.uuid4()
    assert build_counterparty(scenario, 0) == build_counterparty(scenario, 0)


def test_different_scenarios_get_different_people() -> None:
    assert build_counterparty(uuid.uuid4(), 0) != build_counterparty(uuid.uuid4(), 0)


def test_a_real_record_is_not_simulated() -> None:
    assert not is_simulated({"name": "Acme Ltd"})
    assert not is_simulated(None)


def test_disclosure_is_added_to_the_result() -> None:
    disclosed = disclose({"revenue": 100}, 4)
    assert disclosed["simulated_counterparties"] == 4
    assert "not real" in disclosed["simulated_counterparties_note"]


def test_disclosure_does_not_mutate_the_callers_result() -> None:
    original = {"revenue": 100}
    disclose(original, 4)
    assert original == {"revenue": 100}


def test_no_disclosure_when_nobody_was_simulated() -> None:
    assert "simulated_counterparties" not in disclose({"revenue": 100}, 0)
