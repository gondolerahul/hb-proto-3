"""inward_auth/oob.py — the T3 out-of-band confirmation leg.

T3 commands (loop kill-switch, above-band payouts, regulatory filings) are the
ones you cannot take back, so §11.3 demands two legs that do not share a
failure mode: a step-up ceremony **plus** a confirmation on a *second*
registered channel. Confirming on the channel that issued the command would
prove nothing — that channel is precisely the one that might be compromised.

Both-legs-or-nothing is enforced structurally:

* ``issue_challenge`` refuses unless the session is already ``ELEVATED`` (leg
  one is done) *and* a second verified binding exists (leg two is possible).
  No second channel → fail closed, no fallback to a weaker proof.
* ``confirm`` re-checks the elevation before granting ``OOB_CONFIRMED``, so a
  step-up that lapsed while the nonce was in flight does not leave a
  half-authorised command standing.

The nonce is bound to one ``command_ref``: agreeing out of band is agreement to
*that* action, not a general-purpose elevation.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.bindings import second_channel_for
from src.ai.inward_auth.models import (
    AccountManagerSession,
    AuthLevel,
    OobConfirmation,
)
from src.ai.inward_auth.sessions import effective_level, elevate
from src.ai.signals.models import SignalTypes
from src.ai.signals.service import emit_signal
from src.ai.solo_pack.consent import check_outbound_consent
from src.common.config import settings

__all__ = ["OobChallenge", "OobResult", "issue_challenge", "confirm"]

_NONCE_DIGITS = 6
_MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class OobChallenge:
    """A challenge in flight. ``nonce`` is returned only for test/delivery use."""

    ok: bool
    reason: str
    challenge_id: uuid.UUID | None = None
    channel_kind: str | None = None
    address: str | None = None
    nonce: str | None = None


@dataclass(frozen=True)
class OobResult:
    ok: bool
    reason: str


def _hash_nonce(nonce: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), nonce.strip().encode(), hashlib.sha256
    ).hexdigest()


async def issue_challenge(
    db: AsyncSession,
    session: AccountManagerSession,
    *,
    command_ref: str,
    issuing_binding_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> OobChallenge:
    """Mint a nonce and send it to a channel other than the issuing one.

    Fails closed on every missing precondition — an unbound session, a session
    that has not stepped up, no second channel, or a second channel the tenant's
    consent posture forbids contacting.
    """
    at = now or datetime.utcnow()

    if session.user_id is None:
        return OobChallenge(False, "session is not bound to a user")

    if effective_level(session, at) not in (AuthLevel.ELEVATED, AuthLevel.OOB_CONFIRMED):
        return OobChallenge(
            False, "step-up must succeed before the out-of-band leg is issued")

    binding = await second_channel_for(
        db, user_id=session.user_id,
        exclude_binding_id=issuing_binding_id,
        exclude_kind=session.channel_kind,
    )
    if binding is None:
        return OobChallenge(
            False,
            "no second registered channel — T3 cannot be confirmed on the channel "
            "that asked for it",
        )

    decision = await check_outbound_consent(
        session.company_id, binding.channel_kind, binding.address,
        purpose="transactional")
    if not decision.allowed:
        return OobChallenge(
            False, f"second channel cannot be contacted: {decision.reason}")

    nonce = f"{secrets.randbelow(10 ** _NONCE_DIGITS):0{_NONCE_DIGITS}d}"
    challenge = OobConfirmation(
        company_id=session.company_id,
        user_id=session.user_id,
        session_id=session.id,
        second_binding_id=binding.id,
        command_ref=command_ref,
        nonce_hash=_hash_nonce(nonce),
        expires_at=at + timedelta(minutes=settings.INWARD_AUTH_OOB_TTL_MINUTES),
        attempts=0,
    )
    db.add(challenge)
    await db.flush()

    await emit_signal(
        db,
        company_id=session.company_id,
        source="inward_auth",
        type=SignalTypes.AUTHN_OOB_CONFIRM,
        payload={
            "user_id": str(session.user_id),
            "challenge_id": str(challenge.id),
            "command_ref": command_ref,
            "channel_kind": binding.channel_kind,
            "address": binding.address,
            "nonce": nonce,
            "expires_at": challenge.expires_at.isoformat(),
        },
    )

    return OobChallenge(
        True, "challenge issued", challenge_id=challenge.id,
        channel_kind=binding.channel_kind, address=binding.address, nonce=nonce,
    )


async def confirm(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    challenge_id: uuid.UUID,
    command_ref: str,
    nonce: str,
    now: datetime | None = None,
) -> OobResult:
    """Verify the second leg and raise the session to ``OOB_CONFIRMED``.

    ``command_ref`` is checked against the stored one, so a nonce issued for a
    kill-switch cannot be spent on a payout.
    """
    at = now or datetime.utcnow()

    challenge = (await db.execute(
        select(OobConfirmation).where(
            OobConfirmation.id == challenge_id,
            OobConfirmation.company_id == company_id,
            OobConfirmation.user_id == user_id,
        ).limit(1)
    )).scalars().first()

    if challenge is None:
        return OobResult(False, "no such challenge")
    if challenge.confirmed_at is not None:
        return OobResult(False, "challenge already used")
    if challenge.expires_at <= at:
        return OobResult(False, "challenge expired")
    if challenge.attempts >= _MAX_ATTEMPTS:
        return OobResult(False, "too many attempts")
    if challenge.command_ref != command_ref:
        return OobResult(False, "challenge was issued for a different command")

    challenge.attempts += 1
    if not hmac.compare_digest(challenge.nonce_hash, _hash_nonce(nonce)):
        await db.flush()
        return OobResult(False, "confirmation code did not match")

    session = (await db.execute(
        select(AccountManagerSession).where(
            AccountManagerSession.id == challenge.session_id).limit(1)
    )).scalars().first()
    if session is None:
        return OobResult(False, "the issuing session no longer exists")

    # Leg one must still hold: an elevation that lapsed while the nonce was in
    # flight means the command is no longer authorised, however valid the code.
    if effective_level(session, at) not in (AuthLevel.ELEVATED, AuthLevel.OOB_CONFIRMED):
        return OobResult(
            False, "step-up lapsed before confirmation — both legs must hold at once")

    challenge.confirmed_at = at
    await elevate(db, session, method=session.elevated_by or "passkey",
                  level=AuthLevel.OOB_CONFIRMED, now=at)
    return OobResult(True, "out-of-band confirmation accepted")
