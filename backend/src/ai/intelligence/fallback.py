"""intelligence/fallback.py — retryable-provider-error classification (RTR v2, T5).

When a routed call hits a *provider* problem — a rate limit, a 5xx, an
overload, a timeout — the router should try the next-best eligible model rather
than fail the step. But a *request* problem — a bad API key, a malformed
request, a permission error — will recur on any model, so it must propagate.

This is the pure classifier; ``router.reroute`` picks the next candidate and
``LLMRouter.call_llm`` drives the bounded retry. Kept a heuristic over the
exception's type + message because the provider adapters raise varied SDK
exception types.

Design: increment-5/02_router.md §6.
"""
from __future__ import annotations

__all__ = ["is_retryable"]

# A request-level fault recurs on every model — never worth a re-route.
_NON_RETRYABLE = (
    "api key", "api_key", "unauthorized", "auth", "permission", "forbidden",
    "invalid request", "invalid_request", "bad request", "not found",
    "400", "401", "403", "404",
)

# A provider-level fault is worth trying the next model for.
_RETRYABLE = (
    "rate limit", "rate_limit", "ratelimit", "429",
    "500", "502", "503", "internal server", "bad gateway", "unavailable",
    "overloaded", "capacity", "timeout", "timed out", "deadline",
    "connection", "connect error", "temporarily",
)


def is_retryable(exc: BaseException) -> bool:
    """True when trying the next-best model is warranted (a provider fault),
    False for request faults that would recur on any model."""
    hay = f"{type(exc).__name__} {exc}".lower()
    if any(marker in hay for marker in _NON_RETRYABLE):
        return False
    return any(marker in hay for marker in _RETRYABLE)
