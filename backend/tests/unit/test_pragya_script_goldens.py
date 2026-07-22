"""The stage-script regression gate (Inc-4 PRAGYA-RT T7).

Grades *behavioural properties* of a transcript, never its wording — the same
move RETR made when it graded rankings instead of text. Each check enforces a
line from a script Rahul reviewed, so a failure points at reviewed prose rather
than at a model's phrasing.

The load-bearing test in this file is
``test_every_check_is_proven_to_fail_on_a_violating_transcript``. A checker
never observed to fail is a function that returns ``True``, and you discover
that the day it should have caught something.

**What this does not do:** it tests adherence, not quality. A transcript can
pass everything here and still be a poor conversation. Only reading real
transcripts tells you that — see Inc-4 §9.
"""
from __future__ import annotations

import pytest

from tests.eval.pragya_behaviour import (
    CHECKS,
    Turn,
    checks_for_stage,
    pragya_text,
    run_checks,
)
from tests.eval.pragya_corpus import COMPLIANT, VIOLATIONS


# --- the checks are wired to reviewed prose ----------------------------------

def test_every_check_names_the_script_line_it_enforces() -> None:
    """A failure must point at reviewed prose, not at a regex."""
    for check in CHECKS:
        assert check.enforces.strip(), check.name
        assert check.name.strip()


def test_check_names_are_unique() -> None:
    names = [c.name for c in CHECKS]
    assert len(names) == len(set(names))


def test_global_checks_apply_to_every_stage() -> None:
    """Standing rules hold on every channel and in every stage."""
    globals_ = {c.name for c in CHECKS if not c.stages}
    assert "never_collects_approval_in_chat" in globals_
    assert "no_false_completion" in globals_
    for stage in range(1, 10):
        applied = {c.name for c in checks_for_stage(stage)}
        assert globals_ <= applied, stage


# --- the compliant corpus passes ---------------------------------------------

@pytest.mark.parametrize("stage", sorted(COMPLIANT))
def test_a_well_run_stage_passes_every_check(stage: int) -> None:
    failures = [r for r in run_checks(stage, COMPLIANT[stage]) if not r.passed]
    assert not failures, [(f.check, f.detail) for f in failures]


# --- the checks actually fire ------------------------------------------------

def test_every_check_has_a_violating_fixture() -> None:
    """Total mapping: a check with no negative fixture is unproven."""
    assert {c.name for c in CHECKS} == set(VIOLATIONS)


@pytest.mark.parametrize("check_name", sorted(VIOLATIONS))
def test_every_check_is_proven_to_fail_on_a_violating_transcript(
    check_name: str,
) -> None:
    """The load-bearing test. Each fixture must break its own check."""
    stage, transcript = VIOLATIONS[check_name]
    results = {r.check: r for r in run_checks(stage, transcript)}
    assert check_name in results, f"{check_name} did not apply at stage {stage}"
    assert not results[check_name].passed, (
        f"{check_name} passed a transcript written to violate it")
    assert results[check_name].detail.strip(), "a failure must explain itself"


@pytest.mark.parametrize("check_name", sorted(VIOLATIONS))
def test_a_violating_fixture_breaks_only_its_own_check(check_name: str) -> None:
    """Keeps the fixtures honest: a transcript that fails three checks proves
    none of them specifically."""
    stage, transcript = VIOLATIONS[check_name]
    failed = {r.check for r in run_checks(stage, transcript) if not r.passed}
    assert failed == {check_name}, f"also failed {failed - {check_name}}"


# --- the specific properties, spelled out ------------------------------------

def test_stage_one_may_not_ask_what_research_answers() -> None:
    """The defining constraint of stage 1 — if she asks, the reading was
    pointless."""
    asked = [Turn("pragya", "What do you sell, and who are your customers?")]
    result = {r.check: r for r in run_checks(1, asked)}
    assert not result["no_researchable_questions"].passed


def test_an_unnumbered_hypothesis_fails_stage_two() -> None:
    """Numbering is what lets an owner say 'wrong on 4 and 7' in five seconds."""
    prose = [Turn("pragya", "I'm fairly sure you run on referrals and quote personally.")]
    result = {r.check: r for r in run_checks(2, prose)}
    assert not result["assumptions_are_reviewable"].passed
    assert "numbered" in result["assumptions_are_reviewable"].detail


def test_an_unhedged_hypothesis_fails_stage_two() -> None:
    """An assumption with no confidence marker reads as a fact."""
    flat = [Turn("pragya", "1. You run on referrals.\n2. You quote personally.")]
    result = {r.check: r for r in run_checks(2, flat)}
    assert not result["assumptions_are_reviewable"].passed
    assert "confidence" in result["assumptions_are_reviewable"].detail


def test_the_checks_grade_pragya_not_the_owner() -> None:
    """An owner may say anything; only Pragya's half is under test."""
    owner_said_it = [
        Turn("user", "Shall I approve it? Just say yes and I'll push it through."),
        Turn("pragya", "That one goes to the Judgment Desk — I've raised it there."),
    ]
    failures = [r for r in run_checks(9, owner_said_it) if not r.passed]
    assert not failures


def test_pragya_text_excludes_the_owner() -> None:
    text = pragya_text([Turn("user", "SECRET"), Turn("pragya", "hello")])
    assert "secret" not in text
    assert "hello" in text
