"""library/crons.py — the scheduled halves of LIB (T3, T4, T8).

Thin arq entry points only; the policy lives in `influence.py`, `staleness.py`
and `connectors/credential_expiry.py` so all three stay testable without a
worker. Same shape as `learning/crons.py` and `trust/crons.py`.

**The rollup and the reaper are one job**, at 02:40. Not two, and the ordering
inside it is not incidental: the reaper's cutoff is clamped to what the rollup
has covered (`influence.reap_usage_log`), so running them apart would leave the
reaper permanently one schedule behind for no benefit. It is also the rule
`kpi_snapshot_sweep` already follows, for the reason its docstring gives — a
reaper on its own schedule is a reaper that eventually stops being deployed.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["influence_rollup_sweep", "staleness_sweep", "credential_expiry_sweep"]


async def influence_rollup_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron (02:40): aggregate the usage log, then reap what it covered."""
    from src.ai.library.influence import reap_usage_log, roll_up_pending
    from src.common.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            rolled = await roll_up_pending(db)
            await db.commit()
            reaped = await reap_usage_log(db)
            await db.commit()
            return {"rollup": rolled, "reap": reaped}
    except Exception as exc:  # noqa: BLE001
        logger.error("influence_rollup_sweep failed: %s", exc)
        return {"error": str(exc)}


async def staleness_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron (02:50): re-assess every document's staleness, with its reason."""
    from src.ai.library.staleness import sweep_all
    from src.common.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            return await sweep_all(db)
    except Exception as exc:  # noqa: BLE001
        logger.error("staleness_sweep failed: %s", exc)
        return {"error": str(exc)}


async def credential_expiry_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron (03:10): warn about connector credentials before they expire."""
    from src.ai.connectors.credential_expiry import sweep_expiring_credentials
    from src.common.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            summary = await sweep_expiring_credentials(db)
            await db.commit()
            return summary
    except Exception as exc:  # noqa: BLE001
        logger.error("credential_expiry_sweep failed: %s", exc)
        return {"error": str(exc)}
