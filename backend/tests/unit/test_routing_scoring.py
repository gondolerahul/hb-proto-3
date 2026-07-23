"""Inc 5 / RTR v2 — the heuristic scorer (unit, no DB).

The complexity score and the utility function are pure — this is their golden
gate: task-class ordering, monotonicity (demand never lowers the score), the
strict-latency clamp, and the conservative-at-neutral / downshift-under-pressure
selection behaviour.
"""
from __future__ import annotations

from uuid import uuid4

from src.ai.intelligence.complexity import score
from src.ai.intelligence.fallback import is_retryable
from src.ai.intelligence.scoring import Candidate, capability_fit, cost_pressure, utility
from src.ai.intelligence.types import RoutingSignals


def _sig(**kw) -> RoutingSignals:
    return RoutingSignals(task_type=kw.pop("task_type", "text_generation"), **kw)


# --- complexity.score -------------------------------------------------------

def test_task_class_ordering() -> None:
    assert score(_sig(task_type="thinking")) > score(_sig(task_type="text_generation"))
    assert score(_sig(task_type="text_generation")) > score(_sig(task_type="embedding"))


def test_complexity_is_monotone_in_demand() -> None:
    base = score(_sig(task_type="text_generation"))
    assert score(_sig(task_type="text_generation", needs_tools=True)) >= base
    assert score(_sig(task_type="text_generation", context_tokens=200_000)) >= base
    # Adding both never lowers it below either.
    both = score(_sig(task_type="text_generation", needs_tools=True, context_tokens=200_000))
    assert both >= base


def test_strict_latency_caps_the_score() -> None:
    hard = _sig(task_type="thinking", needs_tools=True, context_tokens=200_000)
    assert score(hard) > 0.5
    strict = _sig(task_type="thinking", needs_tools=True, context_tokens=200_000, latency_class="strict")
    assert score(strict) <= 0.5   # a live turn can't wait for a reasoning model


def test_score_is_bounded() -> None:
    for tt in ("thinking", "text_generation", "embedding", "unknown_task"):
        s = score(_sig(task_type=tt, needs_tools=True, context_tokens=500_000))
        assert 0.0 <= s <= 1.0


# --- scoring ----------------------------------------------------------------

def test_capability_fit_penalizes_underpowered_models() -> None:
    strong = {"reasoning_strength": 0.95, "tool_reliability": 0.9}
    weak = {"reasoning_strength": 0.4, "tool_reliability": 0.9}
    # For a hard step, the strong model fits better than the weak one.
    assert capability_fit(strong, 0.9, False) > capability_fit(weak, 0.9, False)
    # For an easy step, both fit well.
    assert capability_fit(weak, 0.2, False) >= 0.99


def test_needs_tools_weights_tool_reliability() -> None:
    reliable = {"reasoning_strength": 0.8, "tool_reliability": 0.95}
    flaky = {"reasoning_strength": 0.8, "tool_reliability": 0.3}
    assert capability_fit(reliable, 0.5, True) > capability_fit(flaky, 0.5, True)


def test_cost_pressure_rises_as_headroom_shrinks() -> None:
    assert cost_pressure(_sig(wallet_headroom_usd=None)) == 1.0
    assert cost_pressure(_sig(wallet_headroom_usd=100.0)) == 1.0
    assert cost_pressure(_sig(wallet_headroom_usd=5.0)) > 1.0
    assert cost_pressure(_sig(wallet_headroom_usd=0.0)) > cost_pressure(_sig(wallet_headroom_usd=5.0))


def _cand(reasoning: float, cost: float) -> Candidate:
    return Candidate(
        integration_id=uuid4(), model_name=f"m{reasoning}", provider="p",
        model_registry_id=uuid4(),
        capability_profile={"reasoning_strength": reasoning, "tool_reliability": 0.9},
        cost_proxy=cost,
    )


def test_neutral_wallet_prefers_the_capable_model() -> None:
    """Conservative by default: at neutral headroom a capable model out-scores a
    cheaper weaker one on a hard step — no gratuitous downshift."""
    capable = _cand(0.95, 0.09)   # expensive, strong
    cheap = _cand(0.55, 0.005)    # cheap, weak
    sig = _sig(task_type="thinking", wallet_headroom_usd=None)
    assert utility(capable, 0.85, sig) > utility(cheap, 0.85, sig)


def test_tight_wallet_downshifts_to_the_cheaper_model() -> None:
    """Under pressure the same hard step routes to the cheaper tier before failing."""
    capable = _cand(0.95, 0.09)
    cheap = _cand(0.55, 0.005)
    sig = _sig(task_type="thinking", wallet_headroom_usd=0.0)   # empty wallet
    assert utility(cheap, 0.85, sig) > utility(capable, 0.85, sig)


# --- fallback.is_retryable --------------------------------------------------

def test_provider_faults_are_retryable() -> None:
    for exc in (RuntimeError("429 rate limit exceeded"),
                Exception("503 Service Unavailable"),
                Exception("model is overloaded, try again"),
                TimeoutError("request timed out"),
                ConnectionError("connection reset")):
        assert is_retryable(exc), exc


def test_request_faults_are_not_retryable() -> None:
    for exc in (RuntimeError("Invalid API key"),
                Exception("401 Unauthorized"),
                Exception("400 Bad Request: malformed"),
                PermissionError("403 forbidden")):
        assert not is_retryable(exc), exc
