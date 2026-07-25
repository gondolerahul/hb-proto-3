"""learning/outcomes.py — what a finished run taught, if anything (LEARN T5).

Charter decision 3 says reuse: a tenant learning *event* is a signal, and a
distilled tenant learning is an Intelligence-tree rule. So this module adds no
store. It adds a **second producer of candidate rules** beside the shipped one
(`core/reflector.persist`, which distils from a run's own reflection) — and the
lifecycle those candidates then live under, `memory/rule_lifecycle.py`'s
`candidate → confirmed → retired`, is untouched.

Two properties are deliberate.

**Silence is the default.** `classify_outcome` returns ``None`` for a run that
graded nothing — no CSAT, no approval decided, a clean completion. Emitting a
learning event per run would fill the bus with rows that teach nothing and make
the ones that do teach something harder to find. A learning store whose signal
is mostly noise is a learning store nobody queries.

**Provenance is recorded, because there are now two producers.** Candidates
written here carry ``kind="outcome_candidate"``; the reflector's carry
``kind="reflection_candidate"``. The design named this as a risk (§12): if the
two disagree the lifecycle resolves it by corroboration, which is right, but a
debugger asking *which loop taught the agent this* needs the answer stored, not
inferred.

Design: docs/product-road-map/increment-6/01_learn.md §5.
"""
from __future__ import annotations

import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "CandidateRule",
    "Outcome",
    "OutcomeKind",
    "OBSERVATIONS_BEFORE_CANDIDATE",
    "classify_outcome",
    "distil",
    "record_outcome",
    "write_candidate",
]


class OutcomeKind(str, Enum):
    """The gradeable endings. Anything else is not evidence."""

    CSAT_POSITIVE = "csat_positive"
    CSAT_NEGATIVE = "csat_negative"
    APPROVAL_REJECTED = "approval_rejected"
    RUN_FAILED = "run_failed"


#: A candidate needs corroboration before it is worth an agent's prompt budget.
#: Matches ``rule_lifecycle.PROMOTE_AFTER`` deliberately: the same amount of
#: evidence that promotes a candidate to confirmed is what creates it in the
#: first place, so a rule reaching prompts has been seen six times, not three.
OBSERVATIONS_BEFORE_CANDIDATE = 3


@dataclass(frozen=True)
class Outcome:
    """One gradeable ending, attributed to the entity that produced it."""

    entity_id: uuid.UUID
    run_id: uuid.UUID
    kind: OutcomeKind
    detail: str = ""


@dataclass(frozen=True)
class CandidateRule:
    """A proposed tenant learning, before the lifecycle has any opinion of it."""

    entity_id: uuid.UUID
    kind: OutcomeKind
    observations: int
    statement: str


def classify_outcome(
    *,
    entity_id: uuid.UUID,
    run_id: uuid.UUID,
    status: str | None,
    csat_score: int | None,
    approval_statuses: Sequence[str] = (),
) -> Outcome | None:
    """Grade a finished run, or decline to.

    Order matters: an explicit human judgement outranks an inferred one. A run
    a person rated is graded by that rating; a run nobody rated but whose card
    was rejected is graded by the rejection; a failure is the weakest evidence
    because it is often about the world rather than about the agent.

    Returns ``None`` when the run graded nothing — see the module docstring on
    why that is the common case and should stay so.
    """
    if csat_score is not None and csat_score != 0:
        return Outcome(
            entity_id=entity_id, run_id=run_id,
            kind=OutcomeKind.CSAT_POSITIVE if csat_score > 0 else OutcomeKind.CSAT_NEGATIVE,
            detail=f"csat={csat_score}")

    if any(s and s.upper() == "REJECTED" for s in approval_statuses):
        return Outcome(entity_id=entity_id, run_id=run_id,
                       kind=OutcomeKind.APPROVAL_REJECTED,
                       detail="a human rejected the proposed act")

    if status and status.upper() == "FAILED":
        return Outcome(entity_id=entity_id, run_id=run_id,
                       kind=OutcomeKind.RUN_FAILED, detail="run failed")

    return None


#: What each repeated outcome says, in the words the rule will carry. Kept as
#: data rather than f-strings at the call site so the whole vocabulary of things
#: this loop can propose is readable in one place — and so it is obvious that
#: none of them touch governance (§7: a tuning proposal may never widen
#: authority; the refusal for that lands in T6, but the vocabulary here already
#: cannot express one).
_STATEMENTS: dict[OutcomeKind, str] = {
    OutcomeKind.CSAT_NEGATIVE: (
        "Recent work from this colleague has been rated poorly {n} times. "
        "Check the goal statement against what the owner actually asked for."
    ),
    OutcomeKind.APPROVAL_REJECTED: (
        "{n} proposed acts were rejected at the approval card. The proposal "
        "is reaching the human in a shape they do not want to authorise."
    ),
    OutcomeKind.RUN_FAILED: (
        "{n} runs failed. Treat the current approach as unreliable until a "
        "cause is identified."
    ),
    OutcomeKind.CSAT_POSITIVE: (
        "Recent work from this colleague has been rated well {n} times. "
        "Whatever the current approach is, keep it."
    ),
}


def distil(
    outcomes: Iterable[Outcome], *, threshold: int = OBSERVATIONS_BEFORE_CANDIDATE,
) -> list[CandidateRule]:
    """Turn repeated outcomes into candidate rules. Pure.

    One bad run is a bad day; three is a pattern. Below the threshold nothing is
    proposed at all — a learning loop that reacts to a single observation is a
    loop that oscillates, and an agent whose charter changes every time a user
    is briefly unhappy is worse than one that never learns.
    """
    counts: Counter[tuple[uuid.UUID, OutcomeKind]] = Counter(
        (o.entity_id, o.kind) for o in outcomes)

    return [
        CandidateRule(
            entity_id=entity_id,
            kind=kind,
            observations=count,
            statement=_STATEMENTS[kind].format(n=count),
        )
        for (entity_id, kind), count in sorted(
            counts.items(), key=lambda kv: (str(kv[0][0]), kv[0][1].value))
        if count >= threshold
    ]


