"""evolution/ledger.py — recording what an entity looked like (VG-17).

Two operations and one rule. The operations: capture a snapshot on every write,
and restore one on a rollback. The rule: **the ledger is written in the same
transaction as the change it records**, so there is no state where an entity has
moved and its history has not.

Version numbering is a monotonic minor bump off whatever the entity currently
carries. It is not semantic versioning and does not pretend to be — nothing here
can tell a breaking charter change from a typo fix, and a scheme that implied it
could would be lying in a field people read.

Design: docs/product-road-map/increment-6/02_sega.md §5.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.evolution.models import (
    SNAPSHOT_BLOCKS,
    ChangeKindValues,
    EntityVersion,
    VersionStatus,
)

logger = logging.getLogger(__name__)

__all__ = [
    "next_version",
    "snapshot_of",
    "record_version",
    "latest_version",
    "version_history",
    "restore",
]


def snapshot_of(entity: Any) -> dict[str, Any]:
    """The entity's blocks, as a plain dict. Pure.

    Missing blocks are recorded as ``None`` rather than omitted, so a snapshot
    always has the same shape and a diff between two versions never has to
    distinguish "absent then" from "absent from the record".
    """
    return {block: getattr(entity, block, None) for block in SNAPSHOT_BLOCKS}


def next_version(current: str | None) -> str:
    """Bump the minor component. Pure, total, and deliberately unclever.

    An unparseable version starts a fresh ``1.0.1`` series rather than raising:
    a malformed version string is not a reason to refuse to record history,
    which is the moment history matters most.
    """
    parts = (current or "1.0.0").split(".")
    try:
        major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    except (IndexError, ValueError):
        return "1.0.1"
    return f"{major}.{minor}.{patch + 1}"


async def record_version(
    db: AsyncSession,
    entity: Any,
    *,
    company_id: uuid.UUID,
    change_kind: str = ChangeKindValues.HUMAN,
    changed_by_user_id: uuid.UUID | None = None,
    proposal_signal_id: uuid.UUID | None = None,
    status: str = VersionStatus.GA,
    bump: bool = True,
) -> EntityVersion | None:
    """Write a ledger row for ``entity``'s current state. The caller commits.

    Returns ``None`` on failure and never raises. That is a deliberate
    asymmetry with the rest of SEGA: the blast-radius predicate must refuse
    loudly, but *recording history* must never be the reason a human's edit
    fails. A missing ledger row is a gap in an audit trail; a failed save is a
    person's work lost.

    ``bump=False`` records the state under the entity's existing version — used
    when capturing the "before" of a change that is about to happen.
    """
    try:
        version = next_version(getattr(entity, "version", None)) if bump else str(
            getattr(entity, "version", None) or "1.0.0")

        row = EntityVersion(
            entity_id=entity.id,
            company_id=company_id,
            version=version,
            snapshot=snapshot_of(entity),
            change_kind=change_kind,
            changed_by_user_id=changed_by_user_id,
            proposal_signal_id=proposal_signal_id,
            status=status,
        )
        db.add(row)
        if bump:
            entity.version = version
        return row
    except Exception as exc:  # noqa: BLE001
        logger.warning("entity ledger: could not record %s: %s",
                       getattr(entity, "id", "?"), exc)
        return None


async def latest_version(
    db: AsyncSession, entity_id: uuid.UUID, *, status: str | None = None,
) -> EntityVersion | None:
    """The most recent ledger row for an entity, optionally filtered by status."""
    query = select(EntityVersion).where(EntityVersion.entity_id == entity_id)
    if status is not None:
        query = query.where(EntityVersion.status == status)
    query = query.order_by(EntityVersion.created_at.desc()).limit(1)
    return (await db.execute(query)).scalar_one_or_none()


async def version_history(
    db: AsyncSession, entity_id: uuid.UUID, *, limit: int = 50,
) -> list[EntityVersion]:
    """Newest first — what the Gallery renders and an incident review reads."""
    return list((await db.execute(
        select(EntityVersion)
        .where(EntityVersion.entity_id == entity_id)
        .order_by(EntityVersion.created_at.desc())
        .limit(limit)
    )).scalars().all())


async def restore(
    db: AsyncSession,
    entity: Any,
    target: EntityVersion,
    *,
    company_id: uuid.UUID,
) -> EntityVersion | None:
    """Put an entity back to a recorded state, and record *that* too.

    A rollback is a change like any other and gets its own ledger row, so the
    history reads forward — *"it was tuned, then rolled back"* — rather than
    appearing to have never happened. Silently rewinding would be the more
    convenient behaviour and the one that makes an incident review impossible.

    Refuses across tenants. A rollback is exempt from the rate cap and the kill
    switch (`blast_radius`), never from scope.
    """
    if target.company_id != company_id or target.entity_id != entity.id:
        logger.warning("entity ledger: refusing a cross-scope restore of %s", entity.id)
        return None

    for block, value in (target.snapshot or {}).items():
        if block in SNAPSHOT_BLOCKS:
            setattr(entity, block, value)

    target.status = VersionStatus.ROLLED_BACK
    return await record_version(
        db, entity, company_id=company_id,
        change_kind=ChangeKindValues.ROLLBACK, status=VersionStatus.GA)
