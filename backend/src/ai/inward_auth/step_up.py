"""inward_auth/step_up.py — the ceremonies that produce an elevation.

Two factors, one outcome: a successful ceremony calls ``sessions.elevate`` and
the session holds ``ELEVATED`` for its window. TOTP is the §11.3 fallback for
users without a passkey-capable device; a TOTP step-up elevates *exactly* like
a passkey one, but ``elevated_by`` records which was used so a later policy can
restrict T3 to passkey-only without touching the schema.

Seeds are encrypted at rest with the shipped AES-256-GCM envelope
(``common.security``) rather than a second key-management story — the same
envelope that protects tenant API keys.

Replay: TOTP codes are valid for a whole 30-second slot, so a code observed in
flight could be replayed inside its own window. ``last_used_slot`` records the
slot a code was accepted in and refuses that slot again.
"""
from __future__ import annotations

import hmac
import time
import uuid
from dataclasses import dataclass

import pyotp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.models import TotpSecret
from src.common.config import settings
from src.common.security import decrypt_api_key, encrypt_api_key

__all__ = [
    "TOTP_PERIOD_SECONDS",
    "StepUpResult",
    "TotpEnrollment",
    "begin_totp_enrollment",
    "confirm_totp_enrollment",
    "verify_totp",
    "has_totp",
]

TOTP_PERIOD_SECONDS = 30
#: One step of clock drift either way, the RFC-6238 norm.
_TOTP_VALID_WINDOW = 1


@dataclass(frozen=True)
class StepUpResult:
    """The outcome of a ceremony attempt — never raises for a wrong code."""

    ok: bool
    method: str
    reason: str


@dataclass(frozen=True)
class TotpEnrollment:
    """What the console needs to render the enrollment QR."""

    secret: str
    provisioning_uri: str


def _slot(at: float | None = None) -> int:
    return int((at if at is not None else time.time()) // TOTP_PERIOD_SECONDS)


def _match_slot(secret: str, code: str, at: float | None = None) -> int | None:
    """Return the time slot ``code`` is valid for, or ``None``.

    Resolving the *matching* slot rather than asking pyotp for a yes/no is what
    makes replay protection real. With a drift window of one step, a code
    captured in slot N is still accepted during slot N+1; comparing the stored
    high-water mark against the current slot would let exactly that through.
    Comparing it against the slot the code actually belongs to does not.
    """
    totp = pyotp.TOTP(secret)
    current = _slot(at)
    candidate = code.strip()
    for offset in range(-_TOTP_VALID_WINDOW, _TOTP_VALID_WINDOW + 1):
        slot = current + offset
        if hmac.compare_digest(totp.at(slot * TOTP_PERIOD_SECONDS), candidate):
            return slot
    return None


async def _load(db: AsyncSession, user_id: uuid.UUID) -> TotpSecret | None:
    return (await db.execute(
        select(TotpSecret).where(TotpSecret.user_id == user_id).limit(1)
    )).scalars().first()


async def has_totp(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Whether the user has a *confirmed* authenticator (a pending one is not one)."""
    row = await _load(db, user_id)
    return row is not None and row.confirmed


async def begin_totp_enrollment(
    db: AsyncSession, *, user_id: uuid.UUID, account_label: str,
) -> TotpEnrollment:
    """Generate (or replace) an unconfirmed seed and return its provisioning URI.

    The row stays ``confirmed=False`` until the user proves they scanned it, so
    an abandoned enrollment can never be used as a factor. Re-enrolling
    overwrites a pending seed but leaves a confirmed one in place until the new
    one is confirmed — losing a working authenticator to a half-finished setup
    would be the worst possible failure mode here.
    """
    secret = pyotp.random_base32()
    row = await _load(db, user_id)

    if row is None:
        row = TotpSecret(user_id=user_id, secret=encrypt_api_key(secret), confirmed=False)
        db.add(row)
    elif not row.confirmed:
        row.secret = encrypt_api_key(secret)
        row.last_used_slot = None
    else:
        # A confirmed authenticator exists; hand back a fresh seed to confirm
        # against, but do not disturb the working one until then.
        pending = pyotp.random_base32()
        return TotpEnrollment(
            secret=pending,
            provisioning_uri=pyotp.TOTP(pending).provisioning_uri(
                name=account_label, issuer_name=settings.WEBAUTHN_RP_NAME),
        )

    await db.flush()
    return TotpEnrollment(
        secret=secret,
        provisioning_uri=pyotp.TOTP(secret).provisioning_uri(
            name=account_label, issuer_name=settings.WEBAUTHN_RP_NAME),
    )


async def confirm_totp_enrollment(
    db: AsyncSession, *, user_id: uuid.UUID, code: str,
) -> StepUpResult:
    """Confirm enrollment by proving the seed was scanned."""
    row = await _load(db, user_id)
    if row is None:
        return StepUpResult(False, "totp", "no enrollment in progress")

    matched = _match_slot(decrypt_api_key(row.secret), code)
    if matched is None:
        return StepUpResult(False, "totp", "code did not match")

    row.confirmed = True
    row.last_used_slot = matched
    await db.flush()
    return StepUpResult(True, "totp", "authenticator confirmed")


async def verify_totp(
    db: AsyncSession, *, user_id: uuid.UUID, code: str, at: float | None = None,
) -> StepUpResult:
    """Verify a TOTP code for step-up. Does **not** elevate — the caller does.

    Keeping elevation out of here is deliberate: the router must count a
    failure against the session's lockout counter, and a function that both
    verifies and elevates makes it easy to forget the failure path.
    """
    row = await _load(db, user_id)
    if row is None or not row.confirmed:
        return StepUpResult(False, "totp", "no confirmed authenticator enrolled")

    matched = _match_slot(decrypt_api_key(row.secret), code, at)
    if matched is None:
        return StepUpResult(False, "totp", "code did not match")

    if row.last_used_slot is not None and matched <= row.last_used_slot:
        return StepUpResult(False, "totp", "code already used — replay refused")

    row.last_used_slot = matched
    await db.flush()
    return StepUpResult(True, "totp", "TOTP verified")
