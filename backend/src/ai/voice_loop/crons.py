"""voice_loop/crons.py — the scheduled half of the post-call loop (Inc-4 T6).

Two jobs, deliberately on different cadences.

``voice_deferred_sweep`` drains a small batch every 10 minutes. There is no
deadline: a call reflected on an hour late is worth exactly what one reflected
on immediately is worth, and the model provider's rate limit belongs to live
conversation. Same posture as RETR's chunk-upgrade sweep.

``voice_deferred_reap`` runs daily. Draining alone would turn an unbounded
queue into an unbounded archive — the leak Inc-3 left is only closed when
finished rows eventually leave.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["voice_deferred_sweep", "voice_deferred_reap"]


async def voice_deferred_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: execute the post-call stages for a batch of finished calls."""
    from src.ai.voice_loop.deferred_runner import drain_batch
    from src.common.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            stats = await drain_batch(db)
        if stats.get("claimed"):
            logger.info("voice deferred sweep: %s", stats)
        return stats
    except Exception as exc:  # noqa: BLE001
        logger.error("voice_deferred_sweep failed: %s", exc, exc_info=True)
        return {"error": str(exc)}


async def voice_deferred_reap(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: delete finished post-call rows past retention."""
    from src.ai.voice_loop.deferred_runner import queue_depth, reap_finished
    from src.common.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            reaped = await reap_finished(db)
            await db.commit()
            depth = await queue_depth(db)
        if reaped:
            logger.info("voice deferred reap: removed=%s remaining=%s",
                        reaped, depth)
        return {"reaped": reaped, "remaining": depth}
    except Exception as exc:  # noqa: BLE001
        logger.error("voice_deferred_reap failed: %s", exc, exc_info=True)
        return {"error": str(exc)}
