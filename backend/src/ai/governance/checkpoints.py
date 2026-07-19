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

__all__ = ["CHECKPOINT_SEED", "CHECKPOINT_KEYS", "MANDATORY_KEYS"]

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
]

CHECKPOINT_KEYS: frozenset[str] = frozenset(row["key"] for row in CHECKPOINT_SEED)
MANDATORY_KEYS: frozenset[str] = frozenset(
    row["key"] for row in CHECKPOINT_SEED if row["platform_mandatory"]
)

assert len(CHECKPOINT_SEED) == 18, "Blueprint §9.7 defines exactly 18 checkpoints"
