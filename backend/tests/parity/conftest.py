"""
tests/parity/conftest.py — Wire the engine adapters Track 2 needs.

Without these registrations, ``run_parity_case`` raises a clear
``RuntimeError`` rather than silently producing a green test on a
half-wired engine. The wiring is intentionally inside conftest so
non-parity test runs don't pay the import cost.
"""
from __future__ import annotations

from typing import Any

from tests.parity.harness import register_engine_adapter


class LegacyAdapter:
    """Runs the pre-Phase-11 ExecutionEngine."""
    async def run(self, db: Any, redis: Any, run_id: Any) -> None:
        from src.ai.core.execution_engine import ExecutionEngine
        await ExecutionEngine(db, redis).execute_run(run_id)


class CandidateAdapter:
    """Runs the Phase 11 Track 2 AgentLoop."""
    async def run(self, db: Any, redis: Any, run_id: Any) -> None:
        from src.ai.core.agent_loop import AgentLoop
        await AgentLoop(db, redis).run(run_id)


register_engine_adapter("legacy", LegacyAdapter())
register_engine_adapter("candidate", CandidateAdapter())
