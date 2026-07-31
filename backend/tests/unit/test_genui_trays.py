"""SEAM T5 — the tray composer's pure parts.

The test that earns its keep here is **conformance**: the certified block our
own composer emits must satisfy the registry schema for its component,
because the client *rejects* a certified component with an undeclared or
missing prop (D4 §2) — and that rejection must never be reachable from our
own code. A composer and a registry that drift produce a tray nobody can
approve, which is the "quietly does less" failure in its most expensive
spot.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from src.ai.genui.registry import load_registry
from src.ai.genui.trays import (
    certified_block,
    compose_tray,
    recommendation_block,
    what_happened_object,
)

APPROVAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

PAYOUT_SNAPSHOT: dict[str, Any] = {
    "category": "outbound_payout",
    "reason": "Payout above the A2 band",
    "band": 2,
    "amount": 84200.0,
    "checkpoint_key": "before_outbound_payout_above_band",
}


def _registry_entry(component: str) -> dict[str, Any]:
    bare = component.split("@")[0]
    return next(e for e in load_registry() if e["type"] == bare)


def _assert_conforms(block: dict[str, Any]) -> None:
    """props must exactly satisfy the registry schema: every required prop
    present, no undeclared prop (additionalProperties: false)."""
    schema = _registry_entry(block["component"])["props"]
    declared = set(schema["properties"])
    required = set(schema.get("required", []))
    present = set(block["props"])
    assert required <= present, f"missing required props: {required - present}"
    assert present <= declared, f"undeclared props: {present - declared}"


# ── component selection ───────────────────────────────────────────────────────

def test_a_gated_amount_composes_a_payment():
    block = certified_block(APPROVAL_ID, PAYOUT_SNAPSHOT)
    assert block["component"] == "certified.payment@1"
    assert block["props"]["amount"] == 84200.0
    assert block["props"]["currency"] is None  # honest absence, never guessed
    assert block["tier"] in ("T2", "T3")
    assert block["tier"] == block["props"]["tier"]
    _assert_conforms(block)


def test_an_uncategorised_approval_composes_a_plain_approval():
    block = certified_block(APPROVAL_ID, {"reason": "plan wants confirmation"})
    assert block["component"] == "certified.approval@1"
    assert block["props"]["tier"] == "T1"
    assert "amount" not in block["props"]
    _assert_conforms(block)


def test_a_categorised_act_without_an_amount_is_not_a_payment():
    block = certified_block(
        APPROVAL_ID, {"category": "email_dispatch", "reason": "outbound email"})
    assert block["component"] == "certified.approval@1"
    _assert_conforms(block)


# ── the hash is an audit artifact ────────────────────────────────────────────

def test_manifest_hash_is_stable_and_content_addressed():
    first = certified_block(APPROVAL_ID, PAYOUT_SNAPSHOT)
    second = certified_block(APPROVAL_ID, PAYOUT_SNAPSHOT)
    assert first["manifest_hash"] == second["manifest_hash"]
    assert first["manifest_hash"].startswith("sha256:")

    changed = certified_block(APPROVAL_ID, {**PAYOUT_SNAPSHOT, "amount": 1.0})
    assert changed["manifest_hash"] != first["manifest_hash"]


# ── the composed tray ─────────────────────────────────────────────────────────

RUN_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
ENTITY_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _approval(snapshot: dict[str, Any] | None = None) -> Any:
    return SimpleNamespace(
        id=APPROVAL_ID,
        run_id=RUN_ID,
        checkpoint_key="before_outbound_payout_above_band",
        context_snapshot=snapshot if snapshot is not None else dict(PAYOUT_SNAPSHOT),
        requested_at=datetime(2026, 7, 29, 11, 0, 0),
    )


def test_tray_fields_in_spec_order_with_honest_absences():
    now = datetime(2026, 7, 29, 12, 0, 0)
    tray = compose_tray(
        approval=_approval(),
        prepared_by=(ENTITY_ID, "Meera"),
        sla_seconds=14400,
        on_timeout="auto_deny",
        now=now,
    )
    assert list(tray.keys()) == [
        "tray_id", "approval_id", "checkpoint_key", "what_happened",
        "recommendation", "paths", "certified", "sla", "prepared_by"]
    assert tray["what_happened"]["sentence"] == "Payout above the A2 band"
    # No stored sentence → null, not prose and not an empty object.
    assert tray["recommendation"] is None
    approve, decline = tray["paths"]
    assert approve["cost"] == {
        "amount": 84200.0, "currency": None, "basis": "the amount itself"}
    assert decline["cost"] is None
    assert tray["sla"] == {"seconds_left": 14400 - 3600, "on_timeout": "auto_deny"}
    assert tray["prepared_by"]["name"] == "Meera"


def test_an_overdue_tray_reads_zero_not_negative():
    approval = _approval()
    now = approval.requested_at + timedelta(days=2)
    tray = compose_tray(
        approval=approval, prepared_by=None,
        sla_seconds=3600, on_timeout="auto_deny", now=now)
    assert tray["sla"]["seconds_left"] == 0


def test_a_tray_without_an_sla_says_none_not_zero():
    tray = compose_tray(
        approval=_approval(), prepared_by=None,
        sla_seconds=None, on_timeout=None,
        now=datetime(2026, 7, 29, 12, 0, 0))
    assert tray["sla"]["seconds_left"] is None


# ── E5: recommendation is one shape, everywhere ──────────────────────────────

def _compose(snapshot: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    return compose_tray(
        approval=_approval(snapshot), prepared_by=(ENTITY_ID, "Meera"),
        sla_seconds=None, on_timeout=None,
        now=datetime(2026, 7, 29, 12, 0, 0), **kwargs)


def test_a_stored_sentence_composes_as_the_contracted_object():
    """The D5 §4.1 shape — an object, never the bare string the watcher used
    to overwrite the field with. A client reading ``.sentence`` must find it
    on the REST copy and the socket copy alike."""
    tray = _compose(recommendation="Within the band — I'd approve.")
    assert tray["recommendation"] == {
        "sentence": "Within the band — I'd approve.", "why": None}


def test_recommendation_block_is_the_one_function_both_legs_call():
    assert recommendation_block("a sentence") == {
        "sentence": "a sentence", "why": None}
    # No sentence and an empty sentence are the same absence: no line at all,
    # never an empty one under the card.
    assert recommendation_block(None) is None
    assert recommendation_block("") is None


def test_a_tray_without_a_recommendation_is_still_a_tray():
    """The failure posture (12_steward.md §5): advice lost, never work. A
    recommendation that could not be written must not block, blank or
    otherwise degrade the certified block the owner acts on."""
    tray = _compose(recommendation=None)
    assert tray["recommendation"] is None
    assert tray["certified"]["component"] == "certified.payment@1"
    assert [p["key"] for p in tray["paths"]] == ["approve", "decline"]


# ── E6: what_happened names an object to click through to ────────────────────

def test_an_ordinary_gate_names_the_run_it_stopped():
    obj = _compose()["what_happened"]["object"]
    assert obj == {"kind": "run", "id": str(RUN_ID), "label": "Meera's run"}


def test_a_cross_owner_write_names_the_record_it_touched():
    obj = _compose({
        "def": "Invoice", "record_id": "3f2a9c11-0000-0000-0000-000000000000",
        "actor": "P08", "owner": "P10",
    })["what_happened"]["object"]
    assert obj["kind"] == "Invoice"
    assert obj["id"] == "3f2a9c11-0000-0000-0000-000000000000"
    assert obj["label"] == "Invoice 3f2a9c11"


def test_a_twin_promotion_names_the_colleague_it_would_change():
    obj = _compose({
        "category": "governance", "reason": "a rehearsal argues for this",
        "twin_promotion": {"entity_id": str(ENTITY_ID), "field": "band"},
    })["what_happened"]["object"]
    assert obj == {"kind": "colleague", "id": str(ENTITY_ID), "label": "Meera"}


def test_a_promotion_whose_run_belongs_to_someone_else_falls_back_to_the_run():
    """The colleague object is only claimed when we hold its name — the
    anchor run is the entity's own by construction, and a mismatch means
    the assumption broke, not that a label may be guessed."""
    obj = what_happened_object(
        {"twin_promotion": {"entity_id": str(uuid.uuid4())}},
        run_id=RUN_ID, prepared_by=(ENTITY_ID, "Meera"))
    assert obj["kind"] == "run"


def test_an_approval_with_no_run_names_nothing_rather_than_inventing_one():
    assert what_happened_object({}, run_id=None, prepared_by=None) is None
