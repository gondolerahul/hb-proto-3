"""governance/checkpoint_sla.py — the per-checkpoint HITL SLA sweep (C3).

Replaces one global 24h approval rule with per-checkpoint SLAs + fallbacks: a
PENDING ``human_approvals`` row past its checkpoint's ``sla_seconds`` gets its
``on_timeout`` applied —

* ``auto_deny``  — the act is denied (status ``TIMEOUT``); money/irreversible
  categories fail safe rather than proceed on silence.
* ``auto_park``  — non-destructive: stays PENDING and re-raises a
  ``approval.parked`` signal (surfaces again next sweep).
* ``escalate``   — stays PENDING, raises ``approval.escalated`` (notify louder).

Run from the signal-sweeper cron (globally, every pass). Idempotent within a
day: parked/escalated re-raises are deduped per calendar day so they resurface
without spamming.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.governance.checkpoints import OnTimeout
from src.ai.governance.models import HITLCheckpointDef
from src.ai.orm.execution import ExecutionRun, HumanApproval

logger = logging.getLogger(__name__)

__all__ = ["apply_checkpoint_timeouts", "TIMEOUT_STATUS"]

TIMEOUT_STATUS = "TIMEOUT"


async def apply_checkpoint_timeouts(
    db: AsyncSession, *, now: Optional[datetime] = None,
) -> dict[str, int]:
    """Apply each overdue PENDING approval's ``on_timeout``. Returns a count map."""
    now = now or datetime.utcnow()

    rows = (await db.execute(
        select(HumanApproval, ExecutionRun.company_id)
        .join(ExecutionRun, HumanApproval.run_id == ExecutionRun.id)
        .where(HumanApproval.status == "PENDING",
               HumanApproval.checkpoint_key.isnot(None))
    )).all()
    counts = {"checked": len(rows), "auto_denied": 0, "auto_parked": 0, "escalated": 0}
    if not rows:
        return counts

    defs = {d.key: d for d in (
        await db.execute(select(HITLCheckpointDef))).scalars().all()}

    for approval, company_id in rows:
        cdef = defs.get(approval.checkpoint_key)
        if cdef is None or cdef.sla_seconds is None or approval.requested_at is None:
            continue
        if now < approval.requested_at + timedelta(seconds=cdef.sla_seconds):
            continue

        if cdef.on_timeout == OnTimeout.AUTO_DENY:
            approval.status = TIMEOUT_STATUS
            approval.responded_at = now
            approval.reviewer_notes = (
                f"SLA {cdef.sla_seconds}s elapsed with no decision — "
                f"auto-denied (fail-safe)")
            counts["auto_denied"] += 1
            await _emit(db, company_id, approval, "approval.auto_denied", now, once=True)
        elif cdef.on_timeout == OnTimeout.AUTO_PARK:
            counts["auto_parked"] += 1
            await _emit(db, company_id, approval, "approval.parked", now)
        else:  # escalate
            counts["escalated"] += 1
            await _emit(db, company_id, approval, "approval.escalated", now)

    await db.flush()
    if any(v for k, v in counts.items() if k != "checked"):
        logger.info("checkpoint SLA sweep: %s", counts)
    return counts


async def _emit(
    db: AsyncSession, company_id: Any, approval: HumanApproval, sig_type: str,
    now: datetime, *, once: bool = False,
) -> None:
    """Emit a platform signal for an approval-timeout action (best-effort)."""
    from src.ai.signals.models import SignalSource, SignalTrust
    from src.ai.signals.service import emit_signal

    # Terminal actions dedupe on the approval; re-raises dedupe per calendar day
    # so they resurface without spamming a 60s sweep.
    dedupe = (f"{sig_type}:{approval.id}" if once
              else f"{sig_type}:{approval.id}:{now:%Y-%m-%d}")
    try:
        await emit_signal(
            db, company_id=company_id, source=SignalSource.TELEMETRY, type=sig_type,
            trust=SignalTrust.PLATFORM,
            payload={"approval_id": str(approval.id),
                     "checkpoint_key": approval.checkpoint_key,
                     "run_id": str(approval.run_id)},
            dedupe_key=dedupe,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("approval-timeout signal skipped: %s", exc)
