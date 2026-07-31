"""trust/consent_read.py — the consent registry, read (D8 E1/E2).

The registry (``consent_registry.py``) has enforced sends since Increment 2
and the three tables have shipped since migration ``trust001``, behind no
router at all: the Bridges board's gate panel and the Undercroft's consent
bay both rendered fixtures. This module is the read half, and it exists
once so the two readers — ``GET /ai/consent`` and the estate's gatehouses —
cannot disagree about a tenant's posture.

Two rules it keeps:

* **The posture is the registry's own answer, never a second copy of the
  rules.** ``channel_posture`` calls :func:`evaluate_channel_posture` — the
  same function the outbound seam calls — once per purpose, and reports
  what it says, including its reason string verbatim. A panel that computed
  "open" from the rows itself would eventually disagree with the gate that
  actually refuses the send, and the tenant would believe the panel.
* **``__channel__`` is not a person.** The channel-wide posture row is
  stored under ``CHANNEL_POSTURE_IDENTITY`` (Inc-6 GATE T3), which is the
  tenant's own switch, not a counterparty who asked to be left alone. It is
  excluded from every count and every entry here and surfaces only as the
  channel's posture — a bay headed "who asked us to stop" that listed the
  tenant's own marketing switch as a person would be a lie about a number
  the tenant is meant to act on.

``posture`` takes three values, all derived from the registry's answers over
the purposes it models: ``open`` (every purpose allowed), ``closed`` (none),
``restricted`` (some). Recording is not asked about — it is a stub until
voice ships (see ``ConsentPurpose``), and asking would invent a posture for
a purpose nothing sets.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.trust.consent_registry import (
    CHANNEL_POSTURE_IDENTITY,
    evaluate_channel_posture,
)
from src.ai.trust.models import (
    ConsentPurpose,
    ConsentRecord,
    ConsentStatus,
    DncEntry,
    UnsubscribeLog,
)

__all__ = [
    "POSTURE_PURPOSES",
    "channel_consent",
    "channel_posture",
    "consent_view",
]

#: The purposes a channel posture is reported for. ``recording`` is left out
#: deliberately: nothing sets it yet, so reporting it would mean publishing
#: "open" for a purpose no tenant has ever been asked about.
POSTURE_PURPOSES: tuple[str, ...] = (
    ConsentPurpose.MARKETING,
    ConsentPurpose.TRANSACTIONAL,
)

#: Ceiling on the entry list, so one busy tenant's DNC list cannot become the
#: response. The router's ``limit`` is bounded by this.
MAX_ENTRIES = 1000


async def channel_posture(
    db: AsyncSession, company_id: uuid.UUID, channel: str,
) -> dict[str, Any]:
    """This tenant's posture on one channel, in the registry's own words."""
    allowed: dict[str, bool] = {}
    reasons: dict[str, str] = {}
    for purpose in POSTURE_PURPOSES:
        decision = await evaluate_channel_posture(db, company_id, channel, purpose)
        allowed[purpose] = decision.allowed
        reasons[purpose] = decision.reason

    denied = [p for p in POSTURE_PURPOSES if not allowed[p]]
    if not denied:
        posture = "open"
    elif len(denied) == len(POSTURE_PURPOSES):
        posture = "closed"
    else:
        posture = "restricted"
    # The reason shown is the one that restricts, where one does — a panel
    # showing "no posture set" beside a closed gate reads as a bug.
    reason = reasons[denied[0]] if denied else reasons[POSTURE_PURPOSES[0]]
    return {"posture": posture, "reason": reason, "purposes": allowed}


async def _dnc_by_channel(
    db: AsyncSession, company_id: uuid.UUID,
) -> dict[str, int]:
    rows = (
        await db.execute(
            select(DncEntry.channel, func.count())
            .where(
                DncEntry.company_id == company_id,
                DncEntry.channel_identity != CHANNEL_POSTURE_IDENTITY,
            )
            .group_by(DncEntry.channel))
    ).all()
    return {str(channel): int(count) for channel, count in rows}


async def _unsubscribed_by_channel(
    db: AsyncSession, company_id: uuid.UUID,
) -> dict[str, int]:
    """Distinct counterparties, not rows: the log is append-only, and one
    person unsubscribing from two purposes is one person."""
    rows = (
        await db.execute(
            select(
                UnsubscribeLog.channel,
                func.count(func.distinct(UnsubscribeLog.channel_identity)))
            .where(UnsubscribeLog.company_id == company_id)
            .group_by(UnsubscribeLog.channel))
    ).all()
    return {str(channel): int(count) for channel, count in rows}


async def _records_by_channel(
    db: AsyncSession, company_id: uuid.UUID,
) -> dict[str, dict[str, int]]:
    rows = (
        await db.execute(
            select(ConsentRecord.channel, ConsentRecord.status, func.count())
            .where(
                ConsentRecord.company_id == company_id,
                ConsentRecord.channel_identity != CHANNEL_POSTURE_IDENTITY,
            )
            .group_by(ConsentRecord.channel, ConsentRecord.status))
    ).all()
    counts: dict[str, dict[str, int]] = {}
    for channel, status, count in rows:
        bucket = counts.setdefault(str(channel), {"granted": 0, "denied": 0})
        if str(status) == ConsentStatus.GRANTED:
            bucket["granted"] += int(count)
        elif str(status) == ConsentStatus.DENIED:
            bucket["denied"] += int(count)
    return counts


async def channel_consent(
    db: AsyncSession, company_id: uuid.UUID, channels: list[str],
) -> dict[str, dict[str, Any]]:
    """Posture plus counterparty counts for each named channel.

    The counts are three grouped queries however many channels are asked
    about. The posture is not batched: it is two queries per channel and
    purpose, because it comes from :func:`evaluate_channel_posture` rather
    than from rows read here. That is the deliberate trade — a batched copy
    of the precedence rules would be the cheaper read that eventually
    disagrees with the gate — and it is bounded by the channel set, which is
    a handful of doors, not a tenant's contact list.
    """
    dnc = await _dnc_by_channel(db, company_id)
    unsubscribed = await _unsubscribed_by_channel(db, company_id)
    records = await _records_by_channel(db, company_id)

    out: dict[str, dict[str, Any]] = {}
    for channel in sorted(set(channels)):
        block = await channel_posture(db, company_id, channel)
        record_counts = records.get(channel, {"granted": 0, "denied": 0})
        block["dnc"] = dnc.get(channel, 0)
        block["unsubscribed"] = unsubscribed.get(channel, 0)
        block["granted"] = record_counts["granted"]
        block["denied"] = record_counts["denied"]
        out[channel] = block
    return out


async def _channels_seen(db: AsyncSession, company_id: uuid.UUID) -> list[str]:
    """Every channel this tenant has any row for — posture rows included, so
    a channel switched off before anyone was ever contacted still appears."""
    channels: set[str] = set()
    for column, model_company in (
        (ConsentRecord.channel, ConsentRecord.company_id),
        (DncEntry.channel, DncEntry.company_id),
        (UnsubscribeLog.channel, UnsubscribeLog.company_id),
    ):
        rows = (
            await db.execute(
                select(column).where(model_company == company_id).distinct())
        ).scalars().all()
        channels.update(str(row) for row in rows)
    return sorted(channels)


def _entry(
    kind: str, channel: Any, identity: Any, at: Any,
    *, purpose: Any = None, status: Any = None, reason: Any = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "channel": str(channel),
        "identity": str(identity),
        "purpose": str(purpose) if purpose is not None else None,
        "status": str(status) if status is not None else None,
        "reason": str(reason) if reason is not None else None,
        "at": at.isoformat() if isinstance(at, datetime) else None,
    }


async def _entries(
    db: AsyncSession, company_id: uuid.UUID, limit: int,
) -> list[dict[str, Any]]:
    """The three tables as one newest-first list. Each table is capped at
    ``limit`` before the merge, so the query cost is bounded even when one
    table dwarfs the others."""
    dnc_rows = (
        await db.execute(
            select(DncEntry)
            .where(
                DncEntry.company_id == company_id,
                DncEntry.channel_identity != CHANNEL_POSTURE_IDENTITY,
            )
            .order_by(DncEntry.created_at.desc())
            .limit(limit))
    ).scalars().all()
    unsub_rows = (
        await db.execute(
            select(UnsubscribeLog)
            .where(UnsubscribeLog.company_id == company_id)
            .order_by(UnsubscribeLog.created_at.desc())
            .limit(limit))
    ).scalars().all()
    record_rows = (
        await db.execute(
            select(ConsentRecord)
            .where(
                ConsentRecord.company_id == company_id,
                ConsentRecord.channel_identity != CHANNEL_POSTURE_IDENTITY,
            )
            .order_by(ConsentRecord.updated_at.desc())
            .limit(limit))
    ).scalars().all()

    entries = [
        _entry("dnc", row.channel, row.channel_identity, row.created_at,
               reason=row.reason)
        for row in dnc_rows
    ] + [
        _entry("unsubscribe", row.channel, row.channel_identity, row.created_at,
               purpose=row.purpose)
        for row in unsub_rows
    ] + [
        _entry("consent", row.channel, row.channel_identity, row.updated_at,
               purpose=row.purpose, status=row.status, reason=row.source)
        for row in record_rows
    ]
    entries.sort(key=lambda e: e["at"] or "", reverse=True)
    return entries[:limit]


async def consent_view(
    db: AsyncSession, company_id: uuid.UUID, *,
    limit: int = 200, now: datetime | None = None,
) -> dict[str, Any]:
    """The whole registry for one company: per-channel posture, the totals
    the bay counts, and the entries themselves.

    Company-scoped by the caller (the router takes it from the session and
    never from a parameter — the VG-05 rule), and every query here filters
    on it: a cross-tenant read is not expressible.
    """
    at = now or datetime.utcnow()
    limit = max(1, min(limit, MAX_ENTRIES))
    channels = await _channels_seen(db, company_id)
    blocks = await channel_consent(db, company_id, channels)
    entries = await _entries(db, company_id, limit)

    return {
        "as_of": at.isoformat(),
        "totals": {
            "dnc": sum(b["dnc"] for b in blocks.values()),
            "unsubscribed": sum(b["unsubscribed"] for b in blocks.values()),
            "granted": sum(b["granted"] for b in blocks.values()),
            "denied": sum(b["denied"] for b in blocks.values()),
        },
        "channels": [
            {"channel": channel, **blocks[channel]} for channel in channels
        ],
        "entries": entries,
        "limit": limit,
    }
