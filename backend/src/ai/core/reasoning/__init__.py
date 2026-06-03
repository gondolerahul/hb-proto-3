"""
ai.core.reasoning — Reasoning-mode strategy registry (Phase 11 Track 2).

Importing this package registers all four canonical reasoning modes
(REACT, CHAIN_OF_THOUGHT, REFLECTION, TREE_OF_THOUGHTS). Track 9
finishes lifting the per-mode bodies out of ``step_executor.py``; for
Track 2 the adapters delegate into the existing ``llm.router`` calls.
"""
from src.ai.core.reasoning.base import (
    REASONING_REGISTRY,
    Reasoning,
    get_reasoning,
    register_reasoning,
    registered_reasoning_modes,
)
from src.ai.core.reasoning import react              # noqa: F401
from src.ai.core.reasoning import chain_of_thought   # noqa: F401
from src.ai.core.reasoning import reflection         # noqa: F401
from src.ai.core.reasoning import tree_of_thoughts   # noqa: F401

__all__ = [
    "REASONING_REGISTRY",
    "Reasoning",
    "get_reasoning",
    "register_reasoning",
    "registered_reasoning_modes",
]
