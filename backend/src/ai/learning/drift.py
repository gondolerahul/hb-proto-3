"""learning/drift.py — noticing behaviour change nobody decided on (LEARN T7).

Drift is the third of B10's three findings: not *what* an agent learns and not
*where* the learning pools, but the case where an agent's behaviour moves and
no one chose it. A demotion trigger catches an agent that is failing. Drift
catches one that is merely becoming *different* — approving less, escalating
more, taking twice as many steps for the same work.

**This module observes; it never acts.** ``governance/demotion.py`` owns
demotion and already has triggers, thresholds and an anti-rubber-stamp
promotion rule. LEARN gives it one more input (``DemotionTrigger.BEHAVIOUR_DRIFT``)
rather than a second opinion — two demotion authorities would be exactly the
"which store is this row in" confusion the increment plan warns about, moved
into the enforcement layer where it would be worse.

**Counts and ratios only.** Every column of ``EntityBehaviourWeekly`` is a
number over outcomes; no prompt, output or record is stored. Same shape as the
shipped ``SourceTrustScore``, and the same reason: an aggregate over outcomes
needs none of that, and storing it would create a second copy of tenant data
with its own retention story.

Design: docs/product-road-map/increment-6/01_learn.md §8.
"""
from __future__ import annotations

import logging
import statistics
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.learning.models import EntityBehaviourWeekly

logger = logging.getLogger(__name__)

__all__ = [
    "TRACKED_METRICS",
    "DriftFinding",
    "detect_drift",
    "measure_week",
    "record_week",
    "sweep_company",
    "week_start_of",
]

#: The behavioural axes worth watching. Deliberately small: each one added is
#: another way for the sweep to cry wolf, and an alert nobody believes is worse
#: than no alert.
TRACKED_METRICS: tuple[str, ...] = (
    "approval_rate", "rejection_rate", "escalation_rate", "mean_steps", "mean_csat",
)

#: How far a week must sit from the entity's own trailing mean to count as a
#: step change. 2.5σ over a small sample is deliberately conservative — the
#: cost of a false positive here is an owner learning to ignore drift alerts.
DEFAULT_SIGMA = 2.5

#: Below this many prior weeks there is no baseline to be different from.
MIN_BASELINE_WEEKS = 3


def week_start_of(day: date) -> date:
    """The Monday (UTC) of ``day``'s week — the grain of the series."""
    return day - timedelta(days=day.weekday())


@dataclass(frozen=True)
class DriftFinding:
    """One metric that moved, with the numbers behind the claim."""

    entity_id: uuid.UUID
    metric: str
    current: float
    baseline_mean: float
    baseline_sigma: float
    week_start: date

    @property
    def direction(self) -> str:
        return "up" if self.current > self.baseline_mean else "down"

    def as_sentence(self) -> str:
        return (f"{self.metric} moved {self.direction} to {self.current:.2f} "
                f"(baseline {self.baseline_mean:.2f} ± {self.baseline_sigma:.2f})")


def detect_drift(
    history: Sequence[EntityBehaviourWeekly],
    current: EntityBehaviourWeekly,
    *,
    sigma: float = DEFAULT_SIGMA,
) -> list[DriftFinding]:
    """Compare a week against the entity's own trailing weeks. Pure.

    **Against itself, never against a fleet average.** A meticulous agent that
    escalates often is not drifting; it is being itself. The only meaningful
    baseline for "has this changed" is what this agent used to do.

    Returns nothing when the baseline is too short (``MIN_BASELINE_WEEKS``) or
    when a metric never varied — a zero-variance baseline would make every
    subsequent value infinitely many sigmas away, which is arithmetic, not
    evidence.
    """
    if len(history) < MIN_BASELINE_WEEKS:
        return []

    findings: list[DriftFinding] = []
    for metric in TRACKED_METRICS:
        values = [v for v in (getattr(h, metric) for h in history) if v is not None]
        now = getattr(current, metric)
        if now is None or len(values) < MIN_BASELINE_WEEKS:
            continue

        mean = statistics.fmean(values)
        deviation = statistics.pstdev(values)
        if deviation <= 0:
            # A metric that has never moved gives no scale to judge movement by.
            continue
        if abs(now - mean) >= sigma * deviation:
            findings.append(DriftFinding(
                entity_id=current.entity_id, metric=metric, current=float(now),
                baseline_mean=mean, baseline_sigma=deviation,
                week_start=current.week_start))
    return findings


_WEEK_SQL = text("""
    SELECT COUNT(DISTINCT er.id)                                        AS runs,
           AVG(er.csat_score)                                           AS mean_csat,
           COUNT(ha.id) FILTER (WHERE ha.status = 'APPROVED')           AS approved,
           COUNT(ha.id) FILTER (WHERE ha.status = 'REJECTED')           AS rejected,
           COUNT(ha.id) FILTER (WHERE ha.status = 'TIMEOUT')            AS escalated,
           COUNT(ha.id)                                                 AS approvals,
           COUNT(til.id)                                                AS tool_calls
    FROM execution_runs er
    LEFT JOIN human_approvals ha        ON ha.run_id = er.id
    LEFT JOIN tool_interaction_logs til ON til.run_id = er.id
    WHERE er.entity_id = :entity_id
      AND er.created_at >= :start
      AND er.created_at <  :end
""")


