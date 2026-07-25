"""learning/models.py — the LEARN stores (B10) and the guarantee one of them makes.

Four **control-plane** tables, and the interesting thing about them is that they
are not all the same *kind* of table:

* :class:`PlatformObservation` — the **pooled** path. It has no ``company_id``
  column, no ``payload``, no ``text``: every column is a foreign key to a
  *platform* catalog row, a member of a closed vocabulary, a date bucket, or a
  counter. Charter decision 2 requires the pooled path to be *structurally
  incapable* of carrying tenant content, and this is what that means in
  practice — a customer's name has nowhere to go, so putting one here is a type
  error rather than a policy violation.
* :class:`KpiSnapshot`, :class:`EntityBehaviourWeekly`, :class:`UserPreference`
  — the **tenant** path, company-scoped by a NOT NULL FK, exactly as every
  other tenant-scoped control-plane table is.

**Do not add a JSONB or text column to** :class:`PlatformObservation`. Charter
decision 8 (pooled learning is disclosed and has no opt-out) is justified *only*
by the guarantee above; the two stand or fall together, and a free-form column
would repeal the first silently. ``test_learning_models.py`` asserts the column
set exactly, so the repeal would at least be loud.

Aggregation, not dual-writing: pooled rows are produced by the daily job in
``learning/pooling.py``, which reads the company-scoped ``routing_decisions``
and applies the k-anonymity floor *there* — where the company ids are still
visible — before writing a row that cannot hold them.

Import-light on purpose (the ``intelligence/models.py`` precedent): column FKs
only, no ``relationship()``, so a test that touches only these tables need not
register the auth/execution mapper graph.

Design: docs/product-road-map/increment-6/01_learn.md §4, §6, §8, §9.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

__all__ = [
    "EntityBehaviourWeekly",
    "KpiSnapshot",
    "NO_MODEL",
    "ObservationMetric",
    "PlatformObservation",
    "POOLED_COLUMNS",
    "UserPreference",
]


class ObservationMetric:
    """The closed vocabulary of ``PlatformObservation.metric``.

    Closed because an open one is a free-text column wearing a different name.
    A new metric is a code change and a review, which is the point.
    """

    ROUTE_OUTCOME = "route_outcome"
    MODEL_FAILURE = "model_failure"
    FALLBACK_USED = "fallback_used"
    ADMISSION_SCORE = "admission_score"

    ALL: frozenset[str] = frozenset(
        {ROUTE_OUTCOME, MODEL_FAILURE, FALLBACK_USED, ADMISSION_SCORE})


#: The stand-in for "this observation names no catalog model" in the grain's
#: unique index. A real ``model_registry.id`` is a uuid4 and can never be nil,
#: so the sentinel collides with nothing.
NO_MODEL = "00000000-0000-0000-0000-000000000000"

#: The exact column set of ``platform_observations``, as the design fixed it.
#: Named here (rather than only in the test) so a reader adding a column meets
#: the constraint in the same file as the table. See §4.2 of the design.
POOLED_COLUMNS: frozenset[str] = frozenset({
    "id",
    "metric",
    "model_registry_id",
    "task_type",
    "reason",
    "bucket_day",
    "observations",
    "successes",
    "latency_ms_sum",
    "cost_usd_sum",
    "contributor_floor_met",
    "updated_at",
})


class PlatformObservation(Base):
    """One pooled bucket of platform learning — no tenant in it, by construction.

    Grain: ``(metric, model_registry_id, task_type, reason, bucket_day)``. The
    aggregation is done **on write** by the daily job; there is deliberately no
    per-tenant row here to aggregate on read, because a read-time aggregate over
    a company-scoped table is a query convention, and charter decision 2 rules
    out exactly that (the guarantee would be a habit, one ``WHERE company_id``
    away from becoming per-tenant learning).

    ``contributor_floor_met`` records that the k-anonymity check ran and passed.
    Rows below the floor are never written at all — the flag exists so a reader
    of the table can tell "checked and passed" from "never checked", which
    matters after a job change.

    **The grain is enforced by an expression index, not a plain constraint.**
    ``model_registry_id`` is nullable (``routing_decisions``' is — an un-bound
    legacy integration still routes), and Postgres treats NULLs as *distinct* in
    a unique constraint, so a plain one would silently permit unlimited
    duplicate buckets for exactly the un-bound rows. Coalescing to the nil UUID
    makes "no model" one value rather than infinitely many. Chosen over PG15's
    ``NULLS NOT DISTINCT`` so the schema carries no version floor.
    """

    __tablename__ = "platform_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: One of ``ObservationMetric.ALL``.
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    #: FK to the **platform** fleet catalog — not to anything tenant-scoped.
    model_registry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_registry.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The routing_decisions vocabulary: pinned|rule|auto|fallback|downshift.
    reason: Mapped[str] = mapped_column(String(16), nullable=False)
    bucket_day: Mapped[date] = mapped_column(Date, nullable=False)

    observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms_sum: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_usd_sum: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"))
    contributor_floor_met: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("uq_platform_observation_bucket",
              "metric",
              text(f"coalesce(model_registry_id, '{NO_MODEL}'::uuid)"),
              "task_type", "reason", "bucket_day",
              unique=True),
        Index("ix_platform_observations_metric_day", "metric", "bucket_day"),
    )


class KpiSnapshot(Base):
    """One KPI reading for one company on one day — **or a recorded absence**.

    ``value IS NULL`` means *not measurable*; it never means zero. That is the
    C6 honest-absence rule (``kpi/compute.py``) surviving persistence, and it is
    the reason the snapshot job writes a row for every (company, KPI) pair every
    day rather than skipping the unmeasurable ones: a row saying "not measurable,
    missing Invoice.due_date" is history too. It is what later lets a Week-12
    answer say *this became measurable in Week 5*, instead of showing a chart
    that silently starts in the middle.

    ``unit`` is denormalised from the definition on purpose — a definition's
    unit may change, and an old row's must not.
    """

    __tablename__ = "kpi_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    kpi_key: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_on: Mapped[date] = mapped_column(Date, nullable=False)

    #: ``None`` means not measurable. It never means zero.
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    #: The explicit flag, so a query never has to infer measurability from NULL.
    measurable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: What was absent, copied from ``KpiResult.missing``.
    missing: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    baseline_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    unit: Mapped[str] = mapped_column(String(16), nullable=False, default="count")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "kpi_key", "captured_on",
                         name="uq_kpi_snapshot_company_key_day"),
        Index("ix_kpi_snapshots_company_day", "company_id", "captured_on"),
    )


class EntityBehaviourWeekly(Base):
    """One entity's behavioural series for one week — counts and ratios only.

    Drift is *behaviour changing without anyone deciding it should*. This table
    is the observation; it does not act. ``governance/demotion.py`` owns
    demotion and already has triggers and an anti-rubber-stamp promotion rule,
    so LEARN gives it one more trigger rather than a second opinion — two
    demotion authorities would be a worse bug than the drift.

    No content columns: every field is a count, a ratio or a mean, for the same
    reason ``SourceTrustScore`` is (``orm/trust.py``) — an aggregate over
    outcomes needs no prompt, output or record in it.
    """

    __tablename__ = "entity_behaviour_weekly"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=False)
    #: The Monday (UTC) of the observed week.
    week_start: Mapped[date] = mapped_column(Date, nullable=False)

    runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approval_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    rejection_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    escalation_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    consent_refusal_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_steps: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_csat: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("entity_id", "week_start",
                         name="uq_entity_behaviour_entity_week"),
        Index("ix_entity_behaviour_company_week", "company_id", "week_start"),
    )


class UserPreference(Base):
    """A per-user preference — explicit, or learned and then confirmed.

    Deliberately dull: a namespaced key (``density.surface.<name>``,
    ``notify.<channel>``) and a small JSON value. Vihara (Increment 7) is the
    consumer; the store ships now so the observation series starts accumulating,
    for the same reason KPI history does.

    ``company_id`` is carried beside ``user_id`` so a tenant-scoped read needs no
    join — the same denormalisation ``entity_versions`` will make in SEGA.
    """

    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    #: True when the value came from observation rather than from the user
    #: saying so. The surface must always be able to show which it was.
    learned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_preference_user_key"),
    )
