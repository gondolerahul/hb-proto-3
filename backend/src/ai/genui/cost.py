"""genui/cost.py — the per-path cost estimator (DRIVER D2, D5 §4.1).

The one sentence this module answers: *"what has saying yes to this kind
of thing cost before?"* — an **observed median, labeled as one**, never a
model guess. The rules, from 11_driver.md §4:

* Source of truth is ``usage_logs`` through the approval's own run: the
  spend a run accrued **after** its approval was granted is what saying
  yes actually cost the wallet last time.
* Grain is ``(company, checkpoint_key)`` over a trailing 90 days,
  **company-scoped only** — no cross-tenant pooling. A platform-wide
  median would describe nothing, and a number that describes nothing is a
  fabrication with a denominator.
* Fewer than :data:`OBSERVATION_FLOOR` observations → ``None`` — the tray
  renders no cost line (the D5 §4.1 rule, unweakened). An approved run
  that spent nothing afterwards **is** an observation, at zero: excluding
  it would bias every estimate upward.
* The act's own amount always wins at the composer — this estimate fills
  only the paths that would otherwise be ``null``, and the two bases are
  never summed into one figure.

The cache is deliberately small: in-process, ten minutes, keyed by the
grain — this is a projection over billing data recomputed cheaply, not a
store. No migration, no cron, no new attribution.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.orm.execution import ExecutionRun, HumanApproval
from src.ai.orm.usage import UsageLog

__all__ = [
    "OBSERVATION_FLOOR",
    "TRAILING_WINDOW_DAYS",
    "estimate_from_observations",
    "observed_decision_cost",
    "reset_cost_cache",
]

OBSERVATION_FLOOR = 5
TRAILING_WINDOW_DAYS = 90
_CACHE_TTL_SECONDS = 600

# (company_id, checkpoint_key) → (expires_at, estimate-or-None)
_cache: dict[tuple[uuid.UUID, str], tuple[datetime, dict[str, Any] | None]] = {}


def reset_cost_cache() -> None:
    _cache.clear()


def estimate_from_observations(
    per_decision_spend: list[Decimal],
) -> dict[str, Any] | None:
    """The pure heart: observations in, an honest cost object or None out.

    ``currency`` is ``None`` by the composer's own rule — the platform does
    not stamp one on spend, and a guessed unit would be wrong for exactly
    the tenants least able to notice. The basis names the denominator so a
    human can weigh the number.
    """
    if len(per_decision_spend) < OBSERVATION_FLOOR:
        return None
    mid = median(per_decision_spend)
    return {
        "amount": float(mid),
        "currency": None,
        "basis": (
            f"observed: median platform spend across "
            f"{len(per_decision_spend)} similar decisions"
        ),
    }


async def observed_decision_cost(
    db: AsyncSession,
    company_id: uuid.UUID,
    checkpoint_key: str | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Median post-approval run spend for this company at this checkpoint.

    A LEFT JOIN keeps zero-spend approvals in the sample (they are real
    observations); usage rows with no timestamp cannot be placed after the
    approval and are excluded rather than guessed about.
    """
    if checkpoint_key is None or checkpoint_key == "":
        return None
    now = now or datetime.utcnow()
    key = (company_id, checkpoint_key)
    cached = _cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]

    window_start = now - timedelta(days=TRAILING_WINDOW_DAYS)
    stmt = (
        select(
            HumanApproval.id,
            func.coalesce(func.sum(UsageLog.calculated_cost), 0),
        )
        .join(ExecutionRun, HumanApproval.run_id == ExecutionRun.id)
        .outerjoin(
            UsageLog,
            (UsageLog.run_id == HumanApproval.run_id)
            & (UsageLog.company_id == company_id)
            & (UsageLog.timestamp.is_not(None))
            & (UsageLog.timestamp >= HumanApproval.responded_at),
        )
        .where(
            ExecutionRun.company_id == company_id,
            HumanApproval.checkpoint_key == checkpoint_key,
            HumanApproval.status == "APPROVED",
            HumanApproval.responded_at.is_not(None),
            HumanApproval.responded_at >= window_start,
        )
        .group_by(HumanApproval.id)
    )
    rows = (await db.execute(stmt)).all()
    estimate = estimate_from_observations([Decimal(row[1]) for row in rows])
    _cache[key] = (now + timedelta(seconds=_CACHE_TTL_SECONDS), estimate)
    return estimate
