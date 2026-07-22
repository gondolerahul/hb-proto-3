"""trust/crons.py — the scheduled halves of TRUST.

C5 shipped the dunning ladder, the ``subscription_status`` column, the
state-aware middleware, and the transition signals — but nothing *drove* them.
This is that driver: a daily sweep that computes each subscription's
``days_past_due`` and advances its ladder position.

It lives here rather than in ``billing/`` because ``billing``'s own cron
functions are written for an external scheduler (systemd/crontab or the admin
endpoints in ``cron_router.py``), while the arq worker is what actually runs on
a schedule in this deployment. The billing service keeps the logic; this is the
thin arq entry point that calls it.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["dunning_sweep"]


async def dunning_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: advance every subscription's C5 dunning ladder position.

    Idempotent by construction — ``advance_dunning`` only moves a company (and
    only emits a ``billing.*`` signal) on a real transition, so re-running this
    against a stable tenant base does nothing.
    """
    from src.billing.cron_service import CronService
    from src.common.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            return await CronService(db).run_dunning_job()
    except Exception as exc:  # noqa: BLE001
        logger.error("dunning_sweep failed: %s", exc)
        return {"error": str(exc)}
