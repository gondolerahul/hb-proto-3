"""Structural invariants for the stage 1–5 scripts (Inc-3 PRAGYA T4).

These do not judge script *quality* — that is Rahul's review checkpoint
(decision 3), and no test can stand in for it. What they pin is the structure
that makes the scripts reviewable in the first place, so a later edit cannot
quietly add an unjustified question or drop a guardrail.
"""
from __future__ import annotations

import pytest

from src.ai.pragya.scripts import (
    DISCOVERY_SCRIPTS,
    GLOBAL_GUARDRAILS,
    script_for_stage,
)

ALL_SCRIPTS = [DISCOVERY_SCRIPTS[s] for s in sorted(DISCOVERY_SCRIPTS)]


def test_exactly_the_five_discovery_stages_are_scripted() -> None:
    """Stages 6-9 are mechanical and unscripted by design."""
    assert sorted(DISCOVERY_SCRIPTS) == [1, 2, 3, 4, 5]
    for stage in (6, 7, 8, 9):
        assert script_for_stage(stage) is None


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda s: s.name)
def test_every_question_justifies_itself(script) -> None:
    """A question that cannot say why it earns the owner's attention is one
    that should be struck — the ``why`` field is what makes that reviewable."""
    for question in script.questions:
        assert question.ask.strip(), script.name
        assert question.why.strip(), f"{script.name}: {question.ask}"
        # skip_if is required, not optional: it is the machine-checkable half
        # of "never ask what you already know".
        assert question.skip_if.strip(), f"{script.name}: {question.ask}"


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda s: s.name)
def test_every_stage_declares_its_contract(script) -> None:
    assert script.goal.strip()
    assert script.entry_condition.strip()
    assert script.system_prompt.strip()
    assert script.must_cover, f"{script.name} resolves nothing"
    assert script.exit_criteria, f"{script.name} can never close"
    assert script.artifacts, f"{script.name} records nothing for later stages"
    assert script.handoff.strip(), f"{script.name} does not hand off"


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda s: s.name)
def test_rendered_prompt_carries_every_global_guardrail(script) -> None:
    """Guardrails are assembled at render time so a change to the global set
    cannot be silently missed by four of the five stages."""
    rendered = script.render_prompt()
    for guardrail in GLOBAL_GUARDRAILS:
        assert guardrail in rendered, f"{script.name} dropped a global guardrail"
    for item in script.must_cover:
        assert item in rendered


def test_the_no_fabricated_numbers_rule_is_global() -> None:
    """C6's honest-absence rule is the one Pragya is most tempted to break,
    because a plausible number always reads better than 'not yet measurable'."""
    joined = " ".join(GLOBAL_GUARDRAILS).lower()
    assert "never state a number you have not computed" in joined
    assert "missing" in joined


def test_pragya_cannot_take_her_own_approvals() -> None:
    """AUTH standing rule 2 — approvals route to the Judgment Desk, never back
    over the channel that asked."""
    joined = " ".join(GLOBAL_GUARDRAILS).lower()
    assert "judgment desk" in joined
    assert "never collect an approval in chat" in joined


def test_stage_1_forbids_asking_what_research_could_answer() -> None:
    """The defining constraint of stage 1 (functional §4.3)."""
    rendered = DISCOVERY_SCRIPTS[1].render_prompt().lower()
    assert "do not ask the owner anything the public record could have told you" in rendered


def test_stage_2_states_assumptions_as_assumptions() -> None:
    script = DISCOVERY_SCRIPTS[2]
    assert any("evidence" in g.lower() for g in script.guardrails)
    assert any("confidence" in item.lower() or "load-bearing" in item.lower()
               for item in script.exit_criteria)


def test_stage_4_keeps_still_open_as_a_first_class_verdict() -> None:
    """The stage exists to surface open questions rather than guess at them."""
    script = DISCOVERY_SCRIPTS[4]
    assert "still open" in script.system_prompt.lower()
    assert any("guess" in g.lower() for g in script.guardrails)


def test_stage_5_proposes_options_rather_than_a_single_recommendation() -> None:
    """The owner decides; a single option is a decision made on their behalf."""
    script = DISCOVERY_SCRIPTS[5]
    assert any("single option" in g.lower() for g in script.guardrails)
    assert any("cannot compute" in g.lower() or "not yet measurable" in g.lower()
               for g in script.guardrails)


def test_stage_5_captures_the_governance_boundary() -> None:
    """Stage 6 configures HITL checkpoints from this answer, so it must exist."""
    script = DISCOVERY_SCRIPTS[5]
    assert any("stop and ask you" in q.ask.lower() for q in script.questions)
    assert any("governance" in c.lower() for c in script.exit_criteria)
