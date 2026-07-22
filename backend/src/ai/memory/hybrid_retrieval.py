"""memory/hybrid_retrieval.py — hybrid lexical+semantic retrieval (RETR T1).

The shipped v1 retrieval was pure cosine over pgvector: `top-5 @ 0.70`. Embeddings
are good at *aboutness* and bad at *exactness* — they blur the difference between
"invoice INV-4417" and "invoice INV-4471", between a part number and its
neighbours in vector space, between a proper noun and a synonym. A lexical index
is the exact opposite: precise on terms, blind to paraphrase.

Technical §24.4 asks for both, fused. This module is that fusion:

* **Lexical** — Postgres full-text (`to_tsvector`/`plainto_tsquery`, GIN-indexed
  by migration ``retr001``), ranked by `ts_rank_cd`.
* **Semantic** — the existing pgvector cosine ranking, unchanged.
* **Reciprocal-rank fusion** — combine by *rank*, not score. This is the point:
  a cosine similarity and a `ts_rank_cd` are not on comparable scales and no
  amount of normalisation makes them so. RRF only asks "how near the top did
  each retriever put this?", so the two can vote without a shared unit.

The fusion itself is pure and unit-tested without a database; the SQL half is
one function that runs both queries and hands their orderings over.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.memory.domain_viewport import filter_by_domain
from src.ai.memory.retrieval_filters import ChunkFilters

logger = logging.getLogger(__name__)

__all__ = [
    "RRF_K",
    "DEFAULT_CANDIDATE_DEPTH",
    "RetrievedChunk",
    "reciprocal_rank_fusion",
    "hybrid_search",
]

# The standard RRF damping constant (Cormack et al. 2009). Larger k flattens the
# curve, so deep hits matter more relative to the top; 60 is the published
# default and behaves well when neither retriever is known to dominate.
RRF_K = 60

# How deep to take each retriever's ranking before fusing. Fusion can only
# reorder what it is given, so this needs to exceed top_k by enough that a
# result ranked poorly by one retriever and well by the other still surfaces.
DEFAULT_CANDIDATE_DEPTH = 50


@dataclass
class RetrievedChunk:
    """One fused result, with the provenance of how it was found."""

    chunk_id: str
    content: str
    score: float = 0.0
    # Which retrievers found it, and at what 1-based rank. This is what makes a
    # bad retrieval debuggable — "lexical-only at rank 1" reads very differently
    # from "both retrievers agreed".
    ranks: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(sorted(self.ranks))

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "score": self.score,
            "sources": list(self.sources),
            "ranks": dict(self.ranks),
            **self.metadata,
        }


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[RetrievedChunk]],
    *,
    k: int = RRF_K,
    top_k: Optional[int] = None,
    weights: Optional[Mapping[str, float]] = None,
) -> list[RetrievedChunk]:
    """Fuse several ranked lists into one by reciprocal rank.

    ``score(d) = Σ_r weight_r / (k + rank_r(d))`` over the retrievers ``r`` that
    returned ``d``, with ranks 1-based.

    Fusing on rank rather than score is deliberate: cosine similarity and
    `ts_rank_cd` are incomparable quantities, and normalising them against each
    other would invent a relationship that is not there. RRF needs only the
    ordering each retriever already committed to.

    Ties break on chunk id so the result is deterministic — retrieval feeding an
    LLM prompt must not reorder between identical calls.
    """
    fused: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}

    for source, ranked in rankings.items():
        weight = float((weights or {}).get(source, 1.0))
        for rank, chunk in enumerate(ranked, start=1):
            existing = fused.get(chunk.chunk_id)
            if existing is None:
                existing = RetrievedChunk(
                    chunk_id=chunk.chunk_id, content=chunk.content,
                    metadata=dict(chunk.metadata),
                )
                fused[chunk.chunk_id] = existing
                scores[chunk.chunk_id] = 0.0
            else:
                # Later retrievers may carry metadata the first one lacked.
                for key, value in chunk.metadata.items():
                    existing.metadata.setdefault(key, value)
            existing.ranks[source] = rank
            scores[chunk.chunk_id] += weight / (k + rank)

    for chunk_id, score in scores.items():
        fused[chunk_id].score = score

    ordered = sorted(
        fused.values(), key=lambda c: (-c.score, c.chunk_id),
    )
    return ordered[:top_k] if top_k is not None else ordered


async def _lexical_candidates(
    db: AsyncSession, query: str, *, entity_id: Optional[uuid.UUID],
    company_id: Optional[uuid.UUID], depth: int,
    extra_sql: str, params: dict[str, Any],
) -> list[RetrievedChunk]:
    """Postgres full-text ranking over document_chunks (GIN-indexed, retr001)."""
    scope = _scope_clause(entity_id, company_id)
    stmt = text(f"""
        SELECT dc.id::text, dc.content, d.memory_domain,
               ts_rank_cd(to_tsvector('english', dc.content),
                          plainto_tsquery('english', :q)) AS rank
        FROM   document_chunks dc
        JOIN   documents d ON d.id = dc.document_id
        WHERE  {scope}
          AND  to_tsvector('english', dc.content) @@ plainto_tsquery('english', :q)
          {extra_sql}
        ORDER  BY rank DESC
        LIMIT  :depth
    """)
    rows = (await db.execute(stmt, {
        "q": query, "depth": depth,
        "entity_id": str(entity_id) if entity_id else None,
        "company_id": str(company_id) if company_id else None,
        **params,
    })).fetchall()
    return [
        RetrievedChunk(chunk_id=r[0], content=r[1],
                       metadata={"memory_domain": r[2], "lexical_rank": float(r[3])})
        for r in rows
    ]


async def _semantic_candidates(
    db: AsyncSession, query_vector: Sequence[float], *,
    entity_id: Optional[uuid.UUID], company_id: Optional[uuid.UUID], depth: int,
    extra_sql: str, params: dict[str, Any],
) -> list[RetrievedChunk]:
    """The existing pgvector cosine ranking, unchanged in behaviour."""
    scope = _scope_clause(entity_id, company_id)
    stmt = text(f"""
        SELECT dc.id::text, dc.content, d.memory_domain,
               1 - (dc.embedding <=> CAST(:vec AS vector)) AS score
        FROM   document_chunks dc
        JOIN   documents d ON d.id = dc.document_id
        WHERE  {scope}
          AND  dc.embedding IS NOT NULL
          {extra_sql}
        ORDER  BY dc.embedding <=> CAST(:vec AS vector)
        LIMIT  :depth
    """)
    rows = (await db.execute(stmt, {
        "vec": json.dumps(list(query_vector)), "depth": depth,
        "entity_id": str(entity_id) if entity_id else None,
        "company_id": str(company_id) if company_id else None,
        **params,
    })).fetchall()
    return [
        RetrievedChunk(chunk_id=r[0], content=r[1],
                       metadata={"memory_domain": r[2], "cosine": float(r[3])})
        for r in rows
    ]


def _scope_clause(
    entity_id: Optional[uuid.UUID], company_id: Optional[uuid.UUID],
) -> str:
    """Tenancy scope. Entity-scoped when given, else company-wide.

    One of the two is always required — an unscoped retrieval would cross
    tenants, so ``hybrid_search`` refuses that up front.
    """
    if entity_id is not None:
        return "d.entity_id = CAST(:entity_id AS uuid)"
    return "d.company_id = CAST(:company_id AS uuid)"


async def hybrid_search(
    db: AsyncSession,
    query: str,
    *,
    query_vector: Optional[Sequence[float]] = None,
    entity_id: Optional[uuid.UUID] = None,
    company_id: Optional[uuid.UUID] = None,
    top_k: int = 5,
    depth: int = DEFAULT_CANDIDATE_DEPTH,
    weights: Optional[Mapping[str, float]] = None,
    filters: Optional[ChunkFilters] = None,
    allowed_domains: Optional[frozenset[str]] = None,
) -> list[RetrievedChunk]:
    """Retrieve by lexical + semantic ranking fused with RRF.

    ``query_vector`` may be ``None`` (embedding unavailable or not worth the
    call) — retrieval then degrades to lexical-only rather than returning
    nothing, which is the behaviour the v1 path lacked: a failed embedding meant
    an empty result and an agent answering from no context at all.

    ``allowed_domains`` is the caller's **domain viewport** (§24.3), from
    ``domain_viewport.resolve_allowed_domains``. It is need-to-know, not
    relevance: it applies *after* fusion and *before* ``top_k``, so a document
    the caller may not see never even consumes one of its result slots. ``None``
    means unrestricted; an untagged document reads as ``general`` and stays
    visible, so tagging only ever narrows.

    Raises ``ValueError`` without a tenancy scope; a KB query that could span
    tenants is a bug, not a broad search.
    """
    if entity_id is None and company_id is None:
        raise ValueError("hybrid_search requires entity_id or company_id")

    extra_sql, params = (filters.to_sql() if filters is not None else ("", {}))

    rankings: dict[str, Sequence[RetrievedChunk]] = {}
    try:
        rankings["lexical"] = await _lexical_candidates(
            db, query, entity_id=entity_id, company_id=company_id,
            depth=depth, extra_sql=extra_sql, params=params)
    except Exception as exc:  # noqa: BLE001
        logger.warning("lexical retrieval failed, continuing semantic-only: %s", exc)

    if query_vector:
        try:
            rankings["semantic"] = await _semantic_candidates(
                db, query_vector, entity_id=entity_id, company_id=company_id,
                depth=depth, extra_sql=extra_sql, params=params)
        except Exception as exc:  # noqa: BLE001
            logger.warning("semantic retrieval failed, continuing lexical-only: %s", exc)

    if not rankings:
        return []

    # Fuse fully, apply need-to-know, and only then truncate — truncating first
    # would let an invisible document eat a result slot and silently shrink what
    # the caller is entitled to see.
    fused = reciprocal_rank_fusion(rankings, weights=weights)
    visible = filter_by_domain(
        fused, allowed_domains,
        domain_getter=lambda c: c.metadata.get("memory_domain"),
    )
    return visible[:top_k]
