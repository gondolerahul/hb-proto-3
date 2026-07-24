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
from typing import Any
from uuid import UUID

from src.ai.intelligence.types import RoutingSignals

__all__ = ["Candidate", "utility", "capability_fit", "cost_pressure"]

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


def capability_fit(profile: dict[str, Any], complexity: float, needs_tools: bool) -> float:
    """1.0 when the model comfortably meets the step's demand; penalized when it
    is under-powered for the complexity, or unreliable with tools when tools are
    needed. Over-powering is not penalized (that is the cost term's job)."""
    reasoning = float(profile.get("reasoning_strength", 0.5))
    fit = 1.0 - max(0.0, complexity - reasoning)   # under-powered → penalty
    if needs_tools:
        fit *= float(profile.get("tool_reliability", 0.5))
    return max(0.0, min(1.0, fit))


def utility(candidate: Candidate, complexity: float, signals: RoutingSignals) -> float:
    """Higher is better: capability-fit minus cost, cost weighted by pressure."""
    fit = capability_fit(candidate.capability_profile, complexity, signals.needs_tools)
    cost_term = candidate.cost_proxy * cost_pressure(signals)
    return _W_FIT * fit - _W_COST * cost_term
