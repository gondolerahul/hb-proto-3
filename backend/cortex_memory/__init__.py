"""
cortex_memory — the CORTEX hierarchical-memory engine, extracted as a
host-independent package (Phase 12 track `04`).

Boundary rule (the whole point of the extraction): **this package never
imports the host** (`src.ai.*`). The host depends on the package and injects
its concerns — LLM calls, embeddings, usage metering, run lookups — through the
Protocols in :mod:`cortex_memory.providers`. A host adapter (the thin
``cortex_bridge`` that stays in ``src/ai/memory``) implements those Protocols.

This is the Stage-B skeleton: the package boundary + provider Protocols + the
first fully host-independent primitive (:mod:`cortex_memory.scope_policy`). The
ORM/`Base` split, the package's own Alembic migrations, and the one-shot host
cutover are the remaining Stage-B work (see ``README.md``).
"""
from __future__ import annotations

from cortex_memory.providers import (
    EmbeddingProvider,
    EmbeddingResult,
    LLMProvider,
    LLMResult,
    RunfRef,
    RunRef,
    RunRegistry,
    UsageReporter,
)
from cortex_memory.scope_policy import ScopePolicy, ScopeViolation

__version__ = "0.0.0.dev0"

__all__ = [
    # providers (the host injects implementations of these)
    "LLMProvider",
    "LLMResult",
    "EmbeddingProvider",
    "EmbeddingResult",
    "UsageReporter",
    "RunRegistry",
    "RunRef",
    "RunfRef",
    # tree primitives
    "ScopePolicy",
    "ScopeViolation",
    "__version__",
]
