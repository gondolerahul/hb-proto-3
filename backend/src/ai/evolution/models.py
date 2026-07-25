"""evolution/models.py — the entity version ledger (VG-17).

``hierarchical_entities.version`` is a single ``String`` defaulting to
``"1.0.0"``, and **editing an entity overwrites its JSON blocks**. So there is
nothing to diff, nothing to roll back to, and nothing for the Gallery's
"every version inspectable" or the Glasshouse's promotion diff to read. This is
that history.

**Full snapshots, not a diff chain.** A chain is smaller and is the wrong
choice here for two reasons: rollback has to work when the chain is broken, and
the Glasshouse's diff view needs two complete states anyway. Entity blocks are
small JSON, and the daily change cap (`blast_radius.Limits`) bounds growth from
the automated side.

**Every write goes through the ledger, human edits included.** A ledger that
records only automated changes cannot answer *"what did this agent look like
last Tuesday"*, which is the question the Gallery and every incident review
actually ask.

Import-light (column FKs, no ``relationship()``), the ``intelligence/models.py``
precedent.

Design: docs/product-road-map/increment-6/02_sega.md §5.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

__all__ = ["ChangeKindValues", "EntityVersion", "VersionStatus", "SNAPSHOT_BLOCKS"]


class ChangeKindValues:
    """Why a version exists. Wider than ``blast_radius.ChangeKind`` on purpose:
    that enum covers what may be *automated*, this covers what may be
    *recorded*, and humans do more than automation is allowed to."""

    HUMAN = "human"
    CHARTER_TUNE = "charter_tune"
    SCHEMA_PROPOSAL = "schema_proposal"
    TEMPLATE_APPLY = "template_apply"
    ROLLBACK = "rollback"


class VersionStatus:
    """Where a version sits in its life.

    ``CANARY`` is a **state, not a delay** — a low-traffic entity can sit in it
    for weeks while the canary honestly lacks the samples to judge, and the
    Gallery should render it that way rather than as something stuck.
    """

    CANARY = "canary"
    GA = "ga"
    ROLLED_BACK = "rolled_back"
    SUPERSEDED = "superseded"


#: The entity blocks a snapshot captures. Named here so "what is a version"
#: has one answer, and so a block added to ``HierarchicalEntity`` later is a
#: deliberate addition to history rather than a silent omission from it.
SNAPSHOT_BLOCKS: tuple[str, ...] = (
    "goal", "description", "identity", "hierarchy", "logic_gate", "planning",
    "capabilities", "governance", "io_contract", "observability",
    "metadata_extensions", "tags", "status",
)


class EntityVersion(Base):
    """One recorded state of one entity."""

    __tablename__ = "entity_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"),
        nullable=False, index=True)
    #: Denormalised so a scope check needs no join — the blast-radius predicate
    #: asks "whose row is this" on every automated change.
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    #: The full block set — see ``SNAPSHOT_BLOCKS``.
    snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    change_kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ChangeKindValues.HUMAN)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    #: The LEARN proposal this came from, when it came from one. **No FK** —
    #: signals are a different module, and this table stays import-light so a
    #: minimal context (a test touching only the ledger) configures its mapper
    #: without registering the signal-bus graph. Same treatment, and the same
    #: reason, as ``CallLog.voice_session_id``. A signal can also be reaped or
    #: replayed; a version must outlive the proposal that caused it.
    proposal_signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VersionStatus.GA)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("entity_id", "version", name="uq_entity_version"),
        Index("ix_entity_versions_company_entity_created",
              "company_id", "entity_id", "created_at"),
    )
