"""pragya/delegation.py — dispatch, promise, report (Inc-4 PRAGYA-RT T4).

The general form of VOICE's promise-don't-complete rule. Some work cannot fit
in a conversational turn — the Architecture Board is seven sequential roles,
deep research is a fan-out of web calls, a bulk ingest is minutes of chunking.
Blocking a turn on any of them would mean the owner staring at a spinner
while a model call they cannot see runs to completion.

So the pattern, uniformly:

1. **Dispatch** the work as a normal execution run. The Board's implementation
   is untouched — Pragya starts it exactly the way a signal would.
2. **Promise** in plain words, with what and roughly how long.
3. **Report** back when it finishes, on the next turn or proactively.

One mechanism covers every long operation, so there is one place to check
"did we actually tell them?" rather than four.

**The promise is a row, not a sentence.** ``pragya_delegations`` records what
was undertaken, so a model that says "I'm building that" has committed the
platform to something checkable. Work that completed and was never reported is
the failure this design is most concerned with, and ``reported_at`` is what
makes it visible.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.orm.entity import HierarchicalEntity
from src.ai.pragya.models import DelegationStatus, PragyaDelegation
from src.ai.pragya.stages import Stage

logger = logging.getLogger(__name__)

__all__ = [
    "DelegationKind",
    "Delegation",
    "PROMISE_COPY",
    "delegate",
    "pending_for",
    "unreported_for",
    "complete",
    "fail",
    "mark_reported",
    "report_copy",
]


class DelegationKind:
    """What kinds of long work Pragya may start.

    A closed set on purpose. "Delegate anything" would make her a general
    job-submission surface, which is a much larger thing to reason about than
    an account manager who can start four known operations.
    """

    RESEARCH = "research"                 # stage 1 — deep company research
    CAPABILITY_BUILD = "capability_build"  # the Meta-Agent board
    BULK_INGEST = "bulk_ingest"           # stage 3 — connected-source pull
    ACTIVATION = "activation"             # stage 8 — bundle activation
    #: Decision 6 — work handed to one of Pragya's child entities. The generic
    #: kind: the child decides what the work *is*, so this does not enumerate
    #: capabilities that have not been designed yet.
    COLLEAGUE = "colleague"


#: What she says when starting each. Concrete about *what* and *how long*:
#: "I'll look into it" is how an owner ends up believing something happened.
PROMISE_COPY: dict[str, str] = {
    DelegationKind.RESEARCH: (
        "Let me read up on {subject} properly before I ask you anything — "
        "give me a minute or two and I'll come back with what I found."
    ),
    DelegationKind.CAPABILITY_BUILD: (
        "You don't have anything that does {subject} yet, so I'm having it "
        "built. That takes a few minutes and it gets reviewed before it goes "
        "anywhere near your data — I'll tell you when it's ready."
    ),
    DelegationKind.BULK_INGEST: (
        "I'm pulling in {subject} now. Larger sets take a few minutes; I'll "
        "let you know what I learned once it's indexed."
    ),
    DelegationKind.ACTIVATION: (
        "Setting up {subject} now — everything starts needing your approval, "
        "so nothing will act on its own. Give me a moment and I'll tell you "
        "what came up."
    ),
    DelegationKind.COLLEAGUE: (
        "I've put {subject} to a colleague who handles that. It runs in the "
        "background — I'll come back to you with what they find."
    ),
}


@dataclass(frozen=True)
class Delegation:
    """A dispatched promise, as the caller sees it."""

    id: uuid.UUID
    kind: str
    promise: str
    run_id: uuid.UUID | None = None


async def _meta_agent_entity(
    db: AsyncSession, company_id: uuid.UUID,
) -> HierarchicalEntity | None:
    """The tenant's Meta-Agent, which the board runs as."""
    return (await db.execute(
        select(HierarchicalEntity).where(
            HierarchicalEntity.company_id == company_id,
            HierarchicalEntity.name.ilike("%meta%agent%"),
        ).limit(1)
    )).scalars().first()


async def _dispatch_run(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    entity: HierarchicalEntity,
    task: str,
    context: dict[str, Any],
) -> uuid.UUID:
    """Create the run that does the work. Enqueued by the caller after commit.

    Deliberately the same shape the signal dispatcher uses — Pragya starting
    the board must be indistinguishable from a signal starting it, or the
    board grows a second entry point with different guarantees.
    """
    from src.ai.orm.execution import ExecutionRun
    from src.ai.schemas.enums import RunStatus

    run = ExecutionRun(
        company_id=company_id,
        entity_id=entity.id,
        input_data={"input": task, "channel": "pragya", **context},
        status=RunStatus.PENDING,
    )
    db.add(run)
    await db.flush()
    return uuid.UUID(str(run.id))


