"""governance/checkpoints.py — the Blueprint §9.7 checkpoint catalog (18).

This is the reviewable seed fixture for `hitl_checkpoint_defs`. Each row:
  key                 — stable identifier, referenced by governance.checkpoint_keys
  category            — the §9.3 authority category it guards (or "governance")
  description         — human-facing reason
  default_threshold   — band above which it fires; None = always fires
  threshold_unit      — "usd" | "pct" | None
  platform_mandatory  — cannot be removed from an entity's opt-in set

The five originals (v1) are marked; the other 13 were added in Blueprint v2.
Thresholds mirror the §9.3 authority-matrix defaults (tenant-tunable per
entity via the governance block's authority bands).
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "CHECKPOINT_SEED", "CHECKPOINT_KEYS", "MANDATORY_KEYS",
    "OnTimeout", "sla_for_category",
]


class OnTimeout:
    """What happens when a checkpoint's SLA elapses with no human decision."""

    AUTO_PARK = "auto_park"    # non-destructive: re-raise on the next sweep
    AUTO_DENY = "auto_deny"    # fail safe: deny the act (money/irreversible)
    ESCALATE = "escalate"      # keep pending, notify louder (needs a human)


# Per-category SLA policy (C3, §9.7): a payment can't wait the way a marketing
# email can, and silence on money must fail safe — not proceed. Money/binding
# categories auto-deny; outbound comms auto-park (re-raise); high-stakes
# governance/HR escalate. Seconds.
_CATEGORY_SLA: dict[str, tuple[int, str]] = {
    "payout": (14400, OnTimeout.AUTO_DENY),          # 4h
    "refund": (14400, OnTimeout.AUTO_DENY),          # 4h
    "contract": (28800, OnTimeout.AUTO_DENY),        # 8h
    "vendor_creation": (28800, OnTimeout.AUTO_DENY),  # 8h
    "price_change": (28800, OnTimeout.AUTO_DENY),    # 8h
    "data_deletion": (86400, OnTimeout.AUTO_DENY),   # 24h — irreversible
    "email": (86400, OnTimeout.AUTO_PARK),           # 24h — a draft can wait
    "external_write": (86400, OnTimeout.AUTO_PARK),  # 24h — a write-back can park + re-raise
    "public_statement": (86400, OnTimeout.AUTO_PARK),  # 24h
    "discount": (86400, OnTimeout.AUTO_PARK),        # 24h
    "governance": (172800, OnTimeout.ESCALATE),      # 48h
    "employment_offer": (172800, OnTimeout.ESCALATE),  # 48h
    "regulatory_filing": (172800, OnTimeout.ESCALATE),  # 48h
}
_DEFAULT_SLA: tuple[int, str] = (86400, OnTimeout.ESCALATE)


def sla_for_category(category: str) -> tuple[int, str]:
    """(sla_seconds, on_timeout) for a checkpoint category — the C3 policy."""
    return _CATEGORY_SLA.get(category, _DEFAULT_SLA)

# key, category, description, default_threshold, threshold_unit, platform_mandatory
CHECKPOINT_SEED: list[dict[str, Any]] = [
    # ── The five originals (Blueprint v1) ─────────────────────────────
    {"key": "before_high_value_email_dispatch", "category": "email",
     "description": "Sending a high-value or externally-binding email.",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": False},
    {"key": "before_contract_esignature_routing", "category": "contract",
     "description": "Routing a contract for e-signature.",
     "default_threshold": 2000.0, "threshold_unit": "usd", "platform_mandatory": False},
    {"key": "before_outbound_payout_above_band", "category": "payout",
     "description": "An outbound payment/payout above the autonomous band.",
     "default_threshold": 500.0, "threshold_unit": "usd", "platform_mandatory": True},
    {"key": "before_high_liability_clause_acceptance", "category": "contract",
     "description": "Accepting a high-liability or non-standard contract clause.",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": True},
    {"key": "before_self_evolving_code_promotion", "category": "governance",
     "description": "Promoting self-evolved code/instructions affecting an entity.",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": True},
    # ── The thirteen added in Blueprint v2 ────────────────────────────
    {"key": "before_public_statement", "category": "public_statement",
     "description": "Issuing a public statement or PR communication.",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": False},
    {"key": "before_regulatory_filing", "category": "regulatory_filing",
     "description": "Submitting a regulatory filing (draft-only is autonomous).",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": True},
    {"key": "before_employment_offer", "category": "employment_offer",
     "description": "Extending an employment offer.",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": True},
    {"key": "before_termination_or_offboarding_action", "category": "employment_offer",
     "description": "A termination or offboarding action.",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": True},
    {"key": "before_price_change_beyond_band", "category": "price_change",
     "description": "A price change beyond the experiment band.",
     "default_threshold": 5.0, "threshold_unit": "pct", "platform_mandatory": False},
    {"key": "before_bulk_data_deletion", "category": "data_deletion",
     "description": "Bulk or ambiguous data deletion (DSAR).",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": True},
    {"key": "before_bank_detail_change_acceptance", "category": "payout",
     "description": "Accepting a counterparty bank-detail change.",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": True},
    {"key": "before_vendor_activation_on_kyb_flags", "category": "vendor_creation",
     "description": "Activating a vendor with KYB flags or above exposure.",
     "default_threshold": 1000.0, "threshold_unit": "usd", "platform_mandatory": False},
    {"key": "before_refund_above_band", "category": "refund",
     "description": "A refund/credit note above the autonomous band.",
     "default_threshold": 200.0, "threshold_unit": "usd", "platform_mandatory": False},
    {"key": "before_discount_above_band", "category": "discount",
     "description": "A discount above the autonomous band.",
     "default_threshold": 10.0, "threshold_unit": "pct", "platform_mandatory": False},
    {"key": "before_incident_public_disclosure", "category": "public_statement",
     "description": "Publicly disclosing an incident.",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": True},
    {"key": "before_autonomy_level_promotion", "category": "governance",
     "description": "Raising an entity's autonomy level (§9.7 evidence-gated).",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": True},
    {"key": "before_new_channel_binding", "category": "governance",
     "description": "Binding a new external channel to an entity.",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": False},
    # ── The 19th, added by Increment 4 / CONN+SOR ─────────────────────
    # Writing back to an external system of record (§21) is an act class the
    # original 18 (all internal decisions) did not contemplate. Not mandatory:
    # a tenant at A2+ syncs autonomously; at A1 every external effect is a card.
    {"key": "before_external_system_write", "category": "external_write",
     "description": "Writing back to an external system of record via a connector (SOR, §21).",
     "default_threshold": None, "threshold_unit": None, "platform_mandatory": False},
]

# Stamp each row with its per-category SLA (C3) so the seed carries sla_seconds
# + on_timeout and the migration backfills them.
for _row in CHECKPOINT_SEED:
    _sla_seconds, _on_timeout = sla_for_category(str(_row["category"]))
    _row["sla_seconds"] = _sla_seconds
    _row["on_timeout"] = _on_timeout

CHECKPOINT_KEYS: frozenset[str] = frozenset(row["key"] for row in CHECKPOINT_SEED)
MANDATORY_KEYS: frozenset[str] = frozenset(
    row["key"] for row in CHECKPOINT_SEED if row["platform_mandatory"]
)

assert len(CHECKPOINT_SEED) == 19, (
    "Blueprint §9.7 defines 18 checkpoints; Increment 4 / CONN+SOR adds the "
    "19th (before_external_system_write) for external system-of-record write-back"
)
