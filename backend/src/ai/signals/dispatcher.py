"""signals/dispatcher.py — claiming and consuming signals (§18.3–§18.4).

Claims are ``SELECT … FOR UPDATE SKIP LOCKED`` on the PENDING row, so any
number of concurrent workers (targeted jobs + the sweeper) can race on the
same signal and exactly one wins. The claimed transition PENDING→CONSUMED
commits atomically with the spawned run row: at-least-once delivery,
exactly-once consumption.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.signals.models import (
    MAX_DISPATCH_ATTEMPTS,
    PARK_REVIEW_DEFAULT_S,
    Signal,
    SignalSource,
    SignalStatus,
    SignalTrust,
    SignalTypes,
    SignalUrgency,
)
from src.ai.signals.service import emit_signal
from src.ai.signals.triggers import resolve_owner

logger = logging.getLogger(__name__)

__all__ = ["dispatch_signal", "process_claimed_signal", "claim_pending_batch"]


async def dispatch_signal(ctx: dict[str, Any], signal_id_str: str) -> dict[str, Any]:
    """Arq job: claim and consume one signal by id.

    A lost race (row already claimed/consumed by another worker) is a
    clean no-op — the enqueue was at-least-once, consumption is not.
    """
    from src.common.database import AsyncSessionLocal

    signal_id = uuid.UUID(signal_id_str)
    async with AsyncSessionLocal() as db:
        claimed = (await db.execute(
            select(Signal)
            .where(Signal.id == signal_id, Signal.status == SignalStatus.PENDING)
            .with_for_update(skip_locked=True)
        )).scalar_one_or_none()
        if claimed is None:
            return {"signal_id": signal_id_str, "outcome": "not_claimable"}
        outcome = await process_claimed_signal(db, ctx.get("redis"), claimed)
        return {"signal_id": signal_id_str, "outcome": outcome}


async def claim_pending_batch(
    db: AsyncSession,
    *,
    limit: int,
    older_than: datetime | None = None,
    now: datetime | None = None,
    company_id: uuid.UUID | None = None,
) -> list[Signal]:
    """Claim a batch of due PENDING signals, critical urgency first (§18.3).

    ``park_review_at`` doubles as the retry not-before timestamp for
    PENDING rows, giving failed dispatches exponential backoff. The cron
    sweep claims globally; ``company_id`` narrows the scan (ops/tests).
    """
    now = now or datetime.utcnow()
    stmt = (
        select(Signal)
        .where(
            Signal.status == SignalStatus.PENDING,
            (Signal.park_review_at.is_(None)) | (Signal.park_review_at <= now),
        )
    )
    if company_id is not None:
        stmt = stmt.where(Signal.company_id == company_id)
    if older_than is not None:
        stmt = stmt.where(Signal.created_at <= older_than)
    stmt = (
        stmt.order_by(
            case((Signal.urgency == SignalUrgency.CRITICAL, 0), else_=1),
            Signal.created_at,
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list((await db.execute(stmt)).scalars().all())


async def process_claimed_signal(
    db: AsyncSession, redis: Any, signal: Signal, *, now: datetime | None = None,
) -> str:
    """Consume one claimed (row-locked) PENDING signal. Commits.

    Outcomes: ``consumed`` (run spawned) · ``audited`` (completion signal
    self-consumed) · ``parked`` (no owning trigger) · ``retry_scheduled`` /
    ``dead`` (dispatch failure paths).
    """
    now = now or datetime.utcnow()
    # Captured before any rollback: a rollback expires the ORM instance and
    # attribute access would need a (sync) refresh — MissingGreenlet on async.
    signal_id = signal.id
    try:
        owner_reg = await resolve_owner(db, signal.company_id, signal.type)
        owner_entity = None
        if owner_reg is not None:
            owner_entity = await _load_active_entity(db, owner_reg.process_entity_id)

        if owner_entity is None:
            # §18.5: completion signals are audit records — with no subscriber
            # they self-consume rather than clogging the parked/escalation queue.
            if signal.type.endswith(SignalTypes.COMPLETED_SUFFIX):
                signal.status = SignalStatus.CONSUMED
                signal.consumed_at = now
                await db.commit()
                return "audited"
            signal.status = SignalStatus.PARKED
            signal.attempts = 0  # repurposed as the park review counter
            signal.park_review_at = now + timedelta(seconds=PARK_REVIEW_DEFAULT_S)
            await db.commit()
            logger.info("signal %s parked (no trigger for type=%s company=%s)",
                        signal.id, signal.type, signal.company_id)
            return "parked"

        run = await _spawn_run(db, signal, owner_entity)
        signal.status = SignalStatus.CONSUMED
        signal.owner_process_id = owner_entity.id
        signal.consumed_by_run_id = run.id
        signal.consumed_at = now
        signal.park_review_at = None
        await db.commit()

        await _enqueue_run(redis, run.id, signal.id)
        return "consumed"

    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        return await _record_dispatch_failure(db, redis, signal_id, exc, now=now)


async def _load_active_entity(db: AsyncSession, entity_id: uuid.UUID) -> Any | None:
    from src.ai.orm.entity import HierarchicalEntity

    entity = (await db.execute(
        select(HierarchicalEntity).where(HierarchicalEntity.id == entity_id)
    )).scalar_one_or_none()
    if entity is None or str(getattr(entity, "status", "")) in {"ARCHIVED", "DELETED"}:
        return None
    return entity


async def _spawn_run(db: AsyncSession, signal: Signal, entity: Any) -> Any:
    """Create the ordinary Process run that consumes the signal (§18.3)."""
    from src.ai.orm.execution import ExecutionRun
    from src.ai.schemas.enums import RunStatus

    run = ExecutionRun(
        company_id=signal.company_id,
        entity_id=entity.id,
        input_data={
            "input": _signal_task_text(signal),
            "channel": "signal",
            "source": signal.source,
            "event_type": signal.type,
            "signal_id": str(signal.id),
            "signal_type": signal.type,
            "signal": {
                "id": str(signal.id),
                "source": signal.source,
                "type": signal.type,
                "urgency": signal.urgency,
                "confidence": signal.confidence,
                "trust": signal.trust,
                "object_refs": signal.object_refs,
                "payload": signal.payload,
                "created_at": signal.created_at.isoformat(),
            },
        },
        status=RunStatus.PENDING,
    )
    db.add(run)
    await db.flush()
    return run


def _signal_task_text(signal: Signal) -> str:
    """Human/planner-readable task line for the run's ``input``."""
    payload = signal.payload if isinstance(signal.payload, dict) else {}
    subject = payload.get("subject") or payload.get("title") or ""
    head = f"Handle signal {signal.type} (urgency: {signal.urgency})"
    return f"{head} — {subject}" if subject else head


