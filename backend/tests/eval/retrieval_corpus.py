"""tests/eval/retrieval_corpus.py — the retrieval golden set (RETR T5).

A small hand-authored corpus with the property that makes hybrid retrieval worth
building: for several queries the right passage is **not** the nearest neighbour
in embedding space. It shares vocabulary and topic with a decoy, and what
distinguishes it is an exact token — an invoice id, a policy number, a product
code, a person's name. That is precisely where a dense retriever is weakest and
a lexical index is strongest.

**On the embeddings.** Real ones would need a live provider and would make the
goldens non-deterministic and slow, so semantic similarity is *simulated*: each
passage and query is placed in a small named concept space, and cosine over
those coordinates behaves like topical overlap. That is honest about what it
tests — it exercises fusion, ranking, and the SQL, not any embedding model's
quality. The lexical half is not simulated at all: it is real Postgres
full-text over the real text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

__all__ = ["CONCEPTS", "GoldenPassage", "GoldenQuery", "PASSAGES", "QUERIES", "embed"]

EMBED_DIM = 768

# The concept space. Position in this list is the vector dimension a concept
# occupies, so cosine similarity between two items is their concept overlap.
CONCEPTS = [
    "billing", "invoice", "refund", "shipping", "warranty",
    "onboarding", "security", "payroll",
]


def embed(weights: dict[str, float]) -> list[float]:
    """Place a passage or query in the concept space as a 768-dim vector."""
    vec = [0.0] * EMBED_DIM
    for concept, weight in weights.items():
        vec[CONCEPTS.index(concept)] = weight
    return vec


@dataclass(frozen=True)
class GoldenPassage:
    key: str
    text: str
    concepts: dict[str, float]
    memory_domain: str | None = None

    @property
    def embedding(self) -> list[float]:
        return embed(self.concepts)


@dataclass(frozen=True)
class GoldenQuery:
    query: str
    concepts: dict[str, float]
    relevant: tuple[str, ...]
    note: str = ""

    @property
    def embedding(self) -> list[float]:
        return embed(self.concepts)


PASSAGES: Sequence[GoldenPassage] = (
    # ── billing / invoices ────────────────────────────────────────────────
    GoldenPassage(
        "inv_4417",
        "Invoice INV-4417 was settled by bank transfer on 12 March 2026.",
        {"billing": 0.60, "invoice": 0.55},
    ),
    GoldenPassage(
        "inv_generic",
        "Invoices are issued monthly and settled by bank transfer or card.",
        {"billing": 0.95, "invoice": 0.95},   # the topical decoy — closer to most billing queries
    ),
    GoldenPassage(
        "inv_9902",
        "Invoice INV-9902 remains unpaid and has entered the dunning ladder.",
        {"billing": 0.58, "invoice": 0.52},
    ),
    # ── refunds ───────────────────────────────────────────────────────────
    GoldenPassage(
        "refund_policy",
        "Refunds are approved within fourteen days of the original purchase.",
        {"refund": 0.90, "billing": 0.30},
    ),
    GoldenPassage(
        "refund_rma_88",
        "Return authorisation RMA-88 was approved for a faulty control board.",
        {"refund": 0.55, "warranty": 0.40},
    ),
    # ── shipping ──────────────────────────────────────────────────────────
    GoldenPassage(
        "ship_generic",
        "Shipments leave the warehouse within two working days of ordering.",
        {"shipping": 0.95},
    ),
    GoldenPassage(
        "ship_tracking",
        "Consignment TRK-70231 was delivered to the Bristol depot on Tuesday.",
        {"shipping": 0.60},
    ),
    # ── warranty ──────────────────────────────────────────────────────────
    GoldenPassage(
        "warranty_terms",
        "The standard warranty covers parts and labour for twenty-four months.",
        {"warranty": 0.92},
    ),
    GoldenPassage(
        "warranty_model_x",
        "Model MX-500 units carry an extended thirty-six month warranty.",
        {"warranty": 0.62},
    ),
    # ── onboarding / security ─────────────────────────────────────────────
    GoldenPassage(
        "onboarding_steps",
        "New customers complete identity checks before the first shipment.",
        {"onboarding": 0.90, "security": 0.35},
    ),
    GoldenPassage(
        "security_sso",
        "Single sign-on is available on Growth plans and above.",
        {"security": 0.88},
    ),
    # ── a domain-restricted passage, for the viewport golden ──────────────
    GoldenPassage(
        "payroll_run",
        "The March payroll run was approved by the finance controller.",
        {"payroll": 0.95},
        memory_domain="payroll",
    ),
)

QUERIES: Sequence[GoldenQuery] = (
    GoldenQuery(
        "invoice INV-4417", {"billing": 0.70, "invoice": 0.70}, ("inv_4417",),
        note="exact invoice id — the generic billing passage is the nearer neighbour",
    ),
    GoldenQuery(
        "INV-9902 unpaid", {"billing": 0.70, "invoice": 0.65}, ("inv_9902",),
        note="exact id again, different passage",
    ),
    GoldenQuery(
        "RMA-88 return authorisation", {"refund": 0.70}, ("refund_rma_88",),
        note="exact RMA code against the generic refund policy",
    ),
    GoldenQuery(
        "TRK-70231 consignment", {"shipping": 0.75}, ("ship_tracking",),
        note="exact tracking code against generic shipping prose",
    ),
    GoldenQuery(
        "MX-500 warranty length", {"warranty": 0.80}, ("warranty_model_x",),
        note="exact model code against the standard warranty terms",
    ),
    GoldenQuery(
        "how long is the standard warranty",
        {"warranty": 0.95}, ("warranty_terms",),
        note="no exact token — pure semantics; hybrid must not REGRESS here",
    ),
    GoldenQuery(
        "refund window", {"refund": 0.88, "billing": 0.25}, ("refund_policy",),
        note="paraphrase, no exact token — the semantic half must carry it",
    ),
    GoldenQuery(
        "single sign-on availability", {"security": 0.85}, ("security_sso",),
        note="paraphrase against a distinct topic",
    ),
)

# The queries whose answer hinges on an exact token — where the lexical half is
# expected to do the work. Kept explicit so a regression here is legible.
EXACT_TOKEN_QUERIES = frozenset({
    "invoice INV-4417", "INV-9902 unpaid", "RMA-88 return authorisation",
    "TRK-70231 consignment", "MX-500 warranty length",
})

# The paraphrase queries, where hybrid must at minimum hold its ground: adding a
# lexical retriever must not push a semantically-correct answer down.
SEMANTIC_QUERIES = frozenset({
    "how long is the standard warranty", "refund window",
    "single sign-on availability",
})
