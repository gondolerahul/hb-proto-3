"""signals/sweeper.py — the safety net that makes "no dropped signals" true.

Every sweep (60s cron):
  1. Re-dispatches due PENDING signals older than one sweep interval —
     covers a crash between the producer's commit and its enqueue, and
     drives the exponential-backoff retry schedule.
  2. Reviews PARKED signals whose timer expired: a trigger registered
     since parking consumes them; after MAX_PARK_REVIEWS unresolved
     reviews they ESCALATE (visible via the signals API; the approvals-
     panel card follows with the Inc-2 admin UI).

Claims are one-row-per-transaction: each processed signal commits before
the next claim, so locks never outlive the row they protect.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.signals import dispatcher as _dispatcher
from src.ai.signals.models import (
    MAX_PARK_REVIEWS,
    PARK_REVIEW_DEFAULT_S,
    Signal,
    SignalStatus,
    SignalUrgency,
)
from src.ai.signals.triggers import resolve_owner

logger = logging.getLogger(__name__)

SWEEP_STALE_S = 60
SWEEP_BATCH_LIMIT = 100

__all__ = ["signal_sweeper", "sweep_pending", "review_parked"]


async def signal_sweeper(ctx: dict[str, Any]) -> dict[str, Any]:
    """Arq cron: one sweep pass. Never raises."""
    from src.common.database import AsyncSessionLocal

    redis = ctx.get("redis")
    now = datetime.utcnow()
    try:
        async with AsyncSessionLocal() as db:
            pending_stats = await sweep_pending(db, redis, now=now)
            parked_stats = await review_parked(db, redis, now=now)
        result = {**pending_stats, **parked_stats}
        if any(result.values()):
            logger.info("signal sweep: %s", result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("signal sweeper failed: %s", exc, exc_info=True)
        return {"error": str(exc)}


async def sweep_pending(
    db: AsyncSession, redis: Any, *, now: datetime | None = None,
) -> dict[str, int]:
    """Claim-and-consume due PENDING signals, one per transaction."""
    now = now or datetime.utcnow()
    stale_before = now - timedelta(seconds=SWEEP_STALE_S)
    outcomes: dict[str, int] = {}
    for _ in range(SWEEP_BATCH_LIMIT):
        batch = await _dispatcher.claim_pending_batch(
            db, limit=1, older_than=stale_before, now=now,
        )
        if not batch:
            break
        outcome = await _dispatcher.process_claimed_signal(db, redis, batch[0], now=now)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {f"pending_{k}": v for k, v in outcomes.items()}


async def review_parked(
    db: AsyncSession, redis: Any, *, now: datetime | None = None,
    company_id: Any = None,
) -> dict[str, int]:
    """Review PARKED signals whose ``park_review_at`` timer expired.

    The cron reviews globally; ``company_id`` narrows the scan (ops/tests).
    """
    now = now or datetime.utcnow()
    consumed = escalated = still_parked = 0
    for _ in range(SWEEP_BATCH_LIMIT):
        stmt = select(Signal).where(
            Signal.status == SignalStatus.PARKED,
            Signal.park_review_at <= now,
        )
        if company_id is not None:
            stmt = stmt.where(Signal.company_id == company_id)
        signal = (await db.execute(
            stmt
            .order_by(
                case((Signal.urgency == SignalUrgency.CRITICAL, 0), else_=1),
                Signal.created_at,
            )
            .limit(1)
            .with_for_update(skip_locked=True),
        )).scalar_one_or_none()
        if signal is None:
            break

        owner_reg = await resolve_owner(db, signal.company_id, signal.type)
        owner_entity = None
        if owner_reg is not None:
            owner_entity = await _dispatcher._load_active_entity(
                db, owner_reg.process_entity_id,
            )

        if owner_entity is not None:
            run = await _dispatcher._spawn_run(db, signal, owner_entity)
            signal.status = SignalStatus.CONSUMED
            signal.owner_process_id = owner_entity.id
            signal.consumed_by_run_id = run.id
            signal.consumed_at = now
            signal.park_review_at = None
            await db.commit()
            await _dispatcher._enqueue_run(redis, run.id, signal.id)
            consumed += 1
            continue

        signal.attempts += 1  # unresolved review count while PARKED
        if signal.attempts >= MAX_PARK_REVIEWS:
            signal.status = SignalStatus.ESCALATED
            signal.park_review_at = None
            await db.commit()
            _dispatcher._ops_event(
                "signal.escalated",
                signal_id=str(signal.id),
                type=signal.type,
                company_id=str(signal.company_id),
                reviews=signal.attempts,
            )
            logger.warning(
                "signal %s ESCALATED after %s unresolved reviews (type=%s company=%s)",
                signal.id, signal.attempts, signal.type, signal.company_id,
            )
            escalated += 1
        else:
            signal.park_review_at = now + timedelta(seconds=PARK_REVIEW_DEFAULT_S)
            await db.commit()
            still_parked += 1
    return {
        "parked_consumed": consumed,
        "parked_escalated": escalated,
        "parked_repark": still_parked,
    }
