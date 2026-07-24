"""governance/policy_gate.py — deterministic policy before LLM judgment (§20.3).

The PolicyGate is a pure-function stage that runs *before* the LLM Pre-Critic.
It maps an act intent to one of three decisions against the entity's autonomy
level, the §9.3 authority matrix (data, not prompt text), and the §18.6 signal
trust hook:

    PASS        → continue to the Pre-Critic (unchanged)
    RAISE_HITL  → a human_approvals row (checkpoint_key) + run PAUSED
    BLOCK       → step blocked; an LLM cannot talk the gate out of it

The evaluation (``evaluate_policy``) is pure and IO-free — exhaustively unit
tested as a decision table. ``PolicyGate`` is the thin runtime wrapper that
adapts a loop ``move`` into an ``ActIntent`` and performs the HITL/pause side
effects; it does zero LLM work.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from src.ai.governance.authority import (
    CATEGORY_RULES,
    HIGH_IMPACT_CATEGORIES,
    CategoryRule,
    category_for_tool,
)
from src.ai.schemas.governance import AutonomyLevel, Governance

logger = logging.getLogger(__name__)

__all__ = [
    "ActIntent",
    "GateDecision",
    "evaluate_policy",
    "intent_from_move",
    "PolicyGate",
    "PASS",
    "RAISE_HITL",
    "BLOCK",
]

PASS = "PASS"
RAISE_HITL = "RAISE_HITL"
BLOCK = "BLOCK"


@dataclass(frozen=True)
class ActIntent:
    """What the entity is about to do, normalised for policy evaluation."""
    action_category: str                 # a CATEGORY_RULES key, or "generic"
    amount_usd: Optional[float] = None
    amount_pct: Optional[float] = None
    counterparty_trust: Optional[str] = None   # signal trust (§18.6): counterparty|...
    is_bulk: bool = False                # for data_deletion: bulk vs single-subject
    tool_id: Optional[str] = None


@dataclass(frozen=True)
class GateDecision:
    decision: str                        # PASS | RAISE_HITL | BLOCK
    checkpoint_key: Optional[str] = None
    reason: str = ""
    category: str = "generic"
    band: Optional[float] = None
    hard_block: Optional[float] = None
    # The amount that was compared against the band, in the category's unit.
    # Carried so the raised approval is self-describing: the human tier gate
    # (inward_auth.guard) needs it to tell a within-band act from an
    # above-band one, and would otherwise have to fail every high-impact
    # approval up to T3 for want of a number the gate already had.
    amount: Optional[float] = None


def _band_for(gov: Governance, rule: "CategoryRule") -> Optional[float]:
    """The entity's tuned band for a category, else the platform default.

    Returns ``None`` only when neither is set — the "unset bands" case, where
    monetary actions pass through until Inc 2 seeds real bands (decision
    2026-07-19).
    """
    if rule.band_field and gov.authority is not None:
        tuned = getattr(gov.authority, rule.band_field, None)
        if tuned is not None:
            return float(tuned)
    return rule.default_band


def _amount_for(intent: ActIntent, unit: str) -> Optional[float]:
    if unit == "pct":
        return intent.amount_pct
    if unit == "usd":
        return intent.amount_usd
    return None


def evaluate_policy(intent: ActIntent, gov: Governance) -> GateDecision:
    """Pure decision function — no IO, no LLM. The authority matrix is data."""
    category = intent.action_category

    # Uncategorised acts (reasoning, retrieval, generic tools) are not external
    # business effects — the gate never touches them.
    rule = CATEGORY_RULES.get(category)
    if rule is None:
        return GateDecision(PASS, category="generic",
                            reason="uncategorised act (no external business effect)")

    autonomy = gov.autonomy_level
    hard = rule.hard_block
    band = _band_for(gov, rule)
    amount = _amount_for(intent, rule.unit)

    # §18.6 trust down-payment: a counterparty-trust triggering signal may not
    # drive a high-impact category at all — refuse before autonomy is even
    # considered. (Full taint tracking: register D3, Increment 6.)
    if intent.counterparty_trust == "counterparty" and category in HIGH_IMPACT_CATEGORIES:
        return GateDecision(
            BLOCK, checkpoint_key=rule.checkpoint_key, category=category,
            band=band, hard_block=hard,
            reason=f"counterparty-trust signal cannot drive {category}",
        )

    # Hard-block ceiling is absolute — above it, no autonomy level may proceed.
    if hard is not None and amount is not None and amount > hard:
        return GateDecision(
            BLOCK, checkpoint_key=rule.checkpoint_key, category=category,
            band=band, hard_block=hard,
            reason=f"{category} {amount} exceeds hard-block ceiling {hard}",
        )

    # A0 Observe — no external effect may leave the loop.
    if autonomy == AutonomyLevel.A0:
        return GateDecision(
            BLOCK, checkpoint_key=rule.checkpoint_key, category=category,
            band=band, hard_block=hard,
            reason="A0 (observe) permits no external effect",
        )

    # A1 Propose — a human approves every external effect.
    if autonomy == AutonomyLevel.A1:
        return GateDecision(
            RAISE_HITL, checkpoint_key=rule.checkpoint_key, category=category,
            band=band, hard_block=hard, amount=amount,
            reason="A1 (propose) requires human approval of every external effect",
        )

    # Categories with no autonomous path always need a human, even at A2+.
    if rule.always_hitl:
        return GateDecision(
            RAISE_HITL, checkpoint_key=rule.checkpoint_key, category=category,
            band=band, hard_block=hard, amount=amount,
            reason=f"{category} always requires human approval",
        )

    # data_deletion: bulk/ambiguous needs a human; single verified subject is fine.
    if category == "data_deletion":
        if intent.is_bulk:
            return GateDecision(
                RAISE_HITL, checkpoint_key=rule.checkpoint_key, category=category,
                amount=amount,
                reason="bulk/ambiguous data deletion requires human approval")
        return GateDecision(PASS, category=category, reason="single verified subject")

    # A2 Act-with-exceptions — inside the band autonomous, above it HITL.
    if autonomy == AutonomyLevel.A2:
        if band is None:
            # Unset bands pass monetary actions through (decision 2026-07-19).
            return GateDecision(PASS, category=category, hard_block=hard,
                                reason="authority band unset — pass-through (pre-Inc2)")
        if amount is not None and amount > band:
            return GateDecision(
                RAISE_HITL, checkpoint_key=rule.checkpoint_key, category=category,
                band=band, hard_block=hard, amount=amount,
                reason=f"{category} {amount} exceeds autonomous band {band}")
        return GateDecision(PASS, category=category, band=band,
                            reason=f"{category} within autonomous band {band}")

    # A3 Act-with-audit / A4 Self-modify — autonomous within scope (already
    # under the hard ceiling checked above); acts are logged and sampled.
    return GateDecision(PASS, category=category, band=band, hard_block=hard,
                        reason=f"{autonomy.value} autonomous within scope")


# ---------------------------------------------------------------------------
# Runtime adapter + side-effecting gate
# ---------------------------------------------------------------------------


def _governance_from_entity(entity: Any) -> Governance:
    """Parse the entity's governance JSON into the typed block (lenient).

    Reads default to A1 + no bands when governance is absent/malformed — the
    gate must never crash a run on a bad config; the save-time validator is
    what rejects malformed governance up front.
    """
    raw = getattr(entity, "governance", None)
    if isinstance(raw, Governance):
        return raw
    if isinstance(raw, dict):
        try:
            return Governance.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("governance parse failed; defaulting to A1: %s", exc)
    return Governance()


def _num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def intent_from_move(move: Any, entity: Any, signal_trust: Optional[str]) -> ActIntent:
    """Adapt a loop ``move`` into an ActIntent (IO-free).

    Category resolution: an explicit ``action_category`` on the step target
    wins; otherwise the step's ``tool_id`` maps via the authority catalogue.
    Amount extraction reads common parameter names (amount/amount_usd/total/
    tcv/discount_pct/...). No mapping → the "generic" category (PASS).
    """
    step = _head_step(move)
    target = (step.get("target") or {}) if isinstance(step, dict) else {}
    params = _step_params(step, target)

    category = (
        target.get("action_category")
        or step.get("action_category")
        or category_for_tool(target.get("tool_id"))
        or "generic"
    )
    amount_usd = _num(
        params.get("amount_usd") or params.get("amount")
        or params.get("total") or params.get("tcv") or params.get("exposure_usd")
    )
    amount_pct = _num(
        params.get("discount_pct") or params.get("price_change_pct")
        or params.get("percent") or params.get("pct")
    )
    is_bulk = bool(params.get("bulk") or params.get("is_bulk"))
    return ActIntent(
        action_category=str(category),
        amount_usd=amount_usd,
        amount_pct=amount_pct,
        counterparty_trust=signal_trust,
        is_bulk=is_bulk,
        tool_id=target.get("tool_id"),
    )


def _head_step(move: Any) -> dict[str, Any]:
    plan = getattr(move, "plan_fragment", None)
    if isinstance(plan, list) and plan and isinstance(plan[0], dict):
        return plan[0]
    payload = getattr(move, "payload", None)
    if isinstance(payload, dict):
        return payload
    return {}


def _step_params(step: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    for key in ("input_parameters", "parameters", "params", "input_data"):
        val = step.get(key) if isinstance(step, dict) else None
        if isinstance(val, dict):
            return val
        val = target.get(key) if isinstance(target, dict) else None
        if isinstance(val, dict):
            return val
    return {}


@dataclass
class PolicyGate:
    """Runtime wrapper: evaluate + perform the HITL/pause side effects.

    Constructed cheaply in the AgentLoop's ``_compose`` and called before the
    Pre-Critic. Enforcement is unconditional — it does *not* sit behind the
    critic-v2 flag, because governance must never be flag-OFF on the sellable
    path (roadmap standing rule 1).
    """
    db: Any
    redis: Any = None
    mandatory_note: str = field(default="", repr=False)

    async def evaluate(self, move: Any, entity: Any, signal_trust: Optional[str]) -> GateDecision:
        gov = _governance_from_entity(entity)
        intent = intent_from_move(move, entity, signal_trust)
        return evaluate_policy(intent, gov)

    async def raise_hitl(self, run_id: Any, decision: GateDecision) -> Any:
        """Create the HITL approval row + publish the pause event (shipped flow)."""
        from src.ai.orm.execution import HumanApproval

        approval = HumanApproval(
            run_id=run_id,
            checkpoint_trigger=f"policy:{decision.category}",
            checkpoint_key=decision.checkpoint_key,
            status="PENDING",
            requested_by="policy_gate",
            context_snapshot={
                "category": decision.category,
                "reason": decision.reason,
                "band": decision.band,
                "hard_block": decision.hard_block,
                # VG-05: the human tier gate reads amount+band off this snapshot
                # to classify the approval. Without the amount a high-impact
                # category fails up to T3 by artifact rather than by policy.
                "amount": decision.amount,
                "message": f"PolicyGate: {decision.reason}",
            },
        )
        self.db.add(approval)
        await self.db.commit()
        await self.db.refresh(approval)
        await self._publish_pause(run_id, approval, decision)
        return approval

    async def _publish_pause(self, run_id: Any, approval: Any, decision: GateDecision) -> None:
        if self.redis is None:
            return
        try:
            import json
            await self.redis.publish(
                f"execution:{run_id}",
                json.dumps({
                    "status": "HITL_PENDING",
                    "approval_id": str(approval.id),
                    "checkpoint_key": decision.checkpoint_key,
                    "trigger": f"policy:{decision.category}",
                    "message": f"PolicyGate: {decision.reason}",
                }),
            )
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            logger.debug("policy pause publish skipped: %s", exc)


async def gate_and_maybe_stop(
    gate: PolicyGate, move: Any, entity: Any, state: Any,
) -> bool:
    """Run the gate before the pre-critic; apply BLOCK/RAISE_HITL to ``state``.

    Returns True when the run must stop this iteration. Lives here (not in the
    AgentLoop) so governance orchestration is one testable unit and the loop
    stays thin. Signal trust (§18.6) is read from the run input the loop seeds
    into ``context_state``. Fail-open on evaluation error — a gate bug must not
    wedge runs; the save-time validator is the front-line guard on bad config.
    """
    from src.ai.core.agent_loop_sse import event_async

    run_id = getattr(state, "run_id", None)
    sig = state.context_state.get("signal") if isinstance(
        getattr(state, "context_state", None), dict) else None
    signal_trust = sig.get("trust") if isinstance(sig, dict) else None

    try:
        decision = await gate.evaluate(move, entity, signal_trust)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PolicyGate evaluation failed (fail-open to critics): %s", exc)
        return False
    if decision.decision == PASS:
        return False

    if isinstance(getattr(state, "context_state", None), dict):
        state.context_state["policy_gate"] = {
            "decision": decision.decision,
            "category": decision.category,
            "checkpoint_key": decision.checkpoint_key,
            "reason": decision.reason,
        }

    if decision.decision == BLOCK:
        await event_async(
            "agent.policy.block", run_id=str(run_id),
            iteration=getattr(state, "iteration", None),
            category=decision.category, checkpoint_key=decision.checkpoint_key,
            reason=decision.reason,
        )
        state.done = True
        state.next_decision = "ABORT"
        return True

    # RAISE_HITL
    try:
        await gate.raise_hitl(run_id, decision)
    except Exception as exc:  # noqa: BLE001
        logger.error("PolicyGate HITL raise failed: %s", exc)
    await event_async(
        "agent.policy.hitl", run_id=str(run_id),
        iteration=getattr(state, "iteration", None),
        category=decision.category, checkpoint_key=decision.checkpoint_key,
        reason=decision.reason,
    )
    state.done = True
    state.next_decision = "PAUSE_HITL"
    return True
