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
    # AUTH (Inc 3): the inward-channel security signals. The out-of-band leg
    # for a T3 command, and the "someone is grinding step-ups" alert that fans
    # out to every channel the user has registered.
    AUTHN_CHANNEL_OTP = "authn.channel_otp"
    AUTHN_OOB_CONFIRM = "authn.oob_confirm"
    AUTHN_SECURITY_ALERT = "authn.security_alert"
    OBJECT_CHANGE_PROPOSED = "object.change_proposed"
    OBJECT_WRITE_CONFLICT = "object.write_conflict"
    # SoR (Inc-4 CONN+SOR, §21): an external change landed in the mirror; a
    # write-back that lost to a concurrent external edit (master wins); and the
    # audit trail of an owner-confirmed ownership migration (§21.4).
    OBJECT_SYNCED = "object.synced"
    SYNC_CONFLICT = "sync.conflict"
    GOVERNANCE_SOR_MIGRATED = "governance.sor_migrated"
    INCIDENT_GOVERNANCE = "incident.governance"
    # C4 (Inc 3): an agent lost an autonomy level. Emitted by the demotion
    # sweep so Pragya can report it in stage 9 rather than the owner finding
    # out by noticing their workforce got quieter.
    GOVERNANCE_AUTONOMY_DEMOTED = "governance.autonomy_demoted"
    INCIDENT_PLATFORM = "incident.platform"
    # EVX (Inc 5): the eval admission gate + canary rollout audit trail. Platform-
    # scoped (emitted on the APP company) — a model-fleet change is a §22.4 event.
    MODEL_ADMISSION_EVALUATED = "model.admission_evaluated"
    MODEL_CANARY_PROMOTED = "model.canary_promoted"
    MODEL_CANARY_ROLLED_BACK = "model.canary_rolled_back"
    # LEARN (Inc 6, B10): tenant-level learning rides the shipped bus rather
    # than a store of its own (charter decision 3). Every one of these is
    # company-scoped by the NOT NULL FK below — which is the tenant half of
    # decision 2's split, and the reason the *pooled* half needed a different
    # table entirely (a signal cannot exist without a company).
    LEARNING_OUTCOME_OBSERVED = "learning.outcome_observed"
    LEARNING_CHARTER_TUNING_PROPOSED = "learning.charter_tuning_proposed"
    LEARNING_DRIFT_DETECTED = "learning.drift_detected"
    LEARNING_DENSITY_OBSERVED = "learning.density_observed"
    # SEGA (Inc 6, B11/VG-17): the entity version ledger's audit trail. A
    # promotion and a rollback are both governance events an owner may be asked
    # about later, so they go on the bus rather than only into a table.
    GOVERNANCE_ENTITY_VERSIONED = "governance.entity_versioned"
    GOVERNANCE_ENTITY_ROLLED_BACK = "governance.entity_rolled_back"
    #: An agent asked for a field its HBS object lacked (§10.2, additive only).
    GOVERNANCE_SCHEMA_FIELD_PROPOSED = "governance.schema_field_proposed"
    # GATE (Inc 6, KAR-05/VG-15): the broadcast channels join the bus. Inbound
    # mentions, public comments and platform DMs arrive as `broadcast.inbound`
    # (trust: counterparty, like every other Karuna channel) for KAR-05 to
    # parse as data; a successful publish emits `broadcast.published` (trust:
    # internal) so the *outbound* half is audited even where the inbound half
    # is not yet polled.
    BROADCAST_INBOUND = "broadcast.inbound"
    BROADCAST_PUBLISHED = "broadcast.published"
    # TWIN (Inc 6, VG-09): the Glasshouse's audit trail. A scenario run is
    # tenant money spent (charter decision 7), and a promotion proposal is an
    # argument someone may be asked about later — both belong on the bus rather
    # than only in `twin_runs`.
    TWIN_SCENARIO_RUN = "twin.scenario_run"
    TWIN_PROMOTION_PROPOSED = "twin.promotion_proposed"
    # LIB (Inc 6, VG-14/VG-16): a connected drive mirrored a file, and a
    # binding's credentials are about to expire. The second is a *tray* signal
    # — §15.2's "bridge under repair" — and it fires before the break rather
    # than after, which is the only version of that notice worth sending.
    DOCUMENT_SYNCED = "document.synced"
    CONNECTOR_CREDENTIALS_EXPIRING = "connector.credentials_expiring"
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