async def delegate(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    kind: str,
    subject: str,
    params: dict[str, Any] | None = None,
    stage: Stage | None = None,
    entity: HierarchicalEntity | None = None,
    task: str | None = None,
) -> Delegation:
    """Start long work and record the promise.

    Returns the promise text for Pragya to say. The run is left ``PENDING``
    and is enqueued by the caller *after* it commits — enqueueing inside the
    transaction races the worker, which can pick the job up before the row it
    needs is visible.
    """
    if kind not in PROMISE_COPY:
        raise ValueError(f"unknown delegation kind {kind!r}")

    run_id: uuid.UUID | None = None

    if entity is not None:
        # Decision 6: work handed to a named child entity. The child's own
        # governance applies from here — Pragya is the caller, not the actor.
        run_id = await _dispatch_run(
            db, company_id=company_id, entity=entity,
            task=task or f"Handle: {subject}",
            context={"delegation_kind": kind, "subject": subject,
                     **(params or {})})

    elif kind == DelegationKind.CAPABILITY_BUILD:
        entity = await _meta_agent_entity(db, company_id)
        if entity is None:
            # No board seeded for this tenant. Say so rather than promising
            # work that will never start — an unkept promise costs more trust
            # than an honest "I can't".
            raise ValueError("no Meta-Agent is configured for this company")
        run_id = await _dispatch_run(
            db, company_id=company_id, entity=entity,
            task=f"Build a capability for: {subject}",
            context={"delegation_kind": kind, "subject": subject,
                     **(params or {})})

    promise = PROMISE_COPY[kind].format(subject=subject)

    row = PragyaDelegation(
        company_id=company_id,
        kind=kind,
        status=DelegationStatus.PROMISED,
        promise=promise,
        params={"subject": subject, **(params or {})},
        run_id=run_id,
        stage=int(stage) if stage is not None else None,
    )
    db.add(row)
    await db.flush()

    logger.info("pragya delegated %s for company=%s (run=%s)",
                kind, company_id, run_id)
    return Delegation(id=uuid.UUID(str(row.id)), kind=kind,
                      promise=promise, run_id=run_id)


async def pending_for(
    db: AsyncSession, company_id: uuid.UUID,
) -> list[PragyaDelegation]:
    """Work still in flight — what Pragya says is 'still going' if asked."""
    return list((await db.execute(
        select(PragyaDelegation).where(
            PragyaDelegation.company_id == company_id,
            PragyaDelegation.status == DelegationStatus.PROMISED,
        ).order_by(PragyaDelegation.created_at.asc())
    )).scalars().all())


async def unreported_for(
    db: AsyncSession, company_id: uuid.UUID,
) -> list[PragyaDelegation]:
    """Finished work the owner has not been told about yet.

    Read at the top of a turn so the first thing Pragya does is close a loop
    she opened. A promise kept late still counts; a promise never mentioned
    again is what makes an assistant untrustworthy.
    """
    return list((await db.execute(
        select(PragyaDelegation).where(
            PragyaDelegation.company_id == company_id,
            PragyaDelegation.status.in_(
                [DelegationStatus.DONE, DelegationStatus.FAILED]),
            PragyaDelegation.reported_at.is_(None),
        ).order_by(PragyaDelegation.completed_at.asc())
    )).scalars().all())


async def complete(
    db: AsyncSession, delegation_id: uuid.UUID, result: dict[str, Any],
) -> PragyaDelegation | None:
    row = await db.get(PragyaDelegation, delegation_id)
    if row is None:
        return None
    row.status = DelegationStatus.DONE
    row.result = result
    row.completed_at = datetime.utcnow()
    await db.flush()
    return row


async def fail(
    db: AsyncSession, delegation_id: uuid.UUID, error: str,
) -> PragyaDelegation | None:
    row = await db.get(PragyaDelegation, delegation_id)
    if row is None:
        return None
    row.status = DelegationStatus.FAILED
    row.error = error[:2000]
    row.completed_at = datetime.utcnow()
    await db.flush()
    return row


async def mark_reported(
    db: AsyncSession, rows: list[PragyaDelegation],
) -> None:
    now = datetime.utcnow()
    for row in rows:
        row.reported_at = now
        row.status = DelegationStatus.REPORTED
    await db.flush()


def report_copy(row: PragyaDelegation) -> str:
    """How Pragya closes the loop she opened.

    A failure is reported as plainly as a success. Quietly dropping work that
    did not pan out is how an owner discovers weeks later that the thing they
    were told was underway never happened.
    """
    subject = (row.params or {}).get("subject", "that")

    if row.status == DelegationStatus.FAILED:
        return (f"That {subject} work I started didn't come off — {row.error}. "
                f"Want me to try again, or take a different route?")

    result = row.result or {}
    summary = result.get("summary")
    if summary:
        return f"Update on {subject}: {summary}"
    return f"That {subject} work I started is done."
