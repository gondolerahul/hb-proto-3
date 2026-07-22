"""Pragya's capability surface (Inc-4 PRAGYA-RT T9, decision 6).

She proposes no raw tools. Her surface is her **child entities**, so a
capability is an entity with its own autonomy, bands and SoD — not an entry on
a tool allowlist that carries none of that.
"""
from __future__ import annotations

import uuid

from src.ai.pragya.children import (
    CALL_CHILD_TOOL,
    ChildCapability,
    child_schemas,
    resolve_child,
    schema_name_for_child,
)


class _Entity:
    def __init__(self, name, display_name=None, description=None, goal=None):
        self.id = uuid.uuid4()
        self.name = name
        self.display_name = display_name
        self.description = description
        self.goal = goal


def _child(handle: str) -> ChildCapability:
    return ChildCapability(
        entity_id=uuid.uuid4(), handle=handle,
        display_name=handle.replace("_", " ").title(),
        description="does a thing")


# --- handles -----------------------------------------------------------------

def test_handles_are_model_safe() -> None:
    entity = _Entity("Meta-Agent Board (v2)!")
    handle = schema_name_for_child(entity)
    assert handle == "meta_agent_board_v2"


def test_a_handle_never_ends_in_separator_noise() -> None:
    assert not schema_name_for_child(_Entity("---weird---")).endswith("_")


# --- the schema --------------------------------------------------------------

def test_no_children_means_no_capability_tool() -> None:
    """Handing her a tool she cannot use invites proposing a colleague that
    does not exist."""
    assert child_schemas([]) == []


def test_the_schema_is_one_tool_over_an_enum_of_colleagues() -> None:
    """One tool with an enum, not one tool per child — the enum is what makes
    naming a non-existent colleague impossible at the schema level rather than
    something to validate afterwards."""
    schemas = child_schemas([_child("meta_agent"), _child("deep_research")])
    assert len(schemas) == 1
    schema = schemas[0]
    assert schema["name"] == CALL_CHILD_TOOL
    enum = schema["parameters"]["properties"]["colleague"]["enum"]
    assert enum == ["meta_agent", "deep_research"]


def test_the_schema_demands_a_task_and_a_subject() -> None:
    """The subject is what she reports back with; without it a closed loop
    cannot name what it closed."""
    schema = child_schemas([_child("meta_agent")])[0]
    assert set(schema["parameters"]["required"]) == {"colleague", "task", "subject"}


def test_the_description_tells_her_not_to_imply_completion() -> None:
    """Delegated work is underway, not done — the same rule VOICE enforces."""
    schema = child_schemas([_child("meta_agent")])[0]
    assert "background" in schema["description"]
    assert "rather than implying it is finished" in schema["description"]


def test_each_colleague_is_described_so_she_can_choose() -> None:
    schema = child_schemas([_child("deep_research")])[0]
    described = schema["parameters"]["properties"]["colleague"]["description"]
    assert "deep_research" in described
    assert "does a thing" in described


# --- resolution --------------------------------------------------------------

def test_a_known_handle_resolves() -> None:
    children = [_child("meta_agent"), _child("deep_research")]
    resolved = resolve_child(children, "deep_research")
    assert resolved is not None and resolved.handle == "deep_research"


def test_an_unknown_handle_resolves_to_nothing() -> None:
    """Handing work to a plausible-looking wrong entity is worse than handing
    it to none, so there is no nearest-match fallback."""
    children = [_child("meta_agent")]
    assert resolve_child(children, "meta_agnet") is None
    assert resolve_child(children, "") is None
