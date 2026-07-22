# Increment 2 / RETR — Retrieval Upgrade (§24.4, Inc-1 carryover)

> **Status:** ✅ **Built** (2026-07-22) — all five tasks; migrations `retr001`–`retr003`; gates green. See §5–§9 for build notes. · **Branch:** `inc2/retr` · **Closes:** the retrieval half of B8 ✅ (the scoping half shipped in Inc-1 SCH).
> **Design authority:** Technical §24.4. KB + CORTEX are control-plane permanent (v3.0.6), so this upgrades control-plane retrieval.
> **Depends on:** SCH (memory scoping shipped); gated by its own retrieval goldens. Sequenced last (quality, not blocking the sellable path).

---

## 1. Design (self-contained)

Replaces the under-specified v2 stack (500-char chunks, top-5 cosine @0.70) with the §24.4 upgrade — on the **control plane**, where KB + CORTEX live (v3.0.6):

* **Hybrid retrieval** — Postgres full-text (lexical) + pgvector (semantic), fused by **reciprocal-rank fusion**. Both indexes are already in the control-plane DB with the KB.
* **Structure-aware chunking** — 1–2k-char chunks split on document structure, carrying heading context; chunk size tunable per source type (replaces the flat 500-char split in the shipped `process_document`).
* **Schema-aware filters** — retrieval accepts metadata predicates from the tenant schema (object type, counterparty, date range) so "invoices for Acme since March" filters before it ranks. Composes with the Inc-1 **domain viewport** (need-to-know still applies after fusion).
* **Optional reranking** — a cross-encoder rerank behind a per-tier flag (Growth+), applied to the fused top-50.
* **Evaluated, not assumed** — retrieval golden sets join the eval harness (§22.1); chunking/fusion changes are regression-gated.

## 2. Code Mapping

| Piece | Where |
|---|---|
| Hybrid retrieval + RRF | `ai/memory/` retrieval path (control-plane KB) + a full-text index migration on `document_chunks` |
| Structure-aware chunking | replace the flat split in `ai/core/arq_jobs.py::process_document` + the knowledge-tree ingest |
| Schema-aware filters | retrieval query accepts predicates; composes with `domain_viewport` (Inc-1) |
| Reranking (flagged) | `ai/memory/` rerank stage, per-tier flag |
| Retrieval goldens | `tests/eval/` retrieval golden set |

## 3. Task Plan (outline)

| # | Task | Acceptance |
|---|---|---|
| T1 | Full-text index + hybrid retrieval with RRF | hybrid beats pure-cosine on the golden set |
| T2 | Structure-aware chunking (re-ingest path) | chunks carry heading context; tunable per source type |
| T3 | Schema-aware metadata filters composing with the domain viewport | "invoices for Acme since March" filters correctly + respects memory_domains |
| T4 | Optional cross-encoder rerank behind a per-tier flag | Growth+ tenants get rerank; others unaffected |
| T5 | Retrieval goldens in the eval harness + gates | chunking/fusion changes are regression-gated; mypy/eval green |

## 4. Brainstorm Decisions (Rahul, 2026-07-20)

