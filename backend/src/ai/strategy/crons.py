"""strategy/crons.py — the scheduled half of STRAT (T6).

One job. Thin arq entry point only; the policy lives in ``review_sweep.py`` so
it stays testable without a worker — the same shape ``learning/crons.py`` and
``library/crons.py`` take.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["review_due_sweep"]


async def review_due_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron (02:20): ask for the reviews whose date has arrived.

    It writes no Review — a review the platform filled in by itself is a review
    nobody read. And it obeys L8: a mandate returns to its owner only at review
    time or on exception.
    """
    from src.ai.strategy.review_sweep import sweep_all

    try:
        return await sweep_all()
    except Exception as exc:  # noqa: BLE001
        logger.error("review_due_sweep failed: %s", exc)
        return {"error": str(exc)}
