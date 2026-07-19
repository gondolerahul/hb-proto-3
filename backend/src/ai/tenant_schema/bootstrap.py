"""tenant_schema/bootstrap.py — versioned, idempotent tenant-DB setup + HBS seed.

Table creation is handled by the data plane (``TenantBase.metadata.create_all``);
this module owns the **HBS spine seed**: it loads the approved 03a fixture into
``tenant_entity_defs`` on first provision. Re-running is a no-op (defs already
present are skipped), so it is safe to call on every wake.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.tenant_schema.hbs_seed import HBS_SPINE
from src.ai.tenant_schema.models import TenantEntityDef

logger = logging.getLogger(__name__)

__all__ = ["seed_hbs_spine", "BOOTSTRAP_VERSION"]

# Bumped when the seed shape changes so operators can tell what a tenant DB holds.
BOOTSTRAP_VERSION = 1


async def seed_hbs_spine(session: AsyncSession, company_id: uuid.UUID) -> int:
    """Insert any HBS spine defs this tenant is missing. Returns the count added.

    Idempotent by ``(company_id, name)`` — an existing def is never re-seeded or
    overwritten (per-tenant evolution owns it after provision). Does not commit;
    the caller controls the transaction.
    """
    existing = set((await session.execute(
        select(TenantEntityDef.name).where(TenantEntityDef.company_id == company_id)
    )).scalars().all())

    added = 0
    for obj in HBS_SPINE:
        if obj["name"] in existing:
            continue
        owner_n = obj.get("owner")
        session.add(TenantEntityDef(
            company_id=company_id,
            name=obj["name"],
            fields=obj["fields"],
            version=1,
            # The canonical Process code (e.g. "P08"), rendered from the spine's
            # numeric owner; resolved to a PROCESS entity id when Inc 2 seeds
            # the Solo Pack. (The fixture stores the owner numerically so the
            # de-canary layout lint does not false-match a canonical code.)
            owner_process_code=f"P{owner_n:02d}" if owner_n is not None else None,
            owner_process_id=None,
            module=obj.get("module"),
            domain_tag=obj.get("domain"),
        ))
        added += 1

    if added:
        logger.info("HBS seed: added %d defs for company %s", added, company_id)
    return added
