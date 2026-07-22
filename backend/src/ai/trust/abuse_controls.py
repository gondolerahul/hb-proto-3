"""trust/abuse_controls.py — free-credit abuse controls (E2).

``$5/day free credits × every tenant`` is platform COGS with no gate: today the
daily cron injects credits into every active company, so a signup farm mints
free inference forever. Finding **E2** asks for the three controls this module
owns:

1. **A verification gate** — daily credits do not activate until someone on the
   company has verified their email. An unverified workspace still functions
   (it can be paid for); it just does not draw from platform COGS.
2. **A per-IP signup throttle** — tenant creation from one origin is capped per
   rolling window. The signup IP is recorded in the company's existing
   ``onboarding_metadata`` JSONB, so this needs no new table and no Redis: the
   throttle is one indexed-by-time count against ``companies``.
3. **A daily-credit eligibility check** — the cron asks before it injects, so a
   suspended or unverified tenant is skipped rather than topped up.

The policy is here (pure + testable); enforcement is wired at the two existing
call sites — ``auth.service.create_user`` and
``billing.credit_service.flush_and_inject_daily_credits`` — the same shape as
C5, whose ladder lives in ``dunning.py`` and is enforced by the middleware.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.trust.dunning import SubscriptionStatus
from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "SIGNUP_IP_KEY",
    "SIGNUP_THROTTLE_WINDOW_HOURS",
    "CreditEligibility",
    "client_ip",
    "signup_allowed",
    "daily_credit_eligibility",
    "stamp_signup_ip",
]

# Where the signup origin is stashed on Company.onboarding_metadata.
SIGNUP_IP_KEY = "signup_ip"

# The rolling window the per-IP signup cap is measured over.
SIGNUP_THROTTLE_WINDOW_HOURS = 24

# Statuses in which a tenant draws no free credits — they are past paying.
_CREDIT_BLOCKED_STATUSES = frozenset({
    SubscriptionStatus.READ_ONLY, SubscriptionStatus.SUSPENDED,
})


@dataclass(frozen=True)
class CreditEligibility:
    """Whether a company may receive its daily free credits, and why not."""

    eligible: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.eligible


def client_ip(headers: Mapping[str, str], fallback: Optional[str]) -> Optional[str]:
    """The originating client IP, honouring a proxy's ``X-Forwarded-For``.

    Takes the FIRST hop in ``X-Forwarded-For`` (the client the edge proxy saw);
    later hops are the proxies themselves. Falls back to the socket peer when
    the app is addressed directly. A spoofable header is acceptable here: the
    throttle raises the cost of farming, it is not an authentication boundary.
    """
    forwarded = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return fallback


async def signup_allowed(db: AsyncSession, ip: Optional[str]) -> bool:
    """False once ``ip`` has created its per-window quota of tenant companies.

    An absent IP (a direct/internal call, or a test) is never throttled — the
    control is about repeated automated signups from one origin, and failing
    closed on a missing header would break admin-created tenants.
    """
    limit = settings.TRUST_SIGNUP_MAX_PER_IP_PER_DAY
    if not ip or limit <= 0:
        return True

    from src.auth.models import Company

    since = datetime.utcnow() - timedelta(hours=SIGNUP_THROTTLE_WINDOW_HOURS)
    recent = (await db.execute(
        select(func.count()).select_from(Company).where(
            Company.created_at >= since,
            Company.onboarding_metadata[SIGNUP_IP_KEY].astext == ip,
        )
    )).scalar_one()

    if recent >= limit:
        logger.warning(
            "E2 signup throttle: ip=%s has created %d companies in %dh (limit %d)",
            ip, recent, SIGNUP_THROTTLE_WINDOW_HOURS, limit,
        )
        return False
    return True


async def daily_credit_eligibility(
    db: AsyncSession, company_id: uuid.UUID,
) -> CreditEligibility:
    """Whether a company may be injected with its daily free credits.

    Ineligible when the company is inactive, past the dunning ladder's paying
    states, or has no verified user yet (the E2 verification gate). Verifying
    an email is all it takes to switch on — no separate activation step.
    """
    from src.auth.models import Company, User

    company = (await db.execute(
        select(Company).where(Company.id == company_id))).scalar_one_or_none()
    if company is None:
        return CreditEligibility(False, "company not found")

    if str(company.status) != "active":
        return CreditEligibility(False, f"company status is {company.status}")

    sub_status = str(company.subscription_status or SubscriptionStatus.CURRENT)
    if sub_status in _CREDIT_BLOCKED_STATUSES:
        return CreditEligibility(False, f"subscription status is {sub_status}")

    if settings.TRUST_REQUIRE_VERIFIED_FOR_CREDITS:
        verified = (await db.execute(
            select(func.count()).select_from(User).where(
                User.company_id == company_id,
                User.is_verified.is_(True),
            )
        )).scalar_one()
        if not verified:
            return CreditEligibility(False, "no verified user on the company")

    return CreditEligibility(True)


def stamp_signup_ip(
    metadata: Optional[dict[str, Any]], ip: Optional[str],
) -> dict[str, Any]:
    """Return ``metadata`` with the signup origin recorded (for the throttle)."""
    stamped = dict(metadata or {})
    if ip:
        stamped[SIGNUP_IP_KEY] = ip
    return stamped
