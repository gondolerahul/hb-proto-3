"""orm/document.py — Document + DocumentChunk (pgvector-backed) ORM."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import pgvector.sqlalchemy
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.common.database import Base

if TYPE_CHECKING:
    from src.auth.models import Company
    from src.ai.orm.entity import HierarchicalEntity

__all__ = ["Document", "DocumentChunk"]


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)  # pdf, docx, txt
    file_size: Mapped[str | None] = mapped_column(String, nullable=True)
    upload_status: Mapped[str | None] = mapped_column(String, default="processing")  # processing, completed, failed
    # RETR T3 — the HBS module this document belongs to, enforced by the Inc-1
    # domain viewport at retrieval. NULL reads as "general" (common knowledge).
    memory_domain: Mapped[str | None] = mapped_column(String, nullable=True)
    # ── LIB T1 (Inc 6): provenance — where this document came from ──────
    # Spec §15.4 wants a Library that knows, for every document, where it came
    # from, who uses it, whether it is still true, and how to open it at the
    # passage that answered the question. `documents` knew none of the four.
    #
    # Existing rows backfill to source_kind='upload' with everything else NULL,
    # which is the honest answer: we genuinely do not know. SEGA's taint ladder
    # reads absent provenance as `external_verified` rather than `internal`
    # for exactly that reason.
    source_kind: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="upload")
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: sha-256 of the extracted text — change detection without re-reading.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ingested_by_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True)
    #: What period the content *describes* — deliberately not when it was
    #: uploaded. A price list uploaded today may describe last year, and
    #: staleness computed from created_at would call it fresh. NULL where
    #: unknown, and staleness then falls back to created_at saying so.
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    staleness_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="fresh")
    staleness_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company: Mapped["Company"] = relationship("Company")
    entity: Mapped["HierarchicalEntity | None"] = relationship("HierarchicalEntity")
    chunks: Mapped[list["DocumentChunk"]] = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    chunk_index: Mapped[str] = mapped_column(String, nullable=False)  # Position in document
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any] = mapped_column(pgvector.sqlalchemy.Vector(768), nullable=True)  # 768 for Gemini embeddings
    # RETR T2 — the heading trail this chunk sat under ("A > B"), and the
    # chunking version that produced it. Version 1 is the legacy flat 500-char
    # split; the lazy background sweep upgrades stale documents over time.
    heading_path: Mapped[str | None] = mapped_column(String, nullable=True)
    chunk_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")
