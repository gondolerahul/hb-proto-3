"""twin/grading.py — how much a Glasshouse result should be believed (TWIN T4, L6).

Three grades that mean three different things:

======== ============================================================
`replay`   Real historical inputs, the real code path, isolated writes
`forecast` A projection from a measured series, by a stated method
`unknown`  Neither — no history, no series, or a lever outside anything
           we have observed
======== ============================================================

**What `replay` does not promise.** Replay is *not* determinism. The same
signal re-run through the same agent with the same model does not produce the
same tokens, and any grade implying it would be a lie the platform tells about
itself. `replay` promises exactly this: *the inputs were real events that
actually happened, the code path was the real one, and the writes went
nowhere.* It does not promise the output would recur.

That sentence is in the design, in this docstring, and in
:data:`GRADE_DESCRIPTIONS` — which is what the surface renders. If it lived
only in the design, the surface would eventually claim more than the engine can
support.

**The grade is computed, never supplied** (§5.4). There is no parameter, no
admin setting and no override anywhere in this module or in `twin.api`. L6 says
the honesty layer is never softened; the cheapest way to guarantee that is to
give nobody a way to soften it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

__all__ = [
    "Grade",
    "GRADE_ORDER",
    "GRADE_DESCRIPTIONS",
    "GradeInputs",
    "grade",
    "worst_of",
    "comparable",
]


class Grade:
    REPLAY = "replay"
    FORECAST = "forecast"
    UNKNOWN = "unknown"


#: Weakest first. The ordering is the whole of :func:`worst_of` — the same
#: monotone discipline SEGA's taint ladder uses, and for the same reason: a
#: result is only as trustworthy as the least trustworthy thing that went into
#: it.
GRADE_ORDER: tuple[str, ...] = (Grade.UNKNOWN, Grade.FORECAST, Grade.REPLAY)

_RANK = {name: index for index, name in enumerate(GRADE_ORDER)}

#: Rendered next to the number, wherever the number appears. The `replay`
#: string is deliberately about what it does *not* promise.
GRADE_DESCRIPTIONS: dict[str, str] = {
    Grade.REPLAY: (
        "Replayed real events that actually happened, through the real code "
        "path, with every write isolated. This does not promise the same "
        "result would recur — the same inputs through the same model do not "
        "produce the same words twice."
    ),
    Grade.FORECAST: (
        "Projected from a measured series by a stated method, with an "
        "interval. A projection is an argument about the future, not a "
        "measurement of it."
    ),
    Grade.UNKNOWN: (
        "Neither replayed nor projected — there was no history to replay, no "
        "long-enough series to project from, or the change is outside "
        "anything we have observed. Treat the number as an illustration."
    ),
}


@dataclass(frozen=True)
class GradeInputs:
    """What a run actually had. Every field is a fact the engine observed.

    Deliberately not "what the caller wants the grade to be": there is no field
    here a caller could set to buy a better grade, because every one of them is
    a count or a flag the engine fills in from its own execution.
    """

    #: Real historical signals replayed. Zero means there was nothing to replay.
    replayed_signals: int = 0
    #: Daily KPI points the forecast drew on.
    series_points: int = 0
    #: The floor below which a forecast is refused (settings.TWIN_MIN_SERIES_POINTS).
    min_series_points: int = 8
    #: True when the code path executed was the shipped one rather than a stub.
    real_code_path: bool = True
    #: True when at least one lever has no observed analogue — a pricing move
    #: to a point the business has never charged, a channel it has never used.
    unobserved_levers: bool = False


def grade(inputs: GradeInputs) -> str:
    """The grade a run earned. Pure and total.

    Order matters and is the honest one: an unobserved lever disqualifies
    everything, because replaying real history through a change nothing in that
    history reflects tells you about the history, not about the change.
    """
    if inputs.unobserved_levers or not inputs.real_code_path:
        return Grade.UNKNOWN
    if inputs.replayed_signals > 0:
        return Grade.REPLAY
    if inputs.series_points >= max(inputs.min_series_points, 1):
        return Grade.FORECAST
    return Grade.UNKNOWN


def worst_of(grades: Iterable[str]) -> str:
    """The weakest grade among its inputs (§5.4).

    A comparison of a replayed scenario against a forecast baseline is a
    *forecast* result, not a replay one. Averaging or taking the best would let
    a strong half launder a weak one, which is precisely what L6 exists to
    prevent.

    An empty set of inputs is ``unknown``: nothing was measured.
    """
    ranks = [_RANK.get(g, 0) for g in grades]
    if not ranks:
        return Grade.UNKNOWN
    return GRADE_ORDER[min(ranks)]


def comparable(left: str, right: str) -> bool:
    """Whether two results may be ranked against each other (§9).

    **Grades are compared, not averaged.** A tournament mixing a `replay`
    result with an `unknown` one shows both grades on the row and refuses to
    rank across them without the mismatch stated. Ranking a forecast above a
    replay because its number was bigger is the failure mode L6 exists to
    prevent.
    """
    return left == right
