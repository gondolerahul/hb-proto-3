"""Increment 6 / TWIN T4 — honesty grading (L6).

Two properties carry the whole of L6, and both are tested by trying to break
them rather than by asserting the happy path:

1. **No input path accepts a grade.** Asserted structurally, over the module
   and the router, so adding an override later fails here.
2. **A mixed result takes the worst grade of its inputs.** Averaging or taking
   the best would let a strong half launder a weak one.
"""
from __future__ import annotations

import inspect

import pytest

from src.ai.twin.grading import (
    GRADE_DESCRIPTIONS,
    GRADE_ORDER,
    Grade,
    GradeInputs,
    comparable,
    grade,
    worst_of,
)


# ── The grade is computed from what the run actually had ─────────────


def test_real_history_earns_replay() -> None:
    assert grade(GradeInputs(replayed_signals=63)) == Grade.REPLAY


def test_a_long_enough_series_earns_forecast() -> None:
    assert grade(GradeInputs(series_points=14, min_series_points=8)) == Grade.FORECAST


def test_a_short_series_is_unknown_not_a_weak_forecast() -> None:
    """§5.3: refused outright rather than returned with an interval nobody
    reads. A forecast the day after LEARN ships is `unknown`, and it should be."""
    assert grade(GradeInputs(series_points=3, min_series_points=8)) == Grade.UNKNOWN


def test_nothing_at_all_is_unknown() -> None:
    assert grade(GradeInputs()) == Grade.UNKNOWN


def test_replay_beats_forecast_when_both_are_present() -> None:
    """Real events that happened outrank a projection about events that did
    not."""
    assert grade(GradeInputs(replayed_signals=10, series_points=90)) == Grade.REPLAY


def test_an_unobserved_lever_disqualifies_everything() -> None:
    """Replaying real history through a change nothing in that history reflects
    tells you about the history, not about the change — so a pricing move to a
    point the business has never charged cannot be graded `replay`."""
    assert grade(GradeInputs(replayed_signals=500, unobserved_levers=True)) == (
        Grade.UNKNOWN)


def test_a_stubbed_code_path_cannot_be_a_replay() -> None:
    """`replay` promises the code path was the real one. If it was not, the
    grade must not say it was."""
    assert grade(GradeInputs(replayed_signals=500, real_code_path=False)) == (
        Grade.UNKNOWN)


def test_grade_is_total() -> None:
    """It is read by a surface that has no fallback rendering."""
    for signals in (0, 1, 1000):
        for points in (0, 7, 8, 900):
            for unobserved in (True, False):
                for real in (True, False):
                    result = grade(GradeInputs(
                        replayed_signals=signals, series_points=points,
                        unobserved_levers=unobserved, real_code_path=real))
                    assert result in GRADE_ORDER


# ── No API accepts a grade (§5.4) ────────────────────────────────────


def test_no_function_in_this_module_takes_a_grade_argument() -> None:
    """L6 says the honesty layer is never softened. The cheapest guarantee is
    to give nobody a way to soften it, so this asserts the absence rather than
    trusting it."""
    import src.ai.twin.grading as grading

    for name, fn in vars(grading).items():
        if not inspect.isfunction(fn) or name.startswith("_"):
            continue
        params = set(inspect.signature(fn).parameters)
        # `worst_of` and `comparable` take grades to *combine*, which is not
        # the same as being told what a run's grade was.
        if name in {"worst_of", "comparable"}:
            continue
        assert "grade" not in params, f"{name} accepts a grade"
        assert "override" not in params, f"{name} accepts an override"


def test_no_router_request_model_carries_a_grade() -> None:
    """The structural half of the same guarantee, on the HTTP surface."""
    import src.ai.twin.api as api
    from pydantic import BaseModel

    for name, obj in vars(api).items():
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            assert "grade" not in obj.model_fields, (
                f"{name} would let a caller supply a grade")


def test_every_grade_has_a_description_the_surface_can_render() -> None:
    """§5.2 says the caveat lives in three places. This is the third — and if
    a grade had no description the surface would show a bare word."""
    for name in GRADE_ORDER:
        assert GRADE_DESCRIPTIONS.get(name), name


def test_replays_description_denies_determinism() -> None:
    """The most likely way this feature misleads someone is a user hearing
    "replay" as "this is what would happen"."""
    text = GRADE_DESCRIPTIONS[Grade.REPLAY].lower()
    assert "does not promise" in text
    assert "recur" in text or "twice" in text


# ── Worst-of, the monotone rule ──────────────────────────────────────


@pytest.mark.parametrize(
    "grades,expected",
    [
        ([Grade.REPLAY, Grade.REPLAY], Grade.REPLAY),
        ([Grade.REPLAY, Grade.FORECAST], Grade.FORECAST),
        ([Grade.REPLAY, Grade.UNKNOWN], Grade.UNKNOWN),
        ([Grade.FORECAST, Grade.UNKNOWN], Grade.UNKNOWN),
        ([Grade.FORECAST], Grade.FORECAST),
    ],
)
def test_a_mixed_result_takes_the_worst_grade(grades, expected) -> None:
    """A replayed scenario compared against a forecast baseline is a *forecast*
    result. Taking the best would let a strong half launder a weak one."""
    assert worst_of(grades) == expected


def test_nothing_measured_is_unknown() -> None:
    assert worst_of([]) == Grade.UNKNOWN


def test_an_unrecognised_grade_ranks_at_the_bottom() -> None:
    """Fail toward caution: a grade this code does not understand must not
    out-rank one it does."""
    assert worst_of([Grade.REPLAY, "excellent"]) == Grade.UNKNOWN


# ── Comparability (§9's tournament rule) ─────────────────────────────


def test_like_grades_are_rankable() -> None:
    assert comparable(Grade.REPLAY, Grade.REPLAY)


def test_unlike_grades_are_not() -> None:
    """Ranking a forecast above a replay because its number was bigger is the
    failure mode L6 exists to prevent."""
    assert not comparable(Grade.REPLAY, Grade.FORECAST)
    assert not comparable(Grade.FORECAST, Grade.UNKNOWN)
