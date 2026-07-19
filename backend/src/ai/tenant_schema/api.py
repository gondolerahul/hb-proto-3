"""tenant_schema/api.py — internal records/links API (Inc 1: API-only).

Company-scoped through the authenticated user; the single write path agents
reach (a record tool wraps it in Inc 2). All ops go through ``RecordService``,
so validation, ref materialisation, CAS, ownership, and soft delete apply
uniformly. Reads/writes route to the tenant's business DB via the data plane.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.ai.tenant_schema.data_plane import tenant_data_plane
from src.ai.tenant_schema.models import TenantEntityDef
from src.ai.tenant_schema.record_service import CONFLICT, RecordService
from src.ai.tenant_schema.validation import ValidationError

router = APIRouter(prefix="/ai/tenant", tags=["Tenant Schema"])


def _cid(user: User) -> uuid.UUID:
    """Normalise the legacy Column-typed company_id to a real UUID."""
    return uuid.UUID(str(user.company_id))


class RecordCreate(BaseModel):
    def_name: str
    data: dict[str, Any]
    actor_process_code: Optional[str] = None


class RecordUpdate(BaseModel):
    data: dict[str, Any]
    expected_version: int
    actor_process_code: Optional[str] = None


def _record_out(rec: Any) -> dict[str, Any]:
    return {
        "id": str(rec.id),
        "entity_def_id": str(rec.entity_def_id),
        "data": rec.data,
        "version": rec.version,
        "def_version": rec.def_version,
        "deleted_at": rec.deleted_at.isoformat() if rec.deleted_at else None,
        "created_at": rec.created_at.isoformat(),
    }


@router.get("/defs")
async def list_defs(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    cid = _cid(current_user)
    async with tenant_data_plane.session(cid) as ts:
        rows = (await ts.execute(
            select(TenantEntityDef).where(TenantEntityDef.company_id == cid)
            .order_by(TenantEntityDef.module, TenantEntityDef.name)
        )).scalars().all()
        return [
            {"name": d.name, "module": d.module, "domain_tag": d.domain_tag,
             "owner_process_code": d.owner_process_code, "version": d.version,
             "fields": d.fields}
            for d in rows
        ]


@router.get("/records")
async def list_records(
    def_name: str,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    cid = _cid(current_user)
    async with tenant_data_plane.session(cid) as ts:
        svc = RecordService(ts, cid)
        rows = await svc.list_records(def_name, limit=min(max(limit, 1), 500))
        return [_record_out(r) for r in rows]


@router.post("/records", status_code=201)
async def create_record(
    body: RecordCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    cid = _cid(current_user)
    async with tenant_data_plane.session(cid) as ts:
        svc = RecordService(ts, cid)
        try:
            res = await svc.create(body.def_name, body.data,
                                   actor_process_code=body.actor_process_code)
        except ValidationError as ve:
            raise HTTPException(422, {"error": "validation_failed", "detail": ve.errors})
        except ValueError as e:
            raise HTTPException(404, str(e))
        await ts.commit()
        return {"status": res.status,
                "record": _record_out(res.record) if res.record else None,
                "signal_id": str(res.signal_id) if res.signal_id else None,
                "reason": res.reason}


@router.get("/records/{record_id}")
async def get_record(
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    cid = _cid(current_user)
    async with tenant_data_plane.session(cid) as ts:
        svc = RecordService(ts, cid)
        rec = await svc.get(record_id)
        if rec is None:
            raise HTTPException(404, "Record not found")
        return _record_out(rec)


@router.patch("/records/{record_id}")
async def update_record(
    record_id: uuid.UUID,
    body: RecordUpdate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    cid = _cid(current_user)
    async with tenant_data_plane.session(cid) as ts:
        svc = RecordService(ts, cid)
        try:
            res = await svc.update(record_id, body.data,
                                   expected_version=body.expected_version,
                                   actor_process_code=body.actor_process_code)
        except ValidationError as ve:
            raise HTTPException(422, {"error": "validation_failed", "detail": ve.errors})
        except ValueError as e:
            raise HTTPException(404, str(e))
        if res.status != CONFLICT:
            await ts.commit()
        return {"status": res.status,
                "record": _record_out(res.record) if res.record else None,
                "signal_id": str(res.signal_id) if res.signal_id else None,
                "reason": res.reason}


@router.delete("/records/{record_id}")
async def delete_record(
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    cid = _cid(current_user)
    async with tenant_data_plane.session(cid) as ts:
        svc = RecordService(ts, cid)
        try:
            res = await svc.soft_delete(record_id)
        except ValueError as e:
            raise HTTPException(404, str(e))
        await ts.commit()
        return {"status": res.status}


@router.get("/export")
async def export_bundle(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """The portable tenant bundle: tenant DB + control-plane KB/memory (§23.4)."""
    from src.ai.tenant_schema.export_service import export_tenant

    return await export_tenant(_cid(current_user))


@router.get("/records/{record_id}/graph")
async def traverse_graph(
    record_id: uuid.UUID,
    rel_type: Optional[str] = None,
    depth: int = 1,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    cid = _cid(current_user)
    async with tenant_data_plane.session(cid) as ts:
        svc = RecordService(ts, cid)
        edges = await svc.traverse(record_id, rel_type=rel_type, depth=min(max(depth, 1), 5))
        return {"root": str(record_id), "edges": edges}
