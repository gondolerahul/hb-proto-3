"""genui/router.py — the /ai/genui surface (D5 §1).

The registry read, the estate read model and the district detail; the stream,
trays, echo and push endpoints land beside them task by task. Everything here
is company-scoped from the session where a company is involved at all — no
endpoint accepts a ``company_id`` parameter (D5 §2.2, the VG-05 lesson
applied before the fact).
"""
from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.genui.estate import district_view, estate_view
from src.ai.genui.registry import registry_payload, registry_version
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.common.database import get_db

router = APIRouter(prefix="/ai/genui", tags=["Vihara GenUI"])


@router.get("/registry")
async def get_registry(
    if_none_match: str | None = Header(None),
    current_user: User = Depends(get_current_user),
) -> Response:
    """The component registry, long-cached by content hash.

    The registry is global data (component contracts, not tenant state), so
    the only scoping is authentication itself. The ETag is the registry's
    content hash; a client holding the current version pays a 304, and the
    version participates in the manifest cache key so a registry change
    invalidates every cached composition (D4 §5).
    """
    version = registry_version()
    if if_none_match is not None and if_none_match.strip('"') == version:
        return Response(status_code=304, headers=_cache_headers(version))
    return JSONResponse(registry_payload(), headers=_cache_headers(version))


def _cache_headers(version: str) -> dict[str, str]:
    return {
        "ETag": f'"{version}"',
        "Cache-Control": "private, max-age=3600",
    }


@router.get("/estate")
async def get_estate(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The estate read model (VG-02). Company from the session, never a
    parameter — cross-tenant access is not expressible on this surface."""
    return await estate_view(db, cast(uuid.UUID, current_user.company_id))


@router.get("/estate/district/{process_code}")
async def get_district(
    process_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One district. 404 when this company has no such process — the same
    answer a cross-tenant probe gets, so a probe learns nothing."""
    district = await district_view(
        db, cast(uuid.UUID, current_user.company_id), process_code)
    if district is None:
        raise HTTPException(status_code=404, detail="District not found")
    return district
