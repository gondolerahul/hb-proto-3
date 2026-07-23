"""pragya/children.py — Pragya's capability surface (Inc-4 T9, decision 6).

**Pragya proposes no raw tools.** Her surface is her *child entities*: the
Meta-Agent, and later a family of purpose-built children that wrap tools —
deep research, tenant record and document access, scheduling and assignment to
other agents.

Three properties fall out of that choice, and they are why it beats a curated
tool allowlist:

* **Governed where governance already lives.** A child is a
  ``hierarchical_entities`` row with autonomy, authority bands, SoD class and
  memory domains. A tool allowlist carries none of that, so an allowlist would
  have needed a second, weaker governance story bolted beside the real one.
* **One mechanism, not two.** Calling a child *is* dispatching a run, which is
  exactly what ``delegation.py`` does. "Tools" and "delegation" stop being
  separate concepts.
* **Extensible without touching her.** A new capability is a new child entity.
  Nothing in Pragya's loop changes when the deep-research child ships.

The schema handed to the model is generated **from the entities that actually
exist** for this tenant, so she can never propose a capability the tenant does
not have. A model that cannot name a thing cannot promise it.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.orm.entity import HierarchicalEntity

logger = logging.getLogger(__name__)

__all__ = [
    "CALL_CHILD_TOOL",
    "ChildCapability",
    "PRAGYA_ENTITY_NAMES",
    "schema_name_for_child",
    "available_children",
    "child_schemas",
    "resolve_child",
]

CALL_CHILD_TOOL = "ask_colleague"

#: How Pragya's own entity is recognised when a tenant has one seeded. Her
#: children are the entities parented to it.
PRAGYA_ENTITY_NAMES = ("pragya", "account-manager", "account_manager")

#: Entity types that can be *asked to do something*. A SKILL or ACTION is a
#: fragment of work, not a colleague with a job.
_CALLABLE_TYPES = frozenset({"AGENT", "PROCESS"})

_SAFE_NAME = re.compile(r"[^a-z0-9_]+")


def schema_name_for_child(entity: HierarchicalEntity) -> str:
    """A stable, model-friendly handle for a child entity."""
    raw = str(entity.name or entity.display_name or entity.id).lower()
    return _SAFE_NAME.sub("_", raw).strip("_")[:60]


@dataclass(frozen=True)
class ChildCapability:
    """A child entity Pragya may hand work to."""

    entity_id: uuid.UUID
    handle: str
    display_name: str
    description: str

    def as_option(self) -> dict[str, Any]:
        return {"handle": self.handle, "name": self.display_name,
                "does": self.description}


async def available_children(
    db: AsyncSession, company_id: uuid.UUID,
) -> list[ChildCapability]:
    """The children Pragya may call for this tenant.

    Resolution is deliberately forgiving about *where* they hang: a tenant
    with a seeded Pragya entity has them parented to her, and one without
    still has a Meta-Agent. Requiring a particular tree shape would mean
    Pragya silently losing every capability on a tenant whose hierarchy was
    seeded slightly differently.
    """
    pragya = (await db.execute(
        select(HierarchicalEntity).where(
            HierarchicalEntity.company_id == company_id,
            or_(*[HierarchicalEntity.name.ilike(f"%{n}%")
                  for n in PRAGYA_ENTITY_NAMES]),
        ).limit(1)
    )).scalars().first()

    stmt = select(HierarchicalEntity).where(
        HierarchicalEntity.company_id == company_id,
        HierarchicalEntity.type.in_(_CALLABLE_TYPES),
        HierarchicalEntity.status == "ACTIVE",
    )
    stmt = (stmt.where(HierarchicalEntity.parent_id == pragya.id)
            if pragya is not None
            else stmt.where(HierarchicalEntity.name.ilike("%meta%agent%")))

    rows = (await db.execute(stmt)).scalars().all()

    children: list[ChildCapability] = []
    for row in rows:
        children.append(ChildCapability(
            entity_id=uuid.UUID(str(row.id)),
            handle=schema_name_for_child(row),
            display_name=str(row.display_name or row.name),
            description=str(row.description or row.goal or
                            "a colleague who can take on work"),
        ))
    return children


def child_schemas(children: list[ChildCapability]) -> list[dict[str, Any]]:
    """The tool schema Pragya sees — one ``ask_colleague`` over the children.

    A single tool with an enumerated ``colleague`` rather than one tool per
    child: the enum is what makes proposing a non-existent colleague
    impossible at the schema level, instead of something to validate after
    the fact.

    Returns ``[]`` when the tenant has no children, so Pragya is handed no
    capability tool at all rather than one she cannot use.
    """
    if not children:
        return []

    return [{
        "name": CALL_CHILD_TOOL,
        "description": (
            "Hand a piece of work to one of your colleagues. Use this when "
            "something needs doing that you do not do yourself — research, "
            "pulling records, building a new capability. The work happens in "
            "the background: you will be told when it is done, so tell the "
            "owner it is underway rather than implying it is finished."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "colleague": {
                    "type": "string",
                    "enum": [c.handle for c in children],
                    "description": "\n".join(
                        f"{c.handle}: {c.display_name} — {c.description}"
                        for c in children),
                },
                "task": {
                    "type": "string",
                    "description": "What you need done, in a sentence. Be "
                                   "specific — they have your conversation "
                                   "but not your judgement about it.",
                },
                "subject": {
                    "type": "string",
                    "description": "A short noun phrase for what this is "
                                   "about, used when reporting back to the "
                                   "owner (e.g. 'your pricing').",
                },
            },
            "required": ["colleague", "task", "subject"],
        },
    }]


def resolve_child(
    children: list[ChildCapability], handle: str,
) -> ChildCapability | None:
    """Map a proposed handle back to a real entity, or ``None``.

    ``None`` is not an error path to smooth over: it means the model named a
    colleague that does not exist, and inventing a plausible substitute would
    hand work to the wrong entity.
    """
    for child in children:
        if child.handle == handle:
            return child
    logger.info("pragya proposed an unknown colleague %r", handle)
    return None
