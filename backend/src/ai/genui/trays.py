"""genui/trays.py — the tray as a composed object (VG-04, D5 §4).

Spec §6.1's order, composed from shipped data: what happened → the
recommendation → the paths with their costs → the certified block → the SLA.
The prose fields come from the **gate's own snapshot** (its ``reason``, its
``category``, its ``amount``) — user input never describes the act it asks
to authorise, and nothing here is generated.

``recommendation`` is **one shape everywhere** (D8 E5): the object D5 §4.1
contracted, or ``null`` — never a bare string. It is written once at first
delivery by the watcher and persisted in ``tray_recommendations``; this
module reads those rows back, so a page reload shows the sentence the owner
was already shown instead of losing it. A tray whose recommendation could
not be written is still a tray: the field is null and the renderer shows no
line (the echo-bus rule — advice lost, never work).

Three honest absences, composed as ``null`` rather than invented (the D5
§4.1 rule — a fabricated consequence on a certified surface is the one field
a human cannot check):

* **``recommendation.why`` is null.** The writer produces one sentence and
  no separate rationale (12_steward.md §5), so there is nothing to put
  there. The key is present because the shape is the contract; a
  paraphrase of the sentence dressed up as its reasoning would not be.
* **``paths[].cost`` prefers the act's own amount.** The approve path of a
  payment costs the payment; that is the gate's number, not an estimate.
  Where the gate carries no amount, DRIVER D2's estimator may supply an
  **observed median** (``genui/cost.py`` — labeled as observed, floored at
  five observations, company-scoped); below the floor the cost stays
  ``null`` and the renderer shows no line. The two bases are never summed.
* **``currency`` is null.** The gate's snapshot records a bare amount; the
  platform does not stamp a currency on it yet. A guessed "INR" would be
  wrong for exactly the tenants least able to notice.

``what_happened.object`` is the thing the card is about, named so the reader
can click through to it (D8 E6). It is read off the gate's own snapshot —
the two gates that name a subject name it there — and otherwise it is the
**run the gate stopped**, which exists for every approval by construction.
It is not a fourth honest null: an approval always has a subject, and a
card that names none leaves the owner nowhere to go to check it.

The certified block's ``props`` must validate against the registry entry for
its component — pinned by a unit test, because the client will *reject* a
tray whose certified block does not (D4 §2), and that rejection must never
be reachable from our own composer.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.genui.cost import observed_decision_cost
from src.ai.genui.estate import sla_seconds_left
from src.ai.genui.models import TrayRecommendation
from src.ai.governance.models import HITLCheckpointDef
from src.ai.inward_auth.guard import approval_summary, intent_for_approval
from src.ai.inward_auth.tiers import classify
from src.ai.orm.entity import HierarchicalEntity
from src.ai.orm.execution import ExecutionRun, HumanApproval


def certified_block(approval_id: uuid.UUID, snapshot: Any) -> dict[str, Any]:
    """The deterministic heart of the tray (L5).

    Component selection is a rule, not a taste: an approval whose gate
    recorded an amount is a ``certified.payment``; anything else is a
    ``certified.approval``. The tier is the same §20 classification Pragya
    uses — one call site's intent, never a second copy of the rules.
    """
    snap = snapshot if isinstance(snapshot, dict) else {}
    tier = classify(intent_for_approval(snapshot)).tier
    amount = snap.get("amount")
    summary = approval_summary(snapshot)
    checkpoint_key = str(snap.get("checkpoint_key") or "")

    if snap.get("category") and amount is not None:
        component = "certified.payment@1"
        props: dict[str, Any] = {
            "approval_id": str(approval_id),
            "checkpoint_key": checkpoint_key,
            "summary": summary,
            "amount": float(amount),
            "currency": None,
            "tier": f"T{int(tier)}",
        }
    else:
        component = "certified.approval@1"
        props = {
            "approval_id": str(approval_id),
            "checkpoint_key": checkpoint_key,
            "summary": summary,
            "tier": f"T{int(tier)}",
        }

    canonical = json.dumps(
        {"type": component, "props": props}, sort_keys=True, separators=(",", ":"))
    return {
        "component": component,
        "tier": f"T{int(tier)}",
        "props": props,
        "manifest_hash": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
    }


def recommendation_block(sentence: str | None) -> dict[str, Any] | None:
    """The one shape ``recommendation`` ever takes (D8 E5).

    Three call sites used to disagree — the contract said an object, the
    REST composer hard-coded ``None``, and the watcher overwrote the field
    with a bare string on its way to the socket. A client that reads
    ``recommendation.sentence`` therefore saw prose over the socket and a
    crash-or-nothing over REST. One function, called by both.

    An empty sentence is no recommendation, not an empty one: the renderer
    shows no line rather than a blank one.
    """
    if not sentence:
        return None
    return {"sentence": sentence, "why": None}


def what_happened_object(
    snapshot: dict[str, Any],
    *,
    run_id: uuid.UUID | None,
    prepared_by: tuple[uuid.UUID, str] | None,
) -> dict[str, Any] | None:
    """The one thing this card is about (D8 E6) — pure over the gate's own
    snapshot, so nothing here costs a query or invents a label.

    Precedence is "most specific subject the gate actually named":

    1. a **twin promotion** names the colleague it would change, and the
       anchor run is that colleague's own — so ``prepared_by`` carries its
       name and the two ids agree by construction;
    2. a **cross-owner record write** names the tenant record it touched
       (``def`` + ``record_id``);
    3. otherwise the object is the **run the gate stopped**. Every approval
       has one, it is where the trace lives, and it is what a reader asking
       "what happened?" needs to open.

    ``label`` is what a human reads and is never invented: a colleague's
    own name, a record's def plus the head of its id (what an operator
    matches a row on), or whose run it was.
    """
    promotion = snapshot.get("twin_promotion")
    if isinstance(promotion, dict) and promotion.get("entity_id"):
        entity_id = str(promotion["entity_id"])
        if prepared_by is not None and str(prepared_by[0]) == entity_id:
            return {"kind": "colleague", "id": entity_id, "label": prepared_by[1]}

    record_id = snapshot.get("record_id")
    def_name = snapshot.get("def")
    if record_id and def_name:
        return {
            "kind": str(def_name),
            "id": str(record_id),
            "label": f"{def_name} {str(record_id)[:8]}",
        }

    if run_id is not None:
        return {
            "kind": "run",
            "id": str(run_id),
            "label": (
                f"{prepared_by[1]}'s run" if prepared_by is not None
                else "this run"),
        }
    return None


def compose_tray(
    *,
    approval: HumanApproval,
    prepared_by: tuple[uuid.UUID, str] | None,
    sla_seconds: int | None,
    on_timeout: str | None,
    now: datetime,
    observed_cost: dict[str, Any] | None = None,
    recommendation: str | None = None,
) -> dict[str, Any]:
    """One tray, in spec §6.1's field order.

    ``observed_cost`` is D2's estimate for this approval's checkpoint. It
    fills the approve path ONLY when the gate carries no amount of its own
    — the gate's number always wins, and the two are never summed.

    ``recommendation`` is the persisted sentence, if one was ever written.
    The composer stays a pure function over rows — it never asks the writer
    for a new one, so a re-render and a re-read can never re-bill.
    """
    snap = approval.context_snapshot if isinstance(approval.context_snapshot, dict) else {}
    # The gate's reason is the honest "what happened" — its own words at the
    # moment it stopped the run, not a retelling.
    sentence = str(snap.get("reason") or snap.get("message") or "An approval is waiting.")
    amount = snap.get("amount")
    summary = approval_summary(approval.context_snapshot)

    approve_cost: dict[str, Any] | None = None
    if amount is not None:
        approve_cost = {
            "amount": float(amount),
            "currency": None,
            "basis": "the amount itself",
        }
    elif observed_cost is not None:
        approve_cost = observed_cost

    block = certified_block(approval.id, {
        **snap, "checkpoint_key": approval.checkpoint_key})

    return {
        "tray_id": str(approval.id),
        "approval_id": str(approval.id),
        "checkpoint_key": approval.checkpoint_key,
        "what_happened": {
            "sentence": sentence,
            "object": what_happened_object(
                snap, run_id=approval.run_id, prepared_by=prepared_by),
        },
        "recommendation": recommendation_block(recommendation),
        "paths": [
            {
                "key": "approve",
                "label": "Approve",
                "consequence": f"{summary} proceeds.",
                "cost": approve_cost,
            },
            {
                "key": "decline",
                "label": "Decline",
                "consequence": f"{summary} does not happen; the run continues without it.",
                "cost": None,
            },
        ],
        "certified": block,
        "sla": {
            "seconds_left": sla_seconds_left(approval.requested_at, sla_seconds, now),
            "on_timeout": on_timeout,
        },
        "prepared_by": (
            {"entity_id": str(prepared_by[0]), "name": prepared_by[1]}
            if prepared_by is not None else None
        ),
    }


async def _pending_with_entities(
    db: AsyncSession, company_id: uuid.UUID,
    approval_id: uuid.UUID | None = None,
) -> list[tuple[HumanApproval, uuid.UUID, str]]:
    """Pending approvals through the company-scoped join (the VG-05 rule),
    each with the entity that raised it."""
    stmt = (
        select(HumanApproval, HierarchicalEntity.id, HierarchicalEntity.name,
               HierarchicalEntity.display_name)
        .join(ExecutionRun, HumanApproval.run_id == ExecutionRun.id)
        .join(HierarchicalEntity, ExecutionRun.entity_id == HierarchicalEntity.id)
        .where(
            ExecutionRun.company_id == company_id,
            HumanApproval.status == "PENDING",
        )
        .order_by(HumanApproval.requested_at)
    )
    if approval_id is not None:
        stmt = stmt.where(HumanApproval.id == approval_id)
    rows = (await db.execute(stmt)).all()
    return [
        (approval, entity_id, display_name or name)
        for approval, entity_id, name, display_name in rows
    ]


async def _sla_map(db: AsyncSession) -> dict[str, tuple[int | None, str | None]]:
    return {
        row.key: (row.sla_seconds, row.on_timeout)
        for row in (await db.execute(select(HITLCheckpointDef))).scalars()
    }


async def _recommendations(
    db: AsyncSession, company_id: uuid.UUID, approval_ids: list[uuid.UUID],
) -> dict[uuid.UUID, str]:
    """The persisted sentences for these approvals (D8 E5).

    One query for the whole list, and scoped on the company as well as the
    ids — the ids already came through the company-scoped join, so this is
    belt and braces on the one field that is Pragya's prose rather than the
    gate's.
    """
    if not approval_ids:
        return {}
    rows = (
        await db.execute(
            select(TrayRecommendation.approval_id, TrayRecommendation.sentence)
            .where(
                TrayRecommendation.company_id == company_id,
                TrayRecommendation.approval_id.in_(approval_ids),
            ))
    ).all()
    return {approval_id: sentence for approval_id, sentence in rows}


async def tray_list(
    db: AsyncSession, company_id: uuid.UUID, *, now: datetime | None = None,
) -> list[dict[str, Any]]:
    now = now or datetime.utcnow()
    slas = await _sla_map(db)
    rows = await _pending_with_entities(db, company_id)
    sentences = await _recommendations(
        db, company_id, [approval.id for approval, _, _ in rows])
    trays: list[dict[str, Any]] = []
    for approval, entity_id, entity_name in rows:
        sla_seconds, on_timeout = slas.get(approval.checkpoint_key or "", (None, None))
        snap = approval.context_snapshot if isinstance(approval.context_snapshot, dict) else {}
        observed = None
        if snap.get("amount") is None:
            observed = await observed_decision_cost(
                db, company_id, approval.checkpoint_key, now=now)
        trays.append(compose_tray(
            approval=approval,
            prepared_by=(entity_id, entity_name),
            sla_seconds=sla_seconds,
            on_timeout=on_timeout,
            now=now,
            observed_cost=observed,
            recommendation=sentences.get(approval.id),
        ))
    return trays


async def tray_detail(
    db: AsyncSession, company_id: uuid.UUID, tray_id: uuid.UUID,
    *, now: datetime | None = None,
) -> dict[str, Any] | None:
    """One tray, or None — a cross-tenant id and an unknown id answer alike."""
    now = now or datetime.utcnow()
    rows = await _pending_with_entities(db, company_id, approval_id=tray_id)
    if not rows:
        return None
    slas = await _sla_map(db)
    approval, entity_id, entity_name = rows[0]
    sla_seconds, on_timeout = slas.get(approval.checkpoint_key or "", (None, None))
    snap = approval.context_snapshot if isinstance(approval.context_snapshot, dict) else {}
    observed = None
    if snap.get("amount") is None:
        observed = await observed_decision_cost(
            db, company_id, approval.checkpoint_key, now=now)
    sentences = await _recommendations(db, company_id, [approval.id])
    return compose_tray(
        approval=approval,
        prepared_by=(entity_id, entity_name),
        sla_seconds=sla_seconds,
        on_timeout=on_timeout,
        now=now,
        observed_cost=observed,
        recommendation=sentences.get(approval.id),
    )
