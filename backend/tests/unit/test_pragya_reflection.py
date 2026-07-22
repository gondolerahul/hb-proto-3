"""Stage-completion reflection (Inc-4 PRAGYA-RT T6).

Inc 3 tried to reflect on a *call* using the task loop's ``Reflector`` — which
takes an ``AgentState`` and an ``Observation``, shapes that describe a task
step. A conversation is not a task step, and a call is an arbitrary slice of a
relationship. Reflection belongs at the stage boundary.
"""
from __future__ import annotations

from src.ai.pragya.reflection import (
    REFLECTION_KEY_PREFIX,
    REFLECTION_SCHEMA,
    StageReflection,
    parse_reflection,
    reflection_key,
    reflection_prompt,
)
from src.ai.pragya.scripts import DISCOVERY_SCRIPTS
from src.ai.pragya.stages import Stage


def test_reflection_keys_are_namespaced_away_from_script_artifacts() -> None:
    """A reflection must never collide with a key a stage script declares."""
    keys = {reflection_key(s) for s in Stage}
    declared = {k for s in DISCOVERY_SCRIPTS.values() for k in s.artifacts}
    assert not keys & declared
    assert all(k.startswith(REFLECTION_KEY_PREFIX) for k in keys)


def test_only_learned_is_required() -> None:
    """Forcing 'surprised' would make manufacturing a surprise the compliant
    answer, and an invented contradiction gets acted on."""
    assert REFLECTION_SCHEMA["parameters"]["required"] == ["learned"]


def test_an_empty_reflection_is_not_recorded() -> None:
    """Writing a contentless reflection would make a stage look reflected-upon
    when it was not."""
    assert parse_reflection(Stage.BASELINE, {"learned": "   "}) is None
    assert parse_reflection(Stage.BASELINE, {}) is None
    assert parse_reflection(Stage.BASELINE, None) is None


def test_a_reflection_round_trips() -> None:
    result = parse_reflection(Stage.ASSUMPTIONS, {
        "learned": "quotes above 2L are approved by the founder personally",
        "surprised": "the CRM is not actually used",
        "still_open": ["who approves below 2L", ""],
        "confidence": "high",
    })
    assert result is not None
    assert result.stage == 2
    assert "founder personally" in result.learned
    assert result.still_open == ("who approves below 2L",)   # blanks dropped
    assert result.confidence == "high"
    assert result.as_dict()["at"]


def test_an_invalid_confidence_falls_back_rather_than_raising() -> None:
    result = parse_reflection(Stage.BASELINE, {
        "learned": "x", "confidence": "extremely"})
    assert result is not None
    assert result.confidence == "moderate"


def test_a_malformed_still_open_does_not_break_the_reflection() -> None:
    result = parse_reflection(Stage.BASELINE, {
        "learned": "x", "still_open": "not a list"})
    assert result is not None
    assert result.still_open == ()


def test_the_prompt_asks_for_contradictions_and_forbids_inventing_them() -> None:
    """The most valuable thing a stage produces, and the easiest to lose."""
    prompt = reflection_prompt(Stage.ANALYSIS)
    assert "contradicted" in prompt
    assert "Do not manufacture" in prompt


def test_the_prompt_demands_specificity() -> None:
    prompt = reflection_prompt(Stage.ASSUMPTIONS)
    assert "worthless" in prompt


def test_confidence_describes_support_not_tone() -> None:
    prompt = reflection_prompt(Stage.BASELINE)
    assert "not how assured you want to sound" in prompt


def test_as_dict_is_json_safe() -> None:
    import json

    reflection = StageReflection(stage=1, learned="x", still_open=("a", "b"))
    assert json.loads(json.dumps(reflection.as_dict()))["still_open"] == ["a", "b"]
