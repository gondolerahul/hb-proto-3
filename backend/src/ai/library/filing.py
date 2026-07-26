"""library/filing.py — generated artifacts become Library documents (LIB T5).

`artifacts` and `documents` grew up separately: the first is where the platform
puts files it produced, the second is what retrieval can see. Nothing joined
them, so a report an agent wrote last month was a path on disk that no agent
could ever find again. Decision 5 settles it — **a generated artifact is filed
as a Document. One Library, not two.**

**Only text-shaped artifacts are chunked.** Recordings, images and video are
filed — they get a Document row, so provenance and the influence log can see
them — but they are not chunked, because there is no honest text to embed. A
transcript of a recording is a *different* artifact and gets filed on its own
merits.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.library.provenance import SourceKind, content_hash

logger = logging.getLogger(__name__)

__all__ = ["CHUNKABLE_CATEGORIES", "file_artifact", "is_chunkable"]


#: `Artifact.file_category` values that carry text worth retrieving. The other
#: three shipped categories (recordings, images, videos) are filed but not
#: chunked.
CHUNKABLE_CATEGORIES: frozenset[str] = frozenset({"documents", "text"})


def is_chunkable(file_category: Optional[str]) -> bool:
    return (file_category or "").lower() in CHUNKABLE_CATEGORIES


def _extract_text(path: str, mime_type: Optional[str]) -> Optional[str]:
    """Best-effort text extraction, reusing the shipped extractor.

    Returns None rather than raising: a filing that cannot read its own file
    should still produce a Document row (the provenance is real and useful even
    when the content is unreachable), just an unchunked one.
    """
    try:
        from src.ai.text_extractor import extract_text_from_file

        return extract_text_from_file(path, mime_type or "")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Artifact text extraction skipped for %s: %s", path, exc)
        return None


async def file_artifact(
    db: AsyncSession, artifact_id: Any, company_id: Any, *,
    memory_domain: Optional[str] = None,
) -> dict[str, Any]:
    """File one artifact into the Library. Idempotent on `artifacts.document_id`.

    Scoped by company as well as artifact id — filing another tenant's artifact
    into this tenant's Library would be a cross-tenant *write*, which is worse
    than the read-shaped disclosures VG-05 and SEGA T0 fixed.
    """
    from src.ai.artifact_models import Artifact
    from src.ai.orm.document import Document, DocumentChunk

    artifact = (await db.execute(
        select(Artifact).where(
            Artifact.id == artifact_id, Artifact.company_id == company_id)
    )).scalar_one_or_none()
    if artifact is None:
        return {"filed": False, "reason": "artifact not found in this company"}
    if artifact.document_id is not None:
        return {"filed": False, "reason": "already filed",
                "document_id": str(artifact.document_id)}

    file_name = artifact.file_name or Path(str(artifact.file_path or "")).name or "artifact"
    document = Document(
        id=uuid.uuid4(),
        company_id=artifact.company_id,
        entity_id=artifact.agent_id,
        filename=file_name,
        file_type=(Path(file_name).suffix.lstrip(".") or "bin").lower(),
        file_size=str(artifact.file_size) if artifact.file_size is not None else None,
        upload_status="completed",
        memory_domain=memory_domain,
        source_kind=SourceKind.GENERATED_ARTIFACT,
        source_uri=artifact.file_path,
        # The producing run, which is the provenance question that matters for
        # a generated file: *which agent decided this was worth writing down*.
        ingested_by_run_id=artifact.run_id,
    )

    chunks_written = 0
    if is_chunkable(artifact.file_category):
        body = _extract_text(str(artifact.file_path or ""), artifact.mime_type)
        if body and body.strip():
            document.content_hash = content_hash(body)
            db.add(document)
            await db.flush()
            chunks_written = await _chunk_into(
                db, document, body, DocumentChunk)
        else:
            db.add(document)
            await db.flush()
    else:
        db.add(document)
        await db.flush()

    artifact.document_id = document.id
    await db.flush()
    return {"filed": True, "document_id": str(document.id),
            "chunks": chunks_written,
            "chunked": bool(chunks_written)}


async def _chunk_into(
    db: AsyncSession, document: Any, body: str, chunk_model: Any,
) -> int:
    """Chunk and embed through the RETR chunker. Returns chunks written.

    Embedding failure is not filing failure: the chunks land with a NULL
    embedding and the lexical half of hybrid retrieval still finds them, which
    is strictly better than refusing to file the document at all. RETR's fusion
    was built to degrade this way.
    """
    from src.ai.memory.chunking import CURRENT_CHUNK_VERSION, chunk_document
    from src.ai.memory.embedding_service import EmbeddingService

    pieces = chunk_document(body, source_type=document.file_type)
    if not pieces:
        return 0

    embedder = EmbeddingService(db, document.company_id)
    for piece in pieces:
        embedding = None
        try:
            embedding = await embedder.embed_text(
                piece.content, task_type="RETRIEVAL_DOCUMENT")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Embedding failed while filing %s: %s", document.id, exc)
        db.add(chunk_model(
            document_id=document.id,
            chunk_index=str(piece.index),
            content=piece.content,
            embedding=embedding,
            heading_path=piece.heading_label or None,
            chunk_version=CURRENT_CHUNK_VERSION,
        ))
    await db.flush()
    return len(pieces)


async def file_pending(
    db: AsyncSession, company_id: Any, *, limit: int = 50,
) -> dict[str, Any]:
    """File this tenant's unfiled text-shaped artifacts, bounded.

    Bounded rather than exhaustive because filing embeds, and an unbounded
    backlog pass on a tenant with ten thousand generated reports would be a
    surprise embedding bill dressed up as a maintenance job.
    """
    rows = (await db.execute(text("""
        SELECT id FROM artifacts
        WHERE company_id = CAST(:company_id AS uuid)
          AND document_id IS NULL
          AND file_category = ANY(:categories)
        ORDER BY created_at
        LIMIT :limit
    """), {"company_id": str(company_id),
           "categories": sorted(CHUNKABLE_CATEGORIES),
           "limit": limit})).all()

    filed = 0
    for (artifact_id,) in rows:
        result = await file_artifact(db, artifact_id, company_id)
        if result.get("filed"):
            filed += 1
    return {"considered": len(rows), "filed": filed}
