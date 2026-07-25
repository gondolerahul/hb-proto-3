"""SEGA T2 — the pure half of the version ledger (VG-17).

Snapshot shape and version bumping, decidable without a database. The
interesting cases are the ugly inputs: an entity missing a block, a malformed
version string. History is most valuable exactly when something has gone
wrong, so the ledger must not be the second thing that breaks.

Design: docs/product-road-map/increment-6/02_sega.md §5.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.ai.evolution.ledger import next_version, snapshot_of
from src.ai.evolution.models import SNAPSHOT_BLOCKS


# ── version bumping ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("current,expected", [
    ("1.0.0", "1.0.1"),
    ("1.0.9", "1.0.10"),
    ("2.7.3", "2.7.4"),
])
def test_the_patch_component_bumps(current, expected):
    assert next_version(current) == expected


@pytest.mark.parametrize("bad", [None, "", "v2", "1.0", "not.a.version", "1.0.x"])
def test_a_malformed_version_starts_a_fresh_series_rather_than_raising(bad):
    """A bad version string is not a reason to refuse to record history — that
    is the moment history matters most."""
    assert next_version(bad) == "1.0.1"


def test_bumping_is_deterministic():
    assert next_version("3.2.1") == next_version("3.2.1")


# ── snapshots ────────────────────────────────────────────────────────────────

def test_a_snapshot_captures_every_declared_block():
    entity = SimpleNamespace(**{b: f"value-{b}" for b in SNAPSHOT_BLOCKS})
    snapshot = snapshot_of(entity)
    assert set(snapshot) == set(SNAPSHOT_BLOCKS)


def test_a_missing_block_is_recorded_as_none_not_omitted():
    """Same shape every time, so a diff never has to distinguish "absent then"
    from "absent from the record"."""
    entity = SimpleNamespace(goal="ship it")
    snapshot = snapshot_of(entity)
    assert set(snapshot) == set(SNAPSHOT_BLOCKS)
    assert snapshot["goal"] == "ship it"
    assert snapshot["governance"] is None


def test_a_snapshot_ignores_fields_outside_the_declared_set():
    """`SNAPSHOT_BLOCKS` is the definition of "what a version is". A block added
    to the entity model later is a deliberate addition to history, not a silent
    one — and secrets or transient state must not drift into the ledger."""
    entity = SimpleNamespace(goal="g", api_key="s3cret", _sa_instance_state=object())
    snapshot = snapshot_of(entity)
    assert "api_key" not in snapshot
    assert "_sa_instance_state" not in snapshot


def test_governance_is_snapshotted_even_though_it_is_never_self_modified():
    """The ledger records *what happened*; the blast-radius predicate decides
    what may happen. A human raising a band must still be in the history —
    conflating the two would leave the most consequential edits unrecorded.
    """
    assert "governance" in SNAPSHOT_BLOCKS
    assert "capabilities" in SNAPSHOT_BLOCKS
