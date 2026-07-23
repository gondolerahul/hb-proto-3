"""intelligence/complexity.py — the heuristic step-complexity score (RTR v2, T3).

Decision (Overview §2.3): heuristic-first — deterministic, no per-step model
call, testable with a golden set. A single 0..1 score from signals available at
the ``call_llm`` seam. Legible on purpose: a routing decision that spends a
customer's wallet must be explainable.

The score is **monotone** in demand — adding tools or context never lowers it —
with one clamp: a ``strict``-latency turn (live voice) is capped, because it
cannot wait for a reasoning model regardless of how hard the step is (§5.3).

Design: increment-5/02_router.md §5.1.
"""
from __future__ import annotations

from src.ai.intelligence.types import RoutingSignals

__all__ = ["score", "TASK_COMPLEXITY_PRIOR"]

# The base prior per task type actually seen at the seam. "thinking"/"reasoning"
# are extended-deliberation tasks; "text_generation" is the workhorse;
# "embedding" is mechanical.
TASK_COMPLEXITY_PRIOR: dict[str, float] = {
    "thinking": 0.85,
    "reasoning": 0.85,
    "goal_validation": 0.70,   # critic-like verification
    "text_generation": 0.50,
    "embedding": 0.10,
}
_DEFAULT_PRIOR = 0.50

# A strict-latency (live voice) turn is treated as at-most-moderate so the router
# never routes it to a slow reasoning tier.
_STRICT_LATENCY_CAP = 0.50


def score(signals: RoutingSignals) -> float:
    """Return a 0..1 complexity score for a step."""
    s = TASK_COMPLEXITY_PRIOR.get(signals.task_type, _DEFAULT_PRIOR)

    # Tool orchestration raises the demand (reliability matters).
    if signals.needs_tools:
        s += 0.10

    # Long-context synthesis is harder.
    if signals.context_tokens > 100_000:
        s += 0.10
    elif signals.context_tokens > 32_000:
        s += 0.05

    s = min(1.0, s)

    # The clamp: a live turn can't afford a reasoning model however hard it is.
    if signals.latency_class == "strict":
        s = min(s, _STRICT_LATENCY_CAP)

    return max(0.0, s)
