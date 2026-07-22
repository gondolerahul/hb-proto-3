"""inward_auth/sessions.py — elevation, expiry, and the ``require_tier`` gate.

This is the predicate every Pragya command passes through before it acts. Two
properties it is built to guarantee:

1. **Elevation is checked at execution time, not classification time.** A
   command classified while the session was elevated must still be elevated
   when it runs, or a long-running plan becomes a way to outlive a ceremony.
   ``effective_level`` therefore derives the level from the clock every call
   rather than trusting the stored ``auth_level`` column.
2. **A rule can only ever demand more.** ``require_tier`` returns what is
   *missing*, so an unmet requirement is an instruction ("do a step-up"),
   never a silent pass.

The stored ``auth_level`` is a cache of the last transition; the clock is the
authority. When they disagree the clock wins, which is why an expired
elevation demotes silently instead of needing a sweeper.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.models import (
    AccountManagerSession,
    AuthLevel,
    ChannelKind,
    normalise_address,
)
from src.ai.inward_auth.tiers import Tier
from src.common.config import settings

__all__ = [
    "AuthDecision",
    "LEVEL_RANK",
    "TIER_REQUIRES",
    "effective_level",
    "is_locked",
    "require_tier",
    "get_or_create_session",
    "elevate",
    "record_failed_stepup",
    "clear_failed_stepups",
]


#: How strong each level is. Ordering is the whole point — comparisons below
#: are all "is what the session has at least what the tier needs".
LEVEL_RANK: dict[str, int] = {
    AuthLevel.NONE: 0,
    AuthLevel.BOUND: 1,
    AuthLevel.ELEVATED: 2,
    AuthLevel.OOB_CONFIRMED: 3,
}

#: The §11.3 verification column, as data.
TIER_REQUIRES: dict[Tier, str] = {
    Tier.T0: AuthLevel.NONE,
    Tier.T1: AuthLevel.BOUND,
    Tier.T2: AuthLevel.ELEVATED,
    Tier.T3: AuthLevel.OOB_CONFIRMED,
}


@dataclass(frozen=True)
class AuthDecision:
    """Whether the command may run, and if not, what would let it.

    ``required_level`` is what the caller must reach; ``needs_step_up`` and
    ``needs_oob`` are the two ceremonies that get them there, split out so the
    console can open the right modal without re-deriving the policy.
    """

    allowed: bool
    tier: Tier
    current_level: str
    required_level: str
    reason: str
    needs_step_up: bool = False
    needs_oob: bool = False
    locked: bool = False


def is_locked(session: AccountManagerSession, now: datetime | None = None) -> bool:
    """True while a step-up lockout is in force."""
    at = now or datetime.utcnow()
    return session.locked_until is not None and session.locked_until > at


def effective_level(
    session: AccountManagerSession, now: datetime | None = None
) -> str:
    """The level the session *actually* holds right now.

    An elevation that has run out demotes to ``BOUND`` (the user is still who
    they were, they just no longer hold a fresh ceremony) — or to ``NONE`` if
    there was never a resolved user behind the session at all.
    """
    at = now or datetime.utcnow()
    stored = session.auth_level or AuthLevel.NONE
    baseline = AuthLevel.BOUND if session.user_id is not None else AuthLevel.NONE

    if LEVEL_RANK.get(stored, 0) <= LEVEL_RANK[AuthLevel.BOUND]:
        return stored
    # ELEVATED / OOB_CONFIRMED are time-boxed.
    if session.elevated_until is None or session.elevated_until <= at:
        return baseline
    return stored


def require_tier(
    session: AccountManagerSession,
    tier: Tier,
    now: datetime | None = None,
) -> AuthDecision:
    """Decide whether ``session`` may run a command of ``tier``, right now."""
    at = now or datetime.utcnow()
    current = effective_level(session, at)
    required = TIER_REQUIRES[tier]
    have, need = LEVEL_RANK.get(current, 0), LEVEL_RANK[required]

    # A lockout bites at T2 and above; reads and general questions still work,
    # so a locked-out owner is never cut off from finding out what happened.
    if tier >= Tier.T2 and is_locked(session, at):
        return AuthDecision(
            allowed=False, tier=tier, current_level=current, required_level=required,
            reason=(f"step-up locked until {session.locked_until:%Y-%m-%d %H:%M} UTC "
                    "after repeated failures"),
            locked=True,
        )

    if have >= need:
        return AuthDecision(
            allowed=True, tier=tier, current_level=current, required_level=required,
            reason=f"session holds {current}, {tier.name} needs {required}",
        )

    if current == AuthLevel.NONE:
        reason = (f"{tier.name} needs {required} but this channel is not bound "
                  "to a user — enroll it from the console first")
    else:
        reason = f"{tier.name} needs {required}, session holds {current}"

    return AuthDecision(
        allowed=False, tier=tier, current_level=current, required_level=required,
        reason=reason,
        # An unbound session cannot step up — it has no user to prove.
        needs_step_up=(required in (AuthLevel.ELEVATED, AuthLevel.OOB_CONFIRMED)
                       and current != AuthLevel.NONE),
        needs_oob=(required == AuthLevel.OOB_CONFIRMED and current != AuthLevel.NONE),
    )


async def get_or_create_session(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    channel_kind: str,
    user_id: uuid.UUID | None = None,
    channel_address: str | None = None,
) -> AccountManagerSession:
    """Fetch (or open) the conversation row for a user on a channel.

    A console session is born ``BOUND``: the JWT login *is* the bound identity
    for that channel. Every other channel starts at ``NONE`` and only reaches
    ``BOUND`` by resolving a verified binding (see ``bindings.resolve_inbound``).
    """
    address = (normalise_address(channel_kind, channel_address)
               if channel_address else None)

    stmt = select(AccountManagerSession).where(
        AccountManagerSession.company_id == company_id,
        AccountManagerSession.channel_kind == channel_kind,
    )
    stmt = (stmt.where(AccountManagerSession.user_id == user_id) if user_id is not None
            else stmt.where(AccountManagerSession.user_id.is_(None)))
    stmt = (stmt.where(AccountManagerSession.channel_address == address)
            if address is not None
            else stmt.where(AccountManagerSession.channel_address.is_(None)))

    existing = (await db.execute(stmt.limit(1))).scalars().first()
    if existing is not None:
        existing.last_activity_at = datetime.utcnow()
        return existing

    born_bound = user_id is not None and channel_kind == ChannelKind.CONSOLE
    session = AccountManagerSession(
        company_id=company_id,
        user_id=user_id,
        channel_kind=channel_kind,
        channel_address=address,
        auth_level=AuthLevel.BOUND if born_bound else AuthLevel.NONE,
        last_activity_at=datetime.utcnow(),
    )
    db.add(session)
    await db.flush()
    return session


async def elevate(
    db: AsyncSession,
    session: AccountManagerSession,
    *,
    method: str,
    level: str = AuthLevel.ELEVATED,
    minutes: int | None = None,
    now: datetime | None = None,
) -> AccountManagerSession:
    """Stamp a successful ceremony onto the session and clear the failure count.

    ``method`` is ``passkey`` or ``totp``; the §11.3 note that policy may later
    restrict T3 to passkey-only is why it is recorded rather than discarded.
    """
    at = now or datetime.utcnow()
    window = minutes if minutes is not None else settings.INWARD_AUTH_ELEVATION_MINUTES
    session.auth_level = level
    session.elevated_by = method
    session.elevated_until = at + timedelta(minutes=window)
    session.failed_stepups = 0
    session.locked_until = None
    session.last_activity_at = at
    await db.flush()
    return session


async def record_failed_stepup(
    db: AsyncSession,
    session: AccountManagerSession,
    now: datetime | None = None,
) -> bool:
    """Count a failed ceremony; lock T2+ once the threshold is crossed.

    Returns whether this failure caused a lockout, so the caller can fire the
    "alert every registered channel" notification exactly once.
    """
    at = now or datetime.utcnow()
    session.failed_stepups = (session.failed_stepups or 0) + 1
    session.last_activity_at = at

    if session.failed_stepups >= settings.INWARD_AUTH_MAX_FAILED_STEPUPS:
        session.locked_until = at + timedelta(
            minutes=settings.INWARD_AUTH_LOCKOUT_MINUTES)
        # The lock must also drop any elevation the session was still holding,
        # or a spoofer who elevated once keeps their window through the lockout.
        session.auth_level = (AuthLevel.BOUND if session.user_id is not None
                              else AuthLevel.NONE)
        session.elevated_until = None
        await db.flush()
        return True

    await db.flush()
    return False


async def clear_failed_stepups(
    db: AsyncSession, session: AccountManagerSession
) -> None:
    """Reset the failure counter and release any lock (an owner-driven undo)."""
    session.failed_stepups = 0
    session.locked_until = None
    await db.flush()
