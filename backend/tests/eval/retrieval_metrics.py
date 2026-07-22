"""tests/eval/retrieval_metrics.py — IR metrics for the retrieval goldens (RETR T5).

The A/B harness beside this (``metrics.py``) grades *runs*: did the agent reach
the goal, at what cost. Retrieval needs a different question — *given a query,
how near the top did the right passage land* — so it needs its own metrics.

Three, deliberately, because each catches something the others miss:

* **recall@k** — did the right passage make the cut at all? The blunt one, and
  the one that matters most: a passage outside the top-k never reaches the
  prompt, so its rank within the corpus is irrelevant.
* **MRR** — how near the *top*? Sensitive to the difference between rank 1 and
  rank 5, which recall@5 cannot see, and that difference is real: earlier
  context is weighted more heavily by the model reading it.
* **nDCG@k** — the graded one, for queries with several relevant passages of
  differing value.

Pure — no DB, no I/O — so the maths is unit-testable and the DB-backed golden
run only has to supply rankings.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

__all__ = [
    "recall_at_k",
    "reciprocal_rank",
    "mean_reciprocal_rank",
    "ndcg_at_k",
    "RetrievalScore",
    "score_rankings",
]


def recall_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    """Fraction of relevant items appearing in the top ``k``.

    An empty relevant set scores 1.0 — nothing was required, so nothing was
    missed. Treating it as 0.0 would drag the mean down for a query whose point
    is that it *should* return nothing.
    """
    if not relevant:
        return 1.0
    top = set(retrieved[:k])
    return len([r for r in set(relevant) if r in top]) / len(set(relevant))


def reciprocal_rank(retrieved: Sequence[str], relevant: Sequence[str]) -> float:
    """``1/rank`` of the first relevant hit; 0.0 when none was retrieved."""
    wanted = set(relevant)
    for i, item in enumerate(retrieved, start=1):
        if item in wanted:
            return 1.0 / i
    return 0.0


def mean_reciprocal_rank(
    per_query: Sequence[tuple[Sequence[str], Sequence[str]]],
) -> float:
    if not per_query:
        return 0.0
    return sum(reciprocal_rank(r, rel) for r, rel in per_query) / len(per_query)


def ndcg_at_k(
    retrieved: Sequence[str], gains: Mapping[str, float], k: int,
) -> float:
    """Normalised discounted cumulative gain over graded relevance.

    Ideal DCG is computed from the best ``k`` gains available, so a query with
    fewer relevant passages than ``k`` can still reach 1.0 rather than being
    permanently capped by a denominator it cannot reach.
    """
    if not gains:
        return 1.0

    def dcg(scores: Sequence[float]) -> float:
        return sum(s / math.log2(i + 1) for i, s in enumerate(scores, start=1))

    actual = dcg([gains.get(item, 0.0) for item in retrieved[:k]])
    ideal = dcg(sorted(gains.values(), reverse=True)[:k])
    return actual / ideal if ideal else 1.0


@dataclass(frozen=True)
class RetrievalScore:
    """One retriever's aggregate performance across the golden queries."""

    label: str
    queries: int
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    k: int

    def summary(self) -> str:
        return (f"{self.label}: recall@{self.k}={self.recall_at_k:.3f} "
                f"mrr={self.mrr:.3f} ndcg@{self.k}={self.ndcg_at_k:.3f} "
                f"({self.queries} queries)")


def score_rankings(
    label: str,
    rankings: Sequence[tuple[Sequence[str], Sequence[str]]],
    *,
    k: int = 5,
    gains: Optional[Sequence[Mapping[str, float]]] = None,
) -> RetrievalScore:
    """Aggregate one retriever over the golden set.

    ``rankings`` is ``(retrieved_ids, relevant_ids)`` per query. ``gains``, when
    given, supplies graded relevance per query for nDCG; without it every
    relevant item is graded 1.0.
    """
    if not rankings:
        return RetrievalScore(label, 0, 0.0, 0.0, 0.0, k)

    graded = list(gains) if gains is not None else [
        {r: 1.0 for r in relevant} for _retrieved, relevant in rankings
    ]
    return RetrievalScore(
        label=label,
        queries=len(rankings),
        recall_at_k=sum(recall_at_k(r, rel, k) for r, rel in rankings) / len(rankings),
        mrr=mean_reciprocal_rank(rankings),
        ndcg_at_k=sum(
            ndcg_at_k(retrieved, g, k)
            for (retrieved, _rel), g in zip(rankings, graded)
        ) / len(rankings),
        k=k,
    )
