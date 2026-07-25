"""learning/pooling.py — the pooled platform aggregate, and the floor that guards it.

Charter decision 2 splits learning: platform-level pools, tenant-level does not.
``models.PlatformObservation`` is the structural half of that guarantee — it has
no column a tenant could occupy. This module is the *procedural* half, and the
order of operations is the whole point:

    read company-scoped rows  →  count distinct contributors  →  drop the
    small groups  →  write rows that cannot hold a company

The k-anonymity check runs **here**, inside the job, precisely because this is
the last place where ``company_id`` is still visible. A bucket for a model only
one tenant has opted into (Kimi, say) is attributable to that tenant by anyone
who can read the opt-in list, even though the row itself names nobody. So a
group with fewer than ``LEARN_POOL_MIN_CONTRIBUTORS`` distinct companies is
**dropped, not deferred**: the data is discarded, because holding it until more
tenants arrive would mean keeping company-attributable rows somewhere in the
meantime, which is the thing being avoided.

Two consequences worth stating rather than discovering: pooled learning **lags a
day**, and the platform learns nothing about rare configurations. Both are
correct. Router priors are not a real-time input, and a configuration too rare
to clear the floor has too small a sample to learn from anyway.

The success proxy is **"did not have to fall back"** — the same SLO proxy
``intelligence/canary.py`` uses, and it carries the same limitation: the shipped
telemetry does not attribute a *generate* failure to a specific model, so a
model that fails loudly and a model that fails silently look alike here.

Design: docs/product-road-map/increment-6/01_learn.md §4.3.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.learning.models import ObservationMetric

logger = logging.getLogger(__name__)

__all__ = ["DecisionRow", "Bucket", "bucket_decisions", "pool_day"]


@dataclass(frozen=True)
class DecisionRow:
    """One routing decision as the job reads it — the last shape with a tenant in it."""

    company_id: uuid.UUID
    task_type: str
    model_registry_id: uuid.UUID | None
    reason: str
    fallback_used: bool
    latency_ms: int = 0
    cost_usd: Decimal = Decimal("0")


@dataclass(frozen=True)
class Bucket:
    """One pooled bucket — the same shape minus the tenant, plus the counts.

    ``contributors`` exists only so the caller can assert the floor was applied;
    it is **not** written to the table (a distinct-company count is itself a
    small fact about tenants). ``PlatformObservation.contributor_floor_met``
    records that the check happened, not its value.
    """

    task_type: str
    model_registry_id: uuid.UUID | None
    reason: str
    observations: int
    successes: float
    latency_ms_sum: int
    cost_usd_sum: Decimal
    contributors: int


def bucket_decisions(
    rows: Iterable[DecisionRow], *, min_contributors: int,
) -> list[Bucket]:
    """Group by ``(task_type, model, reason)`` and drop groups below the floor.

    Pure, so the property that matters is unit-testable without a database: the
    floor counts **distinct companies**, not rows. One chatty tenant generating
    a thousand decisions must not clear a floor of three — if it did, the floor
    would protect nobody while looking like it protected everybody.
    """
    grouped: dict[tuple[str, uuid.UUID | None, str], list[DecisionRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.task_type, row.model_registry_id, row.reason)].append(row)

    buckets: list[Bucket] = []
    for (task_type, model_id, reason), members in sorted(
            grouped.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), kv[0][2])):
        contributors = len({m.company_id for m in members})
        if contributors < min_contributors:
            # Dropped, not deferred — see the module docstring.
            continue
        buckets.append(Bucket(
            task_type=task_type,
            model_registry_id=model_id,
            reason=reason,
            observations=len(members),
            successes=float(sum(1 for m in members if not m.fallback_used)),
            latency_ms_sum=sum(int(m.latency_ms or 0) for m in members),
            cost_usd_sum=sum((m.cost_usd or Decimal("0") for m in members),
                             Decimal("0")),
            contributors=contributors,
        ))
    return buckets


#: One row per routing decision, with its usage joined for latency and cost.
#: Grouped by ``rd.id`` because a decision may have several usage rows (a step
#: that logged an embedding beside its generate), and the decision is the unit.
_DECISIONS_SQL = text("""
    SELECT rd.company_id,
           rd.task_type,
           rd.model_registry_id,
           rd.reason,
           rd.fallback_used,
           COALESCE(SUM((ul.log_metadata->>'latency_ms')::bigint), 0) AS latency_ms,
           COALESCE(SUM(ul.calculated_cost), 0)                       AS cost_usd
    FROM routing_decisions rd
    LEFT JOIN usage_logs ul ON ul.routing_decision_id = rd.id
    WHERE rd.created_at >= :start AND rd.created_at < :end
    GROUP BY rd.id, rd.company_id, rd.task_type, rd.model_registry_id,
             rd.reason, rd.fallback_used
