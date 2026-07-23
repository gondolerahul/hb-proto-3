"""intelligence/canary.py — canary rollout for a model-fleet change (EVX, §22.3).

After admission (§22.4) a change serves the **routed cohort** — the companies on
``routing_mode='router'``, the per-company flag the design reuses rather than
inventing new machinery — and its reliability is watched from the telemetry the
router already writes (``routing_decisions``). A regressing window auto-rolls the
model back to ``preview`` (dropping it from candidates); a clean window promotes.

The SLO proxy is the routed cohort's **fallback rate** — how often a routed call
had to re-route off its first-choice model. It is deliberately cohort-level: the
shipped telemetry does not attribute a generate failure to a specific model, so
finer per-model canary slicing is future work (recording ``fell_back_from``).

Design: docs/product-road-map/increment-5/04_eval_extensions.md §5.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.intelligence.models import ModelRegistry, ModelStatus, RoutingDecision

__all__ = ["CanaryVerdict", "watch", "roll_back", "promote"]

_MAX_FALLBACK_RATE = 0.20   # a routed cohort re-routing >20% of the time is regressed
_MIN_SAMPLES = 5            # below this the canary keeps observing


@dataclass(frozen=True)
class CanaryVerdict:
    healthy: bool
    samples: int
    fallback_rate: float
    reason: str


async def watch(
    db: AsyncSession, *, since: datetime | None = None,
    max_fallback_rate: float = _MAX_FALLBACK_RATE, min_samples: int = _MIN_SAMPLES,
) -> CanaryVerdict:
    """Assess the routed cohort's reliability from ``routing_decisions``."""
    base = select(func.count()).select_from(RoutingDecision)
    if since is not None:
        base = base.where(RoutingDecision.created_at >= since)
    total = (await db.execute(base)).scalar() or 0

    if total < min_samples:
        return CanaryVerdict(True, total, 0.0, "insufficient samples — canary continues")

    fb_q = base.where(RoutingDecision.fallback_used.is_(True))
    fallbacks = (await db.execute(fb_q)).scalar() or 0
    rate = fallbacks / total
    healthy = rate <= max_fallback_rate
    reason = "healthy" if healthy else f"fallback rate {rate:.0%} exceeds {max_fallback_rate:.0%}"
    return CanaryVerdict(healthy, total, rate, reason)


async def roll_back(db: AsyncSession, model_registry_id: UUID) -> None:
    """Revert a canaried model to ``preview`` (drops it from candidates) and emit
    the rollback signal."""
    model = (await db.execute(
        select(ModelRegistry).where(ModelRegistry.id == model_registry_id)
    )).scalar_one_or_none()
    if model is not None:
        model.status = ModelStatus.PREVIEW
    await _emit(db, "MODEL_CANARY_ROLLED_BACK", model_registry_id)
    await db.commit()


async def promote(db: AsyncSession, model_registry_id: UUID) -> None:
    """Confirm a clean canary — the model stays ``active`` — and emit the
    promotion signal."""
    await _emit(db, "MODEL_CANARY_PROMOTED", model_registry_id)
    await db.commit()


async def _emit(db: AsyncSession, signal_attr: str, model_registry_id: UUID) -> None:
    from src.ai.signals.models import SignalSource, SignalTypes
    from src.ai.signals.service import emit_signal
    from src.auth.models import Company

    app_id = (await db.execute(
        select(Company.id).where(Company.type == "APP").limit(1)
    )).scalar_one_or_none()
    if app_id is None:
        return
    await emit_signal(
        db, company_id=app_id, source=SignalSource.TELEMETRY,
        type=getattr(SignalTypes, signal_attr),
        payload={"model_registry_id": str(model_registry_id)},
    )
