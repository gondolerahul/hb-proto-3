"""strategy/pipeline.py — the five steps as pure transitions (STRAT T4).

Every rule here is a predicate over data, testable without a database, and the
module is deliberately the only place that knows what a legal move is. The
record service enforces *who* may write; this enforces *what* a write may say.

Three rules are load-bearing rather than tidy:

* **A Proposition is adopted only from `tabled`.** Adopting straight from
  `draft` skips the step where a human read it, which is the only step that
  makes a Resolution mean anything.
* **A Mandate issues only from an `active` Resolution.** A revoked decision
  must not still be handing out work — and the failure would be quiet, because
  the mandate looks exactly like a legitimate one.
* **A non-`untested` `honesty_grade` requires a `twin_run_id`** (04a §8.5). A
  human typing `replay` into a proposition that never went near the Glasshouse
  would launder an untested bet into the strongest grade the system has. The
  rule in one line: *a grade must have a run behind it.*
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

__all__ = [
    "PLANNING_OBJECTS",
    "TransitionError",
    "Verdict",
    "PROPOSITION_STATUSES",
    "RESOLUTION_STATUSES",
    "MANDATE_STATUSES",
    "check_transition",
    "check_honesty_grade",
    "may_adopt",
    "may_issue_mandate",
    "validate_write",
]

#: The eight objects this module governs. A totality test asserts this matches
#: the Planning objects actually in the spine, so an object added later without
#: a transition table fails CI rather than shipping ungoverned.
PLANNING_OBJECTS: frozenset[str] = frozenset({
    "Objective", "Target", "Forecast", "Minutes",
    "Proposition", "Resolution", "Mandate", "Review",
})

#: Grades that assert a simulation happened. `untested` does not, which is why
#: it is the only one that needs no run behind it.
_GRADES_NEEDING_A_RUN: frozenset[str] = frozenset({"replay", "forecast", "unknown"})
UNTESTED = "untested"


class TransitionError(ValueError):
    """An illegal move. Carries the reason in words a surface can render."""


@dataclass(frozen=True)
class Verdict:
    """Allowed or not, and why. Never a bare bool — the reason is the product."""

    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


def _allowed(reason: str = "") -> Verdict:
    return Verdict(True, reason)


def _refused(reason: str) -> Verdict:
    return Verdict(False, reason)


# ── Transition tables ───────────────────────────────────────────────────────
# Terminal states map to an empty set rather than being absent, so "no legal
# move from here" and "this object has no table" stay distinguishable.

PROPOSITION_STATUSES: dict[str, frozenset[str]] = {
    "draft": frozenset({"tabled", "withdrawn"}),
    # Adoption leaves this step, and only from `tabled` — see the docstring.
    "tabled": frozenset({"adopted", "rejected", "withdrawn"}),
    "adopted": frozenset(),
    "rejected": frozenset({"tabled"}),   # reconsideration is legitimate
    "withdrawn": frozenset({"draft"}),   # so is picking it back up
}

RESOLUTION_STATUSES: dict[str, frozenset[str]] = {
    "active": frozenset({"superseded", "revoked"}),
    "superseded": frozenset(),
    # Deliberately terminal. A revoked decision that can be quietly reactivated
    # is a decision with no audit trail; the honest move is a new Resolution.
    "revoked": frozenset(),
}

MANDATE_STATUSES: dict[str, frozenset[str]] = {
    "issued": frozenset({"in_flight", "closed"}),
    "in_flight": frozenset({"reviewed", "closed"}),
    "reviewed": frozenset({"closed", "in_flight"}),
    "closed": frozenset(),
}

OBJECTIVE_STATUSES: dict[str, frozenset[str]] = {
    "draft": frozenset({"active", "abandoned"}),
    "active": frozenset({"achieved", "abandoned"}),
    "achieved": frozenset(),
    "abandoned": frozenset({"active"}),  # a dropped objective can be revived
}

TARGET_STATUSES: dict[str, frozenset[str]] = {
    "open": frozenset({"met", "missed", "withdrawn"}),
    "met": frozenset(),
    "missed": frozenset({"open"}),
    "withdrawn": frozenset({"open"}),
}

_TABLES: dict[str, dict[str, frozenset[str]]] = {
    "Proposition": PROPOSITION_STATUSES,
    "Resolution": RESOLUTION_STATUSES,
    "Mandate": MANDATE_STATUSES,
    "Objective": OBJECTIVE_STATUSES,
    "Target": TARGET_STATUSES,
}


def check_transition(
    object_name: str, current: Optional[str], proposed: Optional[str],
) -> Verdict:
    """Is `current → proposed` a legal move for this object?

    Objects with no status field (Minutes, Forecast, Review) have no table and
    are unconstrained — returning "allowed" rather than raising, because a
    caller should not need to know which objects have lifecycles.
    """
    table = _TABLES.get(object_name)
    if table is None or proposed is None:
        return _allowed()
    if current is None:
        # A create. Any declared status is a legal starting point; an undeclared
        # one is not, which is what stops a typo from inventing a state.
        if proposed in table:
            return _allowed()
        return _refused(
            f"{proposed!r} is not a {object_name} status "
            f"(expected one of {sorted(table)})")
    if current == proposed:
        return _allowed()
    if current not in table:
        return _refused(f"{current!r} is not a {object_name} status")
    if proposed not in table[current]:
        legal = sorted(table[current])
        return _refused(
            f"a {object_name} cannot go {current} → {proposed}"
            + (f" (legal: {legal})" if legal else f" — {current} is terminal"))
    return _allowed()


def check_honesty_grade(
    grade: Optional[str], twin_run_id: Optional[str],
) -> Verdict:
    """A grade must have a run behind it (04a §8.5).

    `untested` and an absent grade are free. Anything asserting a simulation
    happened must name the run, so a track record cannot be made to look better
    than it was by typing into a form.
    """
    if not grade or grade == UNTESTED:
        return _allowed()
    if grade not in _GRADES_NEEDING_A_RUN:
        return _refused(
            f"{grade!r} is not an honesty grade "
            f"(expected {sorted(_GRADES_NEEDING_A_RUN | {UNTESTED})})")
    if not twin_run_id:
        return _refused(
            f"honesty_grade {grade!r} needs a twin_run_id — a grade must have "
            "a run behind it; use 'untested' where none was made")
    return _allowed()


def may_adopt(proposition: Mapping[str, Any]) -> Verdict:
    """A Proposition may become a Resolution only from `tabled`."""
    status = proposition.get("status")
    if status == "tabled":
        return _allowed()
    if status == "adopted":
        return _refused("this proposition has already been adopted")
    return _refused(
        f"a proposition is adopted from 'tabled', not {status!r} — table it "
        "first so somebody reads it")


def may_issue_mandate(resolution: Mapping[str, Any]) -> Verdict:
    """A Mandate issues only from an `active` Resolution.

    The refusal that matters is `revoked`: a revoked decision still handing out
    work fails *quietly*, because the mandate it produces looks exactly like a
    legitimate one.
    """
    status = resolution.get("status")
    if status == "active":
        return _allowed()
    return _refused(
        f"mandates issue from an active resolution, and this one is {status!r}")


def validate_write(
    object_name: str, data: Mapping[str, Any], *,
    current: Optional[Mapping[str, Any]] = None,
) -> Verdict:
    """Every pipeline rule that applies to one write, in one call.

    The single entry point the record path uses, so a new rule lands here and
    is enforced everywhere rather than at whichever call site remembered it.
    """
    if object_name not in PLANNING_OBJECTS:
        return _allowed()

    if "status" in data:
        verdict = check_transition(
            object_name,
            (current or {}).get("status") if current is not None else None,
            data.get("status"))
        if not verdict:
            return verdict

    if object_name == "Proposition" and "honesty_grade" in data:
        # The run id may be unchanged and therefore absent from the delta, so
        # fall back to what the record already carries — otherwise a write
        # touching only the grade could never satisfy the rule.
        run_id = data.get("twin_run_id")
        if run_id is None and current is not None:
            run_id = current.get("twin_run_id")
        verdict = check_honesty_grade(data.get("honesty_grade"), run_id)
        if not verdict:
            return verdict

    return _allowed()
