"""signals/api.py — internal signals + trigger-registry API (Inc 1: API-only).

Company-scoped through the authenticated user. Admin UI arrives with
Increment 2; until then this API is how escalated/dead queues are worked.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db
from src.ai.signals.models import Signal, SignalStatus, TriggerRegistration
from src.ai.signals.service import emit_signal

router = APIRouter(prefix="/ai/signals", tags=["Signal Bus"])

_VALID_STATUSES = {
    SignalStatus.PENDING, SignalStatus.CONSUMED, SignalStatus.PARKED,
    SignalStatus.ESCALATED, SignalStatus.DEAD,
}


def _signal_out(s: Signal) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "source": s.source,
        "type": s.type,
        "urgency": s.urgency,
        "confidence": s.confidence,
        "trust": s.trust,
        "status": s.status,
        "object_refs": s.object_refs,
        "payload": s.payload,
        "dedupe_key": s.dedupe_key,
        "owner_process_id": str(s.owner_process_id) if s.owner_process_id else None,
        "consumed_by_run_id": str(s.consumed_by_run_id) if s.consumed_by_run_id else None,
        "park_review_at": s.park_review_at.isoformat() if s.park_review_at else None,
        "attempts": s.attempts,
        "replayed_from": str(s.replayed_from) if s.replayed_from else None,
        "last_error": s.last_error,
        "created_at": s.created_at.isoformat(),
        "consumed_at": s.consumed_at.isoformat() if s.consumed_at else None,
    }


class TriggerCreate(BaseModel):
    process_entity_id: uuid.UUID
    type_pattern: str = Field(min_length=1, max_length=120)
    priority: int = 100
    enabled: bool = True


class TriggerUpdate(BaseModel):
    priority: int | None = None
    enabled: bool | None = None


# ── Trigger registry (static routes before /{signal_id}) ────────────────────

@router.get("/triggers")
async def list_triggers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    rows = (await db.execute(
        select(TriggerRegistration)
        .where(TriggerRegistration.company_id == current_user.company_id)
        .order_by(TriggerRegistration.priority.desc(), TriggerRegistration.created_at)
    )).scalars().all()
    return [
        {
            "id": str(r.id),
            "process_entity_id": str(r.process_entity_id),
            "type_pattern": r.type_pattern,
            "priority": r.priority,
            "enabled": r.enabled,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/triggers", status_code=201)
async def create_trigger(
    body: TriggerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from src.ai.orm.entity import HierarchicalEntity

    entity = (await db.execute(
        select(HierarchicalEntity).where(
            HierarchicalEntity.id == body.process_entity_id,
            HierarchicalEntity.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()
    if entity is None:
        raise HTTPException(404, "Process entity not found in this company")
    if str(getattr(entity, "status", "")) in {"ARCHIVED", "DELETED"}:
        raise HTTPException(422, "Cannot register a trigger for an archived entity")

    reg = TriggerRegistration(
        company_id=current_user.company_id,
        process_entity_id=body.process_entity_id,
        type_pattern=body.type_pattern,
        priority=body.priority,
        enabled=body.enabled,
    )
    db.add(reg)
    await db.commit()
    await db.refresh(reg)
    return {"id": str(reg.id)}


@router.patch("/triggers/{trigger_id}")
async def update_trigger(
    trigger_id: uuid.UUID,
    body: TriggerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    reg = (await db.execute(
        select(TriggerRegistration).where(
            TriggerRegistration.id == trigger_id,
            TriggerRegistration.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()
    if reg is None:
        raise HTTPException(404, "Trigger registration not found")
    if body.priority is not None:
        reg.priority = body.priority
    if body.enabled is not None:
        reg.enabled = body.enabled
    await db.commit()
    return {"id": str(reg.id), "priority": reg.priority, "enabled": reg.enabled}


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(
    trigger_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    reg = (await db.execute(
        select(TriggerRegistration).where(
            TriggerRegistration.id == trigger_id,
            TriggerRegistration.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()
    if reg is None:
        raise HTTPException(404, "Trigger registration not found")
    await db.delete(reg)
    await db.commit()
    return {"deleted": str(trigger_id)}


# ── Signals ─────────────────────────────────────────────────────────────────

@router.get("/coverage")
async def signal_coverage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """The §18.5 signal-coverage audit: counts per status, one query."""
    rows = (await db.execute(
        select(Signal.status, func.count())
        .where(Signal.company_id == current_user.company_id)
        .group_by(Signal.status)
    )).all()
    counts = {status: int(n) for status, n in rows}
    total = sum(counts.values())
    uncovered = counts.get(SignalStatus.PARKED, 0) + counts.get(SignalStatus.ESCALATED, 0) \
        + counts.get(SignalStatus.DEAD, 0)
    return {
        "counts": counts,
        "total": total,
        "coverage_pct": round(100.0 * (total - uncovered) / total, 2) if total else 100.0,
    }


@router.get("")
async def list_signals(
    status: str | None = None,
    type_prefix: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if status is not None and status not in _VALID_STATUSES:
        raise HTTPException(422, f"status must be one of {sorted(_VALID_STATUSES)}")
    stmt = select(Signal).where(Signal.company_id == current_user.company_id)
    if status is not None:
        stmt = stmt.where(Signal.status == status)
    if type_prefix:
        stmt = stmt.where(Signal.type.like(f"{type_prefix}%"))
    stmt = stmt.order_by(Signal.created_at.desc()).limit(min(max(limit, 1), 200))
    rows = (await db.execute(stmt)).scalars().all()
    return [_signal_out(s) for s in rows]


@router.get("/{signal_id}")
async def get_signal(
    signal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    s = (await db.execute(
        select(Signal).where(
            Signal.id == signal_id,
            Signal.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "Signal not found")
    return _signal_out(s)


@router.post("/{signal_id}/replay", status_code=201)
async def replay_signal(
    signal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """§18.4: signals are immutable — replay inserts a clone with
    ``replayed_from`` set (fresh dedupe scope) and dispatches it."""
    original = (await db.execute(
        select(Signal).where(
            Signal.id == signal_id,
            Signal.company_id == current_user.company_id,
        )
    )).scalar_one_or_none()
    if original is None:
        raise HTTPException(404, "Signal not found")

    clone_id = await emit_signal(
        db,
        company_id=original.company_id,
        source=original.source,
        type=original.type,
        payload=original.payload,
        urgency=original.urgency,
        confidence=original.confidence,
        trust=original.trust,
        object_refs=original.object_refs,
        dedupe_key=f"replay:{original.id}:{datetime.utcnow().isoformat()}",
        replayed_from=original.id,
    )
    await db.commit()
    if clone_id is None:  # pragma: no cover — timestamped key cannot collide
        raise HTTPException(500, "Replay dedupe collision")
    from src.ai.signals.service import enqueue_dispatch

    try:
        import redis.asyncio as aioredis
        from src.common.config import settings

        redis_pool = aioredis.from_url(settings.REDIS_URL or "redis://localhost:6379")  # type: ignore[no-untyped-call]
        try:
            await enqueue_dispatch(redis_pool, clone_id)
        finally:
            await redis_pool.aclose()
    except Exception:  # noqa: BLE001
        pass  # sweeper delivers within one interval
    return {"id": str(clone_id), "replayed_from": str(original.id)}
