"""schemas/governance.py — Governance, HITL checkpoints, execution limits.

Increment 1 / GOV (technical doc §20.1): the `governance` JSON column on
`hierarchical_entities` gains a Pydantic-validated business-governance block
— the Blueprint §9 constructs (autonomy ladder, authority matrix, SoD class,
Karuna profile, checkpoint opt-ins, budget envelope ref, memory domains) as
typed fields an LLM cannot silently malform. Validation runs at the API
boundary (entity create/update type `governance: Optional[Governance]`), so a
bad value fails the save with a 422.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from src.ai.schemas.enums import HITLTriggerType

__all__ = [
    "ExecutionLimits",
    "HITLCheckpoint",
    "Governance",
    "AutonomyLevel",
    "SoDClass",
    "AuthorityBands",
    "BudgetRef",
]


class AutonomyLevel(str, Enum):
    """The A0–A4 autonomy ladder (Blueprint §9.2). Raised per entity on
    evidence (§9.7), never globally; A1 is the platform default."""
    A0 = "A0"   # Observe — reads/analyses/drafts; nothing leaves the loop
    A1 = "A1"   # Propose — a human approves every external effect
    A2 = "A2"   # Act with exceptions — autonomous inside the authority matrix
    A3 = "A3"   # Act with audit — autonomous in scope; sampled, not queued
    A4 = "A4"   # Self-modify — A3 + may accept self-evolved changes to itself


class SoDClass(str, Enum):
    """Segregation-of-duties role for deploy-time conflict checks (§9.4)."""
    MAKER = "maker"
    CHECKER = "checker"
    AUDITOR = "auditor"
    NONE = "none"


class AuthorityBands(BaseModel):
    """Value bands per action category (Blueprint §9.3 authority matrix).

    Absent bands mean "unset" — the PolicyGate passes monetary actions
    through until Inc 2 seeds real bands (decision 2026-07-19). All amounts
    are the *autonomous-up-to* ceilings; above them the gate raises HITL.
    """
    model_config = ConfigDict(extra="allow")

    payout_usd: Optional[float] = None
    refund_usd: Optional[float] = None
    discount_pct: Optional[float] = None
    contract_tcv_usd: Optional[float] = None
    price_change_pct: Optional[float] = None
    vendor_exposure_usd: Optional[float] = None


class BudgetRef(BaseModel):
    model_config = ConfigDict(extra="allow")
    envelope_ref: Optional[str] = None


class ExecutionLimits(BaseModel):
    max_recursion_depth: int = 5
    max_tool_calls: Optional[int] = None


class HITLCheckpoint(BaseModel):
    """A user-configured checkpoint that pauses execution for human approval.

    This is the shipped *structured* checkpoint config (BEFORE_STEP / TOOL_CALL
    / COST_THRESHOLD / CUSTOM). Distinct from the GOV registry opt-in list
    (`checkpoint_keys`), which names platform checkpoint keys from
    `hitl_checkpoint_defs`.
    """
    trigger_type: HITLTriggerType
    step_ref: Optional[str] = None           # For BEFORE_STEP/AFTER_STEP: step name or step_id
    tool_ref: Optional[str] = None           # For TOOL_CALL: tool_id to gate
    threshold: Optional[float] = None        # For COST_THRESHOLD: USD amount that triggers pause
    expression: Optional[str] = None         # For CUSTOM: a Python-like boolean expression
    timeout_ms: int = 300000                 # How long to wait for approval (default 5 min)
    notification_channels: List[str] = []    # e.g. ["email", "slack", "dashboard"]
    message: Optional[str] = None            # Custom message shown to the reviewer
    auto_approve_on_timeout: bool = False    # If True, auto-approve when timeout expires


class Governance(BaseModel):
    """The entity governance block.

    ``extra="allow"`` preserves kernel-consumed keys not yet modelled here
    (breaker settings, etc.) instead of silently dropping them on save — the
    typed fields below are validated strictly, everything else passes through.
    Tightening to ``extra="forbid"`` follows a full field audit (Inc 2).
    """
    model_config = ConfigDict(extra="allow")

    # ── Shipped kernel fields (retained) ──────────────────────────────
    max_cost_usd: Optional[float] = None
    timeout_ms: int = 60000
    max_recursion_depth: int = 5
    max_concurrent_children: Optional[int] = None
    execution_limits: Optional[ExecutionLimits] = None
    hitl_checkpoints: List[HITLCheckpoint] = []

    # ── Business-governance block (Increment 1 / GOV, §20.1) ───────────
    autonomy_level: AutonomyLevel = AutonomyLevel.A1
    authority: Optional[AuthorityBands] = None
    sod_class: SoDClass = SoDClass.NONE
    karuna_profile: bool = False
    checkpoint_keys: List[str] = []          # opt-in keys from hitl_checkpoint_defs
    budget: Optional[BudgetRef] = None
    memory_domains: Optional[List[str]] = None   # need-to-know viewport allow-list (§24.3)
