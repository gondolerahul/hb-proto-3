"""Backward-compat stub — import from src.ai.memory.cortex_router instead.
This shim will be removed in Phase 12. Update your imports.
"""
import warnings
warnings.warn(
    "Direct import from src.ai.cortex_router is deprecated. "
    "Use src.ai.memory.cortex_router instead. "
    "This shim will be removed in Phase 12.",
    DeprecationWarning,
    stacklevel=2,
)
from src.ai.memory.cortex_router import *  # noqa: F401,F403
