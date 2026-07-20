"""loop/envelopes.py — budget envelopes with the protected reserve (§20.4).

The Loop heartbeat refreshes envelopes on cycle and rolls up ``spent_usd`` from
the shipped cost attribution. At ``downshift_at_pct`` → a notification signal;
at 100% → the Loop stops dispatching that Process's *non-critical* signals
(they park, not drop). The protected reserve (``reserved_usd``, carved out at
refresh for P14/P17) is what lets those processes be "never paused" without a
special exemption — pre-funded, not exempt (register A6).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.loop.models import BUDGET_CLASS_TENANT, BudgetEnvelope
from src.ai.services.cost_attribution import PLATFORM_INITIATED_ATTRIBUTIONS
from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "ensure_loop_envelope",
    "refresh_if_due",
    "rollup_spent",
    "utilization_pct",
    "is_capped",
    "is_downshift",
    "default_envelope_usd",
    "default_reserve_usd",
]


def default_envelope_usd() -> Decimal:
    return Decimal(str(settings.LOOP_DEFAULT_ENVELOPE_USD))


def default_reserve_usd() -> Decimal:
    return (default_envelope_usd() * Decimal(settings.LOOP_DEFAULT_RESERVE_PCT)
            / Decimal(100)).quantize(Decimal("0.0001"))


def _cycle_delta(cycle: str) -> timedelta:
    return timedelta(days=7) if cycle == "weekly" else timedelta(days=30)


async def ensure_loop_envelope(
    db: AsyncSession, company_id: uuid.UUID, loop_entity_id: uuid.UUID,
) -> BudgetEnvelope:
    """Get-or-create the Loop's budget envelope (uniform configurable default)."""
    env = (await db.execute(
        select(BudgetEnvelope).where(
            BudgetEnvelope.company_id == company_id,
            BudgetEnvelope.entity_id == loop_entity_id,
            BudgetEnvelope.budget_class == BUDGET_CLASS_TENANT,
        )
    )).scalar_one_or_none()
    if env is not None:
        return env
    env = BudgetEnvelope(
        company_id=company_id, entity_id=loop_entity_id, cycle="monthly",
        budget_class=BUDGET_CLASS_TENANT,
        envelope_usd=default_envelope_usd(), reserved_usd=default_reserve_usd(),
        spent_usd=Decimal("0"), downshift_at_pct=settings.LOOP_ENVELOPE_DOWNSHIFT_PCT,
        refreshed_at=datetime.utcnow(),
    )
    db.add(env)
    await db.flush()
    return env


async def refresh_if_due(
    db: AsyncSession, env: BudgetEnvelope, *, now: Optional[datetime] = None,
) -> bool:
    """Reset the envelope at the cycle boundary (re-funds the reserve). Returns
    True if a refresh happened."""
    now = now or datetime.utcnow()
    if now - env.refreshed_at < _cycle_delta(env.cycle):
        return False
    env.spent_usd = Decimal("0")
    env.reserved_usd = default_reserve_usd()
    env.refreshed_at = now
    await db.flush()
    return True


async def rollup_spent(
    db: AsyncSession, env: BudgetEnvelope, *, now: Optional[datetime] = None,
) -> Decimal:
    """Sum child run cost attributed to this company since the cycle refresh.

    Reads the shipped ``usage_logs`` cost attribution (the CostLedger's store).
    Excludes the B13 platform-initiated classes — those roll into the separate
    platform envelope (``loop/platform_budget.py``), never the tenant's.
    """
    stmt = text(
        "SELECT COALESCE(SUM(calculated_cost), 0) FROM usage_logs "
        "WHERE company_id = :c AND timestamp >= :since "
        "AND (attribution IS NULL OR attribution NOT IN :platform)"
    ).bindparams(bindparam("platform", expanding=True))
    total = (await db.execute(stmt, {
        "c": str(env.company_id), "since": env.refreshed_at,
        "platform": list(PLATFORM_INITIATED_ATTRIBUTIONS),
    })).scalar_one()
    env.spent_usd = Decimal(str(total or 0))
    await db.flush()
    return env.spent_usd


def utilization_pct(env: BudgetEnvelope) -> float:
    envelope = Decimal(str(env.envelope_usd or 0))
    if envelope <= 0:
        return 0.0
    return float(Decimal(str(env.spent_usd or 0)) / envelope * 100)


def is_downshift(env: BudgetEnvelope) -> bool:
    """At/above the downshift threshold — notify the owner, keep running."""
    return utilization_pct(env) >= float(env.downshift_at_pct)


def is_capped(env: BudgetEnvelope) -> bool:
    """Non-reserved envelope exhausted — non-critical signals park, not drop.

    Protected processes (P14/P17) draw from ``reserved_usd`` and are unaffected;
    that spend is pre-funded, so "never paused" holds without an exemption.
    """
    spendable = Decimal(str(env.envelope_usd or 0)) - Decimal(str(env.reserved_usd or 0))
    return Decimal(str(env.spent_usd or 0)) >= spendable
