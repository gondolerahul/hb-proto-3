"""The realtime execution profile and its live gate (Inc-3 VOICE, B7).

B7 asked which of the eight stages a strict-latency voice turn skips. These
pin the answer, and in particular pin the part that is easy to get wrong under
pressure: **governance is not what gets skipped.** The PolicyGate is a pure
function, so it stays on the latency path; what defers is LLM judgment.
"""
from __future__ import annotations

import pytest

from src.ai.governance.policy_gate import BLOCK, PASS, RAISE_HITL, ActIntent
from src.ai.schemas.governance import AuthorityBands, AutonomyLevel, Governance
from src.ai.voice_loop.live_gate import LiveOutcome, gate_voice_act, profile_note
from src.ai.voice_loop.profile import (
    DEFERRED_STAGES,
    LIVE_COMPLETION_RULE,
    LIVE_STAGES,
    REALTIME_PROFILE,
    Disposition,
    Stage,
    is_model_call,
    profile_for,
    runs_live,
)


# --- the profile is complete and internally consistent ------------------------

def test_every_stage_has_a_disposition_and_a_rationale() -> None:
    assert {p.stage for p in REALTIME_PROFILE} == set(Stage)
    for p in REALTIME_PROFILE:
        assert p.rationale.strip(), f"{p.stage} does not justify its disposition"


def test_live_and_deferred_partition_the_stages() -> None:
    assert set(LIVE_STAGES) | set(DEFERRED_STAGES) == set(Stage)
    assert not set(LIVE_STAGES) & set(DEFERRED_STAGES)


# --- the invariant the latency budget imposes ---------------------------------

def test_no_model_call_stage_runs_live() -> None:
    """The budget's hard constraint. If this fails, a turn cannot fit."""
    for p in REALTIME_PROFILE:
        if p.disposition is Disposition.LIVE:
            assert not p.model_call, f"{p.stage} is a model call but marked live"


def test_the_three_llm_judgment_stages_defer() -> None:
    for stage in (Stage.STRATEGIZE, Stage.PRE_CRITIC, Stage.POST_CRITIC,
                  Stage.REFLECT):
        assert not runs_live(stage), stage
        assert is_model_call(stage) or stage is Stage.REFLECT


# --- the load-bearing line: governance stays inline ---------------------------

def test_the_policy_gate_runs_live() -> None:
    """B7's core answer. Realtime buys no excuse to skip governance, because
    the gate was never a model call in the first place."""
    assert runs_live(Stage.POLICY_GATE)
    assert not is_model_call(Stage.POLICY_GATE)


def test_the_policy_gate_is_never_deferred_by_any_edit() -> None:
    gate = profile_for(Stage.POLICY_GATE)
    assert gate.disposition is Disposition.LIVE
    assert "pure" in gate.rationale.lower()


def test_act_and_observe_run_live_so_a_turn_can_speak() -> None:
    assert runs_live(Stage.ACT)
    assert runs_live(Stage.OBSERVE)
    assert runs_live(Stage.PERCEIVE)


def test_decide_defers_because_its_inputs_do() -> None:
    """Cheap in itself, but it reads what the deferred stages produce."""
    decide = profile_for(Stage.DECIDE)
    assert decide.disposition is Disposition.DEFERRED
    assert not decide.model_call


# --- the live gate: promise, never complete -----------------------------------

def _gov(level: AutonomyLevel = AutonomyLevel.A1, **bands) -> Governance:
    return Governance(
        autonomy_level=level,
        authority=AuthorityBands(**bands) if bands else None,
    )


def test_uncategorised_acts_complete_live() -> None:
    """Reads, lookups and drafting are what a call is mostly made of."""
    decision = gate_voice_act(ActIntent(action_category="generic"), _gov())
    assert decision.outcome is LiveOutcome.COMPLETED
    assert decision.may_execute_live
    assert decision.gate.decision == PASS


def test_a_governed_act_at_a1_is_promised_not_completed() -> None:
    """The normative rule: a voice turn cannot complete a governed action."""
    decision = gate_voice_act(
        ActIntent(action_category="payout", amount_usd=100.0),
        _gov(AutonomyLevel.A1, payout_usd=500.0),
    )
    assert decision.gate.decision == RAISE_HITL
    assert decision.outcome is LiveOutcome.PROMISED
    assert not decision.may_execute_live
    assert decision.checkpoint_key


def test_the_promise_says_what_is_pending_and_who_must_act() -> None:
    """'I'll look into it' is how a caller believes something happened."""
    decision = gate_voice_act(
        ActIntent(action_category="payout", amount_usd=100.0),
        _gov(AutonomyLevel.A1, payout_usd=500.0),
        approver="your finance lead",
    )
    assert "your finance lead" in decision.spoken
    assert "sign off" in decision.spoken
    # It must never imply the thing was done.
    assert "done" not in decision.spoken.lower().replace("i've", "")


def test_a_hard_blocked_act_declines_and_raises_nothing() -> None:
    decision = gate_voice_act(
        ActIntent(action_category="payout", amount_usd=99_000.0),
        _gov(AutonomyLevel.A3, payout_usd=500.0),
    )
    assert decision.gate.decision == BLOCK
    assert decision.outcome is LiveOutcome.DECLINED
    assert not decision.may_execute_live


def test_counterparty_trust_blocks_high_impact_on_a_call_too() -> None:
    """§18.6 applies identically on voice — one gate, not a voice variant."""
    decision = gate_voice_act(
        ActIntent(action_category="payout", amount_usd=10.0,
                  counterparty_trust="counterparty"),
        _gov(AutonomyLevel.A3, payout_usd=500.0),
    )
    assert decision.outcome is LiveOutcome.DECLINED


def test_an_unrecognised_gate_decision_fails_closed() -> None:
    """Defensive: a new decision string must not become an implicit pass."""
    import src.ai.voice_loop.live_gate as module

    class _Weird:
        decision = "MAYBE"
        checkpoint_key = None
        reason = ""
        category = "generic"
        band = None
        hard_block = None

    original = module.evaluate_policy
    module.evaluate_policy = lambda intent, gov: _Weird()  # type: ignore[assignment]
    try:
        decision = gate_voice_act(ActIntent(action_category="generic"), _gov())
        assert decision.outcome is LiveOutcome.DECLINED
    finally:
        module.evaluate_policy = original  # type: ignore[assignment]


def test_the_agent_prompt_and_the_enforcement_quote_the_same_rule() -> None:
    """The gateway's instructions must not state a rule the code doesn't hold."""
    assert profile_note() == LIVE_COMPLETION_RULE
    assert "may not complete" in LIVE_COMPLETION_RULE
