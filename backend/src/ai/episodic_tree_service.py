"""Backward-compat stub — import from src.ai.memory.episodic_tree_service instead.
This shim will be removed in Phase 12. Update your imports.
"""
import warnings
warnings.warn(
    "Direct import from src.ai.episodic_tree_service is deprecated. "
    "Use src.ai.memory.episodic_tree_service instead. "
    "This shim will be removed in Phase 12.",
    DeprecationWarning,
    stacklevel=2,
)
from src.ai.memory.episodic_tree_service import *  # noqa: F401,F403
