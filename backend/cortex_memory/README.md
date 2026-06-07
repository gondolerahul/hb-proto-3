# cortex-memory

The CORTEX hierarchical-memory engine, extracted as a host-independent package
(Phase 12 track `04`). **Import name:** `cortex_memory`. **Distribution name:**
`cortex-memory` (planned). **License:** Apache-2.0.

> Status: **Stage-B code-move COMPLETE.** Every CORTEX module now lives here,
> with **zero host imports** (a package self-test enforces it): the data layer
> (`db`/`models`/`enums`/`dtos`/`schema`), the provider boundary
> (`providers`/`providers_reference`), and all services — `service` (the 7 tree
> ops), `graph`, `ingestion`, the four domain trees (`knowledge_tree`/
> `episodic_tree`/`experience_tree`/`intelligence_tree`), `dreaming`, and
> `assembly` (the v2 assembler) — plus `scope_policy`, `domains`, `prompts`, and
> the embedding/text helpers. The host's `src/ai/memory/` keeps only thin
> re-export/auto-injection **shims** + the genuine host **adapters**
> (`cortex_providers`, `cortex_bridge`, `cortex_router`, `embedding_service`,
> `legacy_episodic_reader`, `failure_pattern_service`). Remaining: Stage C
> (separate repo + dist packaging, ≥85% coverage, `mypy --strict`, CI, PyPI).

## The boundary rule

The package **never imports the host** (`src.ai.*`). CORTEX needs four things
from its host that are not memory concerns; it takes them via the Protocols in
`cortex_memory.providers`, which the host implements in a thin adapter
(`cortex_bridge`, which stays in `src/ai/memory/`):

| Protocol | Host adapter wraps | Seam |
|----------|--------------------|------|
| `LLMProvider` | `LLMRouter` | S1 |
| `EmbeddingProvider` | `EmbeddingService` + `resolve_embedding_model` | S4 |
| `UsageReporter` | `UsageService` / `CostAttribution` | S3 |
| `RunRegistry` | `ExecutionRun` lookups | S6 |

`cortex_memory.providers_reference` ships deterministic, dependency-free
implementations so the package runs in tests with zero host/DB/LLM.

## Locked decisions (plan `04` §4)

| # | Decision |
|---|----------|
| K1 | Import `cortex_memory`; distribution `cortex-memory`. |
| K2 | Apache-2.0. |
| K3 | Separate public repo; host pins the version (submodule/local path during Stage B). |
| K4 | Package owns its `Base`; host shares metadata during cutover. |
| K5 | Opaque nullable UUID FKs in the package; host enforces referential integrity. |
| K6 | `task_classifier` stays host-side (depends on host task families/bandit). |
| K7 | One controlled cutover at the end of Stage B, after `01`'s memory deletions (C2, done). |

## Done so far

- [x] **Data layer** — own `Base` (`db.py`), ORM (`models.py`, opaque FK-free
      external refs), enums (`enums.py`), DTOs (`dtos.py`), standalone schema
      bootstrap (`schema.py`). Host DB schema migrated (external cortex FK
      constraints dropped). Host shims keep all imports working.
- [x] **Provider boundary** — Protocols (`providers.py`) + reference impls
      (`providers_reference.py`) + the host adapters
      (`src/ai/memory/cortex_providers.py`: `HostLLMProvider` /
      `HostEmbeddingProvider` / `HostUsageReporter` / `HostRunRegistry` +
      `build_cortex_providers`).
- [x] **Tree primitives** — `scope_policy.py`, `domains.py` (`DomainTreeBase` +
      retrieval weights).

- [x] **All service bodies** — `service` / `graph` / `ingestion` / the four
      domain trees / `dreaming` / `assembly`, each converted from host imports
      (`LLMRouter` / `EmbeddingService` / `ExecutionRun` / usage) to **injected
      providers** (LLM via `LLMProvider`; embeddings via `EmbeddingProvider` +
      the node-aware `cortex_memory.embedding` helpers; RECURSE child runs via an
      injected `child_run_factory`). Host shims auto-inject the adapters so
      existing call sites are unchanged.

## Remaining (Stage C — separate repo + release)

1. Extract this directory to its own public repo with a `pyproject.toml`
   (name `cortex-memory`, Apache-2.0, deps: SQLAlchemy + pgvector + pydantic).
2. ≥85% coverage, `mypy --strict`, CI, examples, docs.
3. Publish v0.1.0 to PyPI; the host pins the version and drops the in-repo copy.

`cortex_bridge.py`, `cortex_router.py` (HTTP), `embedding_service.py`,
`legacy_episodic_reader.py`, `failure_pattern_service.py` stay host-side as the
genuine adapters / host-specific code (plan §3).
