"""evolution/schema_proposals.py — an agent asks for a field it keeps needing (T8).

Technical §10.2's dynamic-schema evolution, SEGA's half: an agent that
repeatedly needs a field the HBS object lacks proposes one, and applying it is
an **additive** tenant-schema change under the same blast-radius limits as a
charter tune.

**Additive only. Never drop, never retype, never rename — at any autonomy
band.** A dropped column is data loss that no rollback recovers: the version
ledger can restore an entity's *definition*, but nothing can restore records
whose values were deleted with the field. Retyping and renaming are the same
loss wearing a friendlier name — every existing record's value becomes either
invalid or unreachable. So these are not gated, they are absent: there is no
code path that expresses them.

**A design correction (2026-07-25).** §8 of the design said this lands "through
the shipped ``data_plane._sync_columns`` primitive". It does not, because it
needs no DDL at all: a tenant object's fields live in
``TenantEntityDef.fields``, a JSONB list, and its records are JSONB documents
in ``TenantRecord.data``. Adding a field is a JSON append and a version bump.
``_sync_columns`` manages the Inc-4 SoR *mirror* columns and is unrelated —
worth stating, because the design's sentence would send a reader looking for a
migration that should not exist.

Design: docs/product-road-map/increment-6/02_sega.md §8.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.evolution.blast_radius import (
    BlastRadiusError,
    ChangeKind,
    ChangeRequest,
    Limits,
    admit_change,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PROPOSABLE_TYPES",
    "SchemaProposalError",
    "validate_addition",
    "apply_field_proposal",
]


class SchemaProposalError(Exception):
    """The proposed field is not an additive, well-formed addition."""


#: The field types an agent may propose — the shipped closed set from
#: ``tenant_schema/validation._SCALAR_CHECKS`` and the HBS spine, **minus**
#: ``ref``. A ``ref`` field creates an edge in the object graph and materialises
#: rows in ``tenant_record_links``; proposing relationships between business
#: objects is a modelling decision, not a missing column, and it belongs to a
#: human.
PROPOSABLE_TYPES: frozenset[str] = frozenset({
    "string", "text", "integer", "decimal", "boolean", "date", "datetime",
    "enum", "money", "email", "phone", "url", "json",
})

_MAX_FIELDS_PER_OBJECT = 60


def validate_addition(
    existing: list[dict[str, Any]], proposed: dict[str, Any],
) -> dict[str, Any]:
    """Check one proposed field against the object's current fields. Pure.

    Returns the normalised descriptor. Raises ``SchemaProposalError`` on
    anything that is not a clean addition — including a name that already
    exists, which is the case that would otherwise become a silent *retype*.
    """
    name = str(proposed.get("name") or "").strip()
    if not name:
        raise SchemaProposalError("a proposed field needs a name")
    if not name.replace("_", "").isalnum() or not name[0].isalpha():
        raise SchemaProposalError(
            f"`{name}` is not a usable field name (letters, digits, underscores; "
            "must start with a letter)")

    taken = {str(f.get("name")) for f in existing}
    if name in taken:
        # The important refusal: "adding" an existing name is a retype in
        # disguise, and a retype invalidates every record already holding a
        # value for it.
        raise SchemaProposalError(
            f"`{name}` already exists — changing an existing field's type is "
            "not additive and is never automated")

    ftype = str(proposed.get("type") or "string")
    if ftype not in PROPOSABLE_TYPES:
        raise SchemaProposalError(
            f"`{ftype}` is not a proposable type {sorted(PROPOSABLE_TYPES)}")

    if len(existing) >= _MAX_FIELDS_PER_OBJECT:
        raise SchemaProposalError(
            f"this object already carries {len(existing)} fields; a schema that "
            "grows without bound stops being a schema")

    descriptor: dict[str, Any] = {"name": name, "type": ftype}
    if ftype == "enum":
        values = proposed.get("values")
        if not isinstance(values, list) or not values:
            raise SchemaProposalError("an enum field needs a non-empty `values` list")
        descriptor["values"] = [str(v) for v in values]

    # A proposed field is **never required**. Making it required would
    # retroactively invalidate every record that predates it — the same data
    # loss as a retype, arriving as a validation error on the next write.
    descriptor["required"] = False
    if proposed.get("description"):
        descriptor["description"] = str(proposed["description"])
    return descriptor


async def apply_field_proposal(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    object_name: str,
    proposed: dict[str, Any],
    changes_today: int = 0,
    subscription_status: str = "current",
    limits: Limits | None = None,
) -> dict[str, Any]:
    """Add a field to a tenant object. ``db`` must be a **tenant-plane** session.

    Raises ``BlastRadiusError`` when the change is not admitted and
    ``SchemaProposalError`` when the field itself is not a clean addition. The
    caller commits.

    The blast-radius predicate is asked first even though the field check is
    cheaper: a tenant who is suspended, or who has hit the daily change cap,
    should be told *that* — not handed a critique of a field they were never
    going to get.
    """
    from src.ai.tenant_schema.models import TenantEntityDef

    admit_change(
        ChangeRequest(
            kind=ChangeKind.SCHEMA_PROPOSAL,
            initiator_company_id=company_id,
            target_company_id=company_id,
            fields=("fields",),
            changes_today=changes_today,
            canary_fraction=0.0,     # a schema addition is not canaried
            subscription_status=subscription_status,
        ),
        limits or Limits(),
    )

    definition = (await db.execute(
        select(TenantEntityDef).where(
            TenantEntityDef.company_id == company_id,
            TenantEntityDef.name == object_name,
        )
    )).scalar_one_or_none()
    if definition is None:
        raise SchemaProposalError(f"no object named `{object_name}` in this tenant")

    existing = list(definition.fields or [])
    descriptor = validate_addition(existing, proposed)

    # Reassign rather than mutate in place: SQLAlchemy does not track mutations
    # inside a JSONB list, so an `.append()` would be silently discarded.
    definition.fields = [*existing, descriptor]
    definition.version = int(definition.version or 1) + 1
    return descriptor


async def emit_field_proposed(
    db: AsyncSession, *, company_id: uuid.UUID, object_name: str,
    descriptor: dict[str, Any], entity_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Audit the addition on the bus. ``db`` here is a **control-plane** session.

    Two sessions, deliberately: records live in the tenant plane and signals in
    the control plane, and the repo convention is explicit that a cross-plane
    emit goes through its own transaction — never assume one spans both.
    """
    from src.ai.signals.models import SignalSource, SignalTypes
    from src.ai.signals.service import emit_signal

    return await emit_signal(
        db,
        company_id=company_id,
        source=SignalSource.AGENT,
        type=SignalTypes.GOVERNANCE_SCHEMA_FIELD_PROPOSED,
        payload={"object": object_name, "field": descriptor,
                 "entity_id": str(entity_id) if entity_id else None},
        object_refs=[f"object:{object_name}"],
        dedupe_key=f"schema.field:{company_id}:{object_name}:{descriptor['name']}",
    )
