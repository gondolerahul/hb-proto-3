"""loop/models.py — LOOP runtime, budget envelopes, wallet holds (§17, §20.4, §23.3).

All three are control-plane tables (billing attribution + the heartbeat need one
operational store). FK targets are imported for metadata registration, matching
the orm/ and signals/ conventions.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

# FK targets registered before mapper configuration.
from src.auth.models import Company  # noqa: F401
from src.ai.orm.entity import HierarchicalEntity  # noqa: F401
from src.ai.orm.execution import ExecutionRun  # noqa: F401

__all__ = [
    "LoopRuntime",
    "BudgetEnvelope",
    "WalletHold",
    "HoldStatus",
    "PROTECTED_PROCESS_CODES",
    "BUDGET_CLASS_TENANT",
    "BUDGET_CLASS_PLATFORM",
]

# B13 — the two budget classes an envelope can carry.
BUDGET_CLASS_TENANT: str = "tenant"
BUDGET_CLASS_PLATFORM: str = "platform_initiated"

# P14 Continuous Guardrails + P17 Incident-to-Resolution are "never paused":
# their envelope share is pre-funded via reserved_usd (§20.4 / register A6).
PROTECTED_PROCESS_CODES: frozenset[str] = frozenset({"P14", "P17"})


class HoldStatus:
    ACTIVE = "ACTIVE"
    SETTLED = "SETTLED"
    EXHAUSTED = "EXHAUSTED"


class LoopRuntime(Base):
    """Operational state for one Loop — a Loop never gets an execution_runs row."""

    __tablename__ = "loop_runtime"

    loop_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), primary_key=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    heartbeat_interval_s: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    last_beat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_missed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Rolling KPI/cost aggregates per process/arc (§17.2).
    stats: Mapped[Any] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class BudgetEnvelope(Base):
    """A LOOP or PROCESS spend envelope, rolled up by the heartbeat (§20.4)."""

    __tablename__ = "budget_envelopes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=False)
    cycle: Mapped[str] = mapped_column(String(10), nullable=False, default="monthly")  # monthly | weekly
    # B13 — "tenant" (the Loop's spend) or "platform_initiated" (optimizer/meta/
    # sensing), each a separate capped envelope so platform work never starves
    # tenant work.
    budget_class: Mapped[str] = mapped_column(String(20), nullable=False, default="tenant")
    envelope_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    # Protected carve-out (P14/P17), pre-funded at refresh — never exempt.
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    spent_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    downshift_at_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class WalletHold(Base):
    """A cash reservation for a run — closes the E3 wallet race (§23.3)."""

    __tablename__ = "wallet_holds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=False, unique=True)
    amount_held: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)     # planner estimate, floored at tier min
    amount_spent: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=HoldStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
