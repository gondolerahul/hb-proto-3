"""solo_pack/onboarding.py — the wizard step services (Pragya's Inc-3 stages).

The setup wizard is the Inc-2 stand-in for Pragya's HUB role. Each function here
is a wizard step **authored as the stage API Pragya drives in Inc 3** (decision
4), so Inc 3 is a UI swap over the same contract:

* ``list_bundles``          — step 4 picker: what can be activated.
* ``governance_preview``    — step 3: the A1 governance the bundle would seed.
* ``activate_for_company``  — step 4: seed it (over PACK's ``activate_bundle``).
* ``onboarding_status``     — step 5: what's live + where HITL cards land.

The React wizard + admin surfaces are a separate frontend track; this is the
backend contract they (and Pragya) call. Steps 1–2 (connect channels, upload KB)
wrap the shipped connection/document routers and are surfaced in the status.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.solo_pack.activation import ActivationResult, activate_bundle
from src.ai.solo_pack.bundles import BUNDLES, SOLO_PACK, bundle_by_key
from src.ai.solo_pack.templates import GATEWAYS, PROCESS_GROUPS, ProcessGroup

__all__ = [
    "list_bundles", "governance_preview", "activate_for_company", "onboarding_status",
]

CONSOLE_PATH = "/app/approvals"  # where PolicyGate HITL cards land


def _authored_groups(bundle_key: str) -> list[ProcessGroup]:
    """The Wave-0 process groups a bundle key would actually seed."""
    if bundle_key == SOLO_PACK:
        return list(PROCESS_GROUPS)
    bundle = bundle_by_key(bundle_key)
    if bundle is None:
        raise ValueError(f"unknown bundle: {bundle_key!r}")
    return [g for g in PROCESS_GROUPS if g.process_code in bundle.process_codes]


def list_bundles() -> list[dict[str, Any]]:
    """Step 4 picker: the Solo Pack default + the 7 starter bundles, each with the
    Wave-0 processes that activate now (bundles whose §2.1 processes are not yet
    authored show ``available_now: false``)."""
    out: list[dict[str, Any]] = [{
        "key": SOLO_PACK,
        "display_name": "Solo Pack (recommended)",
        "is_default": True,
        "available_now": True,
        "process_codes": [g.process_code for g in PROCESS_GROUPS],
        "agent_count": sum(len(g.agents) for g in PROCESS_GROUPS) + len(GATEWAYS),
    }]
    for bundle in BUNDLES:
        groups = [g for g in PROCESS_GROUPS if g.process_code in bundle.process_codes]
        out.append({
            "key": bundle.key,
            "display_name": bundle.display_name,
            "is_default": False,
            "available_now": len(groups) > 0,
            "process_codes": [g.process_code for g in groups],
            "all_processes": sorted(bundle.process_codes),  # full §2.1 membership
            "agent_count": sum(len(g.agents) for g in groups) + len(GATEWAYS),
        })
    return out


def _code_of(template: dict[str, Any]) -> Optional[str]:
    """The stable Blueprint code — from metadata (gateways/processes) or the
    ``agent_code:``/``process_code:`` tag (workforce agents)."""
    meta = template.get("metadata_extensions", {})
    code = meta.get("process_code") or meta.get("agent_code")
    if code:
        return str(code)
    for tag in template.get("tags", []):
        if isinstance(tag, str) and tag.startswith(("process_code:", "agent_code:")):
            return tag.split(":", 1)[1]
    return None


def _gov_summary(template: dict[str, Any]) -> dict[str, Any]:
    gov = template.get("governance", {})
    return {
        "name": template["name"],
        "display_name": template.get("display_name"),
        "code": _code_of(template),
        "type": template["type"],
        "autonomy_level": gov.get("autonomy_level"),
        "authority": gov.get("authority"),          # None for the money-less
        "checkpoint_keys": gov.get("checkpoint_keys", []),
        "sod_class": gov.get("sod_class", "none"),
        "memory_domains": gov.get("memory_domains", []),
    }


def governance_preview(bundle_key: str) -> dict[str, Any]:
    """Step 3: the A1 governance the bundle would seed — every entity's autonomy,
    authority bands, checkpoints, and SoD role, so the owner confirms before
    activating. Pure (computed from the curated templates), no tenant state."""
    groups = _authored_groups(bundle_key)
    return {
        "bundle": bundle_key,
        "autonomy_note": (
            "Every Solo Pack agent starts at A1 — each external effect raises a "
            "human-approval card. Raising autonomy is a governed checkpoint "
            "(before_autonomy_level_promotion), not a wizard toggle."
        ),
        "gateways": [_gov_summary(g) for g in GATEWAYS],
        "processes": [
            {"process": _gov_summary(g.process),
             "agents": [_gov_summary(a) for a in g.agents]}
            for g in groups
        ],
    }


async def activate_for_company(
    db: AsyncSession, company_id: uuid.UUID, bundle_key: str = SOLO_PACK,
    user_id: Optional[uuid.UUID] = None,
) -> ActivationResult:
    """Step 4: activate the chosen bundle for the tenant (over PACK)."""
    return await activate_bundle(db, company_id, bundle_key, user_id)


async def onboarding_status(
    db: AsyncSession, company_id: uuid.UUID,
) -> dict[str, Any]:
    """Step 5: what's live for the tenant — the seeded Solo Pack entities +
    enabled triggers + the console where approvals land."""
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.signals.models import TriggerRegistration

    entities = (await db.execute(
        select(HierarchicalEntity).where(
            HierarchicalEntity.company_id == company_id,
            HierarchicalEntity.status != "DELETED",
        )
    )).scalars().all()
    solo = [e for e in entities if "solo_pack" in (e.tags or [])]
    triggers = (await db.execute(
        select(TriggerRegistration).where(
            TriggerRegistration.company_id == company_id,
            TriggerRegistration.enabled.is_(True),
        )
    )).scalars().all()
    return {
        "activated": len(solo) > 0,
        "entity_count": len(solo),
        "entities": sorted(e.name for e in solo),
        "trigger_count": len(triggers),
        "console_path": CONSOLE_PATH,
    }
