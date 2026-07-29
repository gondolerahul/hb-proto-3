"""SEAM T6 — the echo bus's pure half: what counts as an echo.

Each refusal reachable alone, because a validator never observed to fail is
a function that returns None — and a permissive echo bus quietly becomes a
general-purpose event dump, which is the fate the preference store's
namespace refusal exists to prevent (D5 §8, the same instinct here).
"""
from __future__ import annotations

from src.ai.genui.echo import ECHO_RETENTION_DAYS, validate_echo


def _valid() -> dict:
    return {
        "sentence": "filtered Invoices to overdue",
        "action_ref": {"kind": "register.filter", "surface_id": "hall.accounting"},
    }


def test_a_well_formed_echo_passes():
    assert validate_echo(_valid()) is None


def test_an_echo_is_a_sentence():
    for bad in ("", "   ", None, 42):
        payload = {**_valid(), "sentence": bad}
        assert validate_echo(payload) is not None, repr(bad)


def test_a_sentence_is_bounded():
    assert validate_echo({**_valid(), "sentence": "x" * 501}) is not None
    assert validate_echo({**_valid(), "sentence": "x" * 500}) is None


def test_an_echo_names_the_kind_of_act():
    assert validate_echo({**_valid(), "action_ref": {}}) is not None
    assert validate_echo({**_valid(), "action_ref": "register.filter"}) is not None
    no_ref = _valid()
    del no_ref["action_ref"]
    assert validate_echo(no_ref) is not None


def test_retention_is_ninety_days():
    """Pinned: the reaper's window is part of the contract (D5 §6), and a
    silent change would silently change what Pragya can learn from."""
    assert ECHO_RETENTION_DAYS == 90
