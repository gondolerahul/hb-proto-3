"""loop/watchdog.py — heartbeat supervision (technical doc §17.3).

A platform cron flags any Loop whose ``last_beat_at`` is older than N intervals:
``consecutive_missed`` increments, an ``incident.platform`` signal is emitted,
and ops is alerted. Recovery is simply the next heartbeat firing — safe because
schedule dispatch dedupes on the slot, so a double-fired heartbeat cannot
double-run a Process.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.loop.models import LoopRuntime
from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = ["loop_watchdog", "find_stalled"]


async def loop_watchdog(ctx: dict[str, Any]) -> dict[str, Any]:
    """Arq cron: flag + alert on stalled Loop heartbeats. Never raises."""
    from src.common.database import AsyncSessionLocal

    redis = ctx.get("redis")
    now = datetime.utcnow()
    flagged = 0
    try:
        async with AsyncSessionLocal() as db:
            stalled = await find_stalled(db, now=now)
            for rt in stalled:
                rt.consecutive_missed += 1
                await _emit_incident(db, redis, rt)
                _ops_alert(rt)
                flagged += 1
            if flagged:
                await db.commit()
        return {"stalled_flagged": flagged}
    except Exception as exc:  # noqa: BLE001
        logger.error("loop_watchdog failed: %s", exc)
        return {"error": str(exc)}


async def find_stalled(
    db: AsyncSession, *, now: datetime | None = None,
    miss_intervals: int | None = None,
) -> list[LoopRuntime]:
    """Loops whose last beat is older than ``miss_intervals`` × their interval."""
    now = now or datetime.utcnow()
    misses = miss_intervals or settings.LOOP_WATCHDOG_MISS_INTERVALS
    rows = (await db.execute(
        select(LoopRuntime).where(LoopRuntime.enabled.is_(True))
    )).scalars().all()
    stalled = []
    for rt in rows:
        if rt.last_beat_at is None:
            continue  # never beaten yet — the heartbeat, not the watchdog, owns first beat
        if now - rt.last_beat_at > timedelta(seconds=rt.heartbeat_interval_s * misses):
            stalled.append(rt)
    return stalled


async def _emit_incident(db: AsyncSession, redis: Any, rt: LoopRuntime) -> None:
    try:
        from src.ai.signals.service import emit_signal, enqueue_dispatch
        from src.ai.signals.models import SignalSource, SignalTrust

        sig = await emit_signal(
            db, company_id=rt.company_id, source=SignalSource.TELEMETRY,
            type="incident.platform", urgency="critical", trust=SignalTrust.PLATFORM,
            payload={"reason": "loop_heartbeat_stalled",
                     "loop_entity_id": str(rt.loop_entity_id),
                     "consecutive_missed": rt.consecutive_missed,
                     "last_beat_at": rt.last_beat_at.isoformat() if rt.last_beat_at else None},
            dedupe_key=f"stalled:{rt.loop_entity_id}:{rt.consecutive_missed}",
        )
        if sig is not None:
            await enqueue_dispatch(redis, sig)
    except Exception as exc:  # noqa: BLE001
        logger.debug("watchdog incident emit skipped: %s", exc)


def _ops_alert(rt: LoopRuntime) -> None:
    try:
        from src.ai.core.events import event

        event("loop.heartbeat.stalled", loop_entity_id=str(rt.loop_entity_id),
              consecutive_missed=rt.consecutive_missed)
    except Exception:  # pragma: no cover  # noqa: BLE001
        pass
    logger.warning("Loop %s heartbeat stalled (missed=%s)",
                   rt.loop_entity_id, rt.consecutive_missed)