async def _enqueue_run(redis: Any, run_id: uuid.UUID, signal_id: uuid.UUID) -> None:
    """Enqueue the spawned run. Best-effort: on queue failure the run row
    stays PENDING and is visible; the consumed signal records it."""
    if redis is None:
        logger.error("no redis in ctx — run %s for signal %s left PENDING",
                     run_id, signal_id)
        return
    try:
        from arq.connections import ArqRedis

        arq = redis if isinstance(redis, ArqRedis) else ArqRedis(
            getattr(redis, "connection_pool", redis),
        )
        await arq.enqueue_job(
            "run_execution_recursive", str(run_id), _queue_name="arq:queue",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("run enqueue failed (run=%s signal=%s): %s",
                     run_id, signal_id, exc)


async def _record_dispatch_failure(
    db: AsyncSession, redis: Any, signal_id: uuid.UUID, exc: Exception,
    *, now: datetime,
) -> str:
    """§18.3 failure path: attempts += 1 with exponential backoff; past
    ``MAX_DISPATCH_ATTEMPTS`` → DEAD + ``incident.governance`` signal."""
    logger.error("signal %s dispatch failed: %s", signal_id, exc, exc_info=True)
    try:
        row = (await db.execute(
            select(Signal).where(Signal.id == signal_id).with_for_update()
        )).scalar_one_or_none()
        if row is None:
            return "failure_row_missing"
        row.attempts += 1
        row.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        if row.attempts >= MAX_DISPATCH_ATTEMPTS:
            row.status = SignalStatus.DEAD
            row.park_review_at = None
            dead_notice = await emit_signal(
                db,
                company_id=row.company_id,
                source=SignalSource.TELEMETRY,
                type=SignalTypes.INCIDENT_GOVERNANCE,
                urgency=SignalUrgency.HIGH,
                trust=SignalTrust.PLATFORM,
                payload={
                    "reason": "signal_dead",
                    "signal_id": str(row.id),
                    "signal_type": row.type,
                    "last_error": row.last_error,
                },
                dedupe_key=f"dead:{row.id}",
            )
            await db.commit()
            if dead_notice is not None:
                from src.ai.signals.service import enqueue_dispatch

                await enqueue_dispatch(redis, dead_notice)
            _ops_event("signal.dead", signal_id=str(row.id), type=row.type)
            return "dead"
        backoff_s = 60 * (2 ** (row.attempts - 1))  # 60s, 120s, 240s, 480s
        row.park_review_at = now + timedelta(seconds=backoff_s)
        await db.commit()
        return "retry_scheduled"
    except Exception as inner:  # noqa: BLE001
        await db.rollback()
        logger.error("failure bookkeeping itself failed for signal %s: %s",
                     signal_id, inner)
        return "failure_unrecorded"


def _ops_event(name: str, **fields: Any) -> None:
    """Best-effort telemetry event (ops alert channel)."""
    try:
        from src.ai.core.events import event

        event(f"signals.{name}", **fields)
    except Exception:  # pragma: no cover  # noqa: BLE001
        pass
