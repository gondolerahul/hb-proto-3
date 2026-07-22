"""pragya/deployment.py — stages 6–9 over the Inc-2 wizard APIs.

Decision 4, realized: the wizard's step APIs *are* Pragya's stage APIs. This
module is a conversational skin over `solo_pack.onboarding` — it does not
re-implement activation, and it must not, or the console wizard and the chat
would start producing different tenants from the same choice.

The four functions map to the four mechanical stages:

* stage 6 **blueprint**   → `list_bundles` + `governance_preview`
* stage 7 **integration** → channel readiness (what the blueprint demands)
* stage 8 **deploy**      → `activate_for_company` + `onboarding_status`
* stage 9 **operate**     → the standing report

The governance preview is what makes stage 6 honest: the owner sees every
autonomy level, authority band and checkpoint *before* anything activates,
which is the difference between confirming a plan and discovering one.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.solo_pack.bundles import SOLO_PACK
from src.ai.solo_pack.onboarding import (
    activate_for_company,
    governance_preview,
    list_bundles,
    onboarding_status,
)

__all__ = [
    "propose_blueprint",
    "integration_readiness",
    "deploy_bundle",
    "operating_report",
]


async def propose_blueprint(bundle_key: str = SOLO_PACK) -> dict[str, Any]:
    """Stage 6: what would activate, and where it would stop for a human.

    Pure — computed from the curated templates, no tenant state — so an owner
    can be walked through the whole configuration before committing to any
    of it.
    """
    preview = governance_preview(bundle_key)
    return {
        "bundle": bundle_key,
        "options": list_bundles(),
        "governance": preview,
        "autonomy_note": (
            "Everything starts at A1: each agent proposes and waits for you. "
            "Nothing acts on its own until you decide it has earned it."
        ),
    }


async def integration_readiness(
    db: AsyncSession, company_id: uuid.UUID
) -> dict[str, Any]:
    """Stage 7: which channels are connected, and which the blueprint needs.

    Reported rather than assumed. An email gateway with no mailbox connected
    is an agent that will sit silent, and the owner should learn that here
    instead of wondering why nothing happened after activation.
    """
    from src.ai.email_models import EmailConnection

    active_email = int((await db.execute(
        select(func.count()).select_from(EmailConnection)
        .where(
            EmailConnection.company_id == company_id,
            EmailConnection.is_active.is_(True),
        )
    )).scalar() or 0)

    return {
        "channels": {"email": active_email},
        "email_connected": active_email > 0,
        "missing": [] if active_email else ["email"],
        "note": (
            "Email is what the acquisition and invoicing agents listen to. "
            "Without it they'll activate but stay quiet."
        ),
    }


async def deploy_bundle(
    db: AsyncSession,
    company_id: uuid.UUID,
    bundle_key: str = SOLO_PACK,
    user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Stage 8: activate at A1 and report what came up.

    Calls exactly the function the wizard calls. The status read-back is not
    decoration — "it activated" is a claim, and the trigger count is the
    evidence for it.
    """
    result = await activate_for_company(db, company_id, bundle_key, user_id=user_id)
    status = await onboarding_status(db, company_id)
    return {
        "activated": True,
        "bundle": bundle_key,
        "entities": dict(result),
        "entity_count": len(result),
        "status": status,
    }


async def operating_report(
    db: AsyncSession, company_id: uuid.UUID
) -> dict[str, Any]:
    """Stage 9: the standing operational picture.

    KPI figures come from the C6 registry (`ai.kpi`), which reports honestly
    when a metric's prerequisites are unmet — a KPI that cannot be computed
    says what is missing rather than showing a plausible number.
    """
    from src.ai.kpi.compute import compute_all

    status = await onboarding_status(db, company_id)
    kpis = await compute_all(db, company_id)
    return {
        "status": status,
        "kpis": [k.as_dict() for k in kpis],
        "measurable": [k.key for k in kpis if k.value is not None],
        "not_yet_measurable": [
            {"key": k.key, "missing": k.missing} for k in kpis if k.value is None
        ],
    }
