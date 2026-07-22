"""The nine-stage machine (Inc-3 PRAGYA T1) — pure transition rules.

The flow is linear except for one deliberate loop: stage 9 re-enters stages
4–6, because a business that has been running for three months has new
evidence to test, not a fresh introduction to make.
"""
from __future__ import annotations

import pytest

from src.ai.pragya.stages import (
    DISCOVERY_STAGES,
    REENTERABLE_STAGES,
    STAGE_INFO,
    Stage,
    TransitionError,
    can_advance,
    can_reenter,
    is_discovery,
    next_stage,
    validate_transition,
)


def test_every_stage_has_display_info() -> None:
    assert set(STAGE_INFO) == set(Stage)
    for info in STAGE_INFO.values():
        assert info.name.strip() and info.summary.strip()


def test_stages_one_to_five_are_the_scripted_discovery_half() -> None:
    assert DISCOVERY_STAGES == {Stage.BASELINE, Stage.ASSUMPTIONS,
                                Stage.INGESTION, Stage.ANALYSIS, Stage.SOLUTION}
    for stage in Stage:
        assert is_discovery(stage) == STAGE_INFO[stage].scripted


# --- forward movement ---------------------------------------------------------

def test_advance_walks_exactly_one_stage() -> None:
    for stage in Stage:
        following = next_stage(stage)
        if stage is Stage.OPERATE:
            assert following is None
        else:
            assert following == stage + 1
            assert can_advance(stage, following)


def test_stages_cannot_be_skipped() -> None:
    """Each stage reads what the previous one produced."""
    assert not can_advance(Stage.BASELINE, Stage.INGESTION)
    with pytest.raises(TransitionError, match="skip"):
        validate_transition(Stage.BASELINE, Stage.INGESTION)


def test_operate_has_no_successor() -> None:
    assert next_stage(Stage.OPERATE) is None
    assert not can_advance(Stage.OPERATE, Stage.OPERATE)


# --- re-entry (continuous re-engagement) --------------------------------------

def test_operate_may_re_enter_stages_four_to_six() -> None:
    assert REENTERABLE_STAGES == {Stage.ANALYSIS, Stage.SOLUTION, Stage.BLUEPRINT}
    for target in REENTERABLE_STAGES:
        assert can_reenter(Stage.OPERATE, target)
        validate_transition(Stage.OPERATE, target)


def test_operate_cannot_re_enter_the_introduction_stages() -> None:
    """Re-introducing yourself to a customer of three months is the failure
    this rule exists to prevent."""
    for target in (Stage.BASELINE, Stage.ASSUMPTIONS, Stage.INGESTION):
        assert not can_reenter(Stage.OPERATE, target)
        with pytest.raises(TransitionError, match="re-engagement"):
            validate_transition(Stage.OPERATE, target)


def test_only_operate_may_move_backwards() -> None:
    """Mid-engagement backtracking is not re-engagement — it's a lost thread."""
    assert not can_reenter(Stage.DEPLOY, Stage.ANALYSIS)
    with pytest.raises(TransitionError):
        validate_transition(Stage.DEPLOY, Stage.ANALYSIS)
    with pytest.raises(TransitionError):
        validate_transition(Stage.SOLUTION, Stage.ASSUMPTIONS)


# --- staying put --------------------------------------------------------------

@pytest.mark.parametrize("stage", list(Stage))
def test_staying_in_the_same_stage_is_always_legal(stage: Stage) -> None:
    """A stage is a conversation; most turns do not move it."""
    validate_transition(stage, stage)


def test_a_full_engagement_walks_one_to_nine_then_loops_to_four() -> None:
    stage = Stage.BASELINE
    seen = [stage]
    while (following := next_stage(stage)) is not None:
        validate_transition(stage, following)
        stage = following
        seen.append(stage)

    assert seen == list(Stage)
    assert stage is Stage.OPERATE
    validate_transition(Stage.OPERATE, Stage.ANALYSIS)
