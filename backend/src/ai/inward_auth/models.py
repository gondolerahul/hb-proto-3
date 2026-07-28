"""inward_auth/models.py — the AUTH control-plane tables (Inc-3, migration ``iauth001``).

Four tables, each answering one question:

* ``channel_bindings``          — which channel addresses speak for which user.
* ``account_manager_sessions``  — how strongly the current conversation is
  authenticated, and until when.
* ``webauthn_credentials``      — the registered passkeys.
* ``totp_secrets``              — the §11.3 fallback authenticator.
* ``oob_confirmations``         — the T3 second-channel leg, in flight.

Bindings are a table rather than columns on ``users`` because one user has many
channels, and the T3 out-of-band leg is *defined* by there being a second one.

``address`` is stored normalised (lower-cased email, digits-only phone), the
same convention TRUST's consent registry uses for ``channel_identity``, so an
inbound contact matches regardless of how the address was formatted on the wire.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

# FK targets registered before mapper configuration.
from src.auth.models import Company, User  # noqa: F401

__all__ = [
    "ChannelKind",
    "AuthLevel",
    "ChannelBinding",
    "AccountManagerSession",
    "WebAuthnCredential",
    "WebAuthnChallenge",
    "TotpSecret",
    "OobConfirmation",
    "normalise_address",
]


class ChannelKind:
    """The channels Pragya can be reached on. ``CONSOLE`` is the browser chat."""

    CONSOLE = "console"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    VOICE = "voice"


class AuthLevel:
    """How strongly the session is authenticated *right now*.

    Deliberately not the same vocabulary as the tiers: a tier describes what a
    command needs, a level describes what the session has. ``require_tier``
    is the only place the two meet.
    """

    NONE = "none"            # unresolved channel — nothing tenant-specific
    BOUND = "bound"          # a resolved binding / logged-in console session
    ELEVATED = "elevated"    # a step-up ceremony passed, within its window
    OOB_CONFIRMED = "oob_confirmed"  # elevated *and* a second channel agreed


def normalise_address(channel_kind: str, address: str) -> str:
    """Normalise a channel address for **exact** matching.

    Email lower-cases; phone-shaped channels keep digits only, so formatting
    noise is stripped (``+91 98765 43210``, ``+919876543210`` and
    ``91-98765-43210`` all normalise alike).

    Deliberately *not* smart about dialling conventions: ``09876543210`` and
    ``919876543210`` stay different addresses. Treating a national-format
    number as equal to its E.164 form means guessing a country, and a wrong
    guess here binds one subscriber's channel to another subscriber's account.
    Inbound WhatsApp and voice both deliver E.164, so the strict rule costs
    nothing at the only place that matters.
    """
    raw = address.strip()
    if channel_kind == ChannelKind.EMAIL:
        return raw.lower()
    if channel_kind in (ChannelKind.WHATSAPP, ChannelKind.VOICE):
        return "".join(ch for ch in raw if ch.isdigit())
    return raw.lower()


class ChannelBinding(Base):
    """A proven link between a channel address and a user.

    ``verified_at`` is what makes the row mean anything — an unverified row is
    a claim, not a binding, and never resolves inbound.
    """

    __tablename__ = "channel_bindings"
    __table_args__ = (
        UniqueConstraint("company_id", "channel_kind", "address",
                         name="uq_channel_binding_address"),
        # **An address belongs to at most one tenant** (owner decision,
        # 2026-07-26). Pragya answers on a *single shared number*, so the
        # number dialled no longer says which company the caller reached —
        # the caller's own address does. That only works if an address cannot
        # mean two tenants at once.
        #
        # Structural rather than a runtime tie-break, deliberately: the
        # alternative was asking a caller "which business?" or picking the
        # most-recent, and a wrong pick there is a cross-tenant disclosure
        # read aloud over the phone. Same reasoning as LEARN's B10 guarantee —
        # make it impossible to represent, not merely impolite to do.
        #
        # Partial on `revoked_at IS NULL`: a revoked binding is history, and
        # someone who genuinely leaves one business for another must be able
        # to register the same phone there.
        Index("uq_channel_binding_address_global", "channel_kind", "address",
              unique=True, postgresql_where=text("revoked_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    channel_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # The enrollment handshake (T5): an OTP hash + expiry, cleared on verify.
    otp_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    otp_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AccountManagerSession(Base):
    """A conversation with Pragya, and its current authentication strength.

    One row per (user, channel) conversation. ``elevated_until`` is checked at
    *execution* time, never at classification time — a command classified while
    elevated must still be elevated when it runs.
    """

    __tablename__ = "account_manager_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    channel_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    channel_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_level: Mapped[str] = mapped_column(String(20), nullable=False, default=AuthLevel.NONE)
    elevated_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    elevated_by: Mapped[str | None] = mapped_column(String(20), nullable=True)  # passkey|totp
    failed_stepups: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class WebAuthnCredential(Base):
    """A registered passkey.

    ``sign_count`` is stored because a counter that goes backwards is the
    standard cloned-authenticator signal; ``credential_id`` is the base64url
    handle the browser returns.
    """

    __tablename__ = "webauthn_credentials"
    __table_args__ = (
        UniqueConstraint("credential_id", name="uq_webauthn_credential_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    credential_id: Mapped[str] = mapped_column(String(512), nullable=False)
    public_key: Mapped[str] = mapped_column(String(2048), nullable=False)  # base64url COSE
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transports: Mapped[str | None] = mapped_column(String(120), nullable=True)
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class WebAuthnChallenge(Base):
    """A WebAuthn challenge issued and not yet spent.

    Challenges are stored rather than signed into a token the client carries,
    because WebAuthn's replay protection depends on a challenge being usable
    **once**. A self-describing token can only be time-boxed, which would leave
    a captured ceremony replayable for the whole of its lifetime.
    """

    __tablename__ = "webauthn_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)  # register|authenticate
    challenge: Mapped[str] = mapped_column(String(512), nullable=False)  # base64url
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class OobConfirmation(Base):
    """A T3 command waiting on its second-channel leg.

    ``command_ref`` binds the nonce to one specific command: a confirmation is
    agreement to *that* action, and a nonce that could confirm any pending T3
    would let an attacker swap in a different one. ``second_binding_id`` is
    recorded so the audit trail shows which channel actually agreed.
    """

    __tablename__ = "oob_confirmations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_manager_sessions.id"), nullable=False)
    second_binding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channel_bindings.id"), nullable=False)
    command_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    nonce_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class TotpSecret(Base):
    """The §11.3 fallback authenticator for users without a passkey device.

    ``secret`` is stored encrypted (see ``step_up.encrypt_seed``);
    ``last_used_slot`` blocks replay of a code inside its own 30-second window.
    """

    __tablename__ = "totp_secrets"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_totp_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    secret: Mapped[str] = mapped_column(String(512), nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_used_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
