"""governance/authority.py — the Blueprint §9.3 authority matrix, as data.

The matrix is data an LLM cannot argue with: per action category, the
autonomous-up-to band (tenant-tunable via the entity's authority block), the
hard-block ceiling (platform default, absolute), and the checkpoint key the
gate raises. A step becomes a *categorised* act either by declaring
``action_category`` on its plan-step target, or by its ``tool_id`` mapping
here; everything else is uncategorised and the PolicyGate passes it through.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CategoryRule",
    "CATEGORY_RULES",
    "TOOL_CATEGORY_MAP",
    "HIGH_IMPACT_CATEGORIES",
    "category_for_tool",
]


@dataclass(frozen=True)
class CategoryRule:
    category: str
    checkpoint_key: str
    band_field: str | None      # AuthorityBands attribute; None → no amount band
    default_band: float | None  # platform default when the entity leaves it unset
    hard_block: float | None    # absolute ceiling; above → BLOCK regardless of autonomy
    unit: str                   # "usd" | "pct" | "none"
    always_hitl: bool = False    # category always needs a human (no autonomous path)


# The §9.3 matrix. "always_hitl" encodes the "—" autonomous cells (employment,
# public statements, regulatory filings) — no autonomous path exists.
CATEGORY_RULES: dict[str, CategoryRule] = {
    "payout": CategoryRule(
        "payout", "before_outbound_payout_above_band",
        "payout_usd", 500.0, 10000.0, "usd"),
    "refund": CategoryRule(
        "refund", "before_refund_above_band",
        "refund_usd", 200.0, 5000.0, "usd"),
    "discount": CategoryRule(
        "discount", "before_discount_above_band",
        "discount_pct", 10.0, 30.0, "pct"),
    "contract": CategoryRule(
        "contract", "before_contract_esignature_routing",
        "contract_tcv_usd", 2000.0, None, "usd"),
    "price_change": CategoryRule(
        "price_change", "before_price_change_beyond_band",
        "price_change_pct", 5.0, None, "pct"),
    "vendor_creation": CategoryRule(
        "vendor_creation", "before_vendor_activation_on_kyb_flags",
        "vendor_exposure_usd", 1000.0, None, "usd"),
    "data_deletion": CategoryRule(
        "data_deletion", "before_bulk_data_deletion",
        None, None, None, "none"),
    "employment_offer": CategoryRule(
        "employment_offer", "before_employment_offer",
        None, None, None, "none", always_hitl=True),
    "public_statement": CategoryRule(
        "public_statement", "before_public_statement",
        None, None, None, "none", always_hitl=True),
    "regulatory_filing": CategoryRule(
        "regulatory_filing", "before_regulatory_filing",
        None, None, None, "none", always_hitl=True),
    # Outbound comms (a quote/proposal email, a support reply): no amount band.
    # At A1 every external effect needs a human (→ HITL); at A2+ comms are
    # autonomous. This is what raises the Solo Pack's A1 quote-send card.
    "email_dispatch": CategoryRule(
        "email_dispatch", "before_high_value_email_dispatch",
        None, None, None, "none"),
    # SOR write-back (§21, Inc-4 CONN/SOR): mutating the tenant's *external*
    # system of record through a connector. A genuinely new act class the
    # original 18 checkpoints (all internal HireBuddha decisions) did not cover
    # — CONN adds the 19th. No amount band: at A1 every external effect is a
    # card, at A2+ it is autonomous comms (same shape as email_dispatch).
    "external_write": CategoryRule(
        "external_write", "before_external_system_write",
        None, None, None, "none"),
}

# Categories that a counterparty-trust triggering signal may not drive at all
# (§18.6 trust down-payment): money movement + binding commitments.
HIGH_IMPACT_CATEGORIES: frozenset[str] = frozenset(
    {"payout", "refund", "contract", "vendor_creation"}
)

# tool_id → action category seed. The shipped catalogue has no payout/refund
# tools yet (Inc 2/4 add them); this seed provides the mechanism and the few
# mappings that already resolve. Authored steps may instead declare
# ``action_category`` directly on the step target (takes precedence).
TOOL_CATEGORY_MAP: dict[str, str] = {
    # placeholders for the Solo Pack tools (Inc 2/4) — keyed by tool_id:
    "stripe_payout": "payout",
    "bank_transfer": "payout",
    "razorpay_payout": "payout",
    "issue_refund": "refund",
    "esign_contract": "contract",
    "docusign_send": "contract",
    # Outbound email — a categorised external effect (Inc-2 SLICE): a quote
    # send at A1 raises a HITL card; at A2+ it's autonomous comms.
    "send_email": "email_dispatch",
    "email_send": "email_dispatch",
    # Connector write-backs (Inc-4 CONN/SOR). Connector tools are qualified
    # ``mcp__<server>__<verb>``; these write verbs resolve by substring, while
    # read tools (get_/list_/search_) deliberately do NOT match — a mirror read
    # is not an external effect and stays uncategorised (PASS).
    "create_invoice": "external_write",
    "update_invoice": "external_write",
    "create_bill": "external_write",
    "record_payment": "external_write",
    "write_back": "external_write",
}


def category_for_tool(tool_id: str | None) -> str | None:
    """Resolve a tool_id to its action category (exact then substring)."""
    if not tool_id:
        return None
    if tool_id in TOOL_CATEGORY_MAP:
        return TOOL_CATEGORY_MAP[tool_id]
    low = tool_id.lower()
    for needle, category in TOOL_CATEGORY_MAP.items():
        if needle in low:
            return category
    return None
