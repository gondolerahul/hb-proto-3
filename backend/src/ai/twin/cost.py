"""twin/cost.py — keeping a what-if cheap, and priced before it runs (TWIN T8).

Charter decision 7 made twin spend **tenant**-initiated, so every what-if is
visibly the tenant's money. That was the right call for B13 — putting it under
the platform class would let tenant experimentation exhaust the cap that exists
to protect tenants *from* platform work — but it has a real product
consequence: a Glasshouse that visibly costs money is a Glasshouse people use
less. §6 answers that with six concrete things, four of which live here.

1. **Estimate before spend.** :func:`estimate` prices a scenario from its scope
   and window before anything runs, and the run path refuses without an
   acknowledged estimate. A tenant should never learn a what-if's price
   afterwards.
2. **Cached baselines.** :func:`find_baseline` reuses the incumbent's replay
   over a given (entity version, window, scope). Most Glasshouse sessions vary
   the candidate, not the baseline, so this halves the typical cost.
3. **A daily cap that parks rather than fails.** At
   ``TWIN_DAILY_CAP_USD`` the shelf says "resumes tomorrow" — the same posture
   platform work takes at its cap. A hard failure would read as a bug; parking
   reads as a budget.
4. **Wallet holds apply**, through the shipped mechanism. No special path, so
   the E3 race stays closed.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.twin.materialise import Scope
from src.common.config import settings

__all__ = [
    "Estimate", "CapDecision", "estimate", "spent_today", "admit", "find_baseline",
]

#: Rough per-signal cost of a replayed run. Deliberately a declared rate rather
#: than a measured one, and named as such in the estimate the tenant sees: the
#: honest claim is "about this much", and a number derived from a model price
#: that changes weekly would be precise and wrong.
USD_PER_REPLAYED_SIGNAL = 0.004
#: The fixed cost of standing the plane up — the copy, the bootstrap, the reap.
USD_PER_MATERIALISATION = 0.01


@dataclass(frozen=True)
class Estimate:
    rows: int
    signals: int
    usd: float
    method: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows, "signals": self.signals,
            "usd": round(self.usd, 4), "method": self.method,
        }


@dataclass(frozen=True)
class CapDecision:
    admitted: bool
    reason: str
    spent_usd: float
    cap_usd: float

    @property
    def parked(self) -> bool:
        """A refusal that is a budget, not an error (§6.6)."""
        return not self.admitted


async def estimate(
    company_id: uuid.UUID, scope: Scope, *, signals: Optional[int] = None,
) -> Estimate:
    """Price a scenario before it runs (§6.4).

    ``signals`` may be supplied when the caller already knows the replay window
    count; otherwise the row count stands in for it, which is the honest
    approximation — a record touched in the window usually corresponds to about
    one event that touched it.
    """
    from src.ai.twin.materialise import estimate_rows

    rows = await estimate_rows(company_id, scope)
    projected_signals = signals if signals is not None else rows
    usd = USD_PER_MATERIALISATION + projected_signals * USD_PER_REPLAYED_SIGNAL
    return Estimate(
        rows=rows,
        signals=projected_signals,
        usd=usd,
        method=(
            f"{projected_signals} signal(s) at a declared "
            f"${USD_PER_REPLAYED_SIGNAL}/signal plus ${USD_PER_MATERIALISATION} "
            f"to stand the plane up. A declared rate, not a measured one."
        ),
    )


async def spent_today(db: AsyncSession, company_id: uuid.UUID) -> float:
    """What this tenant has already spent in the Glasshouse today."""
    from src.ai.twin.models import TwinRun

    since = datetime.utcnow() - timedelta(days=1)
    total = (await db.execute(
        select(func.coalesce(func.sum(TwinRun.cost_usd), 0.0)).where(
            TwinRun.company_id == company_id,
            TwinRun.started_at >= since,
        )
    )).scalar()
    return float(total or 0.0)


async def admit(
    db: AsyncSession, company_id: uuid.UUID, projected_usd: float,
) -> CapDecision:
    """May this scenario run against the tenant's daily twin budget? (§6.6)

    Parks rather than fails at the cap. The message is the deliverable as much
    as the decision is — "resumes tomorrow" is a budget a tenant understands,
    where "twin run failed" is a bug report.
    """
    cap = float(settings.TWIN_DAILY_CAP_USD)
    already = await spent_today(db, company_id)

    if already + projected_usd <= cap:
        return CapDecision(
            True,
            f"${already + projected_usd:.2f} of ${cap:.2f} daily Glasshouse budget",
            already, cap,
        )
    return CapDecision(
        False,
        (
            f"this would take today's Glasshouse spend to "
            f"${already + projected_usd:.2f}, past the ${cap:.2f} daily budget. "
            f"The scenario is kept and resumes tomorrow — nothing is lost."
        ),
        already, cap,
    )


async def find_baseline(
    db: AsyncSession, company_id: uuid.UUID, *,
    entity_version_id: Optional[uuid.UUID], scope: Scope,
    max_age_hours: int = 24,
) -> Optional["object"]:
    """A reusable baseline replay, if one exists (§6.2).

    Matched on the tuple that actually determines the result: the entity
    version replayed, and the scope+window replayed over. A baseline from a
    different window is a different measurement and must not be reused however
    convenient it would be.

    Aged out at a day: the live business moves, so yesterday's baseline is
    yesterday's business.
    """
    from src.ai.twin.models import TwinRun

    since = datetime.utcnow() - timedelta(hours=max_age_hours)
    candidates = (await db.execute(
        select(TwinRun).where(
            TwinRun.company_id == company_id,
            TwinRun.is_baseline.is_(True),
            TwinRun.started_at >= since,
            TwinRun.refusal_reason.is_(None),
            TwinRun.entity_version_id == entity_version_id,
        ).order_by(TwinRun.started_at.desc())
    )).scalars().all()

    wanted = {"objects": list(scope.objects), "window_days": scope.window_days}
    for run in candidates:
        if (run.metrics or {}).get("scope") == wanted:
            return run
    return None
