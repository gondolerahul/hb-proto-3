"""evolution/crons.py — the scheduled half of SEGA.

Thin arq entry point only; the policy lives in ``sweep.py`` so it stays
testable without a worker. Same shape as ``trust/crons.py`` and
``learning/crons.py``.

**01:50 UTC, after C4's demotion sweep at 01:40.** Demotion is about authority
and the canary is about version: running demotion first means a rolled-back
entity is not simultaneously being demoted for the failures its rollback has
just removed.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["entity_canary_sweep"]


async def entity_canary_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: judge every open entity canary — promote, roll back, or keep watching."""
    from src.ai.evolution.sweep import sweep_all
    from src.common.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            return await sweep_all(db)
    except Exception as exc:  # noqa: BLE001
        logger.error("entity_canary_sweep failed: %s", exc)
        return {"error": str(exc)}
