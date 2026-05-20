"""Backward-compat stub — import from src.ai.memory.cortex_ingestion instead.
This shim will be removed in Phase 12. Update your imports.
"""
import warnings
warnings.warn(
    "Direct import from src.ai.cortex_ingestion is deprecated. "
    "Use src.ai.memory.cortex_ingestion instead. "
    "This shim will be removed in Phase 12.",
    DeprecationWarning,
    stacklevel=2,
)
from src.ai.memory.cortex_ingestion import *  # noqa: F401,F403
