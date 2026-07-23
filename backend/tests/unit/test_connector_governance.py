"""Inc 4 / CONN+SOR T3 — connector write-back is a governed act (external_write).

A write to the tenant's external system of record is an external effect: at A1
every one raises a HITL card (before_external_system_write); at A2+ it syncs
autonomously. Read tools (get_/list_) are not external effects and stay
uncategorised (PASS). Pure ``evaluate_policy`` + ``category_for_tool`` — no DB.
"""
from __future__ import annotations

from src.ai.governance.authority import CATEGORY_RULES, category_for_tool
from src.ai.governance.checkpoints import CHECKPOINT_KEYS
from src.ai.governance.policy_gate import (
    BLOCK,
    PASS,
    RAISE_HITL,
    ActIntent,
    evaluate_policy,
)
from src.ai.schemas.governance import AutonomyLevel, Governance


def _gov(level: AutonomyLevel) -> Governance:
    return Governance(autonomy_level=level)


def test_category_and_checkpoint_are_registered() -> None:
    rule = CATEGORY_RULES["external_write"]
    assert rule.checkpoint_key == "before_external_system_write"
    # the checkpoint key is a real seeded def (the 19th)
    assert "before_external_system_write" in CHECKPOINT_KEYS


def test_connector_write_verbs_resolve() -> None:
    assert category_for_tool("mcp__zoho_books__create_invoice") == "external_write"
    assert category_for_tool("mcp__zoho_books__update_invoice") == "external_write"
    assert category_for_tool("mcp__crm_generic__write_back") == "external_write"


def test_connector_reads_are_not_gated() -> None:
    # a mirror read is not an external effect — uncategorised → PASS
    assert category_for_tool("mcp__zoho_books__get_invoice") is None
    assert category_for_tool("mcp__zoho_books__list_invoices") is None


def test_a1_raises_hitl() -> None:
    d = evaluate_policy(ActIntent("external_write"), _gov(AutonomyLevel.A1))
    assert d.decision == RAISE_HITL
    assert d.checkpoint_key == "before_external_system_write"


def test_a2_is_autonomous() -> None:
    # no amount band on external_write → autonomous at A2+ (same as email comms)
    d = evaluate_policy(ActIntent("external_write"), _gov(AutonomyLevel.A2))
    assert d.decision == PASS


def test_a0_blocks() -> None:
    d = evaluate_policy(ActIntent("external_write"), _gov(AutonomyLevel.A0))
    assert d.decision == BLOCK
