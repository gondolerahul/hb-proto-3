# cortex-memory

The CORTEX hierarchical-memory engine, extracted as a host-independent package
(Phase 12 track `04`). **Import name:** `cortex_memory`. **Distribution name:**
`cortex-memory` (planned). **License:** Apache-2.0.

> Status: **Stage-B in progress.** The package now owns its **data layer** —
> its own SQLAlchemy `Base` (`db.py`), the ORM models (`models.py`, opaque
> FK-free external refs), the enums (`enums.py`), the DTOs (`dtos.py`,
> `Provenance`/`GoalNode`/tree shapes), a standalone schema bootstrap
> (`schema.py`), the provider Protocols (`providers.py`), and `scope_policy`.
> The host re-exports all of these via shims (`cortex_models`, `schemas/cortex`,
> `schemas/enums`) so existing imports are unchanged. The CORTEX *services*
> (`CortexService`, graph/domain/dreaming, the v2 assembler) move in next.

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

## Remaining Stage-B work (the service bodies)

The orchestration services still live in `src/ai/memory/` and consume the host
adapters. Each move converts its host imports (`LLMRouter`/`EmbeddingService`/
`ExecutionRun`/usage) to **injected providers**:

1. `cortex_service.py` (the 7 tree ops) + `cortex_ingestion.py`.
2. `graph_service.py` (semantic graph; uses `EmbeddingProvider`).
3. the four domain services + `memory_assembly_service.py` (v2 assembler).
4. `dreaming_engine.py` + `dreaming_prompts.py`.
5. Wire the host to construct these with `build_cortex_providers(...)` injected;
   smoke-replay a run through the loop.

`cortex_bridge.py`, `cortex_router.py` (HTTP), `legacy_episodic_reader.py`,
`failure_pattern_service.py` stay host-side as thin adapters (plan §3).

Then Stage C: docs, ≥85% coverage, `mypy --strict`, CI, publish v0.1.0.
