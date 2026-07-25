"""connectors/router.py — the company-scoped connector admin API (CONN T8).

Catalog + binding management + the owner-gated ownership-migration two-step.
Secrets never leave the server: a binding view reports *whether* a credential is
set, never the credential. The React connector surface is a separate FE track;
this is the contract it calls.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.connectors.catalog import CONNECTOR_CATALOG
from src.ai.connectors.models import ConnectorBinding
from src.ai.connectors.service import (
    ConnectorNotBindable,
    ConnectorService,
    UnknownConnector,
)
from src.ai.connectors.sor_migration import (
    MigrationError,
    apply_migration,
    propose_migration,
)
from src.ai.inward_auth.guard import enforce_kind
from src.ai.inward_auth.tiers import IntentKind
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/connectors", tags=["Connectors"])


class BindRequest(BaseModel):
    credentials: dict[str, Any] = {}
    transport_config: dict[str, Any] | None = None
    tool_allow: list[str] = []
    write_allow: list[str] | None = None


class MigrateRequest(BaseModel):
    to_master: str
    connector_id: str | None = None


def _binding_view(b: ConnectorBinding) -> dict[str, Any]:
    """A safe projection of a binding — status + policy, never the secret."""
    return {
        "connector_id": b.connector_id,
        "status": b.status,
        "cost_sku": b.cost_sku,
        "tool_allow": list(b.tool_allow or []),
        "write_allow": list(b.write_allow or []),
        "has_credential": bool(b.encrypted_secret),
        "last_error": b.last_error,
    }


@router.get("/catalog")
async def get_catalog(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """The §6.6 catalog: every bindable connector, its backend, and what it masters."""
    return [
        {
            "connector_id": c.connector_id, "domain": c.domain,
            "display_name": c.display_name, "backend": c.backend.value,
            "auth": c.auth.value, "masters": list(c.masters), "bindable": c.bindable,
        }
        for c in CONNECTOR_CATALOG
    ]


@router.get("/bindings")
async def get_bindings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """The tenant's current bindings and their status."""
    bindings = await ConnectorService(db).list_bindings(cast(uuid.UUID, current_user.company_id))
    return [_binding_view(b) for b in bindings]


@router.post("/{connector_id}/bind")
async def bind(
    connector_id: str,
    body: BindRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Activate (or re-activate) a connector for the tenant.

    T2 (VG-05): this route receives live third-party credentials and declares
    what the connector may write back. Handing an external system the right to
    act for the tenant is a certified surface, per Vihara §15.2.
    """
    await enforce_kind(
        db, current_user, IntentKind.CONNECTOR_BINDING,
        command_ref=f"connector-bind:{connector_id}",
        command_summary=f"connecting {connector_id} and giving it write access")
    try:
        binding = await ConnectorService(db).activate(
            cast(uuid.UUID, current_user.company_id), connector_id,
            credentials=body.credentials, transport_config=body.transport_config,
            tool_allow=body.tool_allow, write_allow=body.write_allow,
        )
    except UnknownConnector:
        raise HTTPException(status_code=404, detail=f"unknown connector {connector_id}")
    except ConnectorNotBindable:
        raise HTTPException(status_code=400, detail=f"{connector_id} is not bindable")
    return _binding_view(binding)


@router.post("/{connector_id}/pause")
async def pause(
    connector_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    binding = await ConnectorService(db).pause(
        cast(uuid.UUID, current_user.company_id), connector_id)
    if binding is None:
        raise HTTPException(status_code=404, detail=f"no binding for {connector_id}")
    return _binding_view(binding)


@router.get("/{connector_id}/status")
async def connector_status(
    connector_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    binding = await ConnectorService(db).get_binding(
        cast(uuid.UUID, current_user.company_id), connector_id)
    if binding is None:
        raise HTTPException(status_code=404, detail=f"no binding for {connector_id}")
    return _binding_view(binding)


@router.post("/master/{def_name}/propose")
async def propose_master_migration(
    def_name: str,
    body: MigrateRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Step 1 of the §21.4 ownership migration — the plan, for the owner to confirm."""
    try:
        plan = await propose_migration(
            cast(uuid.UUID, current_user.company_id), def_name, body.to_master,
            connector_id=body.connector_id)
    except MigrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return asdict(plan)


@router.post("/master/{def_name}/apply")
async def apply_master_migration(
    def_name: str,
    body: MigrateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Step 2 — execute the owner-confirmed flip (never implicit).

    T2 (VG-05): the flip changes which system is the master of record for an
    HBS object — Vihara §15.2 calls the mastering declaration a certified tray.
    Step 1 (``/propose``) stays ungated: a plan is a read.
    """
    await enforce_kind(
        db, current_user, IntentKind.CONNECTOR_BINDING,
        command_ref=f"master-apply:{def_name}",
        command_summary=f"changing which system masters {def_name}")
    try:
        result = await apply_migration(
            cast(uuid.UUID, current_user.company_id), def_name, body.to_master,
            connector_id=body.connector_id)
    except MigrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return asdict(result)
