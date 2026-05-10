"""
constants.py — Centralized constants for the AI engine.

All magic numbers, model names, and internal keys that were previously
scattered across worker.py, memory_service.py, and service.py are
consolidated here as the single source of truth.
"""
from typing import FrozenSet

# ---------------------------------------------------------------------------
# Embedding Model
# ---------------------------------------------------------------------------
# Single constant used by memory_service.py (semantic search), worker.py
# (document processing), and service.py (document embedding).
# Previously: "text-embedding-004" in memory_service.py vs
#             "gemini-embedding-004" in worker.py/service.py (DATA-4 bug)
EMBEDDING_MODEL = "gemini-embedding-004"

# ---------------------------------------------------------------------------
# Internal Context Keys
# ---------------------------------------------------------------------------
# Keys injected into context_state for engine bookkeeping.
# Must be stripped before persisting or sending to LLM prompts.
# Previously duplicated at worker.py:1974 (7 members) and worker.py:2334
# (11 members) with different sets — a latent context-leakage bug (R5).
INTERNAL_CONTEXT_KEYS: FrozenSet[str] = frozenset({
    "input",
    "cortex_tree_id",
    "subtree_root_id",
    "__memory__",
    "__cortex_viewport__",
    "__cortex_tree_id__",
    "__cortex_cursor__",
    "__cortex_knowledge__",
    "__context_sources__",
    "__episodic_memory__",
    "__semantic_context__",
    "__memory_context__",
    "__completed_steps__",
    "tool_call_counts",
    "company_id",
    "user_id",
})

# ---------------------------------------------------------------------------
# Execution Limits
# ---------------------------------------------------------------------------
MAX_REACT_TURNS = 12
CONTEXT_TOKEN_ESTIMATION_DIVISOR = 4
MAX_CONTENT_CHARS = 50000
MAX_CONTEXT_TRUNCATION_CHARS = 6000
CONTEXT_SUMMARIZE_THRESHOLD = 20000
DEFAULT_TIMEOUT_MS = 60000
