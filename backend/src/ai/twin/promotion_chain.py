"""twin/promotion_chain.py — the proposal reaches a human, and then SEGA
(GLASS X4, decision 3).

TWIN's ``propose_promotion`` emitted ``twin.promotion_proposed`` and
nothing consumed it. This is the consumer and the far end.

**It adds no certified act.** R5 keeps the certified set at ten: a
component is certified iff a backend endpoint calls
``enforce_tier``/``enforce_kind``. A promotion approval is a **HITL card**,
so the human approves it through ``respond_to_approval`` — already
certified endpoint #1, already gated, already rendering
``certified.approval``. GLASS ships no eleventh gate and no eleventh
component.

**The checkpoint already existed, and the fit is exact.** Checkpoint #5,
``before_self_evolving_code_promotion`` — *"Promoting self-evolved
code/instructions affecting an entity"* — is precisely this act, and it
is ``platform_mandatory``. GATE's lesson was that borrowing a
*mismatched* checkpoint mislabels the act to the approver (a payout
checkpoint made an ad campaign un-opt-out-able); it was never that a
checkpoint may not be reused where it fits. So: **no 22nd checkpoint, no
migration.**

**Applying is a sweep, not a completion hook** — the LEARN rule, and for
LEARN's reason: a hook lives at one call site and is missed by every
other path that can approve a card. The sweep finds approved promotions
that have not been applied and applies them through **SEGA's**
``apply_proposal``, where ``admit_change`` bites and B11's five limits
hold. TWIN owns no canary and GLASS does not build one.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.twin.promotion import PromotionEvidence

logger = logging.getLogger(__name__)

__all__ = [
    "PROMOTION_CHECKPOINT",
    "raise_promotion_approval",
    "apply_approved_promotions",
]

#: Checkpoint #5, unchanged since Blueprint v1 and an exact fit.
PROMOTION_CHECKPOINT = "before_self_evolving_code_promotion"


async def raise_promotion_approval(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    entity_id: uuid.UUID,
    evidence: PromotionEvidence,
    field: str,
    addition: str,
    now: Optional[datetime] = None,
) -> Any:
    """Turn promotion evidence into a card a human decides on.

    The anchor run is the entity's own — a promotion is *about* an entity,
    so the run row it hangs from is that entity's, not an arbitrary one
    borrowed from the replay. The card carries the evidence and the exact
    change, because an approver who cannot see what they are approving is
    a ceremony, not a gate.
    """
    from src.ai.orm.execution import ExecutionRun, HumanApproval
    from src.ai.schemas.enums import RunStatus

    at = now or datetime.utcnow()

    run = ExecutionRun(
        company_id=company_id,
        entity_id=entity_id,
        input_data={
            "input": "[glasshouse] promote a rehearsed change",
            "channel": "twin_promotion",
            "twin_run_id": str(evidence.run_id),
        },
        status=RunStatus.PENDING,
    )
    db.add(run)
    await db.flush()

    approval = HumanApproval(
        run_id=run.id,
        checkpoint_trigger="twin:promotion",
        checkpoint_key=PROMOTION_CHECKPOINT,
        status="PENDING",
        requested_at=at,
        context_snapshot={
            "category": "governance",
            "reason": (
                f"A rehearsal in the Glasshouse argues for this change "
                f"({evidence.grade}-graded)."
            ),
            "twin_promotion": {
                "entity_id": str(entity_id),
                "field": field,
                "addition": addition,
                "evidence": evidence.as_card(),
                "applied_version_id": None,
            },
        },
    )
    db.add(approval)
    await db.flush()
    return approval


async def apply_approved_promotions(
    db: AsyncSession, *, now: Optional[datetime] = None, limit: int = 50,
) -> dict[str, int]:
    """Apply every approved-but-unapplied promotion through SEGA.

    A **sweep**, not a completion hook (the LEARN rule): a hook lives at
    one call site and is missed by every other path that can approve a
    card — the console, Pragya, the tray, the pocket.

    Refusals are recorded on the card rather than raised: a promotion
    SEGA declines (blast radius, a suspended tenant, the daily cap) is a
    fact the owner should be able to read next to the thing they
    approved.
    """
    from src.ai.evolution.blast_radius import BlastRadiusError
    from src.ai.evolution.proposals import apply_proposal
    from src.ai.orm.execution import ExecutionRun, HumanApproval

    at = now or datetime.utcnow()
    applied = 0
    refused = 0

    rows = (await db.execute(
        select(HumanApproval, ExecutionRun.company_id)
        .join(ExecutionRun, HumanApproval.run_id == ExecutionRun.id)
        .where(
            HumanApproval.checkpoint_key == PROMOTION_CHECKPOINT,
            HumanApproval.status == "APPROVED",
        )
        .order_by(HumanApproval.responded_at)
        .limit(limit)
    )).all()

    for approval, company_id in rows:
        snapshot = approval.context_snapshot
        if not isinstance(snapshot, dict):
            continue
        promotion = snapshot.get("twin_promotion")
        if not isinstance(promotion, dict):
            continue  # an approval of some other governance act
        if promotion.get("applied_version_id") or promotion.get("refused_because"):
            continue  # already settled

        try:
            version = await apply_proposal(
                db,
                company_id=company_id,
                entity_id=uuid.UUID(str(promotion["entity_id"])),
                field=str(promotion["field"]),
                addition=str(promotion["addition"]),
                now=at,
            )
            promotion["applied_version_id"] = str(version.id)
            applied += 1
        except BlastRadiusError as refusal:
            # B11 held. Recorded where the approver will see it.
            promotion["refused_because"] = str(refusal)
            refused += 1
            logger.info("[twin] promotion refused by blast radius: %s", refusal)
        except Exception as exc:  # noqa: BLE001 — one bad card must not stop the rest
            promotion["refused_because"] = f"could not be applied: {exc}"
            refused += 1
            logger.warning(
                "[twin] promotion application failed for approval %s",
                approval.id, exc_info=True)

        # JSON columns need whole-object reassignment to be detected.
        approval.context_snapshot = {**snapshot, "twin_promotion": promotion}

    await db.commit()
    return {"applied": applied, "refused": refused}
