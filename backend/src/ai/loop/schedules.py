"""loop/schedules.py — schedule dispatch (technical doc §17.1 step 1).

The heartbeat evaluates the Loop's ``loop_config.schedules`` and emits
``schedule.*`` signals with the **schedule slot** as ``dedupe_key`` — so a
double-fired heartbeat cannot double-run a Process (the SIG dedupe partial
unique index rejects the second insert). A schedule is an interval:

    {"signal_type": "schedule.daily_report", "every_seconds": 86400}

The current slot is ``floor(epoch / every_seconds)`` — one signal per window.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.orm.entity import HierarchicalEntity

logger = logging.getLogger(__name__)

__all__ = ["dispatch_due_schedules", "current_slot"]


def current_slot(now: datetime, every_seconds: int) -> int:
    epoch = now.replace(tzinfo=timezone.utc).timestamp() if now.tzinfo is None \
        else now.timestamp()
    return int(epoch // max(1, every_seconds))


async def dispatch_due_schedules(
    db: AsyncSession, redis: Any, company_id: uuid.UUID, loop_entity_id: uuid.UUID,
    *, now: datetime | None = None,
) -> int:
    """Emit one schedule signal per due window. Returns the count emitted."""
    now = now or datetime.utcnow()
    loop = await db.get(HierarchicalEntity, loop_entity_id)
    if loop is None:
        return 0
    schedules = _schedules_of(loop)
    if not schedules:
        return 0

    from src.ai.signals.service import emit_signal, enqueue_dispatch
    from src.ai.signals.models import SignalSource, SignalTrust

    emitted = 0
    for sched in schedules:
        signal_type = sched.get("signal_type")
        every = int(sched.get("every_seconds", 0) or 0)
        if not signal_type or every <= 0:
            continue
        slot = current_slot(now, every)
        dedupe = f"schedule:{loop_entity_id}:{signal_type}:{slot}"
        sig_id = await emit_signal(
            db, company_id=company_id, source=SignalSource.SCHEDULE,
            type=signal_type, trust=SignalTrust.PLATFORM,
            payload={"loop_entity_id": str(loop_entity_id), "slot": slot,
                     "schedule": sched},
            dedupe_key=dedupe,
        )
        if sig_id is not None:
            await enqueue_dispatch(redis, sig_id)
            emitted += 1
    return emitted


def _schedules_of(loop: HierarchicalEntity) -> list[dict[str, Any]]:
    cfg = getattr(loop, "metadata_extensions", None)
    if isinstance(cfg, dict):
        loop_cfg = cfg.get("loop_config")
        if isinstance(loop_cfg, dict):
            scheds = loop_cfg.get("schedules")
            if isinstance(scheds, list):
                return [s for s in scheds if isinstance(s, dict)]
    return []
