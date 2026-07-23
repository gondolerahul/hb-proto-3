"""connectors/sor_migration.py — ownership migration, propose then confirm (§21.4).

Flipping an object's master — the tenant retires a CRM, or adopts one later — is
explicit and **never implicit**: :func:`propose_migration` returns the plan for
the owner to see; :func:`apply_migration` executes it only once an authenticated
owner has confirmed (the ``/ai/connectors`` router enforces that, T8). One
direction at a time:

* **external → hirebuddha** — each mirror is promoted to a native record (``sor``
  + ``external_ref`` cleared, the data kept); the object becomes HireBuddha-
  mastered.
* **hirebuddha → external** — the object is re-declared external; the sweep then
  imports the external truth into mirrors. Existing native records are left for
  the owner to reconcile, never silently overwritten.

Every applied flip emits ``governance.sor_migrated`` for the audit trail.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.connectors.catalog import connector_by_id
from src.ai.tenant_schema.models import TenantEntityDef, TenantRecord
from src.ai.tenant_schema.sor import sor_of

logger = logging.getLogger(__name__)

__all__ = [
    "MigrationError",
    "MigrationPlan",
    "MigrationResult",
    "propose_migration",
    "apply_migration",
]

_MASTERS = ("hirebuddha", "external")


class MigrationError(ValueError):
    """The requested migration is invalid (bad target, missing connector, no-op)."""


@dataclass(frozen=True)
class MigrationPlan:
    def_name: str
    from_master: str
    to_master: str
    connector_id: Optional[str]
    records_to_promote: int   # mirrors that would become native (external → hirebuddha)


@dataclass(frozen=True)
class MigrationResult:
    def_name: str
    from_master: str
    to_master: str
    records_affected: int


def _validate(to_master: str, connector_id: Optional[str]) -> None:
    if to_master not in _MASTERS:
        raise MigrationError(f"master must be one of {_MASTERS}, got {to_master!r}")
    if to_master == "external":
        if not connector_id:
            raise MigrationError("migrating to external master requires a connector_id")
        connector = connector_by_id(connector_id)
        if connector is None or not connector.bindable:
            raise MigrationError(f"{connector_id} is not a bindable connector")


async def _load_def(ts: AsyncSession, def_name: str) -> TenantEntityDef:
    d = (await ts.execute(
        select(TenantEntityDef).where(TenantEntityDef.name == def_name)
    )).scalar_one_or_none()
    if d is None:
        raise MigrationError(f"no def named {def_name!r}")
    return d


async def propose_migration(
    company_id: uuid.UUID, def_name: str, to_master: str, *, connector_id: Optional[str] = None,
) -> MigrationPlan:
    """Return the migration plan for the owner to confirm — no side effects."""
    _validate(to_master, connector_id)
    from src.ai.tenant_schema.data_plane import tenant_data_plane

    async with tenant_data_plane.session(company_id) as ts:
        d = await _load_def(ts, def_name)
        from_master = sor_of(d.sor).master
        if from_master == to_master:
            raise MigrationError(f"{def_name} is already {to_master}-mastered")
        to_promote = 0
        if to_master == "hirebuddha":
            to_promote = (await ts.execute(
                select(func.count()).select_from(TenantRecord).where(
                    TenantRecord.entity_def_id == d.id,
                    TenantRecord.sor.isnot(None),
                    TenantRecord.deleted_at.is_(None),
                )
            )).scalar_one()
    return MigrationPlan(def_name, from_master, to_master, connector_id, to_promote)


async def apply_migration(
    company_id: uuid.UUID, def_name: str, to_master: str, *, connector_id: Optional[str] = None,
) -> MigrationResult:
    """Execute an owner-confirmed migration; emit the audit signal."""
    _validate(to_master, connector_id)
    from src.ai.tenant_schema.data_plane import tenant_data_plane

    affected = 0
    async with tenant_data_plane.session(company_id) as ts:
        d = await _load_def(ts, def_name)
        from_master = sor_of(d.sor).master
        if from_master == to_master:
            raise MigrationError(f"{def_name} is already {to_master}-mastered")
        if to_master == "hirebuddha":
            mirrors = (await ts.execute(
                select(TenantRecord).where(
                    TenantRecord.entity_def_id == d.id,
                    TenantRecord.sor.isnot(None),
                    TenantRecord.deleted_at.is_(None),
                )
            )).scalars().all()
            for rec in mirrors:
                rec.sor = None
                rec.external_ref = None
                rec.version += 1
                affected += 1
            d.sor = {"master": "hirebuddha"}
        else:
            d.sor = {"master": "external", "connector_id": connector_id, "write_back": True}
        await ts.commit()

    await _emit_migrated(company_id, def_name, from_master, to_master, affected)
    return MigrationResult(def_name, from_master, to_master, affected)


async def _emit_migrated(
    company_id: uuid.UUID, def_name: str, from_master: str, to_master: str, affected: int,
) -> None:
    try:
        from src.ai.signals.models import SignalSource, SignalTrust, SignalTypes
        from src.ai.signals.service import emit_signal
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as cp:
            await emit_signal(
                cp, company_id=company_id, source=SignalSource.HUMAN,
                type=SignalTypes.GOVERNANCE_SOR_MIGRATED, trust=SignalTrust.INTERNAL,
                payload={"def": def_name, "from": from_master, "to": to_master,
                         "records_affected": affected},
            )
            await cp.commit()
    except Exception as exc:  # noqa: BLE001 — the audit emit must not fail the migration
        logger.warning("sor_migrated signal emit failed: %s", exc)
