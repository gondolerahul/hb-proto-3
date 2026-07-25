"""evolution/proposals.py — LEARN proposes, SEGA disposes (T7, closes B11).

This is where the two workstreams meet, and it is the only place an automated
entity change can happen. LEARN emits ``learning.charter_tuning_proposed`` and
may not touch an entity — an import-boundary test makes that a build failure.
Here the proposal is *judged* (``blast_radius.admit_change``), *applied*, and
*recorded* as a canary version the sweep will later promote or roll back.

Until this module existed, ``admit_change`` was a guarantee with no caller.
B11 asks what forbids a self-heal from mutating a global artifact; the answer
is only real once something is actually routed through it.

**Every refusal is recorded, not swallowed.** A proposal that fails a limit
parks its signal with the reason, so "why did nothing happen?" has an answer in
the same place a human is already looking. A silent refusal and a silent bug
look identical from the outside.

Design: docs/product-road-map/increment-6/02_sega.md §4, §5, §10.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.evolution.blast_radius import (
    BlastRadiusError,
    ChangeKind,
    ChangeRequest,
    Limits,
    admit_change,
)
from src.ai.evolution.ledger import record_version
from src.ai.evolution.models import ChangeKindValues, EntityVersion, VersionStatus

logger = logging.getLogger(__name__)

__all__ = ["apply_proposal", "consume_proposals"]


async def _changes_today(
    db: AsyncSession, company_id: uuid.UUID, *, now: datetime,
) -> int:
    """Automated ledger rows this company has accrued since midnight UTC.

    Counted from the **ledger**, not from a counter: a counter can drift from
    what actually happened, and the limit is about what actually happened.
    """
    since = datetime(now.year, now.month, now.day)
    return int((await db.execute(
        select(func.count(EntityVersion.id)).where(
            EntityVersion.company_id == company_id,
            EntityVersion.created_at >= since,
            EntityVersion.change_kind.in_(
                (ChangeKindValues.CHARTER_TUNE, ChangeKindValues.SCHEMA_PROPOSAL)),
        )
    )).scalar() or 0)


async def apply_proposal(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    entity_id: uuid.UUID,
    field: str,
    addition: str,
    signal_id: uuid.UUID | None = None,
    now: datetime | None = None,
    limits: Limits | None = None,
) -> EntityVersion:
    """Judge, apply and record one charter tune. Raises ``BlastRadiusError``.

    The caller commits. The entity is loaded **through its company** before
    anything else happens, so a proposal naming another tenant's entity finds
    nothing to change — scope first, then act, and the blast-radius predicate
    is a second layer rather than the only one.
    """
    from src.ai.orm.entity import HierarchicalEntity
    from src.auth.models import Company

    at = now or datetime.utcnow()

    entity = (await db.execute(
        select(HierarchicalEntity).where(
            HierarchicalEntity.id == entity_id,
            HierarchicalEntity.company_id == company_id,
            HierarchicalEntity.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if entity is None:
        raise BlastRadiusError(
            f"refusing: entity {entity_id} is not {company_id}'s to change")

    subscription = (await db.execute(
        select(Company.subscription_status).where(Company.id == company_id)
    )).scalar() or "current"

    admit_change(
        ChangeRequest(
            kind=ChangeKind.CHARTER_TUNE,
            initiator_company_id=company_id,
            target_company_id=entity.company_id,
            fields=(field,),
            changes_today=await _changes_today(db, company_id, now=at),
            # No traffic split exists: an entity has one row, so an applied
            # change is live for everyone (`entity_canary.stamp_run_version`).
            # The cohort limit stays in the predicate for the day the loop can
            # compose from a version snapshot; today there is nothing to cap.
            canary_fraction=0.0,
            subscription_status=str(subscription),
        ),
        limits or Limits(),
    )

    # Append rather than replace. A learning proposal is an *addition* to what
    # a colleague was told, not a rewrite of it: replacing a goal an owner
    # wrote with a sentence a loop inferred is exactly the overreach the field
    # allow-list exists to bound.
    current = getattr(entity, field, None) or ""
    setattr(entity, field, f"{current}\n\n{addition}".strip())

    version = await record_version(
        db, entity, company_id=company_id,
        change_kind=ChangeKindValues.CHARTER_TUNE,
        proposal_signal_id=signal_id,
        status=VersionStatus.CANARY)
    if version is None:
        raise BlastRadiusError("refusing: the change could not be recorded")
    return version


async def consume_proposals(
    db: AsyncSession, company_id: uuid.UUID, *, now: datetime | None = None,
    lookback_days: int = 7,
) -> dict[str, Any]:
    """Apply every pending charter-tuning proposal for a company. Commits.

    A proposal older than ``lookback_days`` is ignored rather than applied: the
    evidence behind it has aged out, and quietly acting on a stale conclusion is
    worse than acting on none.
    """
    from src.ai.signals.models import Signal, SignalStatus, SignalTypes

    at = now or datetime.utcnow()
    proposals = (await db.execute(
        select(Signal).where(
            Signal.company_id == company_id,
            Signal.type == SignalTypes.LEARNING_CHARTER_TUNING_PROPOSED,
            Signal.status == SignalStatus.PENDING,
            Signal.created_at >= at - timedelta(days=lookback_days),
        )
    )).scalars().all()

    applied = 0
    refused: list[str] = []
    for signal in proposals:
        payload = signal.payload if isinstance(signal.payload, dict) else {}
        try:
            await apply_proposal(
                db,
                company_id=company_id,
                entity_id=uuid.UUID(str(payload["entity_id"])),
                field=str(payload["field"]),
                addition=str(payload["addition"]),
                signal_id=signal.id,
                now=at)
        except (BlastRadiusError, KeyError, ValueError) as exc:
            # Parked, with the reason on the row. A refusal a human cannot see
            # is indistinguishable from a bug.
            signal.status = SignalStatus.PARKED
            signal.last_error = str(exc)[:500]
            refused.append(str(exc))
            logger.info("charter tune refused for %s: %s", company_id, exc)
            continue

        signal.status = SignalStatus.CONSUMED
        signal.consumed_at = at
        applied += 1

    await db.commit()
    return {"proposals": len(proposals), "applied": applied, "refused": refused}
