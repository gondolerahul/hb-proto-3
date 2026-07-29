"""genui/router.py — the /ai/genui surface (D5 §1).

Starts with the registry read; the estate, stream, trays, echo and push
endpoints land beside it task by task. Everything here is company-scoped from
the session where a company is involved at all — no endpoint accepts a
``company_id`` parameter (D5 §2.2, the VG-05 lesson applied before the fact).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse

from src.ai.genui.registry import registry_payload, registry_version
from src.auth.dependencies import get_current_user
from src.auth.models import User

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
