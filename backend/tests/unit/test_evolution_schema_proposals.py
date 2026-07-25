"""SEGA T8 — a field an agent may add, and every shape it may not (§10.2).

The whole subject of this file is **what cannot be automated**. A dropped or
retyped field is data loss that no rollback recovers: the version ledger can
restore an entity's *definition*, but nothing restores records whose values went
with the field. So these are not gated by a band — there is no code path that
expresses them, and these tests are how that stays true.

Design: docs/product-road-map/increment-6/02_sega.md §8.
"""
from __future__ import annotations

import pytest

from src.ai.evolution.schema_proposals import (
    PROPOSABLE_TYPES,
    SchemaProposalError,
    validate_addition,
)

EXISTING = [
    {"name": "name", "type": "string", "required": True},
    {"name": "amount", "type": "money"},
]


# ── what is allowed ──────────────────────────────────────────────────────────

def test_a_new_scalar_field_is_a_clean_addition():
    descriptor = validate_addition(EXISTING, {"name": "po_number", "type": "string"})
    assert descriptor["name"] == "po_number"
    assert descriptor["type"] == "string"


def test_a_proposed_field_is_never_required():
    """Making it required would retroactively invalidate every record that
    predates it — the same data loss as a retype, arriving as a validation
    error on the next write."""
    descriptor = validate_addition(
        EXISTING, {"name": "po_number", "type": "string", "required": True})
    assert descriptor["required"] is False


def test_an_enum_field_carries_its_values():
    descriptor = validate_addition(
        EXISTING, {"name": "channel", "type": "enum", "values": ["email", "phone"]})
    assert descriptor["values"] == ["email", "phone"]


def test_a_description_survives_when_offered():
    descriptor = validate_addition(
        EXISTING, {"name": "note", "type": "text", "description": "why it matters"})
    assert descriptor["description"] == "why it matters"


@pytest.mark.parametrize("ftype", sorted(PROPOSABLE_TYPES - {"enum"}))
def test_every_proposable_type_is_actually_proposable(ftype):
    assert validate_addition(EXISTING, {"name": "f", "type": ftype})["type"] == ftype


# ── what is not ──────────────────────────────────────────────────────────────

def test_an_existing_name_is_refused_because_it_would_be_a_retype():
    """The important refusal. "Adding" a name that exists is a retype in
    disguise, and a retype invalidates every record already holding a value."""
    with pytest.raises(SchemaProposalError, match="already exists"):
        validate_addition(EXISTING, {"name": "amount", "type": "string"})


def test_a_ref_field_is_not_proposable():
    """A ref creates an edge in the object graph and materialises link rows.
    Proposing relationships between business objects is a modelling decision,
    not a missing column, and it belongs to a human."""
    with pytest.raises(SchemaProposalError, match="not a proposable type"):
        validate_addition(EXISTING, {"name": "vendor", "type": "ref",
                                     "target": "Vendor"})


def test_an_unknown_type_is_refused():
    with pytest.raises(SchemaProposalError):
        validate_addition(EXISTING, {"name": "f", "type": "quantum"})


@pytest.mark.parametrize("name", ["", "   ", "2fast", "has space", "semi;colon",
                                 "drop table", "-dash"])
def test_an_unusable_name_is_refused(name):
    with pytest.raises(SchemaProposalError):
        validate_addition(EXISTING, {"name": name, "type": "string"})


def test_an_enum_without_values_is_refused():
    with pytest.raises(SchemaProposalError, match="non-empty"):
        validate_addition(EXISTING, {"name": "channel", "type": "enum"})


def test_an_object_cannot_grow_without_bound():
    """A schema that grows forever stops being a schema."""
    many = [{"name": f"f{i}", "type": "string"} for i in range(60)]
    with pytest.raises(SchemaProposalError, match="stops being a schema"):
        validate_addition(many, {"name": "one_more", "type": "string"})


def test_there_is_no_drop_or_rename_entry_point():
    """Not gated — absent. A reader looking for the band that permits a drop
    should find that no such function exists."""
    import src.ai.evolution.schema_proposals as module

    names = [n for n in dir(module) if not n.startswith("_")]
    for forbidden in ("drop", "rename", "retype", "remove", "delete"):
        assert not any(forbidden in n.lower() for n in names), (
            f"a {forbidden}-shaped entry point exists in schema_proposals")
