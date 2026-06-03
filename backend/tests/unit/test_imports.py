"""Phase 11 Track 0 — import-shape assertions.

These tests freeze the cleanup work so it doesn't regress in later
Tracks. Specifically:

  * CortexRouter → CortexService rename (T0-3); the legacy name must
    still resolve via the backwards-compat alias until Track 9 deletes
    it.
  * worker.py re-exports must be gone (T0-4); the canonical paths
    under ``src.ai.core.*`` must work.
"""
from __future__ import annotations

import pytest


def test_cortex_service_canonical_import() -> None:
    """`from src.ai.memory.cortex_service import CortexService` works."""
    from src.ai.memory.cortex_service import CortexService

    assert CortexService.__name__ == "CortexService"


def test_cortex_router_backwards_compat_alias_resolves() -> None:
    """The legacy `CortexRouter` symbol still resolves and points to
    the renamed class. Removed in Track 9."""
    from src.ai.memory.cortex_service import CortexRouter, CortexService

    assert CortexRouter is CortexService


def test_memory_package_exposes_both_names() -> None:
    """`from src.ai.memory import CortexService` and `CortexRouter` both
    resolve while the alias is in place."""
    from src.ai.memory import CortexRouter, CortexService

    assert CortexService is CortexRouter


def test_no_worker_re_exports() -> None:
    """`from src.ai.worker import ExecutionEngine` must raise — the
    Track 0 cleanup removed the worker re-exports."""
    with pytest.raises(ImportError):
        from src.ai.worker import ExecutionEngine  # noqa: F401


def test_canonical_execution_engine_import() -> None:
    """The canonical replacement for the worker re-export works."""
    from src.ai.core.execution_engine import ExecutionEngine

    assert ExecutionEngine.__name__ == "ExecutionEngine"


def test_canonical_recursive_engine_import() -> None:
    from src.ai.core.recursive_engine import RecursiveReasoningEngine

    assert RecursiveReasoningEngine.__name__ == "RecursiveReasoningEngine"


def test_canonical_exception_import() -> None:
    from src.ai.core.exceptions import UncertaintySignal

    assert issubclass(UncertaintySignal, BaseException)
