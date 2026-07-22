"""memory/rechunk.py — the lazy background chunk upgrade (RETR T2, decision 1).

When chunking rules change, every existing document is suddenly chunked the old
way. Re-chunking them all at deploy would mean re-embedding every tenant's KB in
one burst: a large one-off bill, and a long window where retrieval is degraded
because half the corpus is mid-rewrite.

Decision 1 chose the **lazy** path instead, the same shape as SCH's
``def_version``: chunks carry the ``chunk_version`` that produced them, a bounded
sweep upgrades a few documents per tick, and old and new chunks coexist happily
in the meantime — both are indexed, both are retrievable, the new ones are just
better.

**Re-embedding is platform-initiated spend.** The tenant did not ask for this
work, so it draws from B13's platform envelope and parks at that cap rather than
eating into tenant budget. That is exactly the class B13 was built for.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.memory.chunking import CURRENT_CHUNK_VERSION

logger = logging.getLogger(__name__)

__all__ = [
    "RechunkCandidate",
    "find_stale_documents",
    "rechunk_document",
    "rechunk_sweep",
]

# How many documents one sweep tick will re-chunk. Small on purpose: the sweep
# competes with live ingestion for the embedding provider's rate limit, and
# there is no deadline — a document retrieves fine on version 1 meanwhile.
DEFAULT_BATCH = 5


@dataclass(frozen=True)
class RechunkCandidate:
    document_id: uuid.UUID
    company_id: uuid.UUID
    file_type: str
    filename: str


async def find_stale_documents(
    db: AsyncSession, *, limit: int = DEFAULT_BATCH,
    company_id: Optional[uuid.UUID] = None,
) -> list[RechunkCandidate]:
    """Documents whose chunks predate ``CURRENT_CHUNK_VERSION``.

    Ordered oldest-first so a long-neglected corpus drains in a predictable
    order rather than the sweep revisiting whatever Postgres happens to return.
    """
    scope = "AND d.company_id = CAST(:company_id AS uuid)" if company_id else ""
    rows = (await db.execute(text(f"""
        SELECT DISTINCT d.id::text, d.company_id::text, d.file_type, d.filename,
               d.created_at
        FROM   documents d
        JOIN   document_chunks dc ON dc.document_id = d.id
        WHERE  dc.chunk_version < :version
          {scope}
        ORDER  BY d.created_at
        LIMIT  :limit
    """), {
        "version": CURRENT_CHUNK_VERSION, "limit": limit,
        "company_id": str(company_id) if company_id else None,
    })).fetchall()
    return [
        RechunkCandidate(
            document_id=uuid.UUID(r[0]), company_id=uuid.UUID(r[1]),
            file_type=r[2] or "txt", filename=r[3] or "",
        )
        for r in rows
    ]


async def rechunk_document(
    db: AsyncSession, candidate: RechunkCandidate,
) -> dict[str, Any]:
    """Re-chunk one document from its existing chunk text and re-embed.

    The original upload is long gone (only chunks are persisted), so the source
    is the old chunks re-joined in order. That is lossless for the boundary
    problem this fixes: version-1 chunks were a *contiguous* 500-char slicing,
    so concatenating them reproduces the extracted text exactly — and the new
    chunker then cuts it at meaningful boundaries instead of arbitrary ones.
    """
    from src.ai.memory.chunking import chunk_document
    from src.ai.memory.embedding_service import EmbeddingService
    from src.ai.models import DocumentChunk

    rows = (await db.execute(text("""
        SELECT content FROM document_chunks
        WHERE document_id = CAST(:d AS uuid)
        ORDER BY chunk_index::int
    """), {"d": str(candidate.document_id)})).fetchall()
    if not rows:
        return {"skipped": "no chunks"}

    source = "".join(r[0] for r in rows)
    pieces = chunk_document(source, source_type=candidate.file_type)
    if not pieces:
        return {"skipped": "no chunks produced"}

    embedder = EmbeddingService(db, candidate.company_id)
    embedded = []
    for piece in pieces:
        embedded.append((piece, await embedder.embed_text(
            piece.content, task_type="RETRIEVAL_DOCUMENT")))

    # Only swap once every replacement embedding is in hand. A failure partway
    # through would otherwise leave the document with fewer chunks than it
    # started with — strictly worse than the stale version it was replacing.
    if all(e is None for _p, e in embedded):
        logger.warning("rechunk %s: every embedding failed, keeping v1 chunks",
                       candidate.document_id)
        return {"skipped": "embeddings unavailable"}

    await db.execute(text("DELETE FROM document_chunks WHERE document_id = CAST(:d AS uuid)"),
                     {"d": str(candidate.document_id)})
    for piece, embedding in embedded:
        db.add(DocumentChunk(
            document_id=candidate.document_id,
            chunk_index=str(piece.index),
            content=piece.content,
            embedding=embedding,
            heading_path=piece.heading_label or None,
            chunk_version=CURRENT_CHUNK_VERSION,
        ))
    await db.flush()
    logger.info("rechunked %s (%s): %d chunks → %d",
                candidate.document_id, candidate.filename, len(rows), len(pieces))
    return {"document_id": str(candidate.document_id),
            "before": len(rows), "after": len(pieces)}


async def rechunk_sweep(
    db: AsyncSession, *, limit: int = DEFAULT_BATCH,
) -> dict[str, Any]:
    """One bounded pass of the lazy upgrade. Safe to run on a timer."""
    from src.ai.loop.platform_budget import platform_work_admitted

    candidates = await find_stale_documents(db, limit=limit)
    upgraded, parked, skipped = 0, 0, 0

    for candidate in candidates:
        # B13 — the tenant never asked for this re-embed.
        if not await platform_work_admitted(db, candidate.company_id):
            parked += 1
            continue
        try:
            result = await rechunk_document(db, candidate)
            await db.commit()
            if "skipped" in result:
                skipped += 1
            else:
                upgraded += 1
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            logger.error("rechunk failed for %s: %s", candidate.document_id, exc)
            skipped += 1

    return {"considered": len(candidates), "upgraded": upgraded,
            "parked": parked, "skipped": skipped}
