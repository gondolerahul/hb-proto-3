"""library/models.py — the retrieval-usage log (LIB T2, VG-13's influence half).

One row per chunk an agent actually *received*, which is deliberately not the
same set as what the fusion surfaced: the reranker and the `top_k` cut both sit
between them, and only what came back is "influence".

**The query text is never stored.** `query_hash` exists so repeated questions
can be collapsed, not as an anonymity claim — a hash is reversible for short,
guessable queries and this table should not be sold as private. What is true
is narrower and worth stating plainly: the text is not here.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

__all__ = ["RetrievalUsage"]


class RetrievalUsage(Base):
    """A chunk that reached an agent, and who asked for it."""

    __tablename__ = "retrieval_usages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=False)
    #: The colleague that asked. Nullable: a Pragya turn has no entity.
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    #: Nullable for the same reason — a Pragya turn is not an execution run.
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True)
    #: sha-256 of the normalised query. Never the query text (see the module
    #: docstring — a query is tenant content and this table does not need it).
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: 1-based position in what the agent received, after rerank.
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    used_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        # The rollup (T3) groups by document and day; the reaper deletes by
        # age. Both scans want this, and without it the reaper degrades into a
        # sequential scan over the largest table LIB creates.
        Index("ix_retrieval_usages_doc_day", "document_id", "used_at"),
    )
