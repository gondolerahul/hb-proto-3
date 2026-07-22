"""Artifact extraction and stage advancement (Inc-4 PRAGYA-RT T3).

Increment 3 left exit criteria as prose the model reads, so nothing advanced.
The design splits that: prose stays prose (instructions to Pragya), declared
artifacts become the machine-checkable half, and two stages may only move on
an explicit owner action because their deliverable *is* the owner's agreement.
"""
from __future__ import annotations

import pytest

from src.ai.pragya.advancement import (
    AUTO_ADVANCE_STAGES,
    CONFIRM_STAGES,
    advancement_prompt,
    evaluate_eligibility,
    needs_owner_confirmation,
)
from src.ai.pragya.artifacts import (
    ARTIFACT_TOOL_NAME,
    artifact_schema_for,
    parse_extraction,
    schema_key,
)
from src.ai.pragya.scripts import DISCOVERY_SCRIPTS, script_for_stage
from src.ai.pragya.stages import Stage


def _complete(stage: Stage, **overrides):
    """Every declared artifact present, primary carrying content."""
    script = script_for_stage(int(stage))
    assert script is not None
    bag = {key: ["something"] for key in script.artifacts}
    bag.update(overrides)
    return bag


# --- the schema is built from the reviewed scripts ---------------------------

def test_every_discovery_stage_has_an_extraction_schema() -> None:
    for stage_num in DISCOVERY_SCRIPTS:
        schema = artifact_schema_for(Stage(stage_num))
        assert schema is not None
        assert schema["name"] == ARTIFACT_TOOL_NAME


def test_the_schema_covers_exactly_the_declared_artifacts() -> None:
    """A script that gains an artifact gains a slot on the same edit."""
    for stage_num, script in DISCOVERY_SCRIPTS.items():
        schema = artifact_schema_for(Stage(stage_num))
        assert schema is not None
        props = set(schema["parameters"]["properties"])
        assert props == {schema_key(k) for k in script.artifacts}


def test_mechanical_stages_have_no_schema() -> None:
    for stage in (Stage.BLUEPRINT, Stage.INTEGRATION, Stage.DEPLOY, Stage.OPERATE):
        assert artifact_schema_for(stage) is None


def test_nothing_is_required_so_the_model_can_honestly_omit() -> None:
    """Forcing every field would make fabrication the compliant answer."""
    schema = artifact_schema_for(Stage.ASSUMPTIONS)
    assert schema is not None
    assert schema["parameters"]["required"] == []


# --- parsing ------------------------------------------------------------------

def test_extraction_maps_back_to_artifact_keys() -> None:
    parsed = parse_extraction(Stage.ASSUMPTIONS, {
        "assumptions__list": ["a1", "a2"],
        "assumptions__struck": [],
    })
    assert parsed["assumptions.list"] == ["a1", "a2"]
    assert parsed["assumptions.struck"] == []


def test_an_invented_key_is_dropped() -> None:
    """State no script declared is state nothing reads."""
    parsed = parse_extraction(Stage.ASSUMPTIONS, {
        "assumptions__list": ["a1"],
        "assumptions__invented": "x",
    })
    assert parsed == {"assumptions.list": ["a1"]}


def test_nulls_are_dropped_rather_than_stored() -> None:
    parsed = parse_extraction(Stage.ASSUMPTIONS, {"assumptions__list": None})
    assert parsed == {}


def test_no_extraction_yields_no_artifacts() -> None:
    assert parse_extraction(Stage.ASSUMPTIONS, None) == {}
    assert parse_extraction(Stage.OPERATE, {"anything": 1}) == {}


# --- eligibility --------------------------------------------------------------

def test_an_empty_engagement_is_not_eligible() -> None:
    result = evaluate_eligibility(Stage.BASELINE, {})
    assert not result.eligible
    assert result.missing


def test_all_artifacts_present_makes_a_gathering_stage_eligible() -> None:
    result = evaluate_eligibility(Stage.BASELINE, _complete(Stage.BASELINE))
    assert result.eligible
    assert not result.needs_confirmation


def test_an_empty_primary_artifact_blocks_advancement() -> None:
    """"My assumptions about this business: none" is not a completed stage.

    The asymmetry with the test below is the point: an empty collection
    answers a secondary artifact and fails a primary one.
    """
    script = script_for_stage(int(Stage.ASSUMPTIONS))
    assert script is not None and script.primary_artifact
    bag = _complete(Stage.ASSUMPTIONS, **{script.primary_artifact: []})
    result = evaluate_eligibility(Stage.ASSUMPTIONS, bag)
    assert not result.eligible
    assert result.primary_empty


def test_an_empty_secondary_artifact_does_not_stall_the_engagement() -> None:
    """`assumptions.struck` is legitimately empty when nothing was struck."""
    bag = _complete(Stage.ASSUMPTIONS, **{"assumptions.struck": []})
    result = evaluate_eligibility(Stage.ASSUMPTIONS, bag)
    assert result.eligible


def test_a_blank_primary_string_is_absence() -> None:
    bag = _complete(Stage.BASELINE, **{"baseline.research_summary": "   "})
    result = evaluate_eligibility(Stage.BASELINE, bag)
    assert not result.eligible
    assert result.primary_empty


def test_mechanical_stages_are_never_eligible_by_artifacts() -> None:
    """Stages 6-9 advance through the wizard APIs, not this predicate."""
    for stage in (Stage.BLUEPRINT, Stage.DEPLOY, Stage.OPERATE):
        result = evaluate_eligibility(stage, {"anything": "x"})
        assert not result.eligible
        assert "mechanical" in result.reason


# --- who may advance ----------------------------------------------------------

def test_the_two_agreement_stages_need_the_owner() -> None:
    assert CONFIRM_STAGES == {Stage.ASSUMPTIONS, Stage.SOLUTION}
    for stage in CONFIRM_STAGES:
        assert needs_owner_confirmation(stage)


def test_gathering_stages_do_not() -> None:
    assert AUTO_ADVANCE_STAGES == {Stage.BASELINE, Stage.INGESTION, Stage.ANALYSIS}
    for stage in AUTO_ADVANCE_STAGES:
        assert not needs_owner_confirmation(stage)


def test_the_two_sets_partition_the_discovery_stages() -> None:
    assert AUTO_ADVANCE_STAGES | CONFIRM_STAGES == {
        Stage.BASELINE, Stage.ASSUMPTIONS, Stage.INGESTION,
        Stage.ANALYSIS, Stage.SOLUTION}
    assert not AUTO_ADVANCE_STAGES & CONFIRM_STAGES


def test_a_complete_confirm_stage_is_eligible_but_waits() -> None:
    result = evaluate_eligibility(Stage.SOLUTION, _complete(Stage.SOLUTION))
    assert result.eligible
    assert result.needs_confirmation


@pytest.mark.parametrize("stage", sorted(CONFIRM_STAGES))
def test_the_confirmation_prompt_asks_rather_than_announces(stage: Stage) -> None:
    """An owner who was not asked has not agreed."""
    prompt = advancement_prompt(stage)
    assert "?" in prompt or "or is there" in prompt or "say so" in prompt
