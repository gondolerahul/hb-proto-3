"""Backward-compat stub — import from src.ai.governance.governance_service instead.
This shim will be removed in Phase 12. Update your imports.
"""
import warnings
warnings.warn(
    "Direct import from src.ai.governance_service is deprecated. "
    "Use src.ai.governance.governance_service instead. "
    "This shim will be removed in Phase 12.",
    DeprecationWarning,
    stacklevel=2,
)
from src.ai.governance.governance_service import *  # noqa: F401,F403
