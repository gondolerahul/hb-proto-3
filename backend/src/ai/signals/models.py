"""signals/models.py — Signal + TriggerRegistration ORM (technical doc §18.1)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

# FK targets must be registered with the metadata before mapper
# configuration (same rule as src/ai/orm/__init__.py).
from src.auth.models import Company  # noqa: F401
from src.ai.orm.entity import HierarchicalEntity  # noqa: F401
from src.ai.orm.execution import ExecutionRun  # noqa: F401

__all__ = [
    "Signal",
    "TriggerRegistration",
    "SignalStatus",
    "SignalUrgency",
    "SignalTrust",
    "SignalSource",
    "SignalTypes",
    "MAX_DISPATCH_ATTEMPTS",
    "MAX_PARK_REVIEWS",
    "PARK_REVIEW_DEFAULT_S",
]

# Dispatch failure → DEAD after this many attempts (§18.3).
MAX_DISPATCH_ATTEMPTS = 5
# PARKED signals escalate after this many unresolved reviews (decision 2026-07-19).
MAX_PARK_REVIEWS = 3
# Default park review timer: 15 minutes (decision 2026-07-19).
PARK_REVIEW_DEFAULT_S = 900


class SignalStatus:
    PENDING = "PENDING"
    CONSUMED = "CONSUMED"
    PARKED = "PARKED"
    ESCALATED = "ESCALATED"
    DEAD = "DEAD"


class SignalUrgency:
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class SignalTrust:
    COUNTERPARTY = "counterparty"
    EXTERNAL_VERIFIED = "external_verified"
    INTERNAL = "internal"
    PLATFORM = "platform"


class SignalSource:
    KARUNA_GATEWAY = "karuna_gateway"
    CONNECTOR = "connector"
    TELEMETRY = "telemetry"
    SCHEDULE = "schedule"
    AGENT = "agent"
    HUMAN = "human"


class SignalTypes:
    """Increment-1 seed taxonomy (01_sig doc §5; full Blueprint taxonomy in Inc 2)."""

    EMAIL_INBOUND = "email.inbound"
    # KAR (Inc 2): raw inbound from the messaging + voice channels — consumed by
    # the KAR-03 / KAR-01 gateways, same shape as email.inbound.
    MESSAGE_INBOUND = "message.inbound"
    VOICE_INBOUND = "voice.inbound"
    OBJECT_CHANGE_PROPOSED = "object.change_proposed"
    OBJECT_WRITE_CONFLICT = "object.write_conflict"
    INCIDENT_GOVERNANCE = "incident.governance"
    INCIDENT_PLATFORM = "incident.platform"
    SCHEDULE_PREFIX = "schedule."
    COMPLETED_SUFFIX = ".completed"


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    type: Mapped[str] = mapped_column(String(120), nullable=False)
    urgency: Mapped[str] = mapped_column(String(10), nullable=False, default=SignalUrgency.NORMAL)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    trust: Mapped[str] = mapped_column(String(20), nullable=False, default=SignalTrust.INTERNAL)
    object_refs: Mapped[Any] = mapped_column(JSON, nullable=True)
    payload: Mapped[Any] = mapped_column(JSON, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default=SignalStatus.PENDING)
    owner_process_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    consumed_by_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True)
    # For PENDING: retry not-before (exponential backoff); for PARKED: review timer.
    park_review_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # For PENDING: dispatch attempts; for PARKED: unresolved review count.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    replayed_from: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("signals.id"), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        # Producer-side idempotency: one row per external event id (§18.4).
        Index(
            "uq_signals_company_dedupe",
            "company_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
        # Dispatcher claim scan: PENDING/PARKED by age.
        Index("ix_signals_status_created", "status", "created_at"),
        Index("ix_signals_company_status", "company_id", "status"),
    )


class TriggerRegistration(Base):
    """The trigger registry: which Process owns which signal types (§18.1)."""

    __tablename__ = "trigger_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    process_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=False)
    type_pattern: Mapped[str] = mapped_column(String(120), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_trigger_registry_company_enabled", "company_id", "enabled"),
    )