async def record_outcome(
    db: AsyncSession, *, company_id: uuid.UUID, outcome: Outcome,
) -> uuid.UUID | None:
    """Emit ``learning.outcome_observed``. The caller commits.

    Deduped on the run: a run has one ending, and a re-processed run must not
    count twice toward a candidate's threshold.
    """
    from src.ai.signals.models import SignalSource, SignalTypes
    from src.ai.signals.service import emit_signal

    return await emit_signal(
        db,
        company_id=company_id,
        source=SignalSource.TELEMETRY,
        type=SignalTypes.LEARNING_OUTCOME_OBSERVED,
        payload={
            "entity_id": str(outcome.entity_id),
            "run_id": str(outcome.run_id),
            "kind": outcome.kind.value,
            "detail": outcome.detail,
        },
        object_refs=[f"execution_run:{outcome.run_id}"],
        dedupe_key=f"learning.outcome:{outcome.run_id}",
    )


async def write_candidate(
    db: AsyncSession, *, company_id: uuid.UUID, candidate: CandidateRule,
) -> uuid.UUID | None:
    """Write a candidate rule into the entity's Intelligence tree.

    Follows ``core/reflector.persist`` exactly — same tree, same Strategies
    section, same ``source_ref.status = "candidate"`` that
    ``rule_lifecycle.filter_for_prompt`` reads. The only difference is ``kind``,
    which is the provenance the module docstring explains.

    **Scope first, then write.** The entity id arrives in a signal payload, and
    ``get_or_create_intelligence_tree`` will happily *create* a tree for an id
    that does not exist — so a malformed or foreign id would mint an orphan
    tree attributed to this company. The reflector never needed this check
    because it is called with the running entity's own id; a loop reading
    payloads does. Same lesson as VG-05: load the object through its company
    join before acting on it.

    Returns the node id, or ``None`` when the entity is not this company's or
    the tree has no Strategies section to hang a rule from. Failing quietly is
    right here: a learning loop must never break the work it is learning from.
    """
    try:
        from src.ai.orm.entity import HierarchicalEntity

        owned = (await db.execute(
            select(HierarchicalEntity.id).where(
                HierarchicalEntity.id == candidate.entity_id,
                HierarchicalEntity.company_id == company_id,
            )
        )).scalar_one_or_none()
        if owned is None:
            logger.debug("learning: candidate for unknown entity %s in company %s",
                         candidate.entity_id, company_id)
            return None

        from src.ai.memory.cortex_models import (
            CortexNode,
            CortexNodeStatus,
            CortexNodeType,
        )
        from src.ai.memory.intelligence_tree_service import (
            STRATEGIES_TITLE,
            IntelligenceTreeService,
        )

        svc = IntelligenceTreeService(db, company_id)
        tree = await svc.get_or_create_intelligence_tree(candidate.entity_id)
        section = (await db.execute(
            select(CortexNode).where(
                CortexNode.tree_id == tree.id,
                CortexNode.parent_id == tree.root_node_id,
                CortexNode.title == STRATEGIES_TITLE,
            )
        )).scalar_one_or_none()
        if section is None:
            return None

        node_id = uuid.uuid4()
        node = CortexNode(
            id=node_id, tree_id=tree.id, parent_id=section.id,
            node_type=CortexNodeType.STRATEGY,
            title=f"Candidate: {candidate.kind.value} ×{candidate.observations}",
            summary=candidate.statement[:300],
            content=candidate.statement,
            status=CortexNodeStatus.ACTIVE,
            depth=section.depth + 1,
            sibling_order=0,
            source_ref={
                "status": "candidate",
                # The provenance that distinguishes this producer from the
                # reflector's — see the module docstring.
                "kind": "outcome_candidate",
                "outcome_kind": candidate.kind.value,
                "observations": candidate.observations,
            },
            metadata_extra={
                "kind": "outcome_candidate",
                "observations": candidate.observations,
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        db.add(node)
        tree.total_nodes = (tree.total_nodes or 0) + 1
        return node_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("learning: could not write candidate for entity %s: %s",
                       candidate.entity_id, exc)
        return None


async def observed_outcomes(
    db: AsyncSession, company_id: uuid.UUID, *, since: datetime | None = None,
) -> list[Outcome]:
    """Read back the ``learning.outcome_observed`` signals as outcomes.

    The bus **is** the store (charter decision 3), so distillation reads the
    signals rather than re-deriving from runs — which also means a replayed or
    manually emitted observation counts exactly once, through the same dedupe.
    """
    from src.ai.signals.models import Signal, SignalTypes

    query = select(Signal).where(
        Signal.company_id == company_id,
        Signal.type == SignalTypes.LEARNING_OUTCOME_OBSERVED,
    )
    if since is not None:
        query = query.where(Signal.created_at >= since)

    out: list[Outcome] = []
    for signal in (await db.execute(query)).scalars().all():
        payload: dict[str, Any] = signal.payload or {}
        try:
            out.append(Outcome(
                entity_id=uuid.UUID(str(payload["entity_id"])),
                run_id=uuid.UUID(str(payload["run_id"])),
                kind=OutcomeKind(str(payload["kind"])),
                detail=str(payload.get("detail") or ""),
            ))
        except (KeyError, ValueError):
            # A malformed payload is a producer bug; it must not stop the rest
            # of the tenant's learning from being distilled.
            logger.debug("learning: skipping malformed outcome payload %s", signal.id)
    return out
