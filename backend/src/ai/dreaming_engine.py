"""Backward-compat stub — import from src.ai.memory.dreaming_engine instead.
This shim will be removed in Phase 12. Update your imports.
"""
import warnings
warnings.warn(
    "Direct import from src.ai.dreaming_engine is deprecated. "
    "Use src.ai.memory.dreaming_engine instead. "
    "This shim will be removed in Phase 12.",
    DeprecationWarning,
    stacklevel=2,
)
from src.ai.memory.dreaming_engine import *  # noqa: F401,F403
