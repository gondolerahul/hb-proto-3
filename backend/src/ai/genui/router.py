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

from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.ai.genui.echo import record_echo, validate_echo
from src.ai.genui.estate import district_view, estate_view
from src.ai.genui.manifest import (
    ManifestRefused,
    UnknownSurface,
    cached_compose,
    stream_manifest,
)
from src.ai.genui.push import subscribe, unsubscribe
from src.ai.genui.registry import registry_payload, registry_version
from src.ai.genui.stream import stream_events
from src.ai.genui.trays import tray_detail, tray_list
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


@router.get("/trays")
async def get_trays(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Every pending tray, oldest first (VG-04) — spec §6.1's composed object,
    not the raw approval rows."""
    return await tray_list(db, cast(uuid.UUID, current_user.company_id))


@router.get("/trays/{tray_id}")
async def get_tray(
    tray_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One tray. 404 on unknown *and* cross-tenant alike — a probe must not
    learn that an id exists in another tenant."""
    tray = await tray_detail(
        db, cast(uuid.UUID, current_user.company_id), tray_id)
    if tray is None:
        raise HTTPException(status_code=404, detail="Tray not found")
    return tray


@router.get("/stream")
async def get_stream(
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """The company-scoped live stream (VG-03). The company is fixed here,
    at connect, from the session — the emitter never sees a selector. Every
    (re)connect begins with a beacon snapshot; sampled states follow as
    diffs (see stream.py's replay note)."""
    return StreamingResponse(
        stream_events(cast(uuid.UUID, current_user.company_id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/manifest")
async def get_manifest(
    surface: str,
    renderer: str = "S",
    density: str = "novice",
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """A manifest, streamed in two parts (D4 §6): the scaffold line paints,
    the fill line hydrates. Compositions are pure shapes — tenant data
    arrives only through bindings — so this endpoint touches no tenant
    state and the intent-shape cache is shared safely across tenants."""
    if renderer not in ("S", "C", "W"):
        raise HTTPException(status_code=422, detail="renderer must be S, C or W")
    if density not in ("novice", "operator"):
        raise HTTPException(status_code=422, detail="unknown density")
    try:
        manifest, was_cached = await cached_compose(
            surface, renderer=renderer, density=density)
    except UnknownSurface:
        raise HTTPException(status_code=404, detail="Unknown surface")
    except ManifestRefused as refusal:
        # Our own composition failed its own validation — fail loudly, never
        # emit what a renderer would have to discover (D3 §7).
        raise HTTPException(status_code=500, detail=str(refusal))
    return StreamingResponse(
        stream_manifest(manifest),
        media_type="application/x-ndjson",
        headers={"X-Manifest-Cache": "hit" if was_cached else "miss"},
    )


class EchoBody(BaseModel):
    sentence: str
    action_ref: dict[str, Any]
    manifest_hash: str | None = None
    component_id: str | None = None
    occurred_at: str | None = None


@router.post("/echo", status_code=201)
async def post_echo(
    body: EchoBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record one manual act's sentence (L10, VG-06).

    An echo describes an act that already happened; it never causes one —
    this endpoint takes no authority and triggers nothing. A 422 here means
    the payload was not an echo, not that the act failed.
    """
    payload = body.model_dump()
    problem = validate_echo(payload)
    if problem is not None:
        raise HTTPException(status_code=422, detail=problem)
    echo = await record_echo(
        db, cast(uuid.UUID, current_user.company_id),
        cast(uuid.UUID, current_user.id), payload)
    return {"echo_id": str(echo.id)}


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionBody(BaseModel):
    endpoint: str
    keys: PushKeys
    ua: str | None = None


@router.post("/push/subscriptions", status_code=201)
async def post_push_subscription(
    body: PushSubscriptionBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Register this device for tray pushes (VG-19). Idempotent on the
    endpoint — a browser re-subscribing revives its row."""
    subscription = await subscribe(
        db, cast(uuid.UUID, current_user.company_id),
        cast(uuid.UUID, current_user.id),
        endpoint=body.endpoint, p256dh=body.keys.p256dh,
        auth=body.keys.auth, ua=body.ua)
    return {"id": str(subscription.id)}


@router.delete("/push/subscriptions/{subscription_id}", status_code=204)
async def delete_push_subscription(
    subscription_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke one of your subscriptions. 404 for unknown and foreign alike."""
    revoked = await unsubscribe(
        db, cast(uuid.UUID, current_user.company_id),
        cast(uuid.UUID, current_user.id), subscription_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return Response(status_code=204)


@router.get("/push/vapid-public-key")
async def get_vapid_public_key(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """The public half of our VAPID pair (LINE L4) — the push client needs
    it to subscribe. Public by nature; authenticated anyway because nothing
    on this surface answers anonymously."""
    from src.common.config import settings

    key = settings.VIHARA_VAPID_PUBLIC_KEY
    return {"key": key or None, "configured": bool(key)}


@router.get("/line/morning")
async def get_morning_story(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Today's Morning Story (LINE L1, VG-20). The stored telling when the
    job has run — its audio aligned to its cards — else composed fresh,
    text-only, the absence named."""
    from src.ai.genui.morning import morning_story

    return await morning_story(db, cast(uuid.UUID, current_user.company_id))
