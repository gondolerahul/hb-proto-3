"""inward_auth/webauthn_ceremony.py — platform-built passkey ceremonies (T4).

Decision 2 (2026-07-22): full WebAuthn/FIDO2 in-house, no auth vendor, so no
identity dataflow leaves the platform — the same global-neutral posture TRUST
took with consent. ``py_webauthn`` does the CBOR/COSE and signature work; this
module owns the state that library deliberately does not: which challenge is
outstanding, which credentials a user has, and what the sign counter was.

Three properties worth stating, because each is a way passkeys are commonly
got wrong:

* **Challenges are single-use.** Issued into ``webauthn_challenges``, consumed
  on the first verification attempt whether it succeeds or fails. A challenge
  that survives a failed attempt is a retry oracle.
* **A regressing sign counter is rejected.** Authenticators that report a
  counter increment a clone will eventually contradict; that is the only
  cloned-key signal the protocol gives, so it is treated as fatal rather than
  logged.
* **Verification failures never raise into the caller.** Every path returns a
  ``StepUpResult`` so the router can count the failure toward the lockout —
  an exception that escapes here would skip that counter.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

import webauthn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from src.ai.inward_auth.models import WebAuthnChallenge, WebAuthnCredential
from src.ai.inward_auth.step_up import StepUpResult
from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "PURPOSE_REGISTER",
    "PURPOSE_AUTHENTICATE",
    "begin_registration",
    "finish_registration",
    "begin_authentication",
    "finish_authentication",
    "list_credentials",
    "delete_credential",
    "has_passkey",
]

PURPOSE_REGISTER = "register"
PURPOSE_AUTHENTICATE = "authenticate"

#: Ceremonies are interactive; a challenge outliving the dialog is pure risk.
_CHALLENGE_TTL_SECONDS = 300


async def _issue_challenge(
    db: AsyncSession, *, user_id: uuid.UUID, purpose: str, challenge: bytes,
    now: datetime | None = None,
) -> None:
    at = now or datetime.utcnow()
    db.add(WebAuthnChallenge(
        user_id=user_id,
        purpose=purpose,
        challenge=bytes_to_base64url(challenge),
        expires_at=at + timedelta(seconds=_CHALLENGE_TTL_SECONDS),
    ))
    await db.flush()


async def _consume_challenge(
    db: AsyncSession, *, user_id: uuid.UUID, purpose: str,
    now: datetime | None = None,
) -> bytes | None:
    """Take the newest live challenge and burn it, whatever happens next."""
    at = now or datetime.utcnow()
    row = (await db.execute(
        select(WebAuthnChallenge)
        .where(
            WebAuthnChallenge.user_id == user_id,
            WebAuthnChallenge.purpose == purpose,
            WebAuthnChallenge.consumed_at.is_(None),
            WebAuthnChallenge.expires_at > at,
        )
        .order_by(WebAuthnChallenge.created_at.desc())
        .limit(1)
    )).scalars().first()

    if row is None:
        return None

    row.consumed_at = at
    await db.flush()
    return base64url_to_bytes(row.challenge)


async def list_credentials(
    db: AsyncSession, *, user_id: uuid.UUID
) -> list[WebAuthnCredential]:
    return list((await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
    )).scalars().all())


async def has_passkey(db: AsyncSession, *, user_id: uuid.UUID) -> bool:
    return bool(await list_credentials(db, user_id=user_id))


async def begin_registration(
    db: AsyncSession, *, user_id: uuid.UUID, user_name: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Options for ``navigator.credentials.create()``.

    Already-registered credentials are excluded so a user cannot enroll the
    same authenticator twice and believe they have two factors.
    """
    existing = await list_credentials(db, user_id=user_id)
    options = webauthn.generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=user_id.bytes,
        user_name=user_name,
        user_display_name=display_name or user_name,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    await _issue_challenge(
        db, user_id=user_id, purpose=PURPOSE_REGISTER, challenge=options.challenge)

    parsed: dict[str, Any] = json.loads(webauthn.options_to_json(options))
    return parsed


