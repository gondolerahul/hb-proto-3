"""Pragya's act path (Inc-4 PRAGYA-RT T1/T2).

The seam property under test: **no tool executes until the shared PolicyGate
has returned a verdict on it.** Two orchestrators are only safe while "did we
gate this?" has a single answer, so these assert that the one function which
reaches the executor cannot be talked past.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.governance.policy_gate import BLOCK, PASS, RAISE_HITL
from src.ai.pragya.acting import (
    ActOutcome,
    ProposedCall,
    gate_proposal,
    run_tool_calls,
)
from src.ai.schemas.governance import AuthorityBands, AutonomyLevel, Governance

COMPANY = uuid.uuid4()


def _gov(level: AutonomyLevel = AutonomyLevel.A1, **bands) -> Governance:
    return Governance(
        autonomy_level=level,
        authority=AuthorityBands(**bands) if bands else None,
    )


# --- the category comes from the shared map, not a local table ---------------

def test_an_uncategorised_tool_passes_the_gate() -> None:
    decision = gate_proposal(ProposedCall("tenant_record_write"), _gov())
    assert decision.decision == PASS


def test_a_categorised_tool_is_recognised_via_the_shared_map() -> None:
    """`send_email` maps to email_dispatch in governance.authority — Pragya
    must not carry her own copy of that mapping."""
    decision = gate_proposal(ProposedCall("send_email"), _gov())
    assert decision.decision == RAISE_HITL
    assert decision.category == "email_dispatch"


def test_amount_is_lifted_from_the_call_arguments() -> None:
    """A payout above the band must reach BLOCK, which needs the amount."""
    decision = gate_proposal(
        ProposedCall("stripe_payout", {"amount": 99_000}),
        _gov(AutonomyLevel.A3, payout_usd=500.0))
    assert decision.decision == BLOCK


# --- nothing executes without a verdict --------------------------------------

@pytest.mark.asyncio
async def test_a_governed_act_raises_and_never_reaches_the_executor(monkeypatch) -> None:
    """The core property. If the executor is touched, the test fails loudly."""
    import src.ai.pragya.acting as acting

    async def _explode(*args, **kwargs):
        raise AssertionError("tool executor reached for a gated act")

    monkeypatch.setattr(acting.ToolExecutor, "execute_from_function_calls", _explode)

    results = await run_tool_calls(
        [ProposedCall("send_email", {"to": "x@y.z"})], _gov(),
        company_id=COMPANY)

    assert len(results) == 1
    assert results[0].outcome == ActOutcome.RAISED
    assert results[0].checkpoint_key


@pytest.mark.asyncio
async def test_a_blocked_act_never_reaches_the_executor(monkeypatch) -> None:
    import src.ai.pragya.acting as acting

    async def _explode(*args, **kwargs):
        raise AssertionError("tool executor reached for a blocked act")

    monkeypatch.setattr(acting.ToolExecutor, "execute_from_function_calls", _explode)

    results = await run_tool_calls(
        [ProposedCall("stripe_payout", {"amount": 99_000})],
        _gov(AutonomyLevel.A3, payout_usd=500.0), company_id=COMPANY)

    assert results[0].outcome == ActOutcome.DECLINED


@pytest.mark.asyncio
async def test_an_unrecognised_verdict_fails_closed(monkeypatch) -> None:
    """A new decision string must never become an implicit pass."""
    import src.ai.pragya.acting as acting

    class _Weird:
        decision = "MAYBE"
        checkpoint_key = None
        reason = ""
        category = "generic"
        band = None
        hard_block = None

    monkeypatch.setattr(acting, "evaluate_policy", lambda intent, gov: _Weird())

    async def _explode(*args, **kwargs):
        raise AssertionError("executor reached on an unrecognised verdict")

    monkeypatch.setattr(acting.ToolExecutor, "execute_from_function_calls", _explode)

    results = await run_tool_calls(
        [ProposedCall("anything")], _gov(), company_id=COMPANY)
    assert results[0].outcome == ActOutcome.DECLINED


@pytest.mark.asyncio
async def test_a_passing_act_executes_and_reports_its_output(monkeypatch) -> None:
    import src.ai.pragya.acting as acting

    class _Result:
        success = True
        output = {"ok": True}

    async def _fake(calls, extra_context=None, call_counts=None):
        assert extra_context["company_id"] == COMPANY
        return [_Result()]

    monkeypatch.setattr(acting.ToolExecutor, "execute_from_function_calls", _fake)

    results = await run_tool_calls(
        [ProposedCall("tenant_record_write", {"x": 1})], _gov(),
        company_id=COMPANY)
    assert results[0].outcome == ActOutcome.EXECUTED
    assert results[0].output == {"ok": True}


@pytest.mark.asyncio
async def test_a_failing_tool_is_reported_not_raised(monkeypatch) -> None:
    import src.ai.pragya.acting as acting

    class _Result:
        success = False
        error = "upstream 500"
        skip_reason = None

    async def _fake(calls, extra_context=None, call_counts=None):
        return [_Result()]

    monkeypatch.setattr(acting.ToolExecutor, "execute_from_function_calls", _fake)

    results = await run_tool_calls(
        [ProposedCall("tenant_record_write")], _gov(), company_id=COMPANY)
    assert results[0].outcome == ActOutcome.FAILED
    assert "upstream 500" in (results[0].error or "")


# --- what the model is told back ---------------------------------------------

@pytest.mark.asyncio
async def test_a_raised_act_tells_the_model_not_to_claim_completion() -> None:
    """The observation is a fact about the world, not an instruction — and it
    has to stop the model saying 'done'."""
    results = await run_tool_calls(
        [ProposedCall("send_email", {"to": "x@y.z"})], _gov(),
        company_id=COMPANY)
    observation = results[0].observation
    assert "NOT executed" in observation
    assert "Judgment Desk" in observation
    assert "do not imply it is done" in observation
    # It must not invite an in-chat approval — standing rule 2.
    assert "do not ask them to approve it here" in observation
