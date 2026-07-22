"""memory/reranker.py — the Growth+ retrieval rerank (RETR T4).

RRF fuses two orderings without ever reading the passages. It knows that both
retrievers liked a chunk; it does not know whether the chunk actually answers
the question. A reranker does: it reads the query and each candidate together
and scores relevance directly. That is why reranking usually buys more than any
amount of fusion tuning — and why it costs more.

**Decision (Rahul, 2026-07-22): LLM-as-reranker**, over the existing LLM router,
rather than a local cross-encoder. It adds no dependency and no model download,
and it reuses the provider routing, tracing and cost ledger already in place.

The cost is real and per-query, so three things bound it:

* **Growth+ only.** Free and Solo tenants never pay for it and never wait for it.
* **A bounded window.** Only the fused top ``RERANK_WINDOW`` are scored — the
  tail of a 50-candidate list is not worth an LLM's attention.
* **Attributed as ``rerank``, and deliberately *tenant*-initiated.** The tenant
  asked the question, so it draws from tenant budget, not B13's platform
  envelope. Putting it in the platform class would have let ordinary retrieval
  exhaust the cap that exists to protect tenants from platform work.

**It fails open, always.** Any error — provider down, malformed scores, timeout —
returns the fused order untouched. A degraded ranking is a far better outcome
than a failed retrieval, and the fused order is already good.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.memory.hybrid_retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

__all__ = [
    "RERANK_WINDOW",
    "RERANK_TIERS",
    "resolve_tier_name",
    "rerank_allowed",
    "build_rerank_prompt",
    "parse_rerank_scores",
    "apply_scores",
    "llm_rerank",
]

# How many fused candidates get scored. Beyond this the tail is mostly noise and
# every extra passage is prompt tokens on the tenant's bill.
RERANK_WINDOW = 20

# Subscription tiers that get reranking. Tier names are matched case-insensitively.
RERANK_TIERS = frozenset({"growth", "scale", "enterprise"})

# How much of each passage the scorer sees. Enough to judge relevance, bounded
# so one long chunk cannot dominate the prompt.
_SNIPPET_CHARS = 600

_SYSTEM_PROMPT = (
    "You score how well each passage answers a search query. "
    "Reply with ONLY a JSON object mapping each passage number to a relevance "
    "score from 0 to 10, e.g. {\"1\": 8, \"2\": 0}. No prose, no explanation."
)


def rerank_allowed(tier: Optional[str], *, enabled: bool = True) -> bool:
    """Whether this tenant's tier gets reranking.

    An unknown or absent tier is *not* granted it — reranking costs the tenant
    money, so an unrecognised plan must fall back to not spending, never to
    spending.
    """
    if not enabled or not tier:
        return False
    return tier.strip().lower() in RERANK_TIERS


async def resolve_tier_name(
    db: AsyncSession, company_id: uuid.UUID,
) -> Optional[str]:
    """The tenant's subscription tier name, or ``None`` when they have no plan.

    ``subscriptions.plan_tier`` is a level number; the human name lives on
    ``subscription_tiers``. None (no active subscription) means no rerank, which
    is the correct default — a free tenant should not be charged for one.
    """
    from sqlalchemy import text as _text

    try:
        row = (await db.execute(_text("""
            SELECT st.name FROM subscriptions s
            JOIN subscription_tiers st ON st.tier_level = s.plan_tier
            WHERE s.company_id = CAST(:c AS uuid) AND s.status = 'active'
            LIMIT 1
        """), {"c": str(company_id)})).first()
    except Exception as exc:  # noqa: BLE001
        logger.debug("tier resolution failed, treating as no-rerank: %s", exc)
        return None
    return str(row[0]) if row and row[0] else None


def build_rerank_prompt(query: str, candidates: Sequence[RetrievedChunk]) -> str:
    """Number the candidates and ask for a score per number.

    Passages are referenced by position, not by chunk id: ids are long, carry no
    meaning for the model, and waste tokens the tenant pays for.
    """
    lines = [f"Query: {query}", "", "Passages:"]
    for i, chunk in enumerate(candidates, start=1):
        snippet = chunk.content[:_SNIPPET_CHARS].replace("\n", " ").strip()
        lines.append(f"{i}. {snippet}")
    lines.append("")
    lines.append(f"Score each of the {len(candidates)} passages from 0 to 10.")
    return "\n".join(lines)


def parse_rerank_scores(raw: str, expected: int) -> dict[int, float]:
    """Pull ``{position: score}`` out of a model reply.

    Tolerant by design — a fenced code block, stray prose, or a partial answer
    all still yield whatever scores are present. Positions outside
    ``1..expected`` and unparseable values are dropped rather than poisoning the
    ordering. Returns ``{}`` when nothing usable was found, which the caller
    reads as "keep the fused order".
    """
    if not raw:
        return {}

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}

    scores: dict[int, float] = {}
    for key, value in parsed.items():
        try:
            position = int(str(key).strip())
            score = float(value)
        except (TypeError, ValueError):
            continue
        if 1 <= position <= expected:
            scores[position] = score
    return scores


def apply_scores(
    candidates: Sequence[RetrievedChunk], scores: dict[int, float],
) -> list[RetrievedChunk]:
    """Reorder by rerank score, keeping fused order as the tie-break.

    A candidate the model did not score keeps its fused position rather than
    being dropped: a missing score means the model said nothing about it, not
    that it said the passage was irrelevant.
    """
    if not scores:
        return list(candidates)

    ordered = sorted(
        enumerate(candidates, start=1),
        key=lambda pair: (-scores.get(pair[0], -1.0), pair[0]),
    )
    out: list[RetrievedChunk] = []
    for position, chunk in ordered:
        if position in scores:
            chunk.metadata["rerank_score"] = scores[position]
        out.append(chunk)
    return out


async def llm_rerank(
    db: AsyncSession,
    company_id: uuid.UUID,
    query: str,
    candidates: Sequence[RetrievedChunk],
    *,
    top_k: Optional[int] = None,
    window: int = RERANK_WINDOW,
    run_id: Optional[uuid.UUID] = None,
) -> list[RetrievedChunk]:
    """Rescore the fused top ``window`` with the LLM, then truncate to ``top_k``.

    Never raises: on any failure the fused order is returned unchanged.
    """
    from src.ai.llm.router import LLMRouter
    from src.ai.services.attributed_usage import log_llm_response_usage
    from src.ai.services.cost_attribution import CostAttribution

    head = list(candidates[:window])
    tail = list(candidates[window:])
    if len(head) < 2:
        # Nothing to reorder — do not spend a call to confirm it.
        return list(candidates)[:top_k] if top_k else list(candidates)

    try:
        router = LLMRouter(db, company_id)
        response = await router.call_llm(
            task_type="reasoning",
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=build_rerank_prompt(query, head),
            temperature=0.0,
            max_tokens=512,
        )
        await log_llm_response_usage(
            db=db, response=response, attribution=CostAttribution.RERANK.value,
            company_id=company_id, run_id=run_id,
        )
        scores = parse_rerank_scores(getattr(response, "content", "") or "", len(head))
        if not scores:
            logger.debug("rerank returned no usable scores — keeping fused order")
        reordered = apply_scores(head, scores) + tail
    except Exception as exc:  # noqa: BLE001
        logger.warning("rerank failed, keeping fused order: %s", exc)
        reordered = list(candidates)

    return reordered[:top_k] if top_k else reordered
