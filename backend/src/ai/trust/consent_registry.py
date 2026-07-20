"""trust/consent_registry.py — the consent registry (D6) behind the KAR seam.

``evaluate_consent`` is the enforcement: a send is denied when the counterparty
is on the tenant's DNC list, has unsubscribed from that purpose, or carries an
explicit ``denied`` consent record — otherwise allowed. That is the
**tenant-managed** posture (decision 8): the platform imposes no global opt-in
default; the registry enforces exactly what the tenant configured, and a
jurisdiction pack can later *tighten* it by implementing ``ConsentProvider``.

``install_consent_registry`` wires the provider into KAR's
``solo_pack.consent.set_consent_checker`` so every gateway outbound is gated —
no gateway call site changes.
"""
from __future__ import annotations

import uuid
from typing import Optional, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.solo_pack.consent import ConsentDecision
from src.ai.trust.models import (
    ConsentPurpose,
    ConsentRecord,
    ConsentStatus,
    DncEntry,
    UnsubscribeLog,
)

__all__ = [
    "normalise_identity",
    "evaluate_consent",
    "add_dnc",
    "record_unsubscribe",
    "set_consent",
    "ConsentProvider",
    "TenantManagedProvider",
    "install_consent_registry",
]

_PHONE_CHANNELS = frozenset({"whatsapp", "voice", "sms"})


def normalise_identity(channel: str, identity: str) -> str:
    """Canonical form for matching: digits-only phone, lower-cased email — so
    different formattings of the same address collapse to one key."""
    value = (identity or "").strip()
    if channel in _PHONE_CHANNELS:
        return "".join(ch for ch in value if ch.isdigit())
    return value.lower()


async def evaluate_consent(
    db: AsyncSession, company_id: uuid.UUID, channel: str, to_address: str,
    purpose: str = ConsentPurpose.TRANSACTIONAL,
) -> ConsentDecision:
    """Deny on DNC / unsubscribe / an explicit denial; else allow (tenant posture)."""
    ident = normalise_identity(channel, to_address)

    dnc = (await db.execute(
        select(DncEntry).where(
            DncEntry.company_id == company_id,
            DncEntry.channel == channel,
            DncEntry.channel_identity == ident,
        )
    )).scalar_one_or_none()
    if dnc is not None:
        return ConsentDecision(allowed=False, reason="on the do-not-contact list")

    unsub = (await db.execute(
        select(UnsubscribeLog).where(
            UnsubscribeLog.company_id == company_id,
            UnsubscribeLog.channel == channel,
            UnsubscribeLog.channel_identity == ident,
            UnsubscribeLog.purpose == purpose,
        )
    )).first()
    if unsub is not None:
        return ConsentDecision(allowed=False, reason=f"unsubscribed from {purpose}")

    record = (await db.execute(
        select(ConsentRecord).where(
            ConsentRecord.company_id == company_id,
            ConsentRecord.channel == channel,
            ConsentRecord.channel_identity == ident,
            ConsentRecord.purpose == purpose,
        )
    )).scalar_one_or_none()
    if record is not None and record.status == ConsentStatus.DENIED:
        return ConsentDecision(allowed=False, reason=f"consent denied for {purpose}")

    return ConsentDecision(
        allowed=True, reason="no do-not-contact / unsubscribe / denial on record")


async def add_dnc(
    db: AsyncSession, company_id: uuid.UUID, channel: str, identity: str,
    reason: Optional[str] = None,
) -> DncEntry:
    """Add a channel-identity to the tenant's do-not-contact list (idempotent)."""
    ident = normalise_identity(channel, identity)
    existing = (await db.execute(
        select(DncEntry).where(
            DncEntry.company_id == company_id, DncEntry.channel == channel,
            DncEntry.channel_identity == ident)
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    entry = DncEntry(company_id=company_id, channel=channel,
                     channel_identity=ident, reason=reason)
    db.add(entry)
    await db.flush()
    return entry


async def record_unsubscribe(
    db: AsyncSession, company_id: uuid.UUID, channel: str, identity: str,
    purpose: str = ConsentPurpose.MARKETING,
) -> UnsubscribeLog:
    """Log an unsubscribe for a purpose (append-only)."""
    entry = UnsubscribeLog(
        company_id=company_id, channel=channel,
        channel_identity=normalise_identity(channel, identity), purpose=purpose)
    db.add(entry)
    await db.flush()
    return entry


async def set_consent(
    db: AsyncSession, company_id: uuid.UUID, channel: str, identity: str,
    purpose: str, status: str, source: str = "tenant",
) -> ConsentRecord:
    """Upsert an explicit consent status for a channel-identity + purpose."""
    ident = normalise_identity(channel, identity)
    record = (await db.execute(
        select(ConsentRecord).where(
            ConsentRecord.company_id == company_id, ConsentRecord.channel == channel,
            ConsentRecord.channel_identity == ident, ConsentRecord.purpose == purpose)
    )).scalar_one_or_none()
    if record is None:
        record = ConsentRecord(
            company_id=company_id, channel=channel, channel_identity=ident,
            purpose=purpose, status=status, source=source)
        db.add(record)
    else:
        record.status = status
        record.source = source
    await db.flush()
    return record


class ConsentProvider(Protocol):
    """Pluggable consent adapter (the KAR seam contract). Jurisdiction packs
    implement this to tighten the tenant's posture."""

    async def check(
        self, company_id: uuid.UUID, channel: str, to_address: str, purpose: str,
    ) -> ConsentDecision: ...


class TenantManagedProvider:
    """The built-in adapter — enforces the tenant's own DNC/unsubscribe/consent."""

    async def check(
        self, company_id: uuid.UUID, channel: str, to_address: str, purpose: str,
    ) -> ConsentDecision:
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            return await evaluate_consent(db, company_id, channel, to_address, purpose)


def install_consent_registry(provider: Optional[ConsentProvider] = None) -> None:
    """Wire a consent provider into the KAR outbound seam (default: tenant-managed)."""
    from src.ai.solo_pack.consent import set_consent_checker

    set_consent_checker((provider or TenantManagedProvider()).check)
