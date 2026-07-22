"""governance/demotion_sweep.py — enforcement for the C4 demotion policy.

TRUST's shape: the policy is pure in ``demotion.py``, and this module does the
two things a pure function cannot — gather the observations, and write the
consequence. It runs beside ``apply_checkpoint_timeouts`` in the existing cron
family rather than as a new scheduler.

The write is deliberately narrow: it changes ``governance.autonomy_level`` on
the entity and emits ``governance.autonomy_demoted``. It does not pause the
agent or cancel work in flight — a demoted agent keeps running, it just needs
a human for more of what it does, which is the whole point of the ladder.

The signal is emitted for the owner's benefit, not the system's: Pragya reads
it in stage 9 so the owner hears "I pulled X back a level, here's why" rather
than noticing their workforce quietly got more cautious.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.governance.demotion import (
    DEFAULT_THRESHOLDS,
    AgentObservations,
    DemotionThresholds,
    DemotionVerdict,
    evaluate_demotion,
)
from src.ai.orm.entity import HierarchicalEntity
from src.ai.orm.execution import ExecutionRun
from src.ai.schemas.governance import AutonomyLevel
from src.ai.signals.models import SignalTypes
from src.ai.signals.service import emit_signal

logger = logging.getLogger(__name__)

__all__ = ["WINDOW_DAYS", "gather_observations", "apply_demotions"]

#: The observation window. Long enough that a bad afternoon does not demote an
#: agent, short enough that a genuinely failing one does not run for weeks.
WINDOW_DAYS = 7

_FAILED_STATUSES = ("FAILED", "ERROR", "TIMEOUT")


def _autonomy_of(entity: HierarchicalEntity) -> AutonomyLevel:
    raw = (entity.governance or {}).get("autonomy_level") if entity.governance else None
    try:
        return AutonomyLevel(raw) if raw else AutonomyLevel.A1
    except ValueError:
        return AutonomyLevel.A1


async def gather_observations(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    now: Optional[datetime] = None,
) -> list[AgentObservations]:
    """Measure every agent in a company over the window.

    Only agents *above* A0 are worth measuring — there is nothing to take away
    from an agent that already needs approval for everything.
    """
    at = now or datetime.utcnow()
    cutoff = at - timedelta(days=WINDOW_DAYS)

    entities = (await db.execute(
        select(HierarchicalEntity).where(
            HierarchicalEntity.company_id == company_id,
            HierarchicalEntity.type == "AGENT",
        )
    )).scalars().all()

    observations: list[AgentObservations] = []
    for entity in entities:
        level = _autonomy_of(entity)
        if level == AutonomyLevel.A0:
            continue

        totals = (await db.execute(
            select(
                func.count(ExecutionRun.id),
                func.sum(
                    case((ExecutionRun.status.in_(_FAILED_STATUSES), 1), else_=0)
                ),
                func.percentile_cont(0.95).within_group(
                    ExecutionRun.execution_time_ms.asc()),
            ).where(
                ExecutionRun.entity_id == entity.id,
                ExecutionRun.created_at >= cutoff,
            )
        )).one()

        runs_total = int(totals[0] or 0)
        runs_failed = int(totals[1] or 0)
        p95 = float(totals[2]) if totals[2] is not None else None

        governance: dict[str, Any] = entity.governance or {}
        floor = governance.get("timeout_ms")

        observations.append(AgentObservations(
            agent_id=str(entity.id),
            display_name=str(entity.display_name or entity.name),
            current_level=level,
            runs_total=runs_total,
            runs_failed=runs_failed,
            p95_latency_ms=p95,
            latency_floor_ms=float(floor) if floor else None,
        ))

    return observations


async def apply_demotions(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    thresholds: DemotionThresholds = DEFAULT_THRESHOLDS,
    now: Optional[datetime] = None,
) -> list[DemotionVerdict]:
    """Evaluate and apply demotions for a company. Returns every verdict.

    Verdicts that do not demote are returned too — a sweep that reports only
    its actions cannot be checked for having run at all.
    """
    verdicts: list[DemotionVerdict] = []

    for obs in await gather_observations(db, company_id, now=now):
        verdict = evaluate_demotion(obs, thresholds)
        verdicts.append(verdict)
        if not verdict.demote:
            continue

        entity = await db.get(HierarchicalEntity, uuid.UUID(obs.agent_id))
        if entity is None:
            continue

        governance = dict(entity.governance or {})
        governance["autonomy_level"] = verdict.to_level.value
        governance["autonomy_demoted_at"] = (now or datetime.utcnow()).isoformat()
        governance["autonomy_demotion_reason"] = list(verdict.reasons)
        entity.governance = governance

        await emit_signal(
            db,
            company_id=company_id,
            source="governance",
            type=SignalTypes.GOVERNANCE_AUTONOMY_DEMOTED,
            payload={
                "agent_id": obs.agent_id,
                "display_name": obs.display_name,
                "from_level": verdict.from_level.value,
                "to_level": verdict.to_level.value,
                "triggers": [t.value for t in verdict.triggers],
                "reasons": list(verdict.reasons),
                "summary": verdict.as_sentence(),
            },
        )
        logger.info("autonomy demoted: %s", verdict.as_sentence())

    return verdicts