1. **Lazy background re-chunking** — existing KB re-ingests into the new chunking via the background lazy-upgrade pattern (like SCH's `def_version`), so old documents improve without a big-bang migration.
2. **Rerank model choice deferred to build; flagged Growth+** — a cross-encoder behind the per-tier flag; the specific model is picked at build time against its latency/cost budget (feeds E1).
   * **Resolved at build (Rahul, 2026-07-22): LLM-as-reranker**, not a local cross-encoder. A cross-encoder meant a new heavyweight dependency and a model download for a latency budget that does not exist yet; the LLM route reuses the router, tracing and cost ledger already in place. See §9.

---

## 5. Build Notes — T1 hybrid retrieval + RRF (2026-07-22)

1. **The lexical half is what was missing.** v1 was pure cosine (`top-5 @ 0.70`). Embeddings are good at *aboutness* and bad at *exactness* — they blur "INV-4417" against "INV-4471", a part number against its vector neighbours, a proper noun against a synonym. Migration `retr001` adds a GIN index over `to_tsvector('english', content)`; an **expression index needs no column and no backfill**, so every existing chunk became searchable the moment it built.

2. **Fusion is on rank, not score, and that is the design.** A cosine similarity and a `ts_rank_cd` are not comparable quantities, and normalising them against each other would invent a relationship that is not there. RRF (`Σ 1/(k+rank)`, k=60) asks only how near the top each retriever put a chunk, so the two vote without a shared unit. Results carry per-retriever ranks, which makes a bad retrieval legible — "lexical-only at rank 1" reads very differently from "both retrievers agreed".

3. **A failed embedding is no longer fatal.** `search_semantic` now degrades to lexical-only when the embedding call fails. The old path returned an empty list, so the agent answered from no context at all — a silent quality cliff triggered by a provider hiccup.

## 6. Build Notes — T2 structure-aware chunking (2026-07-22)

1. **`text[i:i+500]` was the worst available boundary.** It cut mid-sentence and often mid-word, so a chunk routinely began with half a clause whose subject sat in the previous chunk — and an embedding of a fragment is an embedding of nothing in particular. `memory/chunking.py` splits on structure instead: ATX, numbered, setext, and (for PDF/DOCX, which arrive with no markup at all) isolated bare-title headings; paragraphs packed to a per-source-type target; oversized paragraphs split on sentence boundaries with a hard cut only as a last resort.

2. **Heading context is prepended *into* `content`, not stored beside it.** Both retrievers read that column, so a heading kept only in a metadata field would be invisible to exactly the two consumers that need it. "Net-30 applies." is useless without "§4 Payment Terms — Enterprise"; now it carries it.

3. **The re-chunk is genuinely lazy** (decision 1). `chunk_version` (migration `retr002`) marks what produced each chunk; old and new coexist — both indexed, both retrievable — while a bounded hourly batch upgrades stale documents. Source text is reconstructed losslessly from the v1 *contiguous* slices. The swap happens only once every replacement embedding is in hand: a partial failure keeps the stale chunks, which are strictly better than fewer chunks. **Re-embedding is platform-initiated spend**, so the sweep goes through B13's `platform_work_admitted` and parks at the cap.

## 7. Build Notes — T3 filters + viewport composition (2026-07-22)

1. **Relevance and permission are kept separate**, deliberately. `ChunkFilters` (relevance) renders an `AND`-prefixed fragment with every value bound — never interpolated — and gained `heading_contains` once T2 gave chunks a heading trail, so a caller can narrow to "Payment Terms" without knowing which document holds it.

2. **Need-to-know reached the KB, which it never had.** The Inc-1 domain viewport governed Knowledge and Episodic nodes, but documents carried no domain at all — so the retrieval path an agent uses *most* sat outside §24.3 entirely. `documents.memory_domain` (migration `retr003`) closes it. NULL stays meaningful: the viewport reads an untagged node as `general`, so existing documents behave exactly as before and tagging only ever narrows.

3. **Order of operations is load-bearing.** The viewport applies **after fusion and before `top_k`**. Truncating first would let a document the caller may not see consume a result slot and silently shrink what they are entitled to — pinned by `test_hidden_results_do_not_consume_top_k_slots`.

## 8. Build Notes — T5 retrieval goldens (2026-07-22)

The gate that makes T1's claim more than an anecdote. 12 passages / 8 queries built so the right answer is **not** the nearest neighbour — it shares topic with a decoy and is distinguished by an exact token (invoice id, RMA, model code). Semantic similarity is *simulated* via a small named concept space so the goldens stay deterministic and provider-free; the lexical half is real Postgres FTS over real text.

| Retriever | recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| cosine (v1) | 1.000 | 0.812 | 0.862 |
| **hybrid** | **1.000** | **1.000** | **1.000** |

The entire gain is on the exact-token queries (MRR 0.700 → 1.000). The paraphrase queries score 1.000 under both — and **that** is the assertion worth having: adding a lexical retriever can push a semantically-correct answer down, and an aggregate improvement would hide it. Floors are set at 0.95/0.95 rather than loosely, because the corpus and the fusion are both deterministic and there is no run-to-run noise to absorb.

## 9. Build Notes — T4 Growth+ reranker (2026-07-22)

1. **Why rerank at all.** RRF fuses two orderings without ever reading the passages — it knows both retrievers liked a chunk, not whether the chunk answers the question. A reranker reads query and candidate together, which is why it usually buys more than any amount of fusion tuning.

2. **Three bounds on the per-query cost**, since decision 2's resolution puts real inference on the retrieval path: **Growth+ only** (the tier gate **fails closed** — an unrecognised plan falls back to not spending); only the **fused top-20** are scored; and it is attributed `rerank`, deliberately **not** in `PLATFORM_INITIATED_ATTRIBUTIONS`. The tenant asked the question, so it draws from tenant budget — in the platform class, ordinary retrieval could exhaust the very cap that exists to protect tenants *from* platform work.

3. **It fails open on every path.** Provider down, malformed scores, timeout → the fused order, untouched. An unscored candidate keeps its position: silence about a passage is not a judgement that it is irrelevant. Wired at `memory_service`, not inside `hybrid_search`, so fusion stays pure retrieval and reranking is its own stage.

**RETR is complete** — B8's retrieval half is closed, and with it Increment 2.
