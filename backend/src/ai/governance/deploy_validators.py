"""governance/deploy_validators.py — deploy-time governance checks (§20.5).

Three pure checks that **fail closed**, shared by the Meta-Agent Board
Validator and the manual entity-publish path:

  1. Karuna gate      — an externally-bound entity must carry karuna_profile.
  2. SoD conflicts    — the five Blueprint §9.4 rules as capability-tag pairs
                        that may not coexist on one entity.
  3. Autonomy caps    — a new/published entity may not exceed A1; raises route
                        through the before_autonomy_level_promotion checkpoint.

Each returns ``(name, passed, reason)`` so both call sites can adapt it to
their own result type.
"""
from __future__ import annotations

from typing import Any

from src.ai.schemas.governance import AutonomyLevel

__all__ = [
    "SOD_CONFLICT_TAGS",
    "check_karuna_gate",
    "check_sod_conflicts",
    "check_autonomy_cap",
    "run_governance_deploy_checks",
]

# The five §9.4 SoD rules as capability-tag pairs that must not coexist on a
# single entity. Entities declare their tags in ``capabilities.sod_tags``.
SOD_CONFLICT_TAGS: list[frozenset[str]] = [
    frozenset({"financial_maker", "financial_checker"}),   # maker ≠ checker
    frozenset({"vendor_create", "vendor_pay"}),            # onboarding ≠ payment
    frozenset({"access_grant", "access_use"}),             # granter ≠ user
    frozenset({"audit", "operate"}),                       # auditor independence
]
# Self-modification quarantine: no entity may promote code changes to itself
# outside the platform pipeline.
_SELF_PROMOTE_TAG = "self_promote"

# New entities may not be born above this ceiling (roadmap standing rule 4).
_NEW_ENTITY_AUTONOMY_CEILING = AutonomyLevel.A1
_AUTONOMY_ORDER = {lvl: i for i, lvl in enumerate(
    [AutonomyLevel.A0, AutonomyLevel.A1, AutonomyLevel.A2, AutonomyLevel.A3, AutonomyLevel.A4]
)}


def _governance(spec: dict[str, Any]) -> dict[str, Any]:
    gov = spec.get("governance")
    return gov if isinstance(gov, dict) else {}


def _capabilities(spec: dict[str, Any]) -> dict[str, Any]:
    caps = spec.get("capabilities")
    return caps if isinstance(caps, dict) else {}


def _has_external_binding(spec: dict[str, Any]) -> bool:
    """True when the entity binds an outward channel (voice/email/messaging)."""
    meta = spec.get("metadata_extensions")
    if isinstance(meta, dict):
        if meta.get("telephony_provider") or meta.get("whatsapp_provider"):
            return True
        if meta.get("voice_enabled") or meta.get("channel_bindings"):
            return True
    caps = _capabilities(spec)
    channels = caps.get("channels")
    if isinstance(channels, (list, tuple)) and channels:
        return True
    io = spec.get("io_contract")
    if isinstance(io, dict) and io.get("channels"):
        return True
    return False


def check_karuna_gate(spec: dict[str, Any]) -> tuple[str, bool, str]:
    if not _has_external_binding(spec):
        return ("karuna_gate", True, "")
    karuna = bool(_governance(spec).get("karuna_profile"))
    return (
        "karuna_gate",
        karuna,
        "" if karuna else "externally-bound entity must set governance.karuna_profile=true",
    )


def check_sod_conflicts(spec: dict[str, Any]) -> tuple[str, bool, str]:
    caps = _capabilities(spec)
    raw_tags = caps.get("sod_tags")
    tags = {str(t) for t in raw_tags} if isinstance(raw_tags, (list, tuple, set)) else set()

    if _SELF_PROMOTE_TAG in tags:
        return ("sod_conflicts", False,
                "self-modification quarantine: an entity may not carry 'self_promote'")

    for conflict in SOD_CONFLICT_TAGS:
        if conflict.issubset(tags):
            return ("sod_conflicts", False,
                    f"segregation-of-duties violation: {sorted(conflict)} on one entity")
    return ("sod_conflicts", True, "")


def check_autonomy_cap(spec: dict[str, Any]) -> tuple[str, bool, str]:
    raw = _governance(spec).get("autonomy_level", AutonomyLevel.A1.value)
    try:
        level = AutonomyLevel(str(raw))
    except ValueError:
        return ("autonomy_cap", False, f"unknown autonomy_level: {raw}")
    ceiling = _AUTONOMY_ORDER[_NEW_ENTITY_AUTONOMY_CEILING]
    if _AUTONOMY_ORDER[level] > ceiling:
        return ("autonomy_cap", False,
                f"new entity autonomy {level.value} exceeds ceiling "
                f"{_NEW_ENTITY_AUTONOMY_CEILING.value}; raise via "
                "before_autonomy_level_promotion")
    return ("autonomy_cap", True, "")


def run_governance_deploy_checks(spec: dict[str, Any]) -> list[tuple[str, bool, str]]:
    """All three checks; used by the manual publish path."""
    return [
        check_karuna_gate(spec),
        check_sod_conflicts(spec),
        check_autonomy_cap(spec),
    ]
