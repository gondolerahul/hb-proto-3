"""learning/tuning.py — charter tuning, and the four things it may never touch.

LEARN proposes; **SEGA disposes**. This module can emit a
``learning.charter_tuning_proposed`` signal and nothing else — it holds no
reference to any entity-mutation path, and an import-boundary test
(``test_learning_tuning.py``) makes adding one a build failure. Every entity
change goes through SEGA's version ledger, canary and blast-radius limits, or
it does not happen.

**The refusal lives at proposal time, not at review time** (design §7). A
proposal that would widen authority is never *created*, so it never reaches a
reviewer who might approve it while tired. Refusal at proposal cannot be worn
down; refusal at review can.

What that guards against is B10's reward-hacking half. The register asks which
wins when a KPI and the Karuna empathy floor disagree, and the answer must not
be a policy sentence — a policy sentence is a thing a learning loop can
optimise around. So:

* the proposal *vocabulary* is fixed data (``outcomes._STATEMENTS``), so a
  generated proposal cannot phrase a governance change;
* the proposal *field* must be on a two-item allow-list, so a hand-built one
  cannot address a governance block;
* and KPIs never enter an agent's objective at all — asserted by a test that
  greps the whole of ``src/ai`` for a KPI key outside the registry that defines
  them and the learning package that snapshots them.

Design: docs/product-road-map/increment-6/01_learn.md §5, §7.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.learning.outcomes import CandidateRule

logger = logging.getLogger(__name__)

__all__ = [
    "ALLOWED_FIELDS",
    "REFUSED_FIELDS",
    "TuningProposal",
    "TuningRefused",
    "admit_proposal",
    "emit_proposal",
    "propose_from_candidate",
]


class TuningRefused(Exception):
    """A proposal that must not exist. Raised, never returned as a flag.

    An exception rather than a ``False`` because the caller has no correct way
    to continue: there is no "propose it anyway, marked risky" path, by design.
    """


#: The only fields a learning loop may propose a change to. Both are prose the
#: agent reads; neither confers any capability.
ALLOWED_FIELDS: frozenset[str] = frozenset({"goal", "description"})

#: Named explicitly rather than left to the allow-list's silence, because a
#: reader deserves to see *which* refusals are load-bearing and why. These are
#: the blocks that decide what an agent may do, to whom, with whose money.
REFUSED_FIELDS: dict[str, str] = {
    "governance": "autonomy bands and approval policy are never self-modified",
    "capabilities": "authority categories and SoD tags are never self-modified",
    "logic_gate": "the loop's own control flow is never self-modified",
    "identity": "the Karuna profile and system prompt are not tuning targets",
    "metadata_extensions": "gateway profiles and channel bindings live here",
}


@dataclass(frozen=True)
class TuningProposal:
    """A proposed change to an agent's prose, with the evidence behind it."""

    entity_id: uuid.UUID
    field: str
    addition: str
    evidence_observations: int
    rationale: str


def admit_proposal(proposal: TuningProposal) -> None:
    """Refuse anything that is not a prose change. Pure; raises on refusal.

    The check is on the **field**, structurally, rather than on the content of
    the change. Content inspection is pattern matching, and D3 records why the
    platform does not rely on that: a phrase list is a thing to be worded
    around. A field allow-list is not.
    """
    if proposal.field in REFUSED_FIELDS:
        raise TuningRefused(
            f"refusing to propose a change to `{proposal.field}`: "
            f"{REFUSED_FIELDS[proposal.field]}")
    if proposal.field not in ALLOWED_FIELDS:
        # Unknown fields fail closed. A block added to the entity model after
        # this module was written must be opted *in*, never inherited.
        raise TuningRefused(
            f"refusing to propose a change to `{proposal.field}`: not on the "
            f"tuning allow-list {sorted(ALLOWED_FIELDS)}")
    if not proposal.addition.strip():
        raise TuningRefused("an empty proposal is not a proposal")


def propose_from_candidate(candidate: CandidateRule) -> TuningProposal:
    """Build the one shape of proposal this loop can make.

    The text comes from ``outcomes._STATEMENTS`` via the candidate, which is
    fixed data — so the loop cannot generate a proposal whose *wording* asks
    for something the field allow-list would have refused. Belt and braces, and
    the braces are the ones that hold.
    """
    proposal = TuningProposal(
        entity_id=candidate.entity_id,
        field="goal",
        addition=candidate.statement,
        evidence_observations=candidate.observations,
        rationale=f"{candidate.observations} observations of "
                  f"{candidate.kind.value} over the observation window",
    )
    admit_proposal(proposal)      # never construct one that would be refused
    return proposal


async def emit_proposal(
    db: AsyncSession, *, company_id: uuid.UUID, proposal: TuningProposal,
) -> uuid.UUID | None:
    """Hand the proposal to SEGA over the bus. The caller commits.

    This is the *entire* outward surface of charter tuning in LEARN. There is
    no apply path here and there must never be one: an entity mutation without
    a version ledger row is a change nobody can roll back or explain.
    """
    from src.ai.signals.models import SignalSource, SignalTypes
    from src.ai.signals.service import emit_signal

    admit_proposal(proposal)      # again, at the boundary: cheap, and the
                                  # caller may have built the proposal by hand
    payload: dict[str, Any] = {
        "entity_id": str(proposal.entity_id),
        "field": proposal.field,
        "addition": proposal.addition,
        "rationale": proposal.rationale,
        "evidence_observations": proposal.evidence_observations,
    }
    return await emit_signal(
        db,
        company_id=company_id,
        source=SignalSource.TELEMETRY,
        type=SignalTypes.LEARNING_CHARTER_TUNING_PROPOSED,
        payload=payload,
        object_refs=[f"entity:{proposal.entity_id}"],
        # One live proposal per (entity, field) per evidence level: re-running
        # the harvest must not queue SEGA the same change repeatedly.
        dedupe_key=(f"learning.tuning:{proposal.entity_id}:{proposal.field}:"
                    f"{proposal.evidence_observations}"),
    )
