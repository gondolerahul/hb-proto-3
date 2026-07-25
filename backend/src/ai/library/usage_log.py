"""library/usage_log.py — recording what an agent actually received (LIB T2).

**Where this runs, and why it is not inside `hybrid_search`.** HANDOFF §5
records the RETR rule: retrieval has three deliberately separate stages —
`hybrid_search` fuses, the viewport filters inside it, the reranker runs at the
caller — and the reranker was kept out of `hybrid_search` because it would put
per-query spend inside a function other callers reasonably assume is cheap.

The usage log has exactly that shape, so it gets exactly that answer: it is
written at the caller, after the rerank and the `top_k` cut. That is not only
architectural tidiness — it changes *what is recorded*. Logging inside the
fusion would record what the retriever surfaced; logging here records what the
agent received. Only the second is influence, and the two differ by the whole
of the reranker.

**It must never break a retrieval** (decision 2). A library-analytics feature
that can fail the answer path is a bad trade at any hit rate, so the write
runs in its own session, and every exception is swallowed with a debug log.
The mutation test for this workstream makes the log raise and asserts
retrieval still returns.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

__all__ = ["query_hash", "log_retrieval_usage"]


def query_hash(query: str) -> str:
    """sha-256 of the normalised query, so the same question collapses.

    Lower-cased and whitespace-collapsed: "What is our refund policy?" and
    "what is our  refund policy?" are the same question being asked twice, and
    counting them separately would understate a document's influence.
    """
    normalised = " ".join((query or "").lower().split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _coerce_uuid(value: Any) -> Optional[uuid.UUID]:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


async def log_retrieval_usage(
    company_id: Any,
    query: str,
    hits: Sequence[Mapping[str, Any]],
    *,
    entity_id: Any = None,
    run_id: Any = None,
) -> int:
    """Record the chunks a retrieval returned. Returns how many rows landed.

    ``hits`` are the dicts the memory service returns, so this takes the
    caller's own output rather than a private shape — there is nothing to keep
    in step if the retrieval result gains a field.

    Fire-and-forget by contract: callers must not await this for correctness,
    must not branch on the count, and can rely on it never raising.
    """
    company = _coerce_uuid(company_id)
    if company is None or not hits:
        return 0

    try:
        from src.ai.library.models import RetrievalUsage
        from src.common.database import AsyncSessionLocal

        digest = query_hash(query)
        entity = _coerce_uuid(entity_id)
        run = _coerce_uuid(run_id)

        rows: list[RetrievalUsage] = []
        for position, hit in enumerate(hits, start=1):
            chunk = _coerce_uuid(hit.get("chunk_id"))
            document = _coerce_uuid(hit.get("document_id"))
            # A hit that cannot name its document cannot be attributed, and a
            # row with a null document_id would silently distort every rollup
            # that groups by it. Skipping is the honest handling.
            if chunk is None or document is None:
                continue
            rows.append(RetrievalUsage(
                company_id=company, document_id=document, chunk_id=chunk,
                entity_id=entity, run_id=run, query_hash=digest, rank=position,
            ))

        if not rows:
            return 0

        async with AsyncSessionLocal() as db:
            db.add_all(rows)
            await db.commit()
        return len(rows)
    except Exception as exc:  # noqa: BLE001 — see the module docstring
        logger.debug("Retrieval-usage logging skipped: %s", exc)
        return 0
