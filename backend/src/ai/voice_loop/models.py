"""voice_loop/models.py — handoff + deferred-run state (migration ``voice001``).

Two tables, both existing because a call is a conversation that outlives the
turn that started it.

``voice_handoffs`` records an agent-to-agent switch **on the same media
session**. It is a record rather than a transient because the audit question
"who was driving when that was said?" has to be answerable afterwards, and
because the receiving agent reads its context from here.

``voice_deferred_runs`` is the queue of calls awaiting their post-call loop —
the stages the realtime profile could not fit inside a turn.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

# FK targets registered before mapper configuration.
from src.auth.models import Company  # noqa: F401

__all__ = ["VoiceHandoff", "VoiceDeferredRun", "DeferredRunStatus"]


class DeferredRunStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class VoiceHandoff(Base):
    """An agent-to-agent handoff within one call.

    ``tier_ceiling`` is carried explicitly rather than recomputed: a caller
    must not become better authenticated by being transferred, which would
    make transfer an escalation path.
    """

    __tablename__ = "voice_handoffs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    call_sid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    from_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    to_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Summarised transcript, not a replay — the receiving agent needs the
    #: gist, and a full replay would blow the realtime context window.
    context_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Records already identified, so the caller is not re-asked.
    resolved_records: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    tier_ceiling: Mapped[str] = mapped_column(String(4), nullable=False, default="T1")
    caller_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class VoiceDeferredRun(Base):
    """A completed call awaiting the stages the live turn could not run."""

    __tablename__ = "voice_deferred_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    call_sid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default=DeferredRunStatus.PENDING, index=True)
    transcript: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    #: Which profile stages this run is responsible for executing.
    stages: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    execution_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
