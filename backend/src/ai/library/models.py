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

from datetime import date as _date

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

__all__ = ["RetrievalUsage", "DocumentInfluenceDaily"]


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


class DocumentInfluenceDaily(Base):
    """One document's influence on one day — what survives the reaper.

    The raw log is reaped at 30 days; this is kept indefinitely because it is
    tiny, and it is what answers §5.3's question without scanning the log.

    **Three counters, not one, and the distinction is the whole point.**
    ``retrievals`` counts rows, and a single question can return three chunks
    of the same document — so a document that answered *one* question can show
    three retrievals. The design's own headline claim ("this pricing sheet
    answered 40 customer questions this month") is a count of *questions*, and
    only ``distinct_queries`` measures it. Reporting ``retrievals`` under that
    sentence would overstate a chunky document's influence in proportion to how
    finely it happens to be chunked, which is a property of the chunker rather
    than of the document.
    """

    __tablename__ = "document_influence_daily"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: Present although ``document_id`` already implies it. Reading a tenant's
    #: influence panel without this column means joining `documents` to scope
    #: every read, and a scoping rule that depends on remembering a join is the
    #: exact shape of the VG-05 IDOR and SEGA T0's tool-registry disclosure.
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    day: Mapped[_date] = mapped_column(Date, nullable=False, index=True)
    #: Chunks returned — rows in the raw log.
    retrievals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Distinct questions this document took part in answering.
    distinct_queries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Distinct colleagues that received it. A NULL entity (a Pragya turn) is
    #: not a colleague and is not counted here — it still counts as a query.
    distinct_entities: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # No nullable column in the grain, so ordinary conflict inference works
        # and a day can be re-rolled in place — the LEARN `coalesce` expression
        # index is not needed here, and it is worth knowing why.
        UniqueConstraint("document_id", "day", name="uq_doc_influence_doc_day"),
    )
