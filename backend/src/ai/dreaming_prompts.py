"""Backward-compat stub — import from src.ai.memory.dreaming_prompts instead.
This shim will be removed in Phase 12. Update your imports.
"""
import warnings
warnings.warn(
    "Direct import from src.ai.dreaming_prompts is deprecated. "
    "Use src.ai.memory.dreaming_prompts instead. "
    "This shim will be removed in Phase 12.",
    DeprecationWarning,
    stacklevel=2,
)
from src.ai.memory.dreaming_prompts import *  # noqa: F401,F403
