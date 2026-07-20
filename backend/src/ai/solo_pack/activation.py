"""solo_pack/activation.py — seed a tenant's Solo Pack onto the Inc-1 substrate.

Activation is idempotent per tenant: it ensures Sheel (the root Loop), creates
the curated entities under it with the right parentage, resolves the HBS
`owner_process_code` → the new PROCESS entity id in the tenant data plane
(closing the Inc-1 carryover), and registers the trigger subscriptions so the
signal bus routes work to them. Re-running is a no-op for anything already
present.

SLICE activates the four email→quote entities; PACK generalises this to any
bundle (the loop over templates is the same).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.loop.service import ensure_sheel
from src.ai.orm.entity import HierarchicalEntity
from src.ai.signals.models import TriggerRegistration
from src.ai.solo_pack.loader import validate_all
from src.ai.solo_pack.templates import (
    AGT_013,
    AGT_015,
    KAR_02_EMAIL,
    P03_ACQUISITION,
    SLICE_TEMPLATES,
)

logger = logging.getLogger(__name__)

__all__ = ["activate_slice", "ActivationResult"]


class ActivationResult(dict[str, str]):
    """{name → entity_id} for the entities activated (existing ones included)."""


async def activate_slice(
    db: AsyncSession, company_id: uuid.UUID, user_id: Optional[uuid.UUID] = None,
) -> ActivationResult:
    """Activate the SLICE Solo Pack (email → P03 acquisition) for a tenant."""
    validate_all(SLICE_TEMPLATES)  # never seed an invalid template

    sheel = await ensure_sheel(db, company_id)
    result = ActivationResult()

    # KAR-02 gateway + P03 process are axle/process under Sheel; the two
    # workforce agents are children of P03.
    kar = await _upsert_entity(db, KAR_02_EMAIL, company_id, user_id, parent_id=sheel.id)
    p03 = await _upsert_entity(db, P03_ACQUISITION, company_id, user_id, parent_id=sheel.id)
    agt013 = await _upsert_entity(db, AGT_013, company_id, user_id, parent_id=p03.id)
    agt015 = await _upsert_entity(db, AGT_015, company_id, user_id, parent_id=p03.id)
    await db.commit()

    result.update({
        KAR_02_EMAIL["name"]: str(kar.id), P03_ACQUISITION["name"]: str(p03.id),
        AGT_013["name"]: str(agt013.id), AGT_015["name"]: str(agt015.id),
    })

    # Resolve HBS owner_process_code → P03 entity id in the tenant data plane.
    await _resolve_owner_process(company_id, process_code="P03", process_entity_id=p03.id)

    # Register trigger subscriptions (idempotent).
    await _register_trigger(db, company_id, kar.id, "email.inbound")
    await _register_trigger(db, company_id, p03.id, "lead.inbound")
    await _register_trigger(db, company_id, p03.id, "lead.manual")
    await db.commit()

    logger.info("Solo Pack SLICE activated for company %s: %s", company_id, dict(result))
    return result


async def _upsert_entity(
    db: AsyncSession, template: dict[str, Any], company_id: uuid.UUID,
    user_id: Optional[uuid.UUID], *, parent_id: uuid.UUID,
) -> HierarchicalEntity:
    """Create the entity from its template if absent; else return the existing one."""
    existing = (await db.execute(
        select(HierarchicalEntity).where(
            HierarchicalEntity.company_id == company_id,
            HierarchicalEntity.name == template["name"],
            HierarchicalEntity.status != "DELETED",
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    from src.ai.schemas import HierarchicalEntityCreate

    data = HierarchicalEntityCreate.model_validate(template).model_dump(mode="json")
    data.pop("parent_id", None)   # set explicitly below (avoid duplicate kwarg)
    entity = HierarchicalEntity(
        **data, company_id=company_id, created_by=user_id, parent_id=parent_id,
    )
    db.add(entity)
    await db.flush()
    return entity


async def _resolve_owner_process(
    company_id: uuid.UUID, process_code: str, process_entity_id: uuid.UUID,
) -> None:
    """Point the tenant's HBS defs owned by ``process_code`` at the entity id.

    Runs in the tenant data plane (defs live there, §23.4). Ensures the tenant
    DB is provisioned first (a brand-new tenant may not have been touched yet).
    """
    from src.ai.tenant_schema.data_plane import tenant_data_plane
    from src.ai.tenant_schema.models import TenantEntityDef

    async with tenant_data_plane.session(company_id) as ts:
        await ts.execute(
            update(TenantEntityDef)
            .where(TenantEntityDef.company_id == company_id,
                   TenantEntityDef.owner_process_code == process_code)
            .values(owner_process_id=process_entity_id)
        )
        await ts.commit()


async def _register_trigger(
    db: AsyncSession, company_id: uuid.UUID, entity_id: uuid.UUID, type_pattern: str,
) -> None:
    existing = (await db.execute(
        select(TriggerRegistration).where(
            TriggerRegistration.company_id == company_id,
            TriggerRegistration.process_entity_id == entity_id,
            TriggerRegistration.type_pattern == type_pattern,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return
    db.add(TriggerRegistration(
        company_id=company_id, process_entity_id=entity_id,
        type_pattern=type_pattern, priority=100, enabled=True,
    ))
    await db.flush()
