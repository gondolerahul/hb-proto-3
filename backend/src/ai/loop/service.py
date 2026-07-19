"""loop/service.py — Loop resolution, Sheel seeding, parent-of-LOOP validation.

A Loop is a standing entity, not a run. ``ensure_sheel`` creates the one root
Loop per tenant plus its ``loop_runtime`` and default budget envelope; the
partial unique index (§17.1) guarantees a second root can't be created.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.loop.envelopes import ensure_loop_envelope
from src.ai.loop.models import LoopRuntime
from src.ai.orm.entity import HierarchicalEntity
from src.common.config import settings

logger = logging.getLogger(__name__)

__all__ = ["get_root_loop", "ensure_sheel"]


async def get_root_loop(db: AsyncSession, company_id: uuid.UUID) -> Optional[HierarchicalEntity]:
    return (await db.execute(
        select(HierarchicalEntity).where(
            HierarchicalEntity.company_id == company_id,
            HierarchicalEntity.type == "LOOP",
            HierarchicalEntity.parent_id.is_(None),
            HierarchicalEntity.status != "ARCHIVED",
        )
    )).scalar_one_or_none()


async def ensure_sheel(db: AsyncSession, company_id: uuid.UUID) -> HierarchicalEntity:
    """Create (or return) the tenant's root Loop + loop_runtime + envelope."""
    loop = await get_root_loop(db, company_id)
    if loop is None:
        loop = HierarchicalEntity(
            company_id=company_id, type="LOOP", parent_id=None, status="ACTIVE",
            name="Sheel", display_name="Sheel",
            description="The one Loop — the company's standing top tier.",
            goal="Turn the six arcs of the business as one governed loop.",
            governance={"autonomy_level": "A1"},
        )
        db.add(loop)
        await db.flush()

    rt = await db.get(LoopRuntime, loop.id)
    if rt is None:
        db.add(LoopRuntime(
            loop_entity_id=loop.id, company_id=company_id, enabled=True,
            heartbeat_interval_s=settings.LOOP_HEARTBEAT_SCAN_SECONDS * 2,
            stats={},
        ))
        await db.flush()

    await ensure_loop_envelope(db, company_id, loop.id)
    return loop
