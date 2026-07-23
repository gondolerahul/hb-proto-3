"""intelligence/admission.py — the model-change admission gate (EVX, §22.2 + §22.4).

A model-fleet change (a new catalog row proposed for ``active``, a version bump,
a provider swap, or — later — BabyBuddha) is admitted **only** on non-inferiority
within cost budget, and **only** after the independent-suite rule is satisfied.
Router preference can never override a failed admission: the ``active`` flip
(``RegistryService.activate``) calls this and refuses on failure — the gate lives
in the mutation path, not beside it (design §8).

The actual candidate-vs-incumbent *evaluation* (running the curated corpus
through the models) is the live/ops step, the same tested-seam discipline voice
go-live and the Zoho connector carry — tests inject the ``ModelEval`` scores. The
non-inferiority + cost logic here is pure, and it is what bites.

Design: docs/product-road-map/increment-5/04_eval_extensions.md §3, §4.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "ModelEval", "SuiteSet", "AdmissionResult", "AdmissionError",
    "non_inferior", "within_cost_budget", "require_independent_suites",
    "admit_model_change",
]

_QUALITY_TOLERANCE = 0.02   # candidate may be at most this much worse than incumbent
_COST_BUDGET_RATIO = 1.5    # candidate may cost at most this multiple of incumbent


class AdmissionError(Exception):
    """The independent-suite rule was violated — promotion is refused outright."""


@dataclass(frozen=True)
class ModelEval:
    """A model's aggregate result on the curated corpus (produced by the runner —
    live in prod, injected in tests)."""
    quality: float   # 0..1 aggregate quality
    cost: float      # projected per-unit cost (same unit for candidate + incumbent)


@dataclass(frozen=True)
class SuiteSet:
    """Which suites backed this promotion (§22.2). ``incumbent_golden`` is captured
    from the *current* version before the change; ``platform_curated`` is human-
    seeded. Self-generated tests are additional coverage, never the gate."""
    incumbent_golden: bool
    platform_curated: bool
    self_generated: bool = False
    red_teamed: bool = False


@dataclass(frozen=True)
class AdmissionResult:
    admitted: bool
    quality_ok: bool
    cost_ok: bool
    reason: str


def non_inferior(candidate_quality: float, incumbent_quality: float,
                 tolerance: float = _QUALITY_TOLERANCE) -> bool:
    """The candidate is no worse than the incumbent beyond a small tolerance."""
    return candidate_quality >= incumbent_quality - tolerance


def within_cost_budget(candidate_cost: float, incumbent_cost: float,
                       ratio: float = _COST_BUDGET_RATIO) -> bool:
    """A cheaper model always passes; a pricier one only within the budget ratio."""
    if candidate_cost <= incumbent_cost:
        return True
    if incumbent_cost <= 0:
        return False
    return candidate_cost <= incumbent_cost * ratio


def require_independent_suites(suites: SuiteSet) -> None:
    """§22.2 — the exam predates the student. Refuse promotion on self-generated
    tests alone: the incumbent golden suite **and** a platform curated suite must
    both be present."""
    if not suites.incumbent_golden:
        raise AdmissionError("no incumbent golden suite — the exam must predate the student")
    if not suites.platform_curated:
        raise AdmissionError("no platform curated suite for this artifact class")


async def admit_model_change(
    db: AsyncSession, *,
    model_id: UUID,
    candidate: ModelEval,
    incumbent: ModelEval,
    suites: SuiteSet,
    task_classes: Sequence[str] = (),
    quality_tolerance: float = _QUALITY_TOLERANCE,
    cost_budget_ratio: float = _COST_BUDGET_RATIO,
) -> AdmissionResult:
    """§22.4 — admit only on non-inferiority within cost budget, after §22.2.
    Records the evaluation as a platform-scoped ``model.admission_evaluated``
    signal (the caller commits). Raises ``AdmissionError`` if the independent-
    suite rule is unmet (that is a refusal, not a score)."""
    require_independent_suites(suites)   # §22.2 first — raises on self-generated-only

    quality_ok = non_inferior(candidate.quality, incumbent.quality, quality_tolerance)
    cost_ok = within_cost_budget(candidate.cost, incumbent.cost, cost_budget_ratio)
    admitted = quality_ok and cost_ok
    if admitted:
        reason = "admitted"
    elif not quality_ok:
        reason = "quality regressed below tolerance"
    else:
        reason = "over cost budget"
    result = AdmissionResult(admitted, quality_ok, cost_ok, reason)

    await _emit_admission_signal(db, model_id, task_classes, result, candidate, incumbent)
    return result


async def _emit_admission_signal(
    db: AsyncSession, model_id: UUID, task_classes: Sequence[str],
    result: AdmissionResult, candidate: ModelEval, incumbent: ModelEval,
) -> None:
    """Platform-scoped audit trail (on the APP company). Best-effort: a missing
    platform company never blocks the admission decision."""
    from src.ai.signals.models import SignalSource, SignalTypes
    from src.ai.signals.service import emit_signal
    from src.auth.models import Company

    app_id = (await db.execute(
        select(Company.id).where(Company.type == "APP").limit(1)
    )).scalar_one_or_none()
    if app_id is None:
        return

    await emit_signal(
        db,
        company_id=app_id,
        source=SignalSource.TELEMETRY,
        type=SignalTypes.MODEL_ADMISSION_EVALUATED,
        payload={
            "model_registry_id": str(model_id),
            "admitted": result.admitted,
            "reason": result.reason,
            "task_classes": list(task_classes),
            "candidate_quality": candidate.quality,
            "incumbent_quality": incumbent.quality,
            "candidate_cost": candidate.cost,
            "incumbent_cost": incumbent.cost,
        },
    )
