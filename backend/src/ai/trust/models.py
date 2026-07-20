"""trust/models.py — the consent registry tables (D6, control-plane).

Global-neutral (decision 5): no jurisdiction is hard-coded. Three tables model
a counterparty's contact posture per purpose; the tenant-managed provider reads
them, and jurisdiction packs (India DND, US TCPA, EU GDPR) are later adapters
that may *tighten* — never loosen — what the tenant configured.

* ``consent_records``  — explicit granted/denied per (channel-identity, purpose).
* ``dnc_entries``      — do-not-contact for a channel-identity (any purpose).
* ``unsubscribe_log``  — an unsubscribe event per (channel-identity, purpose).

``channel_identity`` is stored normalised (lower-cased email; digits-only phone)
so matching is exact regardless of how the address was formatted inbound.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

# FK target registered before mapper configuration.
from src.auth.models import Company  # noqa: F401

__all__ = [
    "ConsentPurpose",
    "ConsentStatus",
    "ConsentRecord",
    "DncEntry",
    "UnsubscribeLog",
]


class ConsentPurpose:
    """The per-purpose posture (recording is a stub until voice ships)."""

    MARKETING = "marketing"
    TRANSACTIONAL = "transactional"
    RECORDING = "recording"


class ConsentStatus:
    GRANTED = "granted"
    DENIED = "denied"


class ConsentRecord(Base):
    """Explicit consent status for a counterparty channel-identity + purpose."""

    __tablename__ = "consent_records"
    __table_args__ = (
        UniqueConstraint("company_id", "channel", "channel_identity", "purpose",
                         name="uq_consent_identity_purpose"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)     # email|whatsapp|voice
    channel_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)     # ConsentPurpose
    status: Mapped[str] = mapped_column(String(12), nullable=False)      # ConsentStatus
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="tenant")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class DncEntry(Base):
    """Do-not-contact for a channel-identity across every purpose."""

    __tablename__ = "dnc_entries"
    __table_args__ = (
        UniqueConstraint("company_id", "channel", "channel_identity",
                         name="uq_dnc_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    channel_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class UnsubscribeLog(Base):
    """An unsubscribe event — the presence of a row denies that purpose."""

    __tablename__ = "unsubscribe_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    channel_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
