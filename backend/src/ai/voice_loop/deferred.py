"""voice_loop/deferred.py — the stages the live turn could not run.

The realtime profile defers Strategize, Pre-Critic, Post-Critic, Reflect and
Decide. **Deferred is not skipped.** When the call ends, this queues a run that
executes them over the transcript, so CORTEX reflections and the §7 learning
signal still get written — just after the caller has hung up rather than while
they wait.

Two properties worth stating:

* **Cost attribution is tenant-initiated.** The tenant's own call caused this
  work, so it stays *out* of ``PLATFORM_INITIATED_ATTRIBUTIONS`` and draws on
  the tenant's envelope. Classifying it as platform work would let ordinary
  call volume exhaust the cap that exists to protect tenants *from* platform
  work (HANDOFF §5, the B13 rule).
* **A failed deferred run never retroactively invalidates the call.** The
  conversation happened and was governed inline by the PolicyGate. Reflection
  failing afterwards costs learning, not correctness — so failures are logged
  and bounded, never escalated into the call's outcome.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.voice_loop.models import DeferredRunStatus, VoiceDeferredRun
from src.ai.voice_loop.profile import DEFERRED_STAGES

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_ATTEMPTS",
    "queue_deferred_run",
    "claim_next",
    "mark_done",
    "mark_failed",
    "pending_count",
]

#: Bounded because a transcript that cannot be reflected on will not start
#: being reflectable. Three tries, then it stays failed and visible.
MAX_ATTEMPTS = 3

#: Below this, a call carries no reflectable content — a wrong number, a hangup
#: on the greeting. Queuing those would spend a model call on nothing.
MIN_TURNS_TO_REFLECT = 3


async def queue_deferred_run(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    call_sid: str,
    transcript: list[dict[str, Any]],
    entity_id: uuid.UUID | None = None,
) -> VoiceDeferredRun | None:
    """Queue the post-call loop for a finished call.

    Returns ``None`` when the call was too short to be worth reflecting on, or
    when this call is already queued — carriers fire end-of-call webhooks more
    than once, and a duplicate would double-charge the tenant for the same
    reflection.
    """
    if len(transcript) < MIN_TURNS_TO_REFLECT:
        logger.debug("voice deferred run skipped: call %s too short", call_sid)
        return None

    existing = (await db.execute(
        select(VoiceDeferredRun).where(
            VoiceDeferredRun.company_id == company_id,
            VoiceDeferredRun.call_sid == call_sid,
        ).limit(1)
    )).scalars().first()
    if existing is not None:
        return None

    row = VoiceDeferredRun(
        company_id=company_id,
        call_sid=call_sid,
        entity_id=entity_id,
        status=DeferredRunStatus.PENDING,
        transcript=transcript,
        stages=[s.value for s in DEFERRED_STAGES],
    )
    db.add(row)
    await db.flush()
    return row


async def claim_next(
    db: AsyncSession, *, company_id: uuid.UUID | None = None,
) -> VoiceDeferredRun | None:
    """Claim one pending run for execution.

    ``FOR UPDATE SKIP LOCKED`` so two workers never reflect on the same call —
    the same claim pattern the signal dispatcher uses.
    """
    stmt = (
        select(VoiceDeferredRun)
        .where(
            VoiceDeferredRun.status == DeferredRunStatus.PENDING,
            VoiceDeferredRun.attempts < MAX_ATTEMPTS,
        )
        .order_by(VoiceDeferredRun.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if company_id is not None:
        stmt = stmt.where(VoiceDeferredRun.company_id == company_id)

    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        return None

    row.status = DeferredRunStatus.RUNNING
    row.attempts += 1
    await db.flush()
    return row


async def mark_done(
    db: AsyncSession, row: VoiceDeferredRun,
    *, execution_run_id: uuid.UUID | None = None,
) -> None:
    row.status = DeferredRunStatus.DONE
    row.execution_run_id = execution_run_id
    row.completed_at = datetime.utcnow()
    row.error = None
    await db.flush()


async def mark_failed(
    db: AsyncSession, row: VoiceDeferredRun, error: str,
) -> None:
    """Record a failure. Returns the row to PENDING while retries remain.

    A call whose reflection failed is not a failed call — the conversation was
    governed inline and already happened. This costs learning, not correctness.
    """
    row.error = error[:2000]
    if row.attempts >= MAX_ATTEMPTS:
        row.status = DeferredRunStatus.FAILED
        row.completed_at = datetime.utcnow()
        logger.warning(
            "voice deferred run gave up after %s attempts: call=%s err=%s",
            row.attempts, row.call_sid, error)
    else:
        row.status = DeferredRunStatus.PENDING
    await db.flush()


async def pending_count(db: AsyncSession, company_id: uuid.UUID) -> int:
    from sqlalchemy import func

    return int((await db.execute(
        select(func.count(VoiceDeferredRun.id)).where(
            VoiceDeferredRun.company_id == company_id,
            VoiceDeferredRun.status == DeferredRunStatus.PENDING,
        )
    )).scalar() or 0)
