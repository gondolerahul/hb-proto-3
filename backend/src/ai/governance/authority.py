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
    # Public broadcast (Inc-6 GATE, KAR-05): publishing to a public or
    # semi-public audience — a post, a public reply, an uploaded video. Shaped
    # like email_dispatch: no amount band, so at A1 every publish raises a card
    # and at A2+ it is autonomous comms. Deliberately *not* `public_statement`,
    # which is always_hitl and means a PR/incident statement — folding routine
    # marketing into it would make every scheduled post an approval.
    "broadcast": CategoryRule(
        "broadcast", "before_public_broadcast",
        None, None, None, "none"),
    # Ad spend (Inc-6 GATE): committing budget on an ad platform. Carries an
    # amount band like payout does, so a small boost is autonomous at A3 while
    # a large campaign is not. Separate from `broadcast` (GATE decision 1):
    # publishing and committing money are different acts, and merging them
    # would either under-govern spend or make every post cost an approval.
    "ad_spend": CategoryRule(
        "ad_spend", "before_ad_spend_above_band",
        "ad_spend_usd", 200.0, 5000.0, "usd"),
}

# Categories that a counterparty-trust triggering signal may not drive at all
# (§18.6 trust down-payment): money movement + binding commitments.
# `ad_spend` joins them (Inc-6 GATE decision 2): a hostile DM must not be able
# to drive money into an ad platform, for the same reason it cannot drive a
# payout. `broadcast` deliberately does NOT — a counterparty message prompting
# a public reply is ordinary support work, and the taint firewall already
# routes it through a human at the untrusted levels.
HIGH_IMPACT_CATEGORIES: frozenset[str] = frozenset(
    {"payout", "refund", "contract", "vendor_creation", "ad_spend"}
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
    # ── Social / ad platforms (Inc-6 GATE T2) ─────────────────────────
    # `src/ai/tools/social/` ships 64 tools across 16 platforms and not one was
    # categorised, so every public post and every ad-budget commitment resolved
    # to PASS at every autonomy band — including A1, where every categorised
    # external effect is supposed to raise a card.
    #
    # These are keyed **exactly**, not by substring, because the names collide
    # in ways substrings resolve wrongly: `youtube_ads_manage_ad_groups` writes
    # while `google_ads_get_ad_groups` reads, and one careless needle would
    # categorise a dashboard refresh or miss a campaign. Exactness costs
    # completeness, so completeness is what the totality test in
    # `tests/unit/test_gate_broadcast_categories.py` enforces: every tool under
    # `ai/tools/social/` must be mapped here or match a read pattern, and a new
    # one that is neither fails CI.
    #
    # Write verbs map, read verbs deliberately do not (the connector
    # precedent) — reading a platform's analytics is not an external effect,
    # and categorising it would turn every dashboard refresh into an approval.
    "facebook_create_post": "broadcast",
    "facebook_manage_comments": "broadcast",
    "instagram_publish_media": "broadcast",
    "instagram_manage_comments": "broadcast",
    "linkedin_create_post": "broadcast",
    "linkedin_manage_comments": "broadcast",
    "pinterest_create_pin": "broadcast",
    "pinterest_manage_boards": "broadcast",
    "quora_post_answer": "broadcast",
    "reddit_create_post": "broadcast",
    "reddit_manage_comments": "broadcast",
    "tiktok_publish_video": "broadcast",
    "tiktok_manage_comments": "broadcast",
    "twitter_create_post": "broadcast",
    "youtube_upload_video": "broadcast",
    "youtube_manage_comments": "broadcast",
    "youtube_manage_playlists": "broadcast",
    # Ad surfaces. `*_manage_audiences` maps to ad_spend rather than broadcast
    # because an audience is *who the money reaches* — and it is also where
    # T4's DNC check bites. Creatives, ad sets, ad squads, line items, keywords
    # and targeting all decide where committed budget goes, so they carry the
    # same band as creating the campaign.
    "google_ads_create_campaign": "ad_spend",
    "google_ads_manage_keywords": "ad_spend",
    "linkedin_ads_create_campaign": "ad_spend",
    "linkedin_ads_manage_audiences": "ad_spend",
    "linkedin_ads_manage_creatives": "ad_spend",
    "meta_ads_create_campaign": "ad_spend",
    "meta_ads_manage_adsets": "ad_spend",
    "meta_ads_manage_audiences": "ad_spend",
    "snapchat_ads_create_campaign": "ad_spend",
    "snapchat_ads_manage_ad_squads": "ad_spend",
    "snapchat_ads_manage_audiences": "ad_spend",
    "x_ads_create_campaign": "ad_spend",
    "x_ads_manage_audiences": "ad_spend",
    "x_ads_manage_line_items": "ad_spend",
    "youtube_ads_create_campaign": "ad_spend",
    "youtube_ads_manage_ad_groups": "ad_spend",
    "youtube_ads_manage_targeting": "ad_spend",
    # Two social tools that are outbound effects but not broadcasts. A DM is
    # person-addressed, so it is ordinary outbound comms (the same category the
    # SLICE gave `send_email`) and the person-addressed consent check applies
    # to it literally. Saving a lead into Sales Navigator mutates the tenant's
    # external system of record, which is Inc-4's category.
    "facebook_send_message": "email_dispatch",
    "linkedin_sales_save_lead": "external_write",
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
