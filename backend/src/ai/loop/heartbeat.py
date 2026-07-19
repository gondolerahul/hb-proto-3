"""loop/heartbeat.py — the Loop heartbeat (technical doc §17.1).

A single platform cron scans ``loop_runtime`` and beats each Loop whose per-Loop
interval has elapsed ("simple but configurable" — decision 2026-07-19). Each
beat is four deterministic steps: dispatch due schedules, sweep parked signals,
roll up child cost into the envelope + stats, stamp liveness. All Loop
*cognition* is dispatched as ordinary runs elsewhere — the heartbeat itself is
flat-cost platform code (§17.4).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.loop.envelopes import (
    ensure_loop_envelope,
    is_downshift,
    refresh_if_due,
    rollup_spent,
    utilization_pct,
)
from src.ai.loop.models import LoopRuntime
from src.ai.loop.schedules import dispatch_due_schedules
from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = ["loop_heartbeat", "beat_one"]


async def loop_heartbeat(ctx: dict[str, Any]) -> dict[str, Any]:
    """Arq cron: beat every Loop whose interval has elapsed. Never raises."""
    from src.common.database import AsyncSessionLocal

    redis = ctx.get("redis")
    now = datetime.utcnow()
    beaten = 0
    try:
        async with AsyncSessionLocal() as db:
            due = await _due_loops(db, now)
        for loop_id in due:
            async with AsyncSessionLocal() as db:
                try:
                    await beat_one(db, redis, loop_id, now=now)
                    beaten += 1
                except Exception as exc:  # noqa: BLE001
                    await db.rollback()
                    logger.error("heartbeat failed for loop %s: %s", loop_id, exc)
        return {"loops_beaten": beaten}
    except Exception as exc:  # noqa: BLE001
        logger.error("loop_heartbeat scan failed: %s", exc)
        return {"error": str(exc)}


async def _due_loops(db: AsyncSession, now: datetime) -> list[Any]:
    rows = (await db.execute(
        select(LoopRuntime).where(LoopRuntime.enabled.is_(True))
    )).scalars().all()
    due = []
    for rt in rows:
        if rt.last_beat_at is None:
            due.append(rt.loop_entity_id)
        elif now - rt.last_beat_at >= timedelta(seconds=rt.heartbeat_interval_s):
            due.append(rt.loop_entity_id)
    return due


async def beat_one(
    db: AsyncSession, redis: Any, loop_entity_id: Any, *, now: datetime | None = None,
) -> dict[str, Any]:
    """One heartbeat: schedules → parked sweep → rollup → stamp. Commits."""
    now = now or datetime.utcnow()
    rt = (await db.execute(
        select(LoopRuntime).where(LoopRuntime.loop_entity_id == loop_entity_id)
        .with_for_update(skip_locked=True)
    )).scalar_one_or_none()
    if rt is None:
        return {"skipped": "not claimable"}

    # 1. Dispatch due schedules → schedule.* signals (dedupe by slot).
    schedules_fired = await dispatch_due_schedules(db, redis, rt.company_id, loop_entity_id, now=now)

    # 2. Sweep this company's parked signals whose review timer expired.
    parked = await _sweep_parked(db, redis, rt.company_id, now=now)

    # 3. Roll up child cost into the envelope + stats.
    env = await ensure_loop_envelope(db, rt.company_id, loop_entity_id)
    await refresh_if_due(db, env, now=now)
    spent = await rollup_spent(db, env, now=now)
    util = utilization_pct(env)
    if is_downshift(env):
        await _notify_downshift(db, redis, rt.company_id, loop_entity_id, util)
    rt.stats = {
        "spent_usd": float(spent), "envelope_usd": float(env.envelope_usd),
        "utilization_pct": round(util, 2), "schedules_fired": schedules_fired,
        "parked_swept": parked, "beat_at": now.isoformat(),
    }

    # 4. Stamp liveness.
    rt.last_beat_at = now
    rt.consecutive_missed = 0
    await db.commit()
    return {"loop": str(loop_entity_id), "schedules_fired": schedules_fired,
            "parked_swept": parked, "utilization_pct": round(util, 2)}


async def _sweep_parked(db: AsyncSession, redis: Any, company_id: Any, *, now: datetime) -> int:
    """Re-evaluate this company's PARKED signals (reuses the SIG sweeper)."""
    try:
        from src.ai.signals.sweeper import review_parked

        stats = await review_parked(db, redis, now=now, company_id=company_id)
        return int(stats.get("parked_consumed", 0)) + int(stats.get("parked_escalated", 0))
    except Exception as exc:  # noqa: BLE001
        logger.debug("loop parked sweep skipped: %s", exc)
        return 0


async def _notify_downshift(db: AsyncSession, redis: Any, company_id: Any,
                            loop_id: Any, util: float) -> None:
    try:
        from src.ai.signals.service import emit_signal, enqueue_dispatch
        from src.ai.signals.models import SignalSource, SignalTrust

        sig = await emit_signal(
            db, company_id=company_id, source=SignalSource.TELEMETRY,
            type="budget.downshift", urgency="high", trust=SignalTrust.PLATFORM,
            payload={"loop_entity_id": str(loop_id), "utilization_pct": round(util, 2)},
            dedupe_key=f"downshift:{loop_id}:{datetime.utcnow():%Y-%m-%d}",
        )
        if sig is not None:
            await enqueue_dispatch(redis, sig)
    except Exception as exc:  # noqa: BLE001
        logger.debug("downshift notify skipped: %s", exc)
