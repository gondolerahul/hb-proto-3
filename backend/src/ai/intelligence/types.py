"""intelligence/types.py — the router's data types (RTR).

``RoutingSignals`` is what the router scores; ``ModelBinding`` is what it
returns. Both are frozen — a routing decision is a value, recorded verbatim.

The signal surface is deliberately what the ``LLMRouter.call_llm`` seam has
(task_type, wallet, optional caller hints), not a full PlanStep — the documented
consequence of the delegation placement (increment-5/02_router.md §1.1). v1
populates only ``task_type``; v2 fills complexity/wallet/latency from hints.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

__all__ = ["RoutingSignals", "ModelBinding"]


@dataclass(frozen=True)
class RoutingSignals:
    task_type: str
    complexity: float = 0.0            # 0..1, from complexity.score() — v1 leaves 0
    modality: str = "text"             # "text" | "vision" | "realtime_audio"
    needs_tools: bool = False
    context_tokens: int = 0
    latency_class: str = "standard"    # "strict" | "standard" | "batch"
    wallet_headroom_usd: float | None = None
    cost_ceiling_usd: float | None = None
    allow_list: tuple[str, ...] | None = None
    pinned_model: str | None = None


@dataclass(frozen=True)
class ModelBinding:
    integration_id: UUID               # the per-company binding that carries credentials
    model_name: str                    # the concrete SDK id handed to the adapter
    provider: str
    reason: str                        # "pinned" | "rule" | "auto" | "fallback" | "downshift"
    model_registry_id: UUID | None = None
    decision_id: UUID | None = None    # the routing_decisions row (for the usage-log link)
