"""C4 — autonomy demotion triggers and the anti-rubber-stamp rule (PRAGYA T6).

Promotion existed; demotion did not, which made §9.7's "autonomy is
reversible" a claim rather than a control. These pin both halves: what pulls
an agent down automatically, and what is *not* enough to let it back up.
"""
from __future__ import annotations

import pytest

from src.ai.governance.demotion import (
    AUTONOMY_LADDER,
    AgentObservations,
    DemotionTrigger,
    PromotionEvidence,
    evaluate_demotion,
    one_level_down,
    promotion_evidence_sufficient,
)
from src.ai.schemas.governance import AutonomyLevel


def _obs(**kw) -> AgentObservations:
    base = dict(agent_id="agt-1", display_name="Invoice Chaser",
                current_level=AutonomyLevel.A2)
    base.update(kw)
    return AgentObservations(**base)


# --- the ladder ---------------------------------------------------------------

def test_ladder_is_ordered_weakest_first() -> None:
    assert AUTONOMY_LADDER[0] is AutonomyLevel.A0
    assert AUTONOMY_LADDER[-1] is AutonomyLevel.A4


def test_demotion_steps_exactly_one_rung() -> None:
    assert one_level_down(AutonomyLevel.A3) is AutonomyLevel.A2
    assert one_level_down(AutonomyLevel.A1) is AutonomyLevel.A0


def test_a0_is_the_floor() -> None:
    assert one_level_down(AutonomyLevel.A0) is AutonomyLevel.A0


# --- triggers -----------------------------------------------------------------

def test_healthy_agent_is_left_alone() -> None:
    verdict = evaluate_demotion(_obs(runs_total=100, runs_failed=2,
                                     gate_evaluations=50, gate_blocks=1))
    assert not verdict.demote
    assert verdict.to_level is AutonomyLevel.A2


def test_sustained_failure_rate_demotes() -> None:
    verdict = evaluate_demotion(_obs(runs_total=100, runs_failed=30))
    assert verdict.demote
    assert DemotionTrigger.SLO_BREACH in verdict.triggers
    assert verdict.to_level is AutonomyLevel.A1


def test_a_bad_afternoon_on_low_volume_does_not_demote() -> None:
    """Two failures out of three runs is noise; demoting on noise teaches the
    owner to ignore demotions."""
    verdict = evaluate_demotion(_obs(runs_total=3, runs_failed=2))
    assert not verdict.demote


def test_latency_breach_against_the_sheet_floor_demotes() -> None:
    verdict = evaluate_demotion(_obs(
        runs_total=50, runs_failed=0,
        p95_latency_ms=200_000.0, latency_floor_ms=60_000.0))
    assert verdict.demote
    assert DemotionTrigger.SLO_BREACH in verdict.triggers


def test_a_single_hard_block_demotes_with_no_volume_floor() -> None:
    """A hard block means the agent reached above its absolute ceiling — one
    is enough, and waiting for a trend would be waiting for a pattern of it."""
    verdict = evaluate_demotion(_obs(runs_total=1, hard_block_incidents=1))
    assert verdict.demote
    assert DemotionTrigger.HARD_BLOCK_INCIDENT in verdict.triggers


def test_complaint_spike_demotes_against_baseline() -> None:
    verdict = evaluate_demotion(_obs(
        counterparty_interactions=100, complaints=30,
        complaint_baseline_rate=0.05))
    assert verdict.demote
    assert DemotionTrigger.COMPLAINT_SPIKE in verdict.triggers


def test_a_new_agent_without_a_baseline_still_has_a_ceiling() -> None:
    """No baseline must not mean an unlimited complaint allowance."""
    verdict = evaluate_demotion(_obs(
        counterparty_interactions=100, complaints=40,
        complaint_baseline_rate=0.0))
    assert verdict.demote
    assert DemotionTrigger.COMPLAINT_SPIKE in verdict.triggers


def test_critic_block_surge_demotes() -> None:
    verdict = evaluate_demotion(_obs(gate_evaluations=100, gate_blocks=40))
    assert verdict.demote
    assert DemotionTrigger.CRITIC_BLOCK_SURGE in verdict.triggers


def test_owner_command_demotes_immediately() -> None:
    """'Demote X' is a T2 command; it needs no evidence beyond being asked."""
    verdict = evaluate_demotion(_obs(owner_demotion_requested=True))
    assert verdict.demote
    assert DemotionTrigger.OWNER_COMMAND in verdict.triggers


def test_an_agent_already_at_a0_reports_triggers_without_demoting() -> None:
    verdict = evaluate_demotion(_obs(
        current_level=AutonomyLevel.A0, runs_total=100, runs_failed=50))
    assert not verdict.demote
    assert verdict.triggers
    assert any("lowest" in r for r in verdict.reasons)


def test_every_demotion_explains_itself_to_the_owner() -> None:
    verdict = evaluate_demotion(_obs(runs_total=100, runs_failed=50))
    sentence = verdict.as_sentence()
    assert "A2" in sentence and "A1" in sentence
    assert verdict.reasons and all(r.strip() for r in verdict.reasons)


# --- the anti-rubber-stamp rule ----------------------------------------------

def test_perfect_acceptance_alone_is_not_enough_to_promote() -> None:
    """The core C4 property: an owner approving everything unread produces a
    flawless record for an agent that may be doing real damage."""
    ok, reason = promotion_evidence_sufficient(PromotionEvidence(
        agent_id="agt-1", approvals_total=200, approvals_unedited=200,
        deep_audit_sampled=0, deep_audit_passed=0))
    assert not ok
    assert "rubber-stamped" in reason


def test_a_sample_that_is_too_small_is_refused() -> None:
    ok, _ = promotion_evidence_sufficient(PromotionEvidence(
        agent_id="agt-1", approvals_total=200, approvals_unedited=199,
        deep_audit_sampled=3, deep_audit_passed=3))
    assert not ok


def test_a_failing_deep_audit_blocks_promotion_despite_the_headline_rate() -> None:
    ok, reason = promotion_evidence_sufficient(PromotionEvidence(
        agent_id="agt-1", approvals_total=200, approvals_unedited=200,
        deep_audit_sampled=20, deep_audit_passed=12))
    assert not ok
    assert "not as clean" in reason


def test_too_few_approvals_to_judge() -> None:
    ok, reason = promotion_evidence_sufficient(PromotionEvidence(
        agent_id="agt-1", approvals_total=10, approvals_unedited=10,
        deep_audit_sampled=10, deep_audit_passed=10))
    assert not ok
    assert "10 approvals" in reason


def test_low_acceptance_rate_blocks_promotion() -> None:
    ok, _ = promotion_evidence_sufficient(PromotionEvidence(
        agent_id="agt-1", approvals_total=200, approvals_unedited=150,
        deep_audit_sampled=20, deep_audit_passed=20))
    assert not ok


def test_complete_evidence_promotes() -> None:
    ok, reason = promotion_evidence_sufficient(PromotionEvidence(
        agent_id="agt-1", approvals_total=200, approvals_unedited=198,
        deep_audit_sampled=20, deep_audit_passed=20))
    assert ok
    assert "re-audited" in reason
