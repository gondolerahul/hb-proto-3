"""trust/dunning.py — the graduated dunning ladder (C5).

When the product *is* the tenant's operations, an instant suspension on a lapsed
wallet is unacceptable. The ladder degrades gracefully instead:

``current`` → ``past_due`` (dunning begins, full function) → ``grace`` (a
configurable window, full function, escalating notices) → ``read_only`` (agents
stop *acting* — no external effects; the tenant can still read, export, and pay;
protected P14/P17 keep their reserved envelope) → ``suspended`` (hard, only after
read-only elapses).

The state-aware ``CompanySuspensionMiddleware`` enforces `read_only`/`suspended`;
this module owns the state machine + the transition (emitting a ``billing.*``
signal on each change). What computes ``days_past_due`` (the billing/payment
subsystem) calls ``advance_dunning`` — the ladder itself is here and testable.
Inbound signals are parked, never dropped, throughout (SIG PARKED lifecycle).
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "SubscriptionStatus",
    "status_for_days_past_due",
    "agents_may_act",
    "is_read_only",
    "is_suspended",
    "advance_dunning",
    "SIGNAL_FOR_STATUS",
]


class SubscriptionStatus:
    CURRENT = "current"
    PAST_DUE = "past_due"
    GRACE = "grace"
    READ_ONLY = "read_only"
    SUSPENDED = "suspended"


# The transition signal each state raises when first entered.
SIGNAL_FOR_STATUS: dict[str, str] = {
    SubscriptionStatus.PAST_DUE: "billing.past_due",
    SubscriptionStatus.GRACE: "billing.grace",
    SubscriptionStatus.READ_ONLY: "billing.read_only",
    SubscriptionStatus.SUSPENDED: "billing.suspended",
}

# States in which agents stop acting (no external effects).
_ACTING_BLOCKED = frozenset({SubscriptionStatus.READ_ONLY, SubscriptionStatus.SUSPENDED})


def is_read_only(status: str) -> bool:
    return status == SubscriptionStatus.READ_ONLY


def is_suspended(status: str) -> bool:
    return status == SubscriptionStatus.SUSPENDED


def agents_may_act(status: str) -> bool:
    """False once the tenant is read-only or suspended — agents stop acting."""
    return status not in _ACTING_BLOCKED


def status_for_days_past_due(
    days_past_due: int, *, grace_days: Optional[int] = None,
    read_only_days: Optional[int] = None,
) -> str:
    """The ladder position for how many days a tenant has been past due.

    ``grace_days`` (default ``BILLING_GRACE_DAYS``) is the full-function window;
    ``read_only_days`` (default ``BILLING_READ_ONLY_DAYS``) is how long read-only
    lasts before a hard suspend.
    """
    grace = grace_days if grace_days is not None else settings.BILLING_GRACE_DAYS
    read_only = (read_only_days if read_only_days is not None
                 else settings.BILLING_READ_ONLY_DAYS)
    if days_past_due <= 0:
        return SubscriptionStatus.CURRENT
    if days_past_due <= 1:
        return SubscriptionStatus.PAST_DUE
    if days_past_due <= grace:
        return SubscriptionStatus.GRACE
    if days_past_due <= grace + read_only:
        return SubscriptionStatus.READ_ONLY
    return SubscriptionStatus.SUSPENDED


async def advance_dunning(
    db: AsyncSession, company_id: uuid.UUID, days_past_due: int, *,
    grace_days: Optional[int] = None, read_only_days: Optional[int] = None,
) -> str:
    """Move a company to its ladder position for ``days_past_due``.

    Idempotent: only changes + emits a signal when the status actually moves.
    Returns the (new or unchanged) status.
    """
    from src.auth.models import Company

    company = (await db.execute(
        select(Company).where(Company.id == company_id))).scalar_one_or_none()
    if company is None:
        raise ValueError(f"company {company_id} not found")

    target = status_for_days_past_due(
        days_past_due, grace_days=grace_days, read_only_days=read_only_days)
    current = str(company.subscription_status or SubscriptionStatus.CURRENT)
    if target == current:
        return current

    setattr(company, "subscription_status", target)  # Company uses legacy Column typing
    await db.flush()
    await _emit_transition(db, company_id, target, days_past_due)
    logger.info("dunning: company %s %s → %s (%dd past due)",
                company_id, current, target, days_past_due)
    return target


async def _emit_transition(
    db: AsyncSession, company_id: uuid.UUID, status: str, days_past_due: int,
) -> None:
    sig_type = SIGNAL_FOR_STATUS.get(status)
    if sig_type is None:
        return
    from src.ai.signals.models import SignalSource, SignalTrust
    from src.ai.signals.service import emit_signal

    try:
        await emit_signal(
            db, company_id=company_id, source=SignalSource.TELEMETRY, type=sig_type,
            trust=SignalTrust.PLATFORM, urgency="high",
            payload={"subscription_status": status, "days_past_due": days_past_due},
            dedupe_key=f"{sig_type}:{company_id}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("dunning signal skipped: %s", exc)
