"""tenant_schema/models.py — the tenant data-plane tables (technical doc §10, §19).

These three tables live in the **tenant database** (a dedicated container in
prod, a per-tenant schema in dev/test — see ``data_plane.py``), never in the
control-plane Postgres. They therefore use a **separate declarative base**
(``TenantBase``) so control-plane Alembic autogeneration never sweeps them in;
they are created by the versioned ``bootstrap`` against each tenant DB.

Per the v3.0.6 decision, KB + CORTEX memory stay in the control plane; the
tenant DB holds only business records + their typed link graph.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = [
    "TenantBase",
    "TenantEntityDef",
    "TenantRecord",
    "TenantRecordLink",
    "SEED_REL_TYPES",
    "TENANT_SCHEMA_TOKEN",
]

# Symbolic schema translated per tenant via ``schema_translate_map`` in the
# data plane (``tenant`` → ``t_<hex>``). This is leak-free multi-tenant schema
# routing — SQLAlchemy qualifies every table name; no per-connection SET
# search_path that could bleed onto a pooled control-plane connection.
TENANT_SCHEMA_TOKEN = "tenant"

# Seed rel_type vocabulary (technical doc §19.1); extensible per tenant.
SEED_REL_TYPES: frozenset[str] = frozenset({
    "converted_to", "belongs_to", "attached_to",
    "fulfilled_by", "billed_by", "paid_by", "derived_from",
})


class TenantBase(DeclarativeBase):
    """Declarative base for tenant-DB tables only — kept off the control plane."""
    pass


class TenantEntityDef(TenantBase):
    """An object-type definition (the HBS spine seeds 27 of these)."""

    __tablename__ = "tenant_entity_defs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Evolving field schema: list of {name, type, target?, aliases?, lifecycle?, ...}.
    fields: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Write ownership (§23.1): the canonical Process code (e.g. "P08") at seed
    # time; resolved to a PROCESS entity id when Inc 2 seeds the Solo Pack.
    owner_process_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    owner_process_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    module: Mapped[str | None] = mapped_column(String(40), nullable=True)     # HBS module
    domain_tag: Mapped[str | None] = mapped_column(String(24), nullable=True)  # memory domain (§24.3)
    # SoR block (§21) — reserved; unused until Increment 4.
    sor: Mapped[Any] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_tenant_entity_defs_company_name"),
        {"schema": TENANT_SCHEMA_TOKEN},
    )


class TenantRecord(TenantBase):
    """A JSONB document validated against its def's current fields (§19)."""

    __tablename__ = "tenant_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_def_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{TENANT_SCHEMA_TOKEN}.tenant_entity_defs.id"), nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    # Compare-and-set version (§23.2): bumped on every write.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    def_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # def version at write
    updated_by_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # soft delete (§19.5)
    # SoR (§21, Inc-4 CONN+SOR): a mirror row for an externally-mastered object
    # carries its master + external handle; both NULL for a HireBuddha-mastered
    # record (the standalone norm — §21.3). `sor` mirrors the def's decl at write
    # time; `external_ref` = {connector, external_id, etag, synced_at}.
    sor: Mapped[Any] = mapped_column(JSONB, nullable=True)
    external_ref: Mapped[Any] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_tenant_records_def", "company_id", "entity_def_id"),
        # GIN on the JSONB document for ad-hoc queries (§19.3).
        Index("ix_tenant_records_data_gin", "data", postgresql_using="gin",
              postgresql_ops={"data": "jsonb_path_ops"}),
        {"schema": TENANT_SCHEMA_TOKEN},
    )


class TenantRecordLink(TenantBase):
    """A typed edge in the object graph (§19.1) — materialised from ref fields."""

    __tablename__ = "tenant_record_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    src_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{TENANT_SCHEMA_TOKEN}.tenant_records.id"), nullable=False)
    dst_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{TENANT_SCHEMA_TOKEN}.tenant_records.id"), nullable=False)
    rel_type: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("src_record_id", "dst_record_id", "rel_type",
                         name="uq_tenant_record_links_edge"),
        Index("ix_tenant_record_links_src", "company_id", "src_record_id"),
        Index("ix_tenant_record_links_dst", "company_id", "dst_record_id"),
        {"schema": TENANT_SCHEMA_TOKEN},
    )
