"""talent/brief_read.py — the hiring brief, read (D8 E4).

The Talent Office renders a **brief**: what the role is for, what it may
touch, and the conversation the owner and Pragya had to arrive at it. This
module is the half of that the platform can actually answer, and the list
of what it cannot is a deliverable of equal standing — see
:data:`BRIEF_ABSENT`.

**What a brief is, here.** The one row the shipped platform writes when an
owner asks for a capability they do not have is a
``pragya_delegations`` row of kind ``capability_build``: *"You don't have
anything that does {subject} yet, so I'm having it built"* — dispatched to
the tenant's Meta-Agent, which is the same board the surface's shortlist
comes off. That row carries the subject the owner asked for, when they
asked, Pragya's own promised sentence about it, and the board run. Those
are the brief's real fields and they are projected verbatim.

**The brief is not a conversation the platform can find.** The obvious
source — ``pragya_turns`` — cannot supply one. A turn carries
``(company_id, stage, role, content)`` and nothing else: there is no thread
id, no subject, no link to a delegation, and ``pragya_engagements`` is one
row per company by unique constraint, so the engagement is *the*
conversation rather than one per brief. Nothing marks a run of turns as a
hiring brief. Slicing turns by the timestamps around a delegation would
produce a plausible transcript of a conversation that may never have
happened, which is the one failure this module exists to avoid, so
``turns`` is absent and says why.

Company-scoped by the caller, which takes it from the session and never
from a parameter (D5 §2.2, the VG-05 rule).
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.orm.execution import ExecutionRun
from src.ai.pragya.delegation import DelegationKind
from src.ai.pragya.models import PragyaDelegation

__all__ = [
    "BRIEF_ABSENT",
    "BRIEF_KINDS",
    "MAX_BRIEFS",
    "brief_view",
]

#: The delegation kinds that are a request for a colleague the tenant does
#: not have. Only ``capability_build`` qualifies: it is the one that starts
#: the Meta-Agent board. ``colleague`` hands work to a child that already
#: exists, which is an assignment and not a hire.
BRIEF_KINDS: tuple[str, ...] = (DelegationKind.CAPABILITY_BUILD,)

#: Ceiling on the list, so one busy tenant cannot make the response the
#: whole delegation log. The router's ``limit`` is bounded by this.
MAX_BRIEFS = 100

#: **What the surface asks for and the platform does not store.** Returned
#: on every response so the region renders a stated absence rather than an
#: empty panel that reads like a loading state. Each entry is structural —
#: it is the same for every tenant, because what is missing is a table and
#: not a row.
BRIEF_ABSENT: tuple[dict[str, str], ...] = (
    {
        "field": "turns",
        "why": (
            "The brief as a conversation. `pragya_turns` is one flat "
            "per-company stream — a turn carries no thread id, no subject "
            "and no link to a delegation, and `pragya_engagements` is one "
            "row per company — so nothing marks a run of turns as this "
            "brief. Turns sliced by timestamp would be a transcript of a "
            "conversation that may never have happened."
        ),
    },
    {
        "field": "clauses",
        "why": (
            "What the role is for, its ceiling and who it reports to. "
            "Nothing persists a brief's terms: the delegation stores a "
            "subject and a promise, and the terms of engagement belong to "
            "a charter that does not exist until a colleague does."
        ),
    },
    {
        "field": "may_touch",
        "why": (
            "The records, tools and connectors the role may touch, and the "
            "ones deliberately kept back. Permissions are held on a "
            "colleague entity; a brief names a colleague that has not been "
            "hired, and no store holds a grant for one."
        ),
    },
    {
        "field": "district",
        "why": (
            "Which district and quarter the role would sit in. A "
            "delegation names no process, so the estate placement of an "
            "unhired role is not recorded anywhere."
        ),
    },
)


def _board_run(run: ExecutionRun | None) -> dict[str, Any] | None:
    """The Meta-Agent board run this brief started, where it still exists.

    The shortlist is whatever that run produced, so the run is the join the
    surface needs. Its *output* is not projected here: the board's result
    shape is the Dossier's business (E3), and guessing at candidates from a
    result blob is exactly the invention this endpoint refuses.
    """
    if run is None:
        return None
    return {
        "run_id": str(run.id),
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": (
            run.completed_at.isoformat() if run.completed_at else None),
    }


async def brief_view(
    db: AsyncSession, company_id: uuid.UUID, *, limit: int = 20,
) -> dict[str, Any]:
    """This company's hiring briefs, newest first, with what is missing.

    Every query filters on ``company_id``: a cross-tenant read is not
    expressible.
    """
    limit = max(1, min(limit, MAX_BRIEFS))
    rows = (
        await db.execute(
            select(PragyaDelegation)
            .where(
                PragyaDelegation.company_id == company_id,
                PragyaDelegation.kind.in_(list(BRIEF_KINDS)),
            )
            .order_by(PragyaDelegation.created_at.desc())
            .limit(limit))
    ).scalars().all()

    run_ids = [row.run_id for row in rows if row.run_id is not None]
    runs: dict[uuid.UUID, ExecutionRun] = {}
    if run_ids:
        # Scoped by company as well as by id: an id read from a row is still
        # an id, and the tenant filter is what makes that unarguable.
        found = (
            await db.execute(
                select(ExecutionRun).where(
                    ExecutionRun.company_id == company_id,
                    ExecutionRun.id.in_(run_ids)))
        ).scalars().all()
        runs = {uuid.UUID(str(run.id)): run for run in found}

    briefs: list[dict[str, Any]] = []
    for row in rows:
        params = row.params if isinstance(row.params, dict) else {}
        subject = params.get("subject")
        briefs.append({
            "brief_id": str(row.id),
            # What the owner asked for, in their own words as Pragya
            # recorded them. Deliberately not called `role`: a subject is
            # what was asked for, and a job title is a thing nobody wrote.
            "subject": str(subject) if subject is not None else None,
            "opened_at": row.created_at.isoformat(),
            # Pragya's own committed sentence about this brief — the only
            # part of the conversation that is attributably about it.
            "promise": row.promise,
            "status": row.status,
            "stage": row.stage,
            "board_run": _board_run(
                runs.get(row.run_id) if row.run_id is not None else None),
        })

    return {"briefs": briefs, "absent": [dict(a) for a in BRIEF_ABSENT]}
