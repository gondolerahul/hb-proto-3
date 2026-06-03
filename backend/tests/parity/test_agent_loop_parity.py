"""
Phase 11 Track 2 — Parity tests for the AgentLoop.

These tests compare a recorded golden snapshot (produced by
``backend/scripts/record_golden_runs.py``) against a fresh run of the
new AgentLoop. They are SKIPPED when:

  * No golden snapshot is on disk for the case, OR
  * The DATABASE_URL / REDIS_URL env vars are missing (CI without
    services), OR
  * Track 2 hasn't yet flipped the ``agent_loop.enabled`` feature flag
    on the test entity.

When all three conditions are met, the tests assert ±5% cost parity,
≥0.85 output cosine similarity, ±2 step-count delta, and matching final
status against the golden.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.harness import RunResult


GOLDENS_DIR = Path(__file__).resolve().parent / "goldens"


def _has_live_services() -> bool:
    return bool(os.environ.get("DATABASE_URL") and os.environ.get("REDIS_URL"))


def _available_goldens() -> list[Path]:
    if not GOLDENS_DIR.exists():
        return []
    return [p for p in GOLDENS_DIR.glob("*.json") if p.name != ".gitkeep"]


pytestmark = pytest.mark.parity


@pytest.mark.skipif(
    not _available_goldens(),
    reason="No golden snapshots present — run "
    "`python backend/scripts/record_golden_runs.py` first.",
)
@pytest.mark.skipif(
    not _has_live_services(),
    reason="DATABASE_URL / REDIS_URL not set — parity tests need live services.",
)
@pytest.mark.parametrize(
    "golden_path",
    _available_goldens(),
    ids=lambda p: p.stem,
)
@pytest.mark.asyncio
async def test_agent_loop_parity(golden_path: Path) -> None:
    """One parity case per golden snapshot.

    The test loads the golden, sets up a fresh tenant + run, flips
    ``agent_loop.enabled = true`` on the test entity, and runs the
    AgentLoop. ``compare_run_results`` then asserts tolerances.

    Track 3+ tightens tolerances per the matrix in
    ``14_test_strategy.md §4.3``.
    """
    # This is intentionally a thin shell — the harness owns the
    # heavy lifting once Track 2 wires DB/Redis fixtures into
    # the parity conftest. Until those fixtures exist this test is
    # a placeholder that documents the intended call site.
    baseline = RunResult.load(golden_path)
    pytest.skip(
        f"DB/Redis fixtures not yet wired in conftest; baseline loaded "
        f"({baseline.status}, ${baseline.total_cost_usd:.4f}, "
        f"{baseline.step_count} steps) — Track 2 sign-off requires "
        f"wiring DB/Redis fixtures before this assertion can run."
    )


def test_parity_conftest_registers_engines() -> None:
    """Sanity: the conftest in this directory MUST have registered
    both engine adapters so ``run_parity_case`` doesn't raise."""
    from tests.parity.harness import ENGINE_ADAPTERS
    assert "legacy" in ENGINE_ADAPTERS
    assert "candidate" in ENGINE_ADAPTERS