async def measure_week(
    db: AsyncSession, *, company_id: uuid.UUID, entity_id: uuid.UUID, week_start: date,
) -> EntityBehaviourWeekly:
    """Measure one entity's week. Not persisted here — see :func:`record_week`.

    ``mean_steps`` is tool calls per run, which is the closest thing the shipped
    telemetry has to "how much work did this take": ``execution_runs`` records no
    step count. It is a proxy and it is named as one.

    A metric with no denominator is ``None``, not ``0``. An agent that raised no
    approvals has *no* approval rate, and recording zero would drag its own
    baseline down and then fire drift when it next raises one — the honest-absence
    rule from C6, in a second place that needs it.
    """
    start = datetime.combine(week_start, datetime.min.time())
    row = (await db.execute(_WEEK_SQL, {
        "entity_id": entity_id, "start": start, "end": start + timedelta(days=7),
    })).one()

    runs = int(row.runs or 0)
    approvals = int(row.approvals or 0)

    return EntityBehaviourWeekly(
        company_id=company_id,
        entity_id=entity_id,
        week_start=week_start,
        runs=runs,
        approval_rate=(int(row.approved or 0) / approvals) if approvals else None,
        rejection_rate=(int(row.rejected or 0) / approvals) if approvals else None,
        escalation_rate=(int(row.escalated or 0) / approvals) if approvals else None,
        # Consent refusals are not recorded per run by the shipped consent
        # registry, so this axis stays absent rather than being invented. It is
        # a real gap and it belongs to GATE, which is where consent gets its
        # per-send decision record.
        consent_refusal_rate=None,
        mean_steps=(int(row.tool_calls or 0) / runs) if runs else None,
        mean_csat=float(row.mean_csat) if row.mean_csat is not None else None,
    )


async def record_week(db: AsyncSession, measured: EntityBehaviourWeekly) -> None:
    """Upsert one week's measurement. The caller commits."""
    existing = (await db.execute(
        select(EntityBehaviourWeekly).where(
            EntityBehaviourWeekly.entity_id == measured.entity_id,
            EntityBehaviourWeekly.week_start == measured.week_start,
        )
    )).scalar_one_or_none()

    if existing is None:
        db.add(measured)
        return
    for metric in ("runs", *TRACKED_METRICS, "consent_refusal_rate"):
        setattr(existing, metric, getattr(measured, metric))


async def sweep_company(
    db: AsyncSession, company_id: uuid.UUID, *, now: datetime | None = None,
    sigma: float = DEFAULT_SIGMA,
) -> dict[str, Any]:
    """Measure last week for every agent, then emit drift where it is real.

    Last week rather than this one: a partial week compared against complete
    ones is guaranteed to look like a step change in every volume-shaped metric.
    """
    from src.ai.orm.entity import HierarchicalEntity
    from src.ai.signals.models import SignalSource, SignalTypes
    from src.ai.signals.service import emit_signal

    at = now or datetime.utcnow()
    week = week_start_of(at.date()) - timedelta(days=7)

    entities = (await db.execute(
        select(HierarchicalEntity.id).where(
            HierarchicalEntity.company_id == company_id,
            HierarchicalEntity.type == "AGENT",
            HierarchicalEntity.deleted_at.is_(None),
        )
    )).scalars().all()

    measured_count = 0
    findings: list[DriftFinding] = []
    for entity_id in entities:
        measured = await measure_week(
            db, company_id=company_id, entity_id=entity_id, week_start=week)
        if measured.runs == 0:
            continue                      # a silent week is not a changed one
        await record_week(db, measured)
        measured_count += 1

        history = (await db.execute(
            select(EntityBehaviourWeekly)
            .where(
                EntityBehaviourWeekly.entity_id == entity_id,
                EntityBehaviourWeekly.week_start < week,
            )
            .order_by(EntityBehaviourWeekly.week_start.desc())
            .limit(12)
        )).scalars().all()

        for finding in detect_drift(list(history), measured, sigma=sigma):
            findings.append(finding)
            await emit_signal(
                db,
                company_id=company_id,
                source=SignalSource.TELEMETRY,
                type=SignalTypes.LEARNING_DRIFT_DETECTED,
                payload={
                    "entity_id": str(entity_id),
                    "metric": finding.metric,
                    "current": finding.current,
                    "baseline_mean": finding.baseline_mean,
                    "baseline_sigma": finding.baseline_sigma,
                    "week_start": finding.week_start.isoformat(),
                    "summary": finding.as_sentence(),
                },
                object_refs=[f"entity:{entity_id}"],
                dedupe_key=(f"learning.drift:{entity_id}:{finding.metric}:"
                            f"{finding.week_start.isoformat()}"),
            )

    return {
        "week_start": week.isoformat(),
        "entities_measured": measured_count,
        "drift_findings": len(findings),
    }
