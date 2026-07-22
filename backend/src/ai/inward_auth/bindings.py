"""inward_auth/bindings.py — channel enrollment and inbound resolution (T5).

The rule this file implements is the one the whole increment rests on:
**channel identity routes, verification authorizes.** ``resolve_inbound`` maps
an address to a user so Pragya knows *which conversation* she is in; it never
by itself authorises anything, because a caller ID and a WhatsApp sender are
both trivially forged.

Enrollment is a verified handshake, deliberately asymmetric: the request must
come from an already-authenticated console session at T2 (adding a channel is
itself a sensitive command), and the OTP is delivered *to the channel being
claimed*, so proving control means holding both the console session and the
device. Neither leg alone enrolls anything.

The OTP is stored as a keyed hash, never in the clear — a leaked database row
must not be a working second factor.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.models import ChannelBinding, ChannelKind, normalise_address
from src.ai.signals.models import SignalTypes
from src.ai.signals.service import emit_signal
from src.ai.solo_pack.consent import check_outbound_consent
from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "BindingResult",
    "hash_otp",
    "begin_enrollment",
    "confirm_enrollment",
    "resolve_inbound",
    "list_bindings",
    "revoke_binding",
    "second_channel_for",
    "alert_all_channels",
]

_OTP_DIGITS = 6


@dataclass(frozen=True)
class BindingResult:
    """Outcome of an enrollment step. ``otp`` is set only on ``begin``."""

    ok: bool
    reason: str
    binding_id: uuid.UUID | None = None
    otp: str | None = None


def hash_otp(code: str) -> str:
    """Keyed hash of an OTP. Keyed, so a stolen row cannot be brute-forced offline."""
    return hmac.new(
        settings.SECRET_KEY.encode(), code.strip().encode(), hashlib.sha256
    ).hexdigest()


async def begin_enrollment(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    channel_kind: str,
    address: str,
    label: str | None = None,
    now: datetime | None = None,
) -> BindingResult:
    """Create (or refresh) an unverified binding and mint its OTP.

    The caller is responsible for having enforced T2 on the console session
    *before* getting here, and for delivering ``otp`` over the claimed channel.
    """
    at = now or datetime.utcnow()
    if channel_kind == ChannelKind.CONSOLE:
        # The console channel is the JWT login itself; there is nothing to
        # send an OTP to and nothing an enrollment would add.
        return BindingResult(False, "the console channel is bound by login, not enrollment")

    normalised = normalise_address(channel_kind, address)
    if not normalised:
        return BindingResult(False, "address is empty after normalisation")

    existing = (await db.execute(
        select(ChannelBinding).where(
            ChannelBinding.company_id == company_id,
            ChannelBinding.channel_kind == channel_kind,
            ChannelBinding.address == normalised,
        ).limit(1)
    )).scalars().first()

    if existing is not None and existing.user_id != user_id and existing.verified_at:
        # The address already speaks for someone else in this tenant. Silently
        # re-pointing it would let one user capture another's second factor.
        return BindingResult(False, "address is already bound to another user")

    # The tenant's own consent posture governs contacting the address, even
    # though the user is claiming it — a DNC'd number stays un-messaged.
    consent = await check_outbound_consent(
        company_id, channel_kind, normalised, purpose="transactional")
    if not consent.allowed:
        return BindingResult(False, f"cannot contact this address: {consent.reason}")

    code = f"{secrets.randbelow(10 ** _OTP_DIGITS):0{_OTP_DIGITS}d}"
    expires = at + timedelta(minutes=settings.INWARD_AUTH_OTP_TTL_MINUTES)

    if existing is None:
        binding = ChannelBinding(
            company_id=company_id, user_id=user_id, channel_kind=channel_kind,
            address=normalised, label=label, otp_hash=hash_otp(code),
            otp_expires_at=expires, otp_attempts=0)
        db.add(binding)
        await db.flush()
    else:
        binding = existing
        binding.user_id = user_id
        binding.label = label or binding.label
        binding.otp_hash = hash_otp(code)
        binding.otp_expires_at = expires
        binding.otp_attempts = 0
        binding.revoked_at = None
        await db.flush()

    # Delivery rides the SIG outbound seam rather than a sender of our own —
    # the platform has no separate OTP path, and inventing one here would put
    # a second unaudited way to message a counterparty into the product.
    await emit_signal(
        db,
        company_id=company_id,
        source="inward_auth",
        type=SignalTypes.AUTHN_CHANNEL_OTP,
        payload={
            "user_id": str(user_id),
            "binding_id": str(binding.id),
            "channel_kind": channel_kind,
            "address": normalised,
            "otp": code,
            "expires_at": expires.isoformat(),
        },
    )

    return BindingResult(True, "OTP issued", binding_id=binding.id, otp=code)


async def confirm_enrollment(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    binding_id: uuid.UUID,
    code: str,
    now: datetime | None = None,
) -> BindingResult:
    """Verify the OTP and mark the binding usable.

    Attempts are counted and the OTP is burned on success, so a code cannot be
    replayed and a guesser runs out of tries rather than time.
    """
    at = now or datetime.utcnow()
    binding = (await db.execute(
        select(ChannelBinding).where(
            ChannelBinding.id == binding_id,
            ChannelBinding.company_id == company_id,
            ChannelBinding.user_id == user_id,
        ).limit(1)
    )).scalars().first()

    if binding is None:
        return BindingResult(False, "no such pending binding")
    if binding.otp_hash is None:
        return BindingResult(False, "no enrollment in progress for this binding")
    if binding.otp_expires_at is None or binding.otp_expires_at <= at:
        return BindingResult(False, "the code has expired — start enrollment again")
    if binding.otp_attempts >= settings.INWARD_AUTH_OTP_MAX_ATTEMPTS:
        return BindingResult(False, "too many attempts — start enrollment again")

    binding.otp_attempts += 1
    if not hmac.compare_digest(binding.otp_hash, hash_otp(code)):
        await db.flush()
        return BindingResult(False, "code did not match", binding_id=binding.id)

    binding.verified_at = at
    binding.otp_hash = None
    binding.otp_expires_at = None
    binding.otp_attempts = 0
    await db.flush()
    return BindingResult(True, "channel verified", binding_id=binding.id)


async def resolve_inbound(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    channel_kind: str,
    address: str,
    now: datetime | None = None,
) -> ChannelBinding | None:
    """Resolve an inbound contact to its verified binding, or ``None``.

    ``None`` means unauthenticated, which is a routing outcome and not an
    error: Pragya answers T0 questions and offers an enrollment path, and
    refuses everything tenant-specific.
    """
    normalised = normalise_address(channel_kind, address)
    if not normalised:
        return None

    binding = (await db.execute(
        select(ChannelBinding).where(
            ChannelBinding.company_id == company_id,
            ChannelBinding.channel_kind == channel_kind,
            ChannelBinding.address == normalised,
            ChannelBinding.verified_at.is_not(None),
            ChannelBinding.revoked_at.is_(None),
        ).limit(1)
    )).scalars().first()

    if binding is not None:
        binding.last_seen_at = now or datetime.utcnow()
    return binding


async def list_bindings(
    db: AsyncSession, *, user_id: uuid.UUID, verified_only: bool = False,
) -> list[ChannelBinding]:
    """Every live binding for a user (revoked rows excluded)."""
    stmt = select(ChannelBinding).where(
        ChannelBinding.user_id == user_id,
        ChannelBinding.revoked_at.is_(None),
    )
    if verified_only:
        stmt = stmt.where(ChannelBinding.verified_at.is_not(None))
    return list((await db.execute(stmt)).scalars().all())


async def revoke_binding(
    db: AsyncSession, *, user_id: uuid.UUID, binding_id: uuid.UUID,
    now: datetime | None = None,
) -> bool:
    """Revoke a binding. Revocation is a tombstone, not a delete — the audit
    trail of which channel could once speak for this user has to survive."""
    binding = (await db.execute(
        select(ChannelBinding).where(
            ChannelBinding.id == binding_id,
            ChannelBinding.user_id == user_id,
        ).limit(1)
    )).scalars().first()
    if binding is None or binding.revoked_at is not None:
        return False
    binding.revoked_at = now or datetime.utcnow()
    await db.flush()
    return True


async def second_channel_for(
    db: AsyncSession, *, user_id: uuid.UUID, exclude_binding_id: uuid.UUID | None,
    exclude_kind: str | None = None,
) -> ChannelBinding | None:
    """Pick a verified binding *other than* the one that issued the command.

    This is the T3 out-of-band leg's whole premise: confirming on the channel
    that asked proves nothing, because that channel is the one that might be
    compromised. Returns ``None`` when no second channel exists, and the caller
    must fail closed on that.
    """
    candidates = await list_bindings(db, user_id=user_id, verified_only=True)
    for binding in candidates:
        if exclude_binding_id is not None and binding.id == exclude_binding_id:
            continue
        if exclude_kind is not None and binding.channel_kind == exclude_kind:
            continue
        return binding
    return None


async def alert_all_channels(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    event: str,
    detail: str,
) -> int:
    """Fan a security alert out to every verified channel the user registered.

    Emitted as signals rather than sent directly, so delivery rides the shipped
    outbound seams (and their consent gate) instead of growing a parallel
    sender. Returns how many channels were alerted.

    A channel suppressed by consent is logged and skipped rather than raising:
    losing one alert leg must not stop the others, and the console notification
    is always there regardless.
    """
    bindings = await list_bindings(db, user_id=user_id, verified_only=True)
    alerted = 0

    for binding in bindings:
        decision = await check_outbound_consent(
            company_id, binding.channel_kind, binding.address, purpose="transactional")
        if not decision.allowed:
            logger.info(
                "authn alert suppressed by consent: user=%s channel=%s reason=%s",
                user_id, binding.channel_kind, decision.reason)
            continue

        await emit_signal(
            db,
            company_id=company_id,
            source="inward_auth",
            type=SignalTypes.AUTHN_SECURITY_ALERT,
            payload={
                "user_id": str(user_id),
                "event": event,
                "detail": detail,
                "channel_kind": binding.channel_kind,
                "address": binding.address,
            },
        )
        alerted += 1

    return alerted
