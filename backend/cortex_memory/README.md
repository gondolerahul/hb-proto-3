# cortex-memory

The CORTEX hierarchical-memory engine, extracted as a host-independent package
(Phase 12 track `04`). **Import name:** `cortex_memory`. **Distribution name:**
`cortex-memory` (planned). **License:** Apache-2.0.

> Status: **Stage-B skeleton.** This directory currently holds the package
> *boundary* — the provider Protocols and the first fully host-independent
> primitive. The bulk of the CORTEX code (`CortexService`, the ORM/`Base`, the
> domain/graph/dreaming services, the v2 assembler) still lives in
> `backend/src/ai/memory/` and moves in over the remaining Stage-B steps.

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

## Remaining Stage-B work (scheduled)

1. Host adapter: make `cortex_bridge` implement the four Protocols; inject them
   into the CORTEX services (start with `EmbeddingProvider` — seam S4).
2. Move the host-independent tree primitives next (`domains/base.py`,
   `dreaming_prompts.py`, CORTEX DTOs/`Provenance`).
3. Move `cortex_models.py` onto the package's own SQLAlchemy `Base` + ship the
   package's Alembic migrations (opaque nullable UUID FKs, K5). **DB change —
   its own controlled step.**
4. Move `cortex_service.py` + ingestion/graph/domain/dreaming/v2-assembler.
5. The one-shot cutover: host imports flip to `cortex_memory`; smoke replay.

Then Stage C: docs, ≥85% coverage, `mypy --strict`, CI, publish v0.1.0.
