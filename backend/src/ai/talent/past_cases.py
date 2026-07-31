"""talent/past_cases.py — the exam, read (D8 E4).

The Talent Office's second large structure. Its whole idea is that a
candidate is not read off a CV but watched handling work whose ending is
already known, so a past case is **a real event, the records it turned on,
and what actually happened next**. All three ship:

* the event is a ``signals`` row that was consumed
  (``consumed_by_run_id`` is set — work that arrived and was picked up);
* the records are its ``object_refs``, resolved against the tenant plane;
* what happened is the consuming ``execution_runs`` row, who ran it, and
  the ``human_approvals`` the owner answered on it.

**What ``replayable`` may claim.** The flag is not a judgement about the
case; it is TWIN's own two constraints evaluated at their most generous
setting, which is what makes a "no" a fact rather than an opinion:

1. ``twin.replay.select_signals`` picks the signals inside a scenario's
   window, and ``Scope.validate`` refuses a window longer than
   ``TWIN_MAX_WINDOW_DAYS``. A case older than that cap cannot be selected
   by *any* legal scope.
2. ``twin.materialise`` copies only records whose ``updated_at`` falls
   inside the same window, so a record last touched before the cap would
   not be in the glass room at all.
3. ``twin.materialise`` refuses outright on the container backend, which
   makes every case unreplayable on such a deployment.

Anything the checks cannot see is reported as **unknown, not as false** —
a ref that names no record in the tenant plane leaves the question open
rather than answered, and ``unknown_because`` says so. This mirrors the
grade vocabulary the surface already uses, where ``untested`` ("never
tried") and ``unknown`` ("ran, and could not be graded") are deliberately
not synonyms.

The prose the surface renders around a case — what was in front of whoever
held it, what they did about it, who the counterparty was — is **not** here
and is listed in :data:`PAST_CASE_ABSENT`. Nothing writes those sentences,
and composing them from a payload blob would put a generated summary where
the surface promises a record.

Company-scoped by the caller, from the session (D5 §2.2).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.orm.entity import HierarchicalEntity
from src.ai.orm.execution import ExecutionRun, HumanApproval
from src.ai.signals.models import Signal
from src.ai.tenant_schema.data_plane import tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef, TenantRecord
from src.common.config import settings

__all__ = [
    "MAX_CASES",
    "PAST_CASE_ABSENT",
    "REPLAYABLE_MEANS",
    "REF_PREFIXES",
    "parse_object_ref",
    "replay_verdict",
    "past_cases_view",
]

#: Ceiling on the list. The exam is a handful of cases an owner reads, not
#: a signal log; the router's ``limit`` is bounded by this.
MAX_CASES = 100

#: Ref prefixes the platform actually writes (``learning``, ``evolution``,
#: ``strategy``…). A prefixed ref names something outside the tenant record
#: plane, so it is reported and never counted against materialisation.
REF_PREFIXES: tuple[str, ...] = ("entity", "user", "object", "execution_run")

#: What the flag promises, rendered wherever the flag is. Stated as a
#: constant for the reason ``twin.grading.GRADE_DESCRIPTIONS`` is: a claim
#: that lives only in a design document is a claim the surface will
#: eventually overstate.
REPLAYABLE_MEANS = (
    "Replayable means the twin could select this case and materialise the "
    "records it names: the event is inside the longest window a scenario "
    "scope may ask for, and the records it turned on were touched inside "
    "that window. It does not mean a candidate has answered it, and it "
    "does not promise a replay would reach the same result — the same "
    "inputs through the same model do not produce the same words twice."
)

#: **What the surface asks of a past case and the platform does not hold.**
#: Structural, so it is the same for every tenant and is returned on every
#: response: the region renders a stated absence instead of a blank.
PAST_CASE_ABSENT: tuple[dict[str, str], ...] = (
    {
        "field": "what",
        "why": (
            "What was in front of whoever held the case, in prose. The "
            "signal carries a type and a payload written by whatever "
            "produced it; no store holds a written account of the "
            "situation, and one composed here would be a generated summary "
            "standing where the surface promises a record."
        ),
    },
    {
        "field": "actually",
        "why": (
            "What actually happened, in prose. The structured answer is "
            "returned as `outcome` — the run, its status, who held it and "
            "the approvals the owner answered. The sentence that narrates "
            "them is written nowhere."
        ),
    },
    {
        "field": "party",
        "why": (
            "The counterparty the case was with. A record's fields are "
            "per-tenant, so no field is known to name a party; the records "
            "themselves are returned by def and id instead."
        ),
    },
    {
        "field": "answers",
        "why": (
            "The candidate's attempt, its verdict and its trace. The "
            "interview is a scoped twin session against these cases and no "
            "such session is run anywhere: `twin_runs` holds scenario runs, "
            "which are not per-candidate-per-case, and nothing joins a "
            "candidate to a case."
        ),
    },
    {
        "field": "brief_relevance",
        "why": (
            "Which of these cases belong to a given brief. A brief is a "
            "`capability_build` delegation and names no signal types, "
            "records or district, so the cases returned are the tenant's "
            "own recent handled work rather than a set selected for a role."
        ),
    },
)


def parse_object_ref(ref: str) -> dict[str, Any]:
    """One ``signals.object_refs`` entry, read for what it names.

    The vocabulary is loose by history — producers write either a bare
    record id or a ``kind:id`` pair — so this reports which it got rather
    than forcing one reading. A ``record_id`` is returned only for a bare
    UUID, which is the form every tenant-record producer writes.
    """
    text = ref.strip()
    kind, _, rest = text.partition(":")
    if rest and kind in REF_PREFIXES:
        return {"ref": text, "kind": kind, "record_id": None}
    try:
        return {"ref": text, "kind": None, "record_id": str(uuid.UUID(text))}
    except ValueError:
        # Neither a known prefix nor an id. Reported as-is: a ref we cannot
        # read is a fact about the producer, not something to drop.
        return {"ref": text, "kind": None, "record_id": None}


def _age_days(at: datetime, now: datetime) -> int:
    return max(0, (now - at).days)


def replay_verdict(
    *,
    signal_at: datetime,
    records: list[dict[str, Any]],
    unresolved: int,
    now: datetime,
    backend: str,
    max_window_days: int,
) -> dict[str, Any]:
    """Can this case be put to a candidate at all?

    Pure, and the whole of the honesty claim. ``records`` are the resolved
    tenant records the case names, each with an ``updated_at`` and a
    ``label``; ``unresolved`` counts the refs that looked like record ids
    and matched nothing.

    Three states, deliberately: ``True``, ``False`` with a reason, and
    ``None`` with a different reason. A check that cannot see something
    must not report it as a refusal — that would make the platform's own
    blind spot look like a property of the tenant's history.
    """
    if backend == "container":
        return {
            "replayable": False,
            "blocked_because": (
                "Twin materialisation is implemented for the schema "
                "backend; on the container backend it refuses outright, so "
                "no past case can be put to a candidate on this deployment."
            ),
            "unknown_because": None,
        }

    age = _age_days(signal_at, now)
    if age > max_window_days:
        return {
            "replayable": False,
            "blocked_because": (
                f"The twin replays the events inside a scenario's window "
                f"and refuses a window longer than {max_window_days} days. "
                f"This case arrived {age} days ago, so no scope the "
                f"Glasshouse will accept can select it."
            ),
            "unknown_because": None,
        }

    for record in records:
        updated_at = record.get("updated_at")
        if not isinstance(updated_at, datetime):
            continue
        record_age = _age_days(updated_at, now)
        if record_age > max_window_days:
            return {
                "replayable": False,
                "blocked_because": (
                    f"The twin copies only records touched inside the "
                    f"scenario's window, capped at {max_window_days} days. "
                    f"{record.get('label')} was last touched "
                    f"{record_age} days ago, so the record this case turned "
                    f"on would not be in the glass room."
                ),
                "unknown_because": None,
            }

    if unresolved:
        return {
            "replayable": None,
            "blocked_because": None,
            "unknown_because": (
                f"{unresolved} of the records this case names could not be "
                f"found in this company's records, so whether the twin "
                f"would have them cannot be determined."
            ),
        }

    return {"replayable": True, "blocked_because": None, "unknown_because": None}


async def _resolve_records(
    company_id: uuid.UUID, record_ids: set[str],
) -> dict[str, dict[str, Any]]:
    """The tenant records a set of refs name, by def and last touch.

    A separate session because records are tenant-DB and everything else
    here is control-plane; one transaction never spans both (HANDOFF §5).
    ORM only — raw SQL would name a schema the translate map has not
    rewritten (the STRAT T6 lesson).
    """
    if not record_ids:
        return {}
    ids = [uuid.UUID(value) for value in sorted(record_ids)]
    out: dict[str, dict[str, Any]] = {}
    async with tenant_data_plane.session(company_id) as ts:
        rows = (
            await ts.execute(
                select(
                    TenantRecord.id,
                    TenantEntityDef.name,
                    TenantRecord.updated_at,
                    TenantRecord.deleted_at,
                )
                .join(
                    TenantEntityDef,
                    TenantEntityDef.id == TenantRecord.entity_def_id)
                .where(
                    TenantRecord.company_id == company_id,
                    TenantRecord.id.in_(ids)))
        ).all()
    for row in rows:
        record_id = str(row[0])
        def_name = str(row[1])
        out[record_id] = {
            "record_id": record_id,
            "def": def_name,
            # The label rule the tray already uses: a def plus the head of
            # the id, which is what an operator matches a row on. Never a
            # field guessed out of the document.
            "label": f"{def_name} {record_id[:8]}",
            "updated_at": row[2],
            "deleted": row[3] is not None,
        }
    return out


def _record_block(record: dict[str, Any]) -> dict[str, Any]:
    """The resolved record as it goes over the wire."""
    updated_at = record.get("updated_at")
    return {
        "record_id": record["record_id"],
        "def": record["def"],
        "label": record["label"],
        "updated_at": (
            updated_at.isoformat() if isinstance(updated_at, datetime) else None),
        "deleted": record["deleted"],
    }


async def past_cases_view(
    db: AsyncSession, company_id: uuid.UUID, *,
    limit: int = 20, now: datetime | None = None,
) -> dict[str, Any]:
    """This company's handled work, newest first, with what is missing.

    Every query that *can* filter on ``company_id`` does — including the
    lookups by an id read from another row, because an id is still an id
    and the tenant filter is what makes the scoping unarguable. The one
    that cannot is ``human_approvals``, which carries no company of its
    own; it is filtered by run id, and those run ids came out of a
    company-scoped select, so the scope is inherited rather than assumed.
    """
    at = now or datetime.utcnow()
    limit = max(1, min(limit, MAX_CASES))

    signals = (
        await db.execute(
            select(Signal)
            .where(
                Signal.company_id == company_id,
                Signal.consumed_by_run_id.is_not(None),
            )
            .order_by(Signal.created_at.desc())
            .limit(limit))
    ).scalars().all()

    run_ids = [
        s.consumed_by_run_id for s in signals if s.consumed_by_run_id is not None]
    runs: dict[uuid.UUID, ExecutionRun] = {}
    entities: dict[uuid.UUID, HierarchicalEntity] = {}
    approvals: dict[uuid.UUID, list[HumanApproval]] = {}
    if run_ids:
        found = (
            await db.execute(
                select(ExecutionRun).where(
                    ExecutionRun.company_id == company_id,
                    ExecutionRun.id.in_(run_ids)))
        ).scalars().all()
        runs = {uuid.UUID(str(r.id)): r for r in found}

        entity_ids = {uuid.UUID(str(r.entity_id)) for r in found}
        if entity_ids:
            rows = (
                await db.execute(
                    select(HierarchicalEntity).where(
                        HierarchicalEntity.company_id == company_id,
                        HierarchicalEntity.id.in_(sorted(entity_ids))))
            ).scalars().all()
            entities = {uuid.UUID(str(e.id)): e for e in rows}

        approval_rows = (
            await db.execute(
                select(HumanApproval)
                .where(HumanApproval.run_id.in_(sorted(runs)))
                .order_by(HumanApproval.requested_at.asc()))
        ).scalars().all()
        for approval in approval_rows:
            approvals.setdefault(
                uuid.UUID(str(approval.run_id)), []).append(approval)

    # Resolve every bare-UUID ref in one tenant-plane read rather than one
    # per case: the exam is a page of cases, and a query each would make
    # the honest answer the expensive one.
    parsed: dict[uuid.UUID, list[dict[str, Any]]] = {}
    wanted: set[str] = set()
    for signal in signals:
        refs = signal.object_refs if isinstance(signal.object_refs, list) else []
        entries = [parse_object_ref(str(ref)) for ref in refs]
        parsed[uuid.UUID(str(signal.id))] = entries
        wanted.update(
            str(e["record_id"]) for e in entries if e["record_id"] is not None)
    resolved = await _resolve_records(company_id, wanted)

    cases: list[dict[str, Any]] = []
    for signal in signals:
        signal_id = uuid.UUID(str(signal.id))
        entries = parsed[signal_id]
        records = [
            resolved[str(e["record_id"])]
            for e in entries
            if e["record_id"] is not None and str(e["record_id"]) in resolved
        ]
        unresolved = [
            e for e in entries
            if e["record_id"] is not None and str(e["record_id"]) not in resolved
        ]

        run = (
            runs.get(uuid.UUID(str(signal.consumed_by_run_id)))
            if signal.consumed_by_run_id is not None else None)
        outcome: dict[str, Any] | None = None
        if run is not None:
            entity = entities.get(uuid.UUID(str(run.entity_id)))
            outcome = {
                "run_id": str(run.id),
                "status": run.status,
                "completed_at": (
                    run.completed_at.isoformat() if run.completed_at else None),
                "handled_by": (
                    {
                        "entity_id": str(entity.id),
                        "name": entity.display_name or entity.name,
                        # AGENT, PROCESS…: whoever held it, unfiltered. The
                        # surface's question is "work a candidate would have
                        # handled", and no rule ships that says which of a
                        # tenant's entities a given role would have replaced.
                        "type": entity.type,
                    } if entity is not None else None),
                "approvals": [
                    {
                        "approval_id": str(a.id),
                        "checkpoint_key": a.checkpoint_key,
                        "checkpoint_trigger": a.checkpoint_trigger,
                        "status": a.status,
                        "responded_at": (
                            a.responded_at.isoformat() if a.responded_at else None),
                    }
                    for a in approvals.get(uuid.UUID(str(run.id)), [])
                ],
            }

        case: dict[str, Any] = {
            "case_id": str(signal.id),
            "signal_type": signal.type,
            "when": signal.created_at.isoformat(),
            "source": signal.source,
            "trust": signal.trust,
            "urgency": signal.urgency,
            "records": [_record_block(r) for r in records],
            "unresolved_refs": [str(e["ref"]) for e in unresolved],
            "other_refs": [
                {"ref": str(e["ref"]), "kind": e["kind"]}
                for e in entries if e["record_id"] is None
            ],
            "outcome": outcome,
        }
        case.update(replay_verdict(
            signal_at=signal.created_at,
            records=records,
            unresolved=len(unresolved),
            now=at,
            backend=tenant_data_plane.backend,
            max_window_days=settings.TWIN_MAX_WINDOW_DAYS,
        ))
        cases.append(case)

    return {
        "as_of": at.isoformat(),
        "cases": cases,
        "replayable_means": REPLAYABLE_MEANS,
        "max_window_days": settings.TWIN_MAX_WINDOW_DAYS,
        "absent": [dict(a) for a in PAST_CASE_ABSENT],
    }
