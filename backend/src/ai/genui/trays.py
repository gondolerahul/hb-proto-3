"""genui/trays.py — the tray as a composed object (VG-04, D5 §4).

Spec §6.1's order, composed from shipped data: what happened → the
recommendation → the paths with their costs → the certified block → the SLA.
The prose fields come from the **gate's own snapshot** (its ``reason``, its
``category``, its ``amount``) — user input never describes the act it asks
to authorise, and nothing here is generated.

Three honest absences, composed as ``null`` rather than invented (the D5
§4.1 rule — a fabricated consequence on a certified surface is the one field
a human cannot check):

* **``recommendation`` is null.** Nothing on the platform writes one today —
  a recommendation is Pragya's, and her tray-delivery path is STEWARD's
  work. The shape is contracted now so the renderer knows where it will go.
* **``paths[].cost`` prefers the act's own amount.** The approve path of a
  payment costs the payment; that is the gate's number, not an estimate.
  Where the gate carries no amount, DRIVER D2's estimator may supply an
  **observed median** (``genui/cost.py`` — labeled as observed, floored at
  five observations, company-scoped); below the floor the cost stays
  ``null`` and the renderer shows no line. The two bases are never summed.
* **``currency`` is null.** The gate's snapshot records a bare amount; the
  platform does not stamp a currency on it yet. A guessed "INR" would be
  wrong for exactly the tenants least able to notice.

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


def compose_tray(
    *,
    approval: HumanApproval,
    prepared_by: tuple[uuid.UUID, str] | None,
    sla_seconds: int | None,
    on_timeout: str | None,
    now: datetime,
    observed_cost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One tray, in spec §6.1's field order.

    ``observed_cost`` is D2's estimate for this approval's checkpoint. It
    fills the approve path ONLY when the gate carries no amount of its own
    — the gate's number always wins, and the two are never summed.
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
        "what_happened": {"sentence": sentence, "object": None},
        "recommendation": None,
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


async def tray_list(
    db: AsyncSession, company_id: uuid.UUID, *, now: datetime | None = None,
) -> list[dict[str, Any]]:
    now = now or datetime.utcnow()
    slas = await _sla_map(db)
    trays: list[dict[str, Any]] = []
    for approval, entity_id, entity_name in await _pending_with_entities(db, company_id):
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
    return compose_tray(
        approval=approval,
        prepared_by=(entity_id, entity_name),
        sla_seconds=sla_seconds,
        on_timeout=on_timeout,
        now=now,
        observed_cost=observed,
    )
