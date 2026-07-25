"""evolution/sweep.py — the canary reaches a verdict, or expires (SEGA T5).

T3 built measure/assess/promote/roll_back; nothing called them. This does,
once a day at **01:50 UTC** — after C4's demotion sweep at 01:40, deliberately.
Demotion is about *authority* and the canary is about *version*: running
demotion first means a rolled-back entity is not simultaneously being demoted
for the failures its rollback has just removed.

**An experiment with no end date is not an experiment.** A canary that never
gathers enough evidence would otherwise serve a quarter of an entity's traffic
forever, which is a permanent split disguised as a trial. After
``SEGA_CANARY_MAX_DAYS`` an undecided canary is **rolled back**, not promoted:
the change failed to demonstrate it was an improvement, and the burden of proof
sits with the change.

Design: docs/product-road-map/increment-6/02_sega.md §6.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.evolution.entity_canary import (
    assess,
    measure_version,
    promote,
    roll_back,
    suites_for_entity,
)
from src.ai.evolution.models import EntityVersion, VersionStatus

logger = logging.getLogger(__name__)

__all__ = ["DEFAULT_MAX_CANARY_DAYS", "sweep_company", "sweep_all"]

#: How long a canary may stay undecided before the burden of proof runs out.
DEFAULT_MAX_CANARY_DAYS = 14


async def sweep_company(
    db: AsyncSession, company_id: uuid.UUID, *, now: datetime | None = None,
    max_days: int | None = None,
) -> dict[str, Any]:
    """Judge every open canary for one company. The caller commits.

    Four outcomes per canary, and the third is the one that keeps this honest:
    promoted, rolled back, **still observing**, or *healthy but unpromotable* —
    a change whose evidence is good but which no independent suite backs
    (§22.2). That last one is left in place with the reason logged, because the
    alternative is either promoting on self-assessment or discarding a change
    that has done nothing wrong. A human can promote it.
    """
    from src.common.config import settings
    from src.ai.intelligence.admission import AdmissionError
    from src.ai.orm.entity import HierarchicalEntity

    at = now or datetime.utcnow()
    limit_days = max_days if max_days is not None else int(
        getattr(settings, "SEGA_CANARY_MAX_DAYS", DEFAULT_MAX_CANARY_DAYS))

    canaries = (await db.execute(
        select(EntityVersion).where(
            EntityVersion.company_id == company_id,
            EntityVersion.status == VersionStatus.CANARY,
        )
    )).scalars().all()

    counts = {"observed": 0, "promoted": 0, "rolled_back": 0,
              "expired": 0, "unpromotable": 0}

    for canary in canaries:
        incumbent = (await db.execute(
            select(EntityVersion).where(
                EntityVersion.entity_id == canary.entity_id,
                EntityVersion.status == VersionStatus.GA,
            ).order_by(EntityVersion.created_at.desc()).limit(1)
        )).scalar_one_or_none()

        entity = (await db.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.id == canary.entity_id)
        )).scalar_one_or_none()
        if entity is None:
            continue

        candidate_health = await measure_version(db, canary.id)
        incumbent_health = (await measure_version(db, incumbent.id)
                            if incumbent else await measure_version(db, uuid.uuid4()))
        verdict = assess(candidate_health, incumbent_health)

        if verdict.decided and not verdict.healthy:
            await roll_back(db, entity, canary, company_id=company_id)
            counts["rolled_back"] += 1
            continue

        if verdict.decided and verdict.healthy:
            try:
                await promote(db, canary,
                              suites=suites_for_entity(entity, incumbent_health))
                counts["promoted"] += 1
            except AdmissionError as exc:
                # Healthy, but nothing independent vouches for it. Left in
                # place rather than promoted on its own say-so.
                counts["unpromotable"] += 1
                logger.info("canary %s healthy but unpromotable: %s", canary.id, exc)
            continue

        age_days = (at - canary.created_at).days if canary.created_at else 0
        if age_days >= limit_days:
            # Undecided for too long. Rolled back rather than promoted: the
            # change failed to show it was an improvement, and the burden of
            # proof sits with the change.
            await roll_back(db, entity, canary, company_id=company_id)
            counts["expired"] += 1
            continue

        counts["observed"] += 1

    return {"company_id": str(company_id), "canaries": len(canaries), **counts}


async def sweep_all(db: AsyncSession, *, now: datetime | None = None) -> dict[str, Any]:
    """Sweep every tenant. One tenant's failure must not stop the others."""
    company_ids = [r[0] for r in (await db.execute(
        text("SELECT id FROM companies WHERE type = 'TENANT'"))).all()]

    totals = {"canaries": 0, "observed": 0, "promoted": 0, "rolled_back": 0,
              "expired": 0, "unpromotable": 0}
    failed: list[str] = []
    for company_id in company_ids:
        try:
            summary = await sweep_company(db, company_id, now=now)
            for key in totals:
                totals[key] += int(summary[key])
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            failed.append(str(company_id))
            logger.warning("canary sweep failed for company %s: %s", company_id, exc)

    return {**totals, "companies": len(company_ids), "failed": failed}
