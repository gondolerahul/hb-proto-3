"""intelligence/models.py — the model registry ORM (REG / B12).

Two **control-plane** tables (the fleet is the same fleet for every tenant;
only credentials + allow-listing are per-company, and those stay on
``config.IntegrationRegistry``):

* ``ModelRegistry`` — the fleet catalog. Each row is one model, in one region,
  at one version, with a ``capability_profile`` (what the router scores) and a
  ``data_flow`` block (what D5's allow-list reads). Only ``status='active'``
  rows are router-eligible.
* ``ModelPrice`` — **effective-dated** pricing. A price change *closes* the
  current window (``effective_to = now``) and *inserts* a new open row; it
  never mutates a price in place. Billing for an event at time *t* resolves the
  window whose ``[effective_from, effective_to)`` contains *t* — which is what
  makes a past invoice reproducible (the B12 fix). See
  ``registry.RegistryService.resolve_price``.

Design: increment-5/01_model_registry.md §3.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.common.database import Base

# NOTE: these tables carry no *outbound* FK to another model — model_prices
# references model_registry (both defined here). The binding FK runs the other
# way (config.IntegrationRegistry.model_registry_id -> model_registry.id, added
# in REG T1), resolved by table name at DDL time, so this module deliberately
# imports no consumer model. Keeping it import-light means a minimal context
# (a test that only touches the registry) needn't register auth/config mappers.

__all__ = ["ModelRegistry", "ModelPrice", "ModelStatus", "RoutingDecision"]


class ModelStatus:
    """Lifecycle of a catalog row. Only ACTIVE is router-eligible; a flip to
    ACTIVE is a §22.4 admission event (EVX gates it — see intelligence/admission.py)."""

    PREVIEW = "preview"        # registered, not yet admitted; never a router candidate
    ACTIVE = "active"          # admitted; router-eligible
    DEPRECATED = "deprecated"  # superseded; still priced for reproducibility, not selected
    RETIRED = "retired"        # gone; kept for historical price resolution only


class ModelRegistry(Base):
    """One model, in one region, at one version — the fleet catalog (§3.1)."""

    __tablename__ = "model_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Router-facing stable key (family+profile), e.g. "claude-opus",
    # "gemini-2.5-flash", "glm-4.6". NOT the raw SDK id.
    model_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # anthropic · google · openai · azure_openai · mistral · zhipu · alibaba · internal
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # The concrete SDK id handed to the adapter, e.g. "claude-opus-4-8".
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Snapshot / version tag, e.g. "4-8", "002", "2025-01" (B12's missing axis).
    version: Mapped[str] = mapped_column(String(48), nullable=False, default="")
    # Deployment region, e.g. "us-east5", "eu-west1", "global" (B12's missing axis).
    region: Mapped[str] = mapped_column(String(48), nullable=False, default="global")

    # {reasoning_strength: 0..1, tool_reliability: 0..1, max_context: int,
    #  latency_class: "strict"|"standard"|"batch", modalities: [...], supports_tools: bool}
    capability_profile: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    # D5 sovereignty facts: {data_region, subprocessor, trains_on_customer_data, default_allowed}
    data_flow: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String(12), nullable=False, default=ModelStatus.PREVIEW)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    prices: Mapped[list["ModelPrice"]] = relationship(
        "ModelPrice", back_populates="model", cascade="all, delete-orphan")

    __table_args__ = (
        # The same model in two regions is two rows (they price + route differently).
        UniqueConstraint("provider", "model_name", "version", "region",
                         name="uq_model_registry_provider_model_version_region"),
        Index("ix_model_registry_status", "status"),
    )


class ModelPrice(Base):
    """An effective-dated price window for one (model, component) (§3.2).

    Invariant: for a given (model_registry_id, component_type) the
    [effective_from, effective_to) windows are non-overlapping and gap-free.
    A change closes the open row and inserts a new one — never mutates in place.
    """

    __tablename__ = "model_prices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_registry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="CASCADE"), nullable=False)

    # input_token · output_token · minute · character · image · ... (mirrors
    # IntegrationRegistry.component_type).
    component_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    cost_unit: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. "1k_tokens", "minute"
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # inclusive (UTC)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # exclusive; NULL = current

    model: Mapped["ModelRegistry"] = relationship("ModelRegistry", back_populates="prices")

    __table_args__ = (
        Index("ix_model_prices_lookup", "model_registry_id", "component_type", "effective_from"),
    )


class RoutingDecision(Base):
    """One router decision — which model, why, over which signals (RTR v1, §3.1).

    Column FKs only (run_id -> execution_runs, company_id -> companies,
    model_registry_id -> model_registry), **no relationships**, so this module
    stays import-light — the mapper configures without registering the run/auth
    graph. run_id is nullable (a standalone/Pragya call has no loop run);
    model_registry_id is nullable (an un-bound legacy integration still routes)."""

    __tablename__ = "routing_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True, index=True)
    step_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model_registry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_registry.id"), nullable=True)
    # "pinned" | "rule" | "auto" | "fallback" | "downshift"
    reason: Mapped[str] = mapped_column(String(16), nullable=False)
    signals: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)  # the RoutingSignals snapshot
    fallback_used: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
