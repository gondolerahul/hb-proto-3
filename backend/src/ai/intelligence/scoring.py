"""intelligence/scoring.py — candidate utility (RTR v2, T4).

Scores each eligible candidate on **capability-fit vs cost**, biased by wallet
pressure. Deliberately conservative: at neutral wallet, capability-fit dominates
so the router does **not** downshift a capable model just to save pennies; only
as headroom tightens does the cost term take over — the "downshift before
failing" behaviour (§5.3–.4).

Pure functions over a ``Candidate`` (a company-credentialed, catalog-eligible
model) — the DB resolution lives in ``router._candidates``.

Design: increment-5/02_router.md §5.2, §5.3.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from src.ai.intelligence.types import RoutingSignals

__all__ = ["Candidate", "utility", "capability_fit", "cost_pressure",
           "blend_reliability"]

# Utility weights. W_COST is intentionally modest so that at neutral pressure a
# capable model out-scores a cheaper weaker one; cost_pressure (below) is what
# lets cost dominate when the wallet is tight.
_W_FIT = 1.0
_W_COST = 2.0


@dataclass(frozen=True)
class Candidate:
    integration_id: UUID              # the company's binding (credentials)
    model_name: str
    provider: str
    model_registry_id: UUID
    capability_profile: dict[str, Any]
    cost_proxy: float                 # blended per-1k price (input+output) for ranking


def cost_pressure(signals: RoutingSignals) -> float:
    """1.0 = neutral; rises as wallet headroom shrinks or a cost ceiling bites."""
    p = 1.0
    h = signals.wallet_headroom_usd
    if h is not None:
        if h <= 0.0:
            p = 4.0
        elif h < 1.0:
            p = 2.5
        elif h < 10.0:
            p = 1.5
    c = signals.cost_ceiling_usd
    if c is not None and c <= 0.01:
        p = max(p, 2.0)
    return p


def blend_reliability(
    declared: float, observed: float | None, *, weight: float,
) -> float:
    """Correct a declared reliability by what the fleet was observed doing (LEARN T9).

    Pure, and **bounded on purpose**: the result moves at most ``weight`` away
    from the declaration, so a bad week cannot invert the router's ordering. A
    model that is genuinely bad is removed by EVX admission — score drift is the
    wrong instrument for that, because it is gradual, silent and reversible by
    the next quiet fortnight.

    ``observed is None`` means the pooled store had too few samples for this
    model (or none at all, which is the state right after deploy). Then the
    declaration stands unmodified, which is the correct default: a declaration
    is real information, and an absent observation is not evidence against it.
    """
    if observed is None or weight <= 0.0:
        return declared
    delta = max(-weight, min(weight, observed - declared))
    return max(0.0, min(1.0, declared + delta))


def capability_fit(
    profile: dict[str, Any],
    complexity: float,
    needs_tools: bool,
    *,
    observed_reliability: float | None = None,
    observation_weight: float = 0.0,
) -> float:
    """1.0 when the model comfortably meets the step's demand; penalized when it
    is under-powered for the complexity, or unreliable with tools when tools are
    needed. Over-powering is not penalized (that is the cost term's job).

    ``observed_reliability`` corrects the *declared* ``tool_reliability`` within
    ``observation_weight`` (LEARN T9). Both default to no correction, so every
    existing caller and the whole un-routed path behave exactly as before —
    which is what keeps the parity suite honest about this change.
    """
    reasoning = float(profile.get("reasoning_strength", 0.5))
    fit = 1.0 - max(0.0, complexity - reasoning)   # under-powered → penalty
    if needs_tools:
        declared = float(profile.get("tool_reliability", 0.5))
        fit *= blend_reliability(
            declared, observed_reliability, weight=observation_weight)
    return max(0.0, min(1.0, fit))


def utility(
    candidate: Candidate,
    complexity: float,
    signals: RoutingSignals,
    *,
    observed: Mapping[UUID, float] | None = None,
    observation_weight: float = 0.0,
) -> float:
    """Higher is better: capability-fit minus cost, cost weighted by pressure."""
    fit = capability_fit(
        candidate.capability_profile, complexity, signals.needs_tools,
        observed_reliability=(observed or {}).get(candidate.model_registry_id),
        observation_weight=observation_weight)
    cost_term = candidate.cost_proxy * cost_pressure(signals)
    return _W_FIT * fit - _W_COST * cost_term