async def finish_registration(
    db: AsyncSession, *, user_id: uuid.UUID, credential: dict[str, Any],
    label: str | None = None,
) -> StepUpResult:
    """Verify the attestation and store the new passkey."""
    challenge = await _consume_challenge(
        db, user_id=user_id, purpose=PURPOSE_REGISTER)
    if challenge is None:
        return StepUpResult(False, "passkey", "no registration ceremony in progress")

    try:
        verified = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
        )
    except Exception as exc:  # py_webauthn raises a family of validation errors
        logger.info("passkey registration failed for user=%s: %s", user_id, exc)
        return StepUpResult(False, "passkey", f"registration rejected: {exc}")

    credential_id = bytes_to_base64url(verified.credential_id)
    clash = (await db.execute(
        select(WebAuthnCredential)
        .where(WebAuthnCredential.credential_id == credential_id).limit(1)
    )).scalars().first()
    if clash is not None:
        return StepUpResult(False, "passkey", "this authenticator is already registered")

    db.add(WebAuthnCredential(
        user_id=user_id,
        credential_id=credential_id,
        public_key=bytes_to_base64url(verified.credential_public_key),
        sign_count=verified.sign_count,
        label=label,
    ))
    await db.flush()
    return StepUpResult(True, "passkey", "passkey registered")


async def begin_authentication(
    db: AsyncSession, *, user_id: uuid.UUID
) -> dict[str, Any] | None:
    """Options for ``navigator.credentials.get()``, or ``None`` with no passkey."""
    credentials = await list_credentials(db, user_id=user_id)
    if not credentials:
        return None

    options = webauthn.generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in credentials
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    await _issue_challenge(
        db, user_id=user_id, purpose=PURPOSE_AUTHENTICATE, challenge=options.challenge)

    parsed: dict[str, Any] = json.loads(webauthn.options_to_json(options))
    return parsed


async def finish_authentication(
    db: AsyncSession, *, user_id: uuid.UUID, credential: dict[str, Any],
    now: datetime | None = None,
) -> StepUpResult:
    """Verify an assertion. Does **not** elevate — the router does, so that the
    failure path stays visible to the lockout counter."""
    at = now or datetime.utcnow()
    challenge = await _consume_challenge(
        db, user_id=user_id, purpose=PURPOSE_AUTHENTICATE, now=at)
    if challenge is None:
        return StepUpResult(False, "passkey", "no authentication ceremony in progress")

    raw_id = credential.get("id") or credential.get("rawId")
    if not isinstance(raw_id, str):
        return StepUpResult(False, "passkey", "malformed credential")

    stored = (await db.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.user_id == user_id,
            WebAuthnCredential.credential_id == raw_id,
        ).limit(1)
    )).scalars().first()
    if stored is None:
        return StepUpResult(False, "passkey", "unknown authenticator")

    try:
        verified = webauthn.verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            credential_public_key=base64url_to_bytes(stored.public_key),
            credential_current_sign_count=stored.sign_count,
        )
    except Exception as exc:
        logger.info("passkey authentication failed for user=%s: %s", user_id, exc)
        return StepUpResult(False, "passkey", f"assertion rejected: {exc}")

    # A counter that fails to advance is the protocol's only clone signal.
    # Authenticators that don't implement counters report 0 forever, which is
    # legitimate; anything that once counted and then went backwards is not.
    if stored.sign_count > 0 and verified.new_sign_count <= stored.sign_count:
        logger.warning(
            "passkey sign-count regression user=%s stored=%s new=%s",
            user_id, stored.sign_count, verified.new_sign_count)
        return StepUpResult(
            False, "passkey",
            "authenticator sign counter went backwards — possible cloned key")

    stored.sign_count = verified.new_sign_count
    stored.last_used_at = at
    await db.flush()
    return StepUpResult(True, "passkey", "passkey verified")


async def delete_credential(
    db: AsyncSession, *, user_id: uuid.UUID, credential_row_id: uuid.UUID
) -> bool:
    row = (await db.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.id == credential_row_id,
            WebAuthnCredential.user_id == user_id,
        ).limit(1)
    )).scalars().first()
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True
