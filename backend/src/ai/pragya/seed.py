"""pragya/seed.py — giving Pragya an entity to exist as.

**The gap this closes.** Everything that looks for Pragya —
``children.available_children``, ``channels/routing.pragya_entity_for``,
``assign_pragya_number`` — matches an entity by name against
``PRAGYA_ENTITY_NAMES``, and every one of them was written as *"the tenant's
Pragya entity, **if one is seeded**"*. Nothing ever seeded one. The gap sat
open from Increment 3 until a phone number needed somewhere to point.

**Why she is an entity at all**, when her turn loop is her own (Inc-4): because
governance is not. Her autonomy band, memory domains, SoD class and the parent
her child capabilities hang off are all `hierarchical_entities` columns, and
`available_children` finds her children by parentage. An entity is the only
shape those questions have an answer in.

**One per tenant, even with a shared phone number.** `pragya_entity_for` takes
a `company_id`; her engagement state, memory viewport and governance band are
all per-tenant. A single platform-wide entity would have to carry one
governance block for every business at once, which is not a thing a governance
block can be.

**Her band is A1 and her memory domains are deliberately narrow.** A1 means
every categorised external effect raises a HITL card — the right default for
something that answers the phone. The domains list is what she may *retrieve*,
not what she may discuss, and it starts at `general` because widening it is a
decision someone should make on purpose.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.orm.entity import HierarchicalEntity
from src.ai.pragya.children import PRAGYA_ENTITY_NAMES

logger = logging.getLogger(__name__)

__all__ = ["PRAGYA_NAME", "pragya_template", "seed_pragya", "seed_pragya_everywhere"]

#: The canonical name. It must match `PRAGYA_ENTITY_NAMES`, and a test asserts
#: that it does — the resolvers search by name, so a rename here that missed
#: that tuple would seed an entity nothing could ever find.
PRAGYA_NAME = "pragya"


def pragya_template() -> dict[str, Any]:
    """Her entity as declared data, the way Solo Pack templates are.

    Data rather than an inline construction so the governance block is
    reviewable in one place and a test can assert its shape without a database.
    """
    return {
        "name": PRAGYA_NAME,
        "display_name": "Pragya",
        "description": "The account manager — the tenant's steward. Runs the "
                       "nine-stage engagement, answers the console and the "
                       "phone, and executes only what the caller has proven "
                       "enough to ask for.",
        "goal": "Hold a months-long relationship with the owner: understand "
                "the business, deploy and tune their workforce, and report "
                "honestly on what it did.",
        "type": "AGENT",
        "version": "1.0.0",
        "status": "ACTIVE",
        "tags": ["pragya", "account_manager", "inward_face"],
        "capabilities": {
            # Deliberately empty. Her surface is her *child entities*
            # (`children.py`, Inc-4 decision 6), not a tool allow-list — a
            # child is governed where governance already lives, and an
            # allow-list would have needed a second, weaker story beside it.
            "tools": [],
            "memory": {"enabled": True, "mode": "CORTEX"},
        },
        "governance": {
            # A1: every categorised external effect raises a card. The right
            # default for the thing that answers the phone.
            "autonomy_level": "A1",
            "karuna_profile": False,   # she is the *inward* face, not a gateway
            "sod_class": "none",
            # What she may retrieve. `strategy` is **not** here — Planning
            # records stay invisible until someone grants it deliberately
            # (04a §8.9), and that is the feature.
            "memory_domains": ["general"],
            "max_cost_usd": 0.50,
            "timeout_ms": 120000,
        },
        "metadata_extensions": {
            "agent_code": "PRAGYA",
            "surface": "account_manager",
            # The inward voice face. `route_for_number` reads the assignment
            # from `phone_numbers`, not from here; this is documentation.
            "voice_face": "inward",
        },
    }


async def find_pragya(
    db: AsyncSession, company_id: uuid.UUID,
) -> Optional[HierarchicalEntity]:
    """This company's Pragya, or None. Name-matched, as the resolvers are."""
    from sqlalchemy import or_

    return (await db.execute(
        select(HierarchicalEntity).where(
            HierarchicalEntity.company_id == company_id,
            HierarchicalEntity.type == "AGENT",
            HierarchicalEntity.deleted_at.is_(None),
            or_(*[HierarchicalEntity.name.ilike(f"%{n}%")
                  for n in PRAGYA_ENTITY_NAMES]),
        ).limit(1)
    )).scalars().first()


async def seed_pragya(
    db: AsyncSession, company_id: uuid.UUID,
) -> tuple[HierarchicalEntity, bool]:
    """Ensure this company has a Pragya. Returns ``(entity, created)``.

    **Idempotent by name**, matching the same predicate the resolvers use — so
    a second call finds the first call's entity rather than seeding a rival
    that `pragya_entity_for`'s ``.limit(1)`` would then pick between
    arbitrarily. Does not commit; the caller owns the transaction.
    """
    existing = await find_pragya(db, company_id)
    if existing is not None:
        return existing, False

    template = pragya_template()
    entity = HierarchicalEntity(
        id=uuid.uuid4(),
        company_id=company_id,
        parent_id=None,          # she is a root — her children hang off her
        type=template["type"],
        status=template["status"],
        name=template["name"],
        display_name=template["display_name"],
        description=template["description"],
        goal=template["goal"],
        tags=template["tags"],
        is_template=False,
        capabilities=template["capabilities"],
        governance=template["governance"],
        metadata_extensions=template["metadata_extensions"],
        version=template["version"],
    )
    db.add(entity)
    await db.flush()
    logger.info("seeded Pragya for company %s (%s)", company_id, entity.id)
    return entity, True


async def seed_pragya_everywhere(db: AsyncSession) -> dict[str, Any]:
    """Seed a Pragya for every active tenant. Returns a tally.

    Tenants only: an APP or PARTNER company is not a business with an owner who
    needs a steward, and giving one a Pragya would put an account manager in
    front of the platform's own books.
    """
    from sqlalchemy import text as _text

    company_ids = [r[0] for r in (await db.execute(_text(
        "SELECT id FROM companies WHERE type = 'TENANT' AND status = 'active'"
    ))).all()]

    created = 0
    for company_id in company_ids:
        _entity, was_created = await seed_pragya(db, company_id)
        created += 1 if was_created else 0
    return {"companies": len(company_ids), "created": created,
            "already_present": len(company_ids) - created}