""")

_DELETE_DAY_SQL = text("""
    DELETE FROM platform_observations
    WHERE metric = :metric AND bucket_day = :day
""")

_INSERT_SQL = text("""
    INSERT INTO platform_observations
        (id, metric, model_registry_id, task_type, reason, bucket_day,
         observations, successes, latency_ms_sum, cost_usd_sum,
         contributor_floor_met, updated_at)
    VALUES
        (:id, :metric, :model_registry_id, :task_type, :reason, :day,
         :observations, :successes, :latency_ms_sum, :cost_usd_sum,
         true, now())
""")


async def pool_day(
    db: AsyncSession,
    day: date,
    *,
    min_contributors: int | None = None,
) -> dict[str, Any]:
    """Aggregate one UTC day of routing decisions into pooled buckets.

    **Replace, don't upsert.** The job recomputes the whole day from source, so
    deleting the day's rows and re-inserting is both simpler and more obviously
    idempotent than an ``ON CONFLICT`` — which would additionally have to infer
    the grain's *expression* index (``coalesce(model_registry_id, …)``), a
    fragile thing to depend on for a job whose entire input is re-read anyway.

    The caller commits.
    """
    if min_contributors is None:
        from src.common.config import settings
        min_contributors = int(getattr(settings, "LEARN_POOL_MIN_CONTRIBUTORS", 3))

    start = datetime.combine(day, time.min)
    result = await db.execute(_DECISIONS_SQL, {"start": start, "end": start + timedelta(days=1)})
    rows: Sequence[Any] = result.all()

    decisions = [
        DecisionRow(
            company_id=r.company_id,
            task_type=r.task_type,
            model_registry_id=r.model_registry_id,
            reason=r.reason,
            fallback_used=bool(r.fallback_used),
            latency_ms=int(r.latency_ms or 0),
            cost_usd=Decimal(str(r.cost_usd or 0)),
        )
        for r in rows
    ]

    buckets = bucket_decisions(decisions, min_contributors=min_contributors)

    await db.execute(_DELETE_DAY_SQL,
                     {"metric": ObservationMetric.ROUTE_OUTCOME, "day": day})
    for bucket in buckets:
        await db.execute(_INSERT_SQL, {
            "id": uuid.uuid4(),
            "metric": ObservationMetric.ROUTE_OUTCOME,
            "model_registry_id": bucket.model_registry_id,
            "task_type": bucket.task_type,
            "reason": bucket.reason,
            "day": day,
            "observations": bucket.observations,
            "successes": bucket.successes,
            "latency_ms_sum": bucket.latency_ms_sum,
            "cost_usd_sum": bucket.cost_usd_sum,
        })

    dropped = len({(d.task_type, d.model_registry_id, d.reason) for d in decisions}) - len(buckets)
    logger.info("pool_day %s: %d decisions → %d buckets (%d groups below floor of %d)",
                day, len(decisions), len(buckets), dropped, min_contributors)
    return {
        "day": day.isoformat(),
        "decisions": len(decisions),
        "buckets": len(buckets),
        "dropped_below_floor": dropped,
        "min_contributors": min_contributors,
    }
