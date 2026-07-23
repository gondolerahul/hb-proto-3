"""Inc 5 / REG — the declared fleet catalog is well-formed (unit, no DB).

The catalog is code-resident data (like the connector catalog + Solo Pack
bundles), so a malformed row is a code bug caught here, not a runtime seed error.
"""
from __future__ import annotations

from decimal import Decimal

from src.ai.intelligence.catalog import FLEET
from src.ai.intelligence.models import ModelStatus

_CAP_KEYS = {"reasoning_strength", "tool_reliability", "max_context",
             "latency_class", "modalities", "supports_tools"}
_FLOW_KEYS = {"data_region", "subprocessor", "trains_on_customer_data", "default_allowed"}


def test_catalog_keys_are_unique() -> None:
    """(provider, model_name, version, region) is the uniqueness key — the same
    model in two regions is two rows, but no accidental duplicates."""
    keys = [(m.provider, m.model_name, m.version, m.region) for m in FLEET]
    assert len(keys) == len(set(keys)), "duplicate catalog identity"
    # model_key is the router-facing handle; it should be unique too.
    model_keys = [m.model_key for m in FLEET]
    assert len(model_keys) == len(set(model_keys)), "duplicate model_key"


def test_every_row_is_well_formed() -> None:
    for m in FLEET:
        assert m.capability_profile.keys() >= _CAP_KEYS, f"{m.model_key} capability_profile"
        assert m.data_flow.keys() >= _FLOW_KEYS, f"{m.model_key} data_flow"
        assert m.capability_profile["modalities"], f"{m.model_key} has no modality"
        assert m.capability_profile["latency_class"] in {"strict", "standard", "batch"}
        # A priced model needs both token components, and prices must be positive.
        comps = {p.component_type for p in m.prices}
        assert {"input_token", "output_token"} <= comps, f"{m.model_key} missing token price"
        assert all(isinstance(p.unit_price, Decimal) and p.unit_price > 0 for p in m.prices)


def test_shipped_fleet_is_active_and_default_allowed() -> None:
    """The shipped providers are the conservative-default set (D5): all live,
    all default-allowed. FLEET expansion adds preview/opt-in rows separately."""
    for m in FLEET:
        assert m.status == ModelStatus.ACTIVE, f"{m.model_key} not active"
        assert m.data_flow["default_allowed"] is True, f"{m.model_key} not default-allowed"
        assert m.data_flow["trains_on_customer_data"] is False, f"{m.model_key} trains on data"


def test_fleet_covers_a_reasoning_and_a_cheap_tier() -> None:
    """The router needs real choices: at least one strong-reasoning model and one
    cheap model, or downshift has nowhere to go."""
    strengths = [m.capability_profile["reasoning_strength"] for m in FLEET]
    assert max(strengths) >= 0.9, "no reasoning-tier model"
    assert min(strengths) <= 0.6, "no cheap/low-complexity-tier model"
