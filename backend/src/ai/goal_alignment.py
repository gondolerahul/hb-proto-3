"""Backward-compat stub — import from src.ai.planning.goal_alignment instead.
This shim will be removed in Phase 12. Update your imports.
"""
import warnings
warnings.warn(
    "Direct import from src.ai.goal_alignment is deprecated. "
    "Use src.ai.planning.goal_alignment instead. "
    "This shim will be removed in Phase 12.",
    DeprecationWarning,
    stacklevel=2,
)
from src.ai.planning.goal_alignment import *  # noqa: F401,F403
