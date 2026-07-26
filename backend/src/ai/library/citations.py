"""library/citations.py — the citation shape, and opening one (LIB T6).

Retrieval already returns everything a citation needs — `document_id`,
`chunk_index`, `heading_path`, and now `staleness_state`. What was missing was
a *contract* for it and a way to **open** it. Without both, a citation is a
uuid in a log rather than something a person can follow, and an answer whose
sources cannot be opened is an answer that has to be taken on trust.

**The passage read returns neighbours.** A citation that opens at the top of a
40-page PDF has technically cited it and practically told you nothing. One
chunk either side is enough to see whether the sentence means what the answer
said it meant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["Citation", "citations_from_hits", "read_passage"]


@dataclass(frozen=True)
class Citation:
    """One source behind an answer, in the shape a surface can render.

    `staleness_state` is carried deliberately: it is the difference between
    "here is your source" and "here is your source, and nobody has confirmed it
    in fourteen months". LIB T4 computes it; refusing to carry it here would
    make the sweep's output invisible at the only moment it matters.
    """

    document_id: str
    chunk_id: str
    rank: int
    filename: Optional[str] = None
    heading_path: Optional[str] = None
    chunk_index: Optional[str] = None
    staleness_state: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "rank": self.rank,
            "filename": self.filename,
            "heading_path": self.heading_path,
            "chunk_index": self.chunk_index,
            "staleness_state": self.staleness_state,
            **self.extra,
        }


def citations_from_hits(hits: Sequence[Mapping[str, Any]]) -> list[Citation]:
    """Build citations from the memory service's own hit dicts.

    Takes the caller's output shape rather than a private one — the same choice
    `log_retrieval_usage` made, and for the same reason: there is nothing to
    keep in step when a retrieval result gains a field.

    A hit that cannot name its document is **skipped**, not emitted with a null
    id. A citation nobody can open is worse than no citation, because it looks
    like evidence.
    """
    citations: list[Citation] = []
    for position, hit in enumerate(hits, start=1):
        document_id = hit.get("document_id")
        chunk_id = hit.get("chunk_id")
        if not document_id or not chunk_id:
            continue
        citations.append(Citation(
            document_id=str(document_id),
            chunk_id=str(chunk_id),
            rank=position,
            filename=hit.get("filename") or hit.get("source"),
            heading_path=hit.get("heading_path"),
            chunk_index=(str(hit["chunk_index"])
                         if hit.get("chunk_index") is not None else None),
            staleness_state=hit.get("staleness_state"),
        ))
    return citations


async def read_passage(
    db: AsyncSession, company_id: Any, document_id: Any, *,
    chunk_index: int, context: int = 1,
) -> Optional[dict[str, Any]]:
    """A chunk plus `context` neighbours either side, or None if not found.

    **Scoped by company through the document**, not by chunk id alone: this is a
    read that turns a uuid into tenant content, which is exactly the shape of
    the two cross-tenant disclosures Increment 6 has already fixed. Returning
    None on a cross-tenant miss (rather than 403) is deliberate for the same
    reason SEGA T0 chose 404 — a probe must not learn that an id exists
    somewhere else.
    """
    document = (await db.execute(text("""
        SELECT id, filename, memory_domain, source_kind, source_uri,
               staleness_state, staleness_reason, effective_from
        FROM documents
        WHERE id = CAST(:document_id AS uuid)
          AND company_id = CAST(:company_id AS uuid)
    """), {"document_id": str(document_id),
           "company_id": str(company_id)})).mappings().first()
    if document is None:
        return None

    low = max(0, chunk_index - max(0, context))
    high = chunk_index + max(0, context)
    rows = (await db.execute(text("""
        SELECT id, chunk_index, content, heading_path
        FROM document_chunks
        WHERE document_id = CAST(:document_id AS uuid)
          AND chunk_index ~ '^[0-9]+$'
          AND CAST(chunk_index AS integer) BETWEEN :low AND :high
        ORDER BY CAST(chunk_index AS integer)
    """), {"document_id": str(document_id), "low": low, "high": high})).mappings().all()

    # `chunk_index` is a String column (it predates LIB), so the regex guard is
    # not decoration — a legacy non-numeric index would abort the whole
    # statement with a cast error rather than skipping one row.
    if not rows:
        return None

    return {
        "document": {
            "id": str(document["id"]),
            "filename": document["filename"],
            "memory_domain": document["memory_domain"],
            "source_kind": document["source_kind"],
            "source_uri": document["source_uri"],
            "staleness_state": document["staleness_state"],
            "staleness_reason": document["staleness_reason"],
            "effective_from": (document["effective_from"].isoformat()
                               if document["effective_from"] else None),
        },
        "requested_chunk_index": chunk_index,
        "context": context,
        "passages": [{
            "chunk_id": str(row["id"]),
            "chunk_index": row["chunk_index"],
            "heading_path": row["heading_path"],
            "content": row["content"],
            "is_cited": str(row["chunk_index"]) == str(chunk_index),
        } for row in rows],
    }
