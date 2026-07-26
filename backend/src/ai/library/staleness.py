"""library/staleness.py — whether a document is still true (LIB T4).

`staleness_state` shipped as a column in T1 and nothing ever wrote to it, so
every document read `fresh` — which was a fact about the sweep's absence rather
than about the documents. This module is the sweep.

**Three properties are deliberate.**

*Stated, never inferred silently.* Every transition also writes
`staleness_reason` in words — "no effective_from; 400 days since upload". A
flag whose basis is invisible is a flag people learn to dismiss, and the
dismissal is permanent while the flag is not.

*A fact about our knowledge, not a claim about the content.* `stale` does not
mean wrong. It means nobody has confirmed it recently, which is the only thing
an age threshold can honestly assert.

*It never withholds.* Staleness travels **with** the chunk into the retrieval
result so the answer path can say "this is from a document flagged stale".
Silently dropping a stale document would replace a slightly-wrong answer with a
confidently empty one, which is strictly worse and much harder to notice.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.library.provenance import SourceKind, StalenessState

logger = logging.getLogger(__name__)

__all__ = [
    "AGE_THRESHOLD_DAYS",
    "AGING_WINDOW_DAYS",
    "StalenessVerdict",
    "assess",
    "sweep_company",
    "sweep_all",
    "raise_contradiction",
    "clear_contradiction",
]


#: Days before a document of each kind is considered stale, measured from
#: `effective_from` where it is known and `created_at` where it is not.
#:
#: The three in the design (upload / connected_drive / conversation_derived)
#: plus `generated_artifact`, which the design omitted. A generated report
#: describes the business at the moment it was produced, so it ages like a
#: mirrored drive file rather than like an uploaded reference document —
#: 180 days.
AGE_THRESHOLD_DAYS: dict[str, int] = {
    SourceKind.UPLOAD: 365,
    SourceKind.CONNECTED_DRIVE: 180,
    SourceKind.GENERATED_ARTIFACT: 180,
    SourceKind.CONVERSATION_DERIVED: 90,
}

#: How long before the threshold a document starts reading `aging`.
AGING_WINDOW_DAYS = 30

#: Applied to a source_kind nobody has given a threshold. Deliberately the
#: most generous rather than the strictest: an unknown kind is a gap in this
#: table, and a gap in our own configuration should not accuse a tenant's
#: document of being out of date.
_DEFAULT_THRESHOLD_DAYS = 365


@dataclass(frozen=True)
class StalenessVerdict:
    """A state and the reason for it. Both, always — see the module docstring."""

    state: str
    reason: str


def assess(
    *,
    source_kind: str,
    created_at: Optional[datetime],
    effective_from: Optional[date],
    superseded_by_id: Optional[Any],
    current_state: Optional[str],
    now: Optional[date] = None,
) -> StalenessVerdict:
    """The ordered rules, pure. First one that fires wins.

    Pure so the ladder is unit-testable without a database — the same shape
    SEGA's taint ladder and GATE's category resolution take, and for the same
    reason: the interesting part is the ordering, not the SQL.
    """
    today = now or datetime.utcnow().date()

    # 1. Superseded outranks everything, including a contradiction: if a
    #    replacement exists, the argument about whether the old one is true is
    #    settled by the replacement.
    if superseded_by_id is not None:
        return StalenessVerdict(
            StalenessState.SUPERSEDED, "a newer document supersedes this one")

    # 2. Contradiction is *sticky*. LIB owns the store and the state, not a
    #    detector (§6.1) — the critics raise it. It therefore has nowhere else
    #    to live, and an age rule must not quietly clear it: a contradiction is
    #    resolved by a human or by a supersession, never by the passage of time.
    if current_state == StalenessState.CONTRADICTED:
        return StalenessVerdict(
            StalenessState.CONTRADICTED,
            "a contradiction was raised against this document and is unresolved")

    threshold = AGE_THRESHOLD_DAYS.get(source_kind, _DEFAULT_THRESHOLD_DAYS)

    if effective_from is not None:
        basis, basis_words = effective_from, "effective from"
    elif created_at is not None:
        basis, basis_words = created_at.date(), "no effective_from; created"
    else:
        # Neither date. Not an error and not stale — we know nothing about its
        # age, and `fresh` with a reason that says so is more honest than a
        # verdict invented from an absent column.
        return StalenessVerdict(
            StalenessState.FRESH, "no effective_from and no created_at; age unknown")

    age = (today - basis).days
    if age >= threshold:
        return StalenessVerdict(
            StalenessState.STALE,
            f"{basis_words} {basis.isoformat()}; {age} days old, past the "
            f"{threshold}-day {source_kind} threshold")
    if age >= threshold - AGING_WINDOW_DAYS:
        return StalenessVerdict(
            StalenessState.AGING,
            f"{basis_words} {basis.isoformat()}; {age} days old, within "
            f"{AGING_WINDOW_DAYS} days of the {threshold}-day {source_kind} threshold")
    return StalenessVerdict(
        StalenessState.FRESH,
        f"{basis_words} {basis.isoformat()}; {age} days old")


_SELECT_SQL = text("""
    SELECT id, source_kind, created_at, effective_from, superseded_by_id,
           staleness_state
    FROM documents
    WHERE company_id = CAST(:company_id AS uuid)
