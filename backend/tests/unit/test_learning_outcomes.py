"""LEARN T5 — grading a run, and refusing to grade most of them.

The two pure halves: which endings count as evidence, and how much evidence it
takes before anything is proposed. Both are places where being eager is the
failure mode — a loop that learns from one bad afternoon will rewrite an
agent's charter every time a user is briefly unhappy.

Design: docs/product-road-map/increment-6/01_learn.md §5.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.learning.outcomes import (
    OBSERVATIONS_BEFORE_CANDIDATE,
    Outcome,
    OutcomeKind,
    classify_outcome,
    distil,
)

ENTITY = uuid.uuid4()


def _classify(**kw):
    base = dict(entity_id=ENTITY, run_id=uuid.uuid4(), status="COMPLETED",
                csat_score=None, approval_statuses=())
    return classify_outcome(**{**base, **kw})


# ── what counts as evidence ──────────────────────────────────────────────────

def test_a_clean_run_nobody_rated_teaches_nothing():
    """The common case, and it must stay silent.

    A learning event per run would fill the bus with rows that teach nothing
    and bury the ones that do.
    """
    assert _classify() is None


def test_a_thumbs_down_is_graded():
    outcome = _classify(csat_score=-1)
    assert outcome is not None and outcome.kind is OutcomeKind.CSAT_NEGATIVE


def test_a_thumbs_up_is_graded_too():
    """Learning is not only about failure — "keep doing this" is a finding."""
    outcome = _classify(csat_score=1)
    assert outcome is not None and outcome.kind is OutcomeKind.CSAT_POSITIVE


def test_a_zero_rating_is_not_a_rating():
    """`csat_score` is +1/-1/NULL; a 0 is a caller mistake, not neutral feedback."""
    assert _classify(csat_score=0) is None


def test_a_rejected_approval_is_graded():
    outcome = _classify(approval_statuses=("APPROVED", "REJECTED"))
    assert outcome is not None and outcome.kind is OutcomeKind.APPROVAL_REJECTED


def test_an_approved_card_alone_is_not_evidence():
    """Approval is the *expected* path at A1 — it says the system worked, not
    that the agent did something notable."""
    assert _classify(approval_statuses=("APPROVED",)) is None


def test_a_failed_run_is_the_weakest_evidence_and_still_counts():
    outcome = _classify(status="FAILED")
    assert outcome is not None and outcome.kind is OutcomeKind.RUN_FAILED


def test_an_explicit_human_rating_outranks_an_inferred_one():
    """A person who said "this was good" outranks a machine's inference.

    A run whose card was rejected but which the owner then rated positively is
    graded by the rating: the human had the last word and the most context.
    """
    outcome = _classify(csat_score=1, approval_statuses=("REJECTED",), status="FAILED")
    assert outcome is not None and outcome.kind is OutcomeKind.CSAT_POSITIVE


def test_a_rejection_outranks_a_failure():
    outcome = _classify(status="FAILED", approval_statuses=("REJECTED",))
    assert outcome is not None and outcome.kind is OutcomeKind.APPROVAL_REJECTED


@pytest.mark.parametrize("status", ["completed", "Completed", "PAUSED", None, ""])
def test_non_failure_statuses_grade_nothing_on_their_own(status):
    assert _classify(status=status) is None


# ── how much evidence is enough ──────────────────────────────────────────────

def _outcomes(n: int, kind=OutcomeKind.CSAT_NEGATIVE, entity=ENTITY):
    return [Outcome(entity_id=entity, run_id=uuid.uuid4(), kind=kind) for _ in range(n)]


def test_one_observation_proposes_nothing():
    """One bad run is a bad day. A loop that reacts to it oscillates."""
    assert distil(_outcomes(1)) == []


def test_the_threshold_is_honoured_exactly():
    assert distil(_outcomes(OBSERVATIONS_BEFORE_CANDIDATE - 1)) == []
    assert len(distil(_outcomes(OBSERVATIONS_BEFORE_CANDIDATE))) == 1


def test_a_candidate_carries_its_evidence_count():
    """The count is what the lifecycle and a human reviewer both need."""
    candidate = distil(_outcomes(5))[0]
    assert candidate.observations == 5
    assert "5" in candidate.statement


def test_outcomes_of_different_kinds_do_not_pool():
    """Three failures and three rejections are two findings, not one of six."""
    outcomes = (_outcomes(3, OutcomeKind.RUN_FAILED)
                + _outcomes(3, OutcomeKind.APPROVAL_REJECTED))
    candidates = distil(outcomes)
    assert {c.kind for c in candidates} == {OutcomeKind.RUN_FAILED,
                                            OutcomeKind.APPROVAL_REJECTED}
    assert all(c.observations == 3 for c in candidates)


def test_outcomes_from_different_entities_do_not_pool():
    """Learning is per-colleague. Two agents each failing twice is not a pattern
    about either of them."""
    other = uuid.uuid4()
    outcomes = _outcomes(2) + _outcomes(2, entity=other)
    assert distil(outcomes) == []


def test_distillation_is_deterministic():
    """Same evidence, same proposal — a candidate that reorders between runs
    would look like new learning to anything watching the tree."""
    outcomes = _outcomes(4, OutcomeKind.RUN_FAILED) + _outcomes(4, OutcomeKind.CSAT_NEGATIVE)
    assert distil(outcomes) == distil(list(reversed(outcomes)))


def test_no_candidate_statement_proposes_a_governance_change():
    """§7 — Karuna bounds are constraints, not preferences.

    The vocabulary this loop can propose from is fixed data, and none of it can
    express "widen this agent's authority". T6 adds the *refusal* for a
    proposal that tries; this asserts the producer cannot even phrase one.
    """
    forbidden = ("autonomy", "authority", "band", "consent", "dnc", "approval limit")
    for kind in OutcomeKind:
        statement = distil(_outcomes(3, kind))[0].statement.lower()
        assert not any(word in statement for word in forbidden), (
            f"{kind.value} proposes something governance-shaped")


def test_empty_input_proposes_nothing():
    assert distil([]) == []
