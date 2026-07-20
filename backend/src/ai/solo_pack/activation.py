"""solo_pack/activation.py — seed a tenant's Solo Pack onto the Inc-1 substrate.

Activation is idempotent per tenant: it ensures Sheel (the root Loop), creates
the curated entities under it with the right parentage (gateways + processes
under Sheel, workforce agents under their process), resolves each HBS
`owner_process_code` → the new PROCESS entity id in the tenant data plane
(closing the Inc-1 carryover), and registers the trigger subscriptions so the
signal bus routes work to them. Re-running is a no-op for anything present.

Three entry points over one core:

* ``activate_solo_pack`` — the default cross-functional pack (all Wave-0 groups).
* ``activate_bundle``    — one starter bundle's authored processes (§2.1).
* ``activate_slice``     — the P03 email→quote slice (back-compat; unchanged).

All three always seed the shared gateways (the outward face feeds every
process). A bundle whose §2.1 processes are not yet authored seeds only the
gateways + Sheel — activating it again once the templates land brings them
online with no plumbing change.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.loop.service import ensure_sheel
from src.ai.orm.entity import HierarchicalEntity
from src.ai.signals.models import TriggerRegistration
from src.ai.solo_pack.bundles import SOLO_PACK, bundle_by_key
from src.ai.solo_pack.loader import validate_all
from src.ai.solo_pack.templates import (
    GATEWAYS,
    KAR_02_EMAIL,
    PROCESS_GROUPS,
    ProcessGroup,
    process_group,
)

logger = logging.getLogger(__name__)

__all__ = [
    "activate_solo_pack", "activate_bundle", "activate_slice", "ActivationResult",
]


class ActivationResult(dict[str, str]):
    """{name → entity_id} for the entities activated (existing ones included)."""


async def activate_solo_pack(
    db: AsyncSession, company_id: uuid.UUID, user_id: Optional[uuid.UUID] = None,
) -> ActivationResult:
    """Activate the full Solo Pack (all Wave-0 processes) for a tenant."""
    return await _activate(db, company_id, user_id, groups=PROCESS_GROUPS)


async def activate_bundle(
    db: AsyncSession, company_id: uuid.UUID, bundle_key: str,
    user_id: Optional[uuid.UUID] = None,
) -> ActivationResult:
    """Activate one starter bundle's authored Wave-0 processes for a tenant.

    ``bundle_key`` is a §2.1 bundle key (e.g. ``"fiscal"``) or the ``solo_pack``
    sentinel for the full pack. Seeds the intersection of the bundle's processes
    with the authored templates; unknown keys raise ``ValueError``.
    """
    if bundle_key == SOLO_PACK:
        return await activate_solo_pack(db, company_id, user_id)
    bundle = bundle_by_key(bundle_key)
    if bundle is None:
        raise ValueError(f"unknown bundle: {bundle_key!r}")
    groups = [g for g in PROCESS_GROUPS if g.process_code in bundle.process_codes]
    logger.info("Activating bundle %s for company %s: processes %s",
                bundle_key, company_id, [g.process_code for g in groups])
    return await _activate(db, company_id, user_id, groups=groups)


async def activate_slice(
    db: AsyncSession, company_id: uuid.UUID, user_id: Optional[uuid.UUID] = None,
) -> ActivationResult:
    """Activate the SLICE Solo Pack (email → P03 acquisition) for a tenant.

    The slice is the email path only, so it seeds just the email gateway — the
    full pack / any bundle seeds every gateway (the shared outward face).
    """
    p03 = process_group("P03")
    groups = [p03] if p03 is not None else []
    return await _activate(db, company_id, user_id, groups=groups, gateways=[KAR_02_EMAIL])


async def _activate(
    db: AsyncSession, company_id: uuid.UUID, user_id: Optional[uuid.UUID],
    *, groups: Iterable[ProcessGroup], gateways: Optional[list[dict[str, Any]]] = None,
) -> ActivationResult:
    """Seed the gateways + the given process groups under Sheel (idempotent)."""
    groups = list(groups)
    gateways = list(GATEWAYS if gateways is None else gateways)
    seeded_templates = [*gateways, *(t for g in groups for t in g.templates)]
    validate_all(seeded_templates)  # never seed an invalid template

    sheel = await ensure_sheel(db, company_id)
    result = ActivationResult()

    # Gateways + processes are axle/process under Sheel; workforce agents are
    # children of their process.
    for gateway in gateways:
        ent = await _upsert_entity(db, gateway, company_id, user_id, parent_id=sheel.id)
        result[gateway["name"]] = str(ent.id)
    for group in groups:
        proc = await _upsert_entity(db, group.process, company_id, user_id, parent_id=sheel.id)
        result[group.process["name"]] = str(proc.id)
        for agent in group.agents:
            child = await _upsert_entity(db, agent, company_id, user_id, parent_id=proc.id)
            result[agent["name"]] = str(child.id)
    await db.commit()

    # Resolve HBS owner_process_code → the process entity id (tenant data plane),
    # and register each entity's trigger subscriptions (idempotent).
    for group in groups:
        proc_id = uuid.UUID(result[group.process["name"]])
        await _resolve_owner_process(company_id, group.process_code, proc_id)
    for gateway in gateways:
        await _register_triggers(db, company_id, gateway, uuid.UUID(result[gateway["name"]]))
    for group in groups:
        await _register_triggers(
            db, company_id, group.process, uuid.UUID(result[group.process["name"]]))
    await db.commit()

    logger.info("Solo Pack activated for company %s: %d entities", company_id, len(result))
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
    A process that owns no object (e.g. the read-all planner) resolves nothing.
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


async def _register_triggers(
    db: AsyncSession, company_id: uuid.UUID, template: dict[str, Any], entity_id: uuid.UUID,
) -> None:
    """Register every trigger pattern the template subscribes to (idempotent)."""
    patterns = (template.get("metadata_extensions") or {}).get("trigger_patterns") or []
    for type_pattern in patterns:
        await _register_trigger(db, company_id, entity_id, str(type_pattern))


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
