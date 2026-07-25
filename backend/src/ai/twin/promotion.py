"""twin/promotion.py — getting a good result out of the glass room (TWIN T10).

Ratified spec §134: *diff → certified approval → Board build → canary → GA.*

======================= ==========================================
Diff                     SEGA's ``entity_versions`` (two snapshots)
**Certified approval**   ``inward_auth/guard.py`` — T2, the same
                         ceremony as an autonomy raise
Board build              the shipped Meta-Agent board
**Canary**               **SEGA's** ``evolution/entity_canary.py``
GA                       SEGA's promote path
======================= ==========================================

**TWIN owns no canary** (decision 5). It calls SEGA's. Building a second one
inside TWIN would duplicate B11's blast-radius logic in the one place it must
not be duplicated — a limit enforced in two places is a limit enforced in
neither, because the next change only updates one of them.

**A Glasshouse result is an argument, never an authorisation.** TWIN
contributes *evidence* — which scenario, which grade, which metrics — and
carries it onto the approval card. It contributes no new gate. That is the
whole of this module's discipline: :func:`evidence_for` builds a payload, and
:func:`propose_promotion` refuses on its own account only when the evidence is
too weak to put in front of a human.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.twin.grading import Grade

__all__ = ["PromotionEvidence", "EvidenceTooWeak", "evidence_for", "propose_promotion"]


class EvidenceTooWeak(ValueError):
    """The scenario does not support the change it is being used to argue for."""


@dataclass(frozen=True)
class PromotionEvidence:
    """What the approval card shows the human deciding.

    The grade is on the card, prominently, because a T2 ceremony asks someone
    to accept a change on this evidence — and evidence graded `unknown` is an
    illustration, not a result. Hiding the grade behind a number would make the
    ceremony worse than no ceremony, since it would launder a guess as proof.
    """

    scenario_id: uuid.UUID
    run_id: uuid.UUID
    grade: str
    method: Optional[str]
    metrics: dict[str, Any]
    entity_version_id: Optional[uuid.UUID]
    baseline_run_id: Optional[uuid.UUID]

    def as_card(self) -> dict[str, Any]:
        from src.ai.twin.grading import GRADE_DESCRIPTIONS

        return {
            "source": "glasshouse",
            "scenario_id": str(self.scenario_id),
            "run_id": str(self.run_id),
            "grade": self.grade,
            # Rendered, not just stored: the surface must not be able to show
            # the number without the caveat.
            "grade_means": GRADE_DESCRIPTIONS.get(self.grade, ""),
            "method": self.method,
            "metrics": self.metrics,
            "entity_version_id": (
                str(self.entity_version_id) if self.entity_version_id else None),
            "baseline_run_id": (
                str(self.baseline_run_id) if self.baseline_run_id else None),
            "caveat": (
                "A Glasshouse result is an argument, not an authorisation. "
                "This card asks you to decide; the rehearsal does not decide "
                "for you."
            ),
        }


def evidence_for(run: Any, *, baseline: Any = None) -> PromotionEvidence:
    """Build the evidence payload from a completed twin run."""
    return PromotionEvidence(
        scenario_id=run.scenario_id,
        run_id=run.id,
        grade=run.grade,
        method=run.method,
        metrics=dict(run.metrics or {}),
        entity_version_id=run.entity_version_id,
        baseline_run_id=getattr(baseline, "id", None),
    )


async def propose_promotion(
    db: AsyncSession, run: Any, *, baseline: Any = None,
) -> PromotionEvidence:
    """Turn a twin run into promotion evidence, refusing weak arguments.

    Two refusals, and both are about not wasting a human's attention rather
    than about safety — the actual safety gates are the certified approval and
    SEGA's canary, neither of which this replaces:

    * a **refused** run has no result to argue from;
    * an **`unknown`**-graded run is an illustration. Putting one in front of
      an owner as though it were evidence trains them to click through the
      ceremony, which is how a gate stops working.
    """
    if getattr(run, "refusal_reason", None):
        raise EvidenceTooWeak(
            f"this scenario did not produce a result: {run.refusal_reason}")
    if run.grade == Grade.UNKNOWN:
        raise EvidenceTooWeak(
            "an `unknown`-graded run is an illustration, not evidence. There "
            "was no history to replay and no long-enough series to project "
            "from, so there is nothing here for an approver to weigh."
        )

    evidence = evidence_for(run, baseline=baseline)

    from src.ai.signals.models import SignalSource, SignalTrust, SignalTypes
    from src.ai.signals.service import emit_signal

    await emit_signal(
        db,
        company_id=run.company_id,
        source=SignalSource.AGENT,
        type=SignalTypes.TWIN_PROMOTION_PROPOSED,
        trust=SignalTrust.INTERNAL,
        payload=evidence.as_card(),
    )
    return evidence
