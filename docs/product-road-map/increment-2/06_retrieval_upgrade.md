# Increment 2 / RETR — Retrieval Upgrade (§24.4, Inc-1 carryover)

> **Status:** Draft — for brainstorm review · **Branch:** `inc2/retr` · **Closes:** the retrieval half of B8 (the scoping half shipped in Inc-1 SCH).
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

## 4. Open Questions

1. **Re-chunking existing KB** — re-ingest all existing documents into the new chunking, or apply new chunking only to new uploads? Proposal: background re-ingest with the lazy-upgrade pattern (like SCH's def_version), so old KB improves without a big-bang migration.
2. **Rerank model + cost** — which cross-encoder, and does its latency/cost fit the per-tier flag economics (feeds E1)? Defer model choice to build; keep it flagged Growth+.
