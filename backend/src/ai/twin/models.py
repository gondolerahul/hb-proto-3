"""twin/models.py — the scenario shelf and its runs (TWIN T3).

Control-plane tables. The twin *plane* itself is not a migration — tenant
tables bootstrap per tenant (SCH, Inc 1), so `twin001` adds these two and
nothing else.

The one thing to notice in the shape: **`TwinRun.grade` has no setter path from
any API**. It is written by the engine from what the run actually had (§5.4).
L6 says the honesty layer is never softened, and the cheapest way to guarantee
that is to give no one a way to soften it.
"""
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
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

__all__ = ["ScenarioKind", "ScenarioStatus", "TwinScenario", "TwinRun"]


class ScenarioKind:
    """What a scenario varies. Closed, because each kind implies what has to be
    materialised and which levers mean anything."""

    CHARTER = "charter"
    POLICY = "policy"
    ROSTER = "roster"
    PRICING = "pricing"
    CUSTOM = "custom"


class ScenarioStatus:
    DRAFT = "draft"
    READY = "ready"        # estimated and acknowledged (§6.4)
    ARCHIVED = "archived"


class TwinScenario(Base):
    """A named, re-runnable what-if — the Scenario Shelf (§9)."""

    __tablename__ = "twin_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    #: What the scenario changes — the candidate side of the comparison.
    levers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: ``{"objects": [...], "window_days": n}`` — see `twin.materialise.Scope`.
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ScenarioStatus.DRAFT)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    #: The estimate the owner acknowledged before running (§6.4). Null until
    #: they have seen one, and the run path refuses without it.
    acknowledged_estimate_usd: Mapped[float | None] = mapped_column(
        Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class TwinRun(Base):
    """One execution in the glass room, and how much it should be believed."""

    __tablename__ = "twin_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    #: Nullable: a cached *baseline* replay belongs to no single scenario, which
    #: is the whole point — it is reused by every scenario comparing against it
    #: (§6.2).
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("twin_scenarios.id"), nullable=True)
    #: `replay` | `forecast` | `unknown`. **Computed, never supplied** (§5.4).
    grade: Mapped[str] = mapped_column(String(16), nullable=False)
    #: How the number was arrived at, in words the surface renders next to it —
    #: "seasonal-naive over 14 daily points", "replayed 63 signals".
    method: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Which version of the entity was in the glass room — the link to SEGA's
    #: ledger, and what makes a promotion's evidence checkable later.
    entity_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_versions.id"), nullable=True)
    #: Set when the run did not happen: over the daily cap, scope refused,
    #: series too short. A refusal is a result, not an error to be swallowed.
    refusal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        # The baseline cache lookup (§6.2) and the daily-cap sum (§6.6) both
        # scan by company and time.
        Index("ix_twin_runs_company_started", "company_id", "started_at"),
        Index("ix_twin_runs_baseline", "company_id", "is_baseline"),
    )
