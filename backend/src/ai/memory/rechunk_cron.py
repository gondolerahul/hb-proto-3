"""memory/rechunk_cron.py — the arq entry point for the lazy chunk upgrade.

Kept separate from ``rechunk.py`` so the sweep logic stays importable and
testable without pulling in the worker's session plumbing — the same split
``trust/crons.py`` uses for the dunning sweep.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["chunk_upgrade_sweep"]


async def chunk_upgrade_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: upgrade a small batch of stale-chunked documents (RETR T2).

    Deliberately low-frequency and small-batch. There is no deadline — a
    document retrieves perfectly well on its old chunks meanwhile — and the
    sweep shares the embedding provider's rate limit with live ingestion, which
    must always win.
    """
    from src.ai.memory.rechunk import rechunk_sweep
    from src.common.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            return await rechunk_sweep(db)
    except Exception as exc:  # noqa: BLE001
        logger.error("chunk_upgrade_sweep failed: %s", exc)
        return {"error": str(exc)}