""")

_UPDATE_SQL = text("""
    UPDATE documents
    SET staleness_state = :state, staleness_reason = :reason
    WHERE id = :document_id
""")


async def sweep_company(
    db: AsyncSession, company_id: Any, *, now: Optional[date] = None,
) -> dict[str, Any]:
    """Re-assess every document for one tenant. Returns a per-state tally.

    Writes only where the state or the reason actually changed. The reason is
    part of that comparison on purpose: "412 days old" becoming "413 days old"
    is a real change to what the surface shows, and a sweep that only compared
    states would leave a visibly wrong number on the screen forever.
    """
    rows = (await db.execute(
        _SELECT_SQL, {"company_id": str(company_id)})).mappings().all()

    tally: dict[str, int] = {}
    changed = 0
    for row in rows:
        verdict = assess(
            source_kind=row["source_kind"] or SourceKind.UPLOAD,
            created_at=row["created_at"],
            effective_from=row["effective_from"],
            superseded_by_id=row["superseded_by_id"],
            current_state=row["staleness_state"],
            now=now,
        )
        tally[verdict.state] = tally.get(verdict.state, 0) + 1
        if row["staleness_state"] != verdict.state:
            changed += 1
        await db.execute(_UPDATE_SQL, {
            "document_id": row["id"], "state": verdict.state,
            "reason": verdict.reason[:255],
        })

    return {"documents": len(rows), "changed": changed, "states": tally}


async def sweep_all(db: AsyncSession, *, now: Optional[date] = None) -> dict[str, Any]:
    """Every tenant, one commit each — a bad tenant must not lose the others."""
    company_ids = [r[0] for r in (await db.execute(
        text("SELECT id FROM companies WHERE type = 'TENANT'"))).all()]

    totals = {"documents": 0, "changed": 0}
    failed = 0
    for company_id in company_ids:
        try:
            summary = await sweep_company(db, company_id, now=now)
            totals["documents"] += int(summary["documents"])
            totals["changed"] += int(summary["changed"])
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            failed += 1
            logger.warning("staleness sweep failed for company %s: %s", company_id, exc)
    return {**totals, "companies": len(company_ids), "failed": failed}


async def raise_contradiction(
    db: AsyncSession, company_id: Any, document_id: Any, reason: str,
) -> bool:
    """Flag a document as contradicted. Returns whether a row was flagged.

    **LIB owns the state, not the detection** (§6.1). The dreaming engine and
    the critics already read retrieved context; when two chunks assert
    incompatible facts, the run calls this. Building a contradiction detector
    inside a data-layer workstream would be the wrong place and the wrong
    scope.

    Scoped by company as well as id, so a run cannot flag another tenant's
    document — the same rule the influence read follows, for the same reason.
    """
    flagged = (await db.execute(text("""
        UPDATE documents
        SET staleness_state = :state, staleness_reason = :reason
        WHERE id = CAST(:document_id AS uuid)
          AND company_id = CAST(:company_id AS uuid)
          AND superseded_by_id IS NULL
        RETURNING id
    """), {"state": StalenessState.CONTRADICTED,
           "reason": (reason or "contradiction raised")[:255],
           "document_id": str(document_id), "company_id": str(company_id)})).all()
    return bool(flagged)


async def clear_contradiction(
    db: AsyncSession, company_id: Any, document_id: Any,
) -> bool:
    """Resolve a contradiction, returning the document to the age rules.

    The counterpart `raise_contradiction` needs in order for stickiness to be
    a state rather than a trap. Clearing sets `fresh` with a reason; the next
    sweep re-derives the real state from age within hours.
    """
    cleared = (await db.execute(text("""
        UPDATE documents
        SET staleness_state = :state, staleness_reason = :reason
        WHERE id = CAST(:document_id AS uuid)
          AND company_id = CAST(:company_id AS uuid)
          AND staleness_state = :contradicted
        RETURNING id
    """), {"state": StalenessState.FRESH,
           "reason": "contradiction resolved; awaiting the next staleness sweep",
           "contradicted": StalenessState.CONTRADICTED,
           "document_id": str(document_id), "company_id": str(company_id)})).all()
    return bool(cleared)
