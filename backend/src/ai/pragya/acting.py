"""pragya/acting.py — Pragya's act path: propose → gate → execute → observe.

Four steps, all cheap except the tool itself. This is the whole of what her
turn loop needs from the task loop's Act stage, and it is deliberately thin:
the §3 seam makes the **gate** and the **executor** shared, so this module is
plumbing between two things it does not own.

The rule this file enforces, and the reason it exists as a separate module
rather than inline in ``runtime``:

> **No tool executes until ``evaluate_policy`` has returned a verdict on it.**

There is exactly one function that reaches the executor, so there is exactly
one place to audit. A second orchestrator is only safe if "did we gate this?"
has a single answer, and T2 makes that structural rather than conventional.

Governed acts follow VOICE's shape — the card is raised and the owner is told,
but nothing executes. That is the same rule on every channel: Pragya can never
satisfy her own checkpoint, so an approval she needs goes to the Judgment Desk
and not into the conversation that asked for it.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.ai.governance.policy_gate import (
    BLOCK,
    PASS,
    RAISE_HITL,
    ActIntent,
    GateDecision,
    evaluate_policy,
)
from src.ai.governance.authority import category_for_tool
from src.ai.schemas.governance import Governance
from src.ai.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)

__all__ = [
    "ActOutcome",
    "ProposedCall",
    "ToolTurnResult",
    "gate_proposal",
    "run_tool_calls",
]


class ActOutcome:
    EXECUTED = "executed"
    RAISED = "raised"       # HITL card; settles at the Judgment Desk
    DECLINED = "declined"   # hard-blocked
    FAILED = "failed"       # ran and errored


@dataclass(frozen=True)
class ProposedCall:
    """A tool call the model proposed, before anything has been decided."""

    name: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_intent(self) -> ActIntent:
        """Normalise the proposal for policy evaluation.

        The category comes from the shared ``TOOL_CATEGORY_MAP`` — not from a
        Pragya-local table. One taxonomy, two enforcement points.
        """
        category = category_for_tool(self.name) or "generic"
        amount = self.args.get("amount") or self.args.get("amount_usd")
        pct = self.args.get("percent") or self.args.get("discount_pct")
        return ActIntent(
            action_category=category,
            amount_usd=float(amount) if isinstance(amount, (int, float)) else None,
            amount_pct=float(pct) if isinstance(pct, (int, float)) else None,
            tool_id=self.name,
        )


@dataclass
class ToolTurnResult:
    """What one proposed call actually did."""

    call: ProposedCall
    outcome: str
    decision: GateDecision
    output: Any = None
    error: str | None = None
    checkpoint_key: str | None = None

    @property
    def observation(self) -> str:
        """What the model is told happened — fed back into the turn.

        A raised card reads as a *fact about the world*, not an instruction:
        the model must not then claim the action completed, and telling it
        plainly that a human now holds the decision is what prevents that.
        """
        if self.outcome == ActOutcome.EXECUTED:
            return f"{self.call.name} completed: {self.output!r}"
        if self.outcome == ActOutcome.RAISED:
            return (
                f"{self.call.name} was NOT executed. It needs human approval and "
                f"a card is now waiting at the Judgment Desk. Tell the owner it "
                f"is pending — do not imply it is done, and do not ask them to "
                f"approve it here."
            )
        if self.outcome == ActOutcome.DECLINED:
            return (f"{self.call.name} was refused by policy: {self.decision.reason}. "
                    f"Say so plainly rather than trying another route.")
        return f"{self.call.name} failed: {self.error}"


def gate_proposal(call: ProposedCall, gov: Governance) -> GateDecision:
    """The shared PolicyGate, over a proposed tool call. Pure."""
    return evaluate_policy(call.to_intent(), gov)


async def run_tool_calls(
    calls: list[ProposedCall],
    gov: Governance,
    *,
    company_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    call_counts: dict[str, int] | None = None,
) -> list[ToolTurnResult]:
    """Gate then execute each proposed call, in order.

    **The only path from Pragya to a tool.** Every call is evaluated before it
    runs; a ``RAISE_HITL`` or ``BLOCK`` verdict returns without touching the
    executor, so a governed act cannot complete inside a conversational turn.
    """
    results: list[ToolTurnResult] = []
    counts = call_counts if call_counts is not None else {}

    for call in calls:
        decision = gate_proposal(call, gov)

        if decision.decision == RAISE_HITL:
            results.append(ToolTurnResult(
                call=call, outcome=ActOutcome.RAISED, decision=decision,
                checkpoint_key=decision.checkpoint_key))
            logger.info("pragya act raised HITL: tool=%s checkpoint=%s",
                        call.name, decision.checkpoint_key)
            continue

        if decision.decision == BLOCK:
            results.append(ToolTurnResult(
                call=call, outcome=ActOutcome.DECLINED, decision=decision,
                checkpoint_key=decision.checkpoint_key))
            logger.info("pragya act blocked: tool=%s reason=%s",
                        call.name, decision.reason)
            continue

        if decision.decision != PASS:
            # An unrecognised verdict is not a pass. Fail closed.
            results.append(ToolTurnResult(
                call=call, outcome=ActOutcome.DECLINED, decision=decision,
                error=f"unrecognised gate decision {decision.decision!r}"))
            continue

        executed = await ToolExecutor.execute_from_function_calls(
            [{"name": call.name, "args": call.args}],
            extra_context={"company_id": company_id, "user_id": user_id},
            call_counts=counts,
        )
        result = executed[0] if executed else None

        if result is None or not getattr(result, "success", False):
            results.append(ToolTurnResult(
                call=call, outcome=ActOutcome.FAILED, decision=decision,
                error=str(getattr(result, "error", None)
                         or getattr(result, "skip_reason", None)
                         or "tool returned nothing")))
            continue

        results.append(ToolTurnResult(
            call=call, outcome=ActOutcome.EXECUTED, decision=decision,
            output=getattr(result, "output", None)))

    return results
