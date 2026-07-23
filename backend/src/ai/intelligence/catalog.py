"""intelligence/catalog.py — the fleet as declared data (REG T2).

Hand-authored like the connector catalog (``connectors/catalog.py``) and the
Solo Pack bundles — code-resident data, not rows hand-inserted per environment.
``RegistryService.install_model_catalog`` upserts these idempotently at boot.

This module declares the **shipped providers** (Anthropic / Google / Azure-OpenAI),
all ``status='active'`` (already in production use) and ``default_allowed=True``
(the conservative-default set, D5). FLEET ([03](../../../docs/product-road-map/increment-5/03_fleet_expansion.md))
appends GLM / Qwen / Mistral rows as ``status='preview'`` and — for GLM/Qwen —
``default_allowed=False``, so a new provider is registered but never a router
candidate until the EVX admission gate flips it to ``active``.

Prices are **reference fleet prices** in USD per 1k tokens, opened as an
effective-dated window at ``PRICE_EPOCH``. They are approximate; the per-company
``IntegrationRegistry.internal_cost`` stays authoritative for an un-bound row.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from src.ai.intelligence.models import ModelStatus

__all__ = ["PriceSpec", "ModelSpec", "FLEET", "PRICE_EPOCH"]

# The initial effective-dated price window opens here. A later price change
# closes this window and opens a new one (never mutates it) — see
# RegistryService.install_model_catalog.
PRICE_EPOCH = datetime(2026, 1, 1)


@dataclass(frozen=True)
class PriceSpec:
    component_type: str            # "input_token" | "output_token" | ...
    unit_price: Decimal
    cost_unit: str = "1k_tokens"
    currency: str = "USD"


@dataclass(frozen=True)
class ModelSpec:
    model_key: str                 # router-facing family+profile key
    provider: str
    model_name: str                # concrete SDK id
    version: str
    region: str
    capability_profile: dict[str, Any]
    data_flow: dict[str, Any]
    status: str
    prices: tuple[PriceSpec, ...] = field(default_factory=tuple)


# --- helpers so every row's shape is uniform -------------------------------

def _cap(reasoning: float, tool: float, ctx: int, latency: str,
         modalities: tuple[str, ...], *, tools: bool = True) -> dict[str, Any]:
    return {
        "reasoning_strength": reasoning,
        "tool_reliability": tool,
        "max_context": ctx,
        "latency_class": latency,          # a model's *native* latency class
        "modalities": list(modalities),
        "supports_tools": tools,
    }


def _flow(data_region: str, subprocessor: str, trains: bool, default_allowed: bool) -> dict[str, Any]:
    return {
        "data_region": data_region,
        "subprocessor": subprocessor,
        "trains_on_customer_data": trains,
        "default_allowed": default_allowed,
    }


def _px(inp: str, out: str) -> tuple[PriceSpec, ...]:
    return (
        PriceSpec("input_token", Decimal(inp)),
        PriceSpec("output_token", Decimal(out)),
    )


_TEXT = ("text",)
_TEXT_VISION = ("text", "vision")


# --- the shipped fleet (all active, all default-allowed) -------------------

FLEET: tuple[ModelSpec, ...] = (
    # Anthropic — Claude on Vertex AI (us-east5). No training on API traffic.
    ModelSpec("claude-opus", "anthropic", "claude-opus-4-8", "4-8", "us-east5",
              _cap(0.95, 0.95, 200_000, "standard", _TEXT_VISION),
              _flow("us", "Anthropic (Google Vertex)", False, True),
              ModelStatus.ACTIVE, _px("0.015", "0.075")),
    ModelSpec("claude-sonnet", "anthropic", "claude-sonnet-4-5", "4-5", "us-east5",
              _cap(0.85, 0.92, 200_000, "standard", _TEXT_VISION),
              _flow("us", "Anthropic (Google Vertex)", False, True),
              ModelStatus.ACTIVE, _px("0.003", "0.015")),
    ModelSpec("claude-haiku", "anthropic", "claude-haiku-4-5", "4-5", "us-east5",
              _cap(0.65, 0.82, 200_000, "standard", _TEXT_VISION),
              _flow("us", "Anthropic (Google Vertex)", False, True),
              ModelStatus.ACTIVE, _px("0.0008", "0.004")),

    # Google — Gemini on Vertex AI (us-central1). No training on Vertex data.
    ModelSpec("gemini-pro", "google", "gemini-2.5-pro", "2.5", "us-central1",
              _cap(0.90, 0.85, 1_000_000, "standard", _TEXT_VISION),
              _flow("us", "Google (Vertex)", False, True),
              ModelStatus.ACTIVE, _px("0.00125", "0.010")),
    ModelSpec("gemini-flash", "google", "gemini-2.5-flash", "2.5", "us-central1",
              _cap(0.72, 0.80, 1_000_000, "standard", _TEXT_VISION),
              _flow("us", "Google (Vertex)", False, True),
              ModelStatus.ACTIVE, _px("0.0003", "0.0025")),
    ModelSpec("gemini-flash-lite", "google", "gemini-2.5-flash-lite", "2.5", "us-central1",
              _cap(0.50, 0.70, 1_000_000, "batch", _TEXT_VISION),
              _flow("us", "Google (Vertex)", False, True),
              ModelStatus.ACTIVE, _px("0.0001", "0.0004")),

    # OpenAI — GPT via Azure OpenAI. No training on Azure enterprise data.
    ModelSpec("gpt", "azure_openai", "gpt-5", "5", "global",
              _cap(0.90, 0.90, 400_000, "standard", _TEXT_VISION),
              _flow("us/eu (Azure region-pinned)", "Microsoft Azure OpenAI", False, True),
              ModelStatus.ACTIVE, _px("0.010", "0.030")),
    ModelSpec("gpt-mini", "azure_openai", "gpt-4o-mini", "4o", "global",
              _cap(0.55, 0.75, 128_000, "standard", _TEXT),
              _flow("us/eu (Azure region-pinned)", "Microsoft Azure OpenAI", False, True),
              ModelStatus.ACTIVE, _px("0.00015", "0.0006")),
)
