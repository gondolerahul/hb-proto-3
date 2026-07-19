"""signals/service.py — producing signals (outbox pattern, §18.2).

``emit_signal`` inserts the signal row **in the caller's open transaction**
so it commits or rolls back atomically with the business write. Dispatch is
enqueued separately *after* the caller commits (``enqueue_dispatch``); the
sweeper covers a crash between commit and enqueue, which is what makes
"no dropped signals" auditable rather than asserted.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.signals.models import (
    Signal,
    SignalStatus,
    SignalTrust,
    SignalTypes,
    SignalUrgency,
)

logger = logging.getLogger(__name__)

__all__ = ["emit_signal", "enqueue_dispatch", "emit_completion_for_run"]


async def emit_signal(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    source: str,
    type: str,
    payload: dict[str, Any] | None = None,
    urgency: str = SignalUrgency.NORMAL,
    confidence: float = 1.0,
    trust: str = SignalTrust.INTERNAL,
    object_refs: list[str] | None = None,
    dedupe_key: str | None = None,
    replayed_from: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Insert a signal row into the caller's transaction (outbox insert).

    Returns the new signal id, or ``None`` when ``dedupe_key`` already
    exists for this company (idempotent producer, §18.4). Uses
    ``ON CONFLICT DO NOTHING`` so a duplicate never poisons the caller's
    transaction.
    """
    signal_id = uuid.uuid4()
    stmt = (
        pg_insert(Signal)
        .values(
            id=signal_id,
            company_id=company_id,
            source=source,
            type=type,
            urgency=urgency,
            confidence=confidence,
            trust=trust,
            object_refs=object_refs,
            payload=payload,
            dedupe_key=dedupe_key,
            status=SignalStatus.PENDING,
            attempts=0,
            replayed_from=replayed_from,
            created_at=datetime.utcnow(),
        )
        .on_conflict_do_nothing(
            index_elements=["company_id", "dedupe_key"],
            index_where=text("dedupe_key IS NOT NULL"),
        )
        .returning(Signal.id)
    )
    inserted = (await db.execute(stmt)).scalar_one_or_none()
    if inserted is None:
        logger.debug(
            "signal emit deduped: company=%s type=%s dedupe_key=%s",
            company_id, type, dedupe_key,
        )
        return None
    return inserted


async def enqueue_dispatch(redis: Any, signal_id: uuid.UUID) -> bool:
    """Enqueue ``dispatch_signal`` for a committed signal (best-effort).

    Call only after the emitting transaction has committed. Returns False
    when the queue is unreachable — the sweeper re-dispatches the row
    within one sweep interval, so failure here is never fatal.
    """
    if redis is None:
        return False
    try:
        from arq.connections import ArqRedis

        arq = redis if isinstance(redis, ArqRedis) else ArqRedis(
            getattr(redis, "connection_pool", redis),
        )
        await arq.enqueue_job(
            "dispatch_signal", str(signal_id), _queue_name="arq:queue",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("dispatch enqueue failed for signal %s: %s", signal_id, exc)
        return False


async def emit_completion_for_run(
    db: AsyncSession, redis: Any, run: Any,
) -> uuid.UUID | None:
    """§18.5 completion hook: emit ``<type>.completed`` for a consumed signal.

    Called from run finalization. No-op unless the run's ``input_data``
    carries the ``signal_id``/``signal_type`` the dispatcher stamped.
    Idempotent via dedupe_key, so resume/retry paths cannot double-emit.
    Commits its own small transaction; never raises.
    """
    try:
        input_data = getattr(run, "input_data", None) or {}
        signal_id = input_data.get("signal_id")
        signal_type = input_data.get("signal_type")
        if not signal_id or not signal_type:
            return None
        if str(signal_type).endswith(SignalTypes.COMPLETED_SUFFIX):
            return None  # never chain completions of completions
        company_id = getattr(run, "company_id", None)
        if company_id is None:
            return None
        emitted = await emit_signal(
            db,
            company_id=company_id,
            source="agent",
            type=f"{signal_type}{SignalTypes.COMPLETED_SUFFIX}",
            trust=SignalTrust.PLATFORM,
            payload={
                "signal_id": str(signal_id),
                "run_id": str(run.id),
                "run_status": str(getattr(run, "status", "")),
            },
            dedupe_key=f"completed:{signal_id}",
        )
        await db.commit()
        if emitted is not None:
            await enqueue_dispatch(redis, emitted)
        return emitted
    except Exception as exc:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:  # pragma: no cover  # noqa: BLE001
            pass
        logger.warning("completion-signal emit skipped for run %s: %s",
                       getattr(run, "id", "?"), exc)
        return None
