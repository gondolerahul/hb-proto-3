"""loop/platform_budget.py — the platform-initiated budget class (B13).

Optimizer runs, self-healing/dreaming, Meta-Agent iterations, and perpetual
sensing burn the wallet without the tenant asking — the #1 churn driver. They
draw from a **separate capped envelope** (``budget_class='platform_initiated'``)
so that when platform work hits its cap it **parks — never tenant work**. Spend
is attributed by the CostLedger's ``attribution`` (the
``PLATFORM_INITIATED_ATTRIBUTIONS`` set), so the tenant envelope and this one
never double-count.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.loop.models import BUDGET_CLASS_PLATFORM, BudgetEnvelope
from src.ai.services.cost_attribution import PLATFORM_INITIATED_ATTRIBUTIONS
from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "default_platform_envelope_usd",
    "ensure_platform_envelope",
    "rollup_platform_spent",
    "platform_spend_admitted",
    "platform_work_admitted",
]


def default_platform_envelope_usd() -> Decimal:
    return Decimal(str(settings.LOOP_PLATFORM_ENVELOPE_USD))


async def ensure_platform_envelope(
    db: AsyncSession, company_id: uuid.UUID, loop_entity_id: uuid.UUID,
) -> BudgetEnvelope:
    """Get-or-create the tenant's platform-initiated envelope (own cap, no reserve)."""
    env = (await db.execute(
        select(BudgetEnvelope).where(
            BudgetEnvelope.company_id == company_id,
            BudgetEnvelope.entity_id == loop_entity_id,
            BudgetEnvelope.budget_class == BUDGET_CLASS_PLATFORM,
        )
    )).scalar_one_or_none()
    if env is not None:
        return env
    env = BudgetEnvelope(
        company_id=company_id, entity_id=loop_entity_id, cycle="monthly",
        budget_class=BUDGET_CLASS_PLATFORM,
        envelope_usd=default_platform_envelope_usd(),
        reserved_usd=Decimal("0"),   # no protected reserve — platform work is cappable
        spent_usd=Decimal("0"), downshift_at_pct=100,  # cap, don't downshift-notify
        refreshed_at=datetime.utcnow(),
    )
    db.add(env)
    await db.flush()
    return env


async def rollup_platform_spent(
    db: AsyncSession, env: BudgetEnvelope,
) -> Decimal:
    """Sum the platform-attributed usage since the cycle refresh into the envelope."""
    stmt = text(
        "SELECT COALESCE(SUM(calculated_cost), 0) FROM usage_logs "
        "WHERE company_id = :c AND timestamp >= :since AND attribution IN :platform"
    ).bindparams(bindparam("platform", expanding=True))
    total = (await db.execute(stmt, {
        "c": str(env.company_id), "since": env.refreshed_at,
        "platform": list(PLATFORM_INITIATED_ATTRIBUTIONS),
    })).scalar_one()
    env.spent_usd = Decimal(str(total or 0))
    await db.flush()
    return env.spent_usd


async def platform_spend_admitted(
    db: AsyncSession, company_id: uuid.UUID, loop_entity_id: uuid.UUID,
    prospective_usd: Decimal,
) -> bool:
    """True if ``prospective_usd`` of platform-initiated work fits under the cap.

    False → the caller must **park the platform work** (never tenant work). This
    is the B13 guarantee: platform-initiated spend can starve only itself.
    """
    env = await ensure_platform_envelope(db, company_id, loop_entity_id)
    spent = await rollup_platform_spent(db, env)
    cap = Decimal(str(env.envelope_usd or 0))
    admitted = spent + Decimal(str(prospective_usd)) <= cap
    if not admitted:
        logger.info("platform spend parked: company %s spent %s + %s > cap %s",
                    company_id, spent, prospective_usd, cap)
    return admitted


async def platform_work_admitted(
    db: AsyncSession, company_id: uuid.UUID,
    prospective_usd: Decimal = Decimal("0"),
) -> bool:
    """The call-site-friendly admission check — resolves the Loop itself.

    Platform-initiated runners (dreaming, optimizer, meta iterations, sensing)
    know their company but have no reason to know about Loop entities. This
    resolves the tenant's root Loop and asks ``platform_spend_admitted``.

    ``prospective_usd`` defaults to 0, which asks the honest question a runner
    can actually answer before it starts: *is the platform envelope already
    exhausted?* A run's own cost lands in the ledger and counts against the
    next check. Pass an estimate when the caller has one.

    **Fails open when there is no Loop** — a tenant without a seeded Sheel has
    no envelope to check, and missing infrastructure must not silently disable
    platform work. The cap is a spend control, not a safety interlock.
    """
    from src.ai.loop.service import get_root_loop

    loop = await get_root_loop(db, company_id)
    if loop is None:
        logger.debug("no root Loop for company %s — platform work admitted", company_id)
        return True
    return await platform_spend_admitted(db, company_id, loop.id, prospective_usd)
