"""voice_loop/deferred_runner.py — draining the post-call queue (Inc-4 T6).

Increment 3 built the queue and the webhook that fills it, and nothing that
empties it. Two consequences, and the second is the worse one:

1. Calls wrote no reflections, so the §7 learning loop got nothing from voice.
2. ``voice_deferred_runs`` grew without bound — a table that only ever gets
   rows is a slow leak, and it was leaking in production shape.

This module fixes both. It executes the **corrected** deferred set: Post-Critic
and Reflect. Strategize and Decide are gone — Inc-4 diagnosed them as having no
post-hoc meaning at all, and running them after a call would have been theatre.
Pre-Critic replay is calibration and is skipped here; nothing depends on it.

**A failed deferred run never invalidates the call.** The conversation happened
and was governed inline by the PolicyGate. Reflection failing afterwards costs
learning, not correctness — so failures are bounded, recorded, and dropped.

The reaper is not an afterthought. Draining alone leaves every completed row in
place forever; a queue is only bounded if finished work eventually leaves it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.voice_loop.deferred import claim_next, mark_done, mark_failed
from src.ai.voice_loop.models import DeferredRunStatus, VoiceDeferredRun
from src.ai.voice_loop.profile import REQUIRED_DEFERRED_STAGES

logger = logging.getLogger(__name__)

__all__ = [
    "BATCH_LIMIT",
    "queue_depth",
    "RETENTION_DAYS",
    "REFLECTION_TOOL",
    "run_deferred",
    "drain_batch",
    "reap_finished",
]

#: Small batch, like the RETR chunk-upgrade sweep. There is no deadline — a
#: call reflected on an hour late is worth exactly as much as one reflected
#: on immediately, and the model provider's rate limit belongs to live work.
BATCH_LIMIT = 20

#: How long a finished row stays. Long enough to debug a bad week, short
#: enough that the table has a ceiling.
RETENTION_DAYS = 30

REFLECTION_TOOL = "record_call_reflection"

_SCHEMA: dict[str, Any] = {
    "name": REFLECTION_TOOL,
    "description": "Record what this call established and how it was handled.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {"type": "string",
                        "description": "What the caller wanted and what happened."},
            "outcome": {"type": "string",
                        "enum": ["resolved", "partial", "unresolved", "misrouted"]},
            "handled_well": {"type": "string",
                             "description": "What the agent did that worked."},
            "handled_poorly": {"type": "string",
                               "description": "What it got wrong. Empty if "
                                              "nothing — do not invent a fault."},
            "follow_up": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "outcome"],
    },
}


def _prompt() -> str:
    return (
        "A phone call has ended. Review the transcript as a supervisor would: "
        "what the caller wanted, what the agent did, and whether that was the "
        "right handling.\n\n"
        "This is the supervision and reflection the live call could not run — "
        "a conversational turn has no room for a model call, so it happens "
        "now. Nothing you write blocks or reverses anything; the call is over "
        "and was governed as it happened. You are writing for whoever handles "
        "this customer next.\n\n"
        "Be specific and be willing to say the agent got it wrong. Leave "
        "'handled_poorly' empty if it did not — an invented fault is worse "
        "than none, because it will be acted on."
    )


async def run_deferred(
    db: AsyncSession, row: VoiceDeferredRun,
) -> dict[str, Any]:
    """Execute the deferred stages for one call. Raises on model failure."""
    from src.ai.llm.router import LLMRouter

    transcript = row.transcript or []
    lines = "\n".join(
        f"{t.get('role', 'caller')}: {t.get('content', '')}"
        for t in transcript if isinstance(t, dict))

    router = LLMRouter(db=db, company_id=row.company_id)
    response = await router.call_llm(
        task_type="text_generation",
        system_prompt=_prompt(),
        user_prompt=f"=== CALL TRANSCRIPT ===\n{lines}\n=== END ===",
        tools=[_SCHEMA],
        temperature=0.2,
    )

    for call in response.function_calls:
        if call.get("name") == REFLECTION_TOOL:
            args = dict(call.get("args") or {})
            return {
                "stages": [s.value for s in REQUIRED_DEFERRED_STAGES],
                "summary": str(args.get("summary") or ""),
                "outcome": str(args.get("outcome") or "unresolved"),
                "handled_well": str(args.get("handled_well") or ""),
                "handled_poorly": str(args.get("handled_poorly") or ""),
                "follow_up": list(args.get("follow_up") or []),
            }

    # No tool call: the model had nothing to say about the transcript. That is
    # a real outcome for a 4-turn wrong number, not an error.
    return {"stages": [s.value for s in REQUIRED_DEFERRED_STAGES],
            "summary": "", "outcome": "unresolved"}


async def drain_batch(
    db: AsyncSession, *, limit: int = BATCH_LIMIT,
) -> dict[str, int]:
    """Claim and execute up to ``limit`` pending runs."""
    stats = {"claimed": 0, "done": 0, "failed": 0}

    for _ in range(limit):
        row = await claim_next(db)
        if row is None:
            break
        stats["claimed"] += 1
        try:
            result = await run_deferred(db, row)
            row.stages = result.get("stages", row.stages)
            await mark_done(db, row)
            stats["done"] += 1
        except Exception as exc:  # noqa: BLE001
            # Bounded by claim_next's attempts check — a transcript that
            # cannot be reflected on will not become reflectable.
            await mark_failed(db, row, str(exc))
            stats["failed"] += 1
        await db.commit()

    return stats


async def reap_finished(
    db: AsyncSession, *, older_than_days: int = RETENTION_DAYS,
    now: datetime | None = None,
) -> int:
    """Delete finished rows past retention. Returns how many went.

    Without this, draining converts an unbounded queue into an unbounded
    archive. Only terminal rows are eligible — anything still pending or
    running is left alone however old it looks.
    """
    cutoff = (now or datetime.utcnow()) - timedelta(days=older_than_days)
    result = await db.execute(
        delete(VoiceDeferredRun).where(
            VoiceDeferredRun.status.in_(
                [DeferredRunStatus.DONE, DeferredRunStatus.FAILED,
                 DeferredRunStatus.SKIPPED]),
            VoiceDeferredRun.completed_at.is_not(None),
            VoiceDeferredRun.completed_at < cutoff,
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def queue_depth(db: AsyncSession) -> int:
    """Total rows, for the operational check that this stays bounded."""
    return int((await db.execute(
        select(func.count(VoiceDeferredRun.id))
    )).scalar() or 0)
