"""genui/push.py — Web Push, self-hosted (VG-19, charter decision 7).

A subscription is a row in our own table; VAPID keys are our own settings;
there is no vendor, no SDK fee, and revocation is an UPDATE.

**L8's single-writer law is structural.** ``send_tray_push`` — the only
function that can reach a device — may be imported by exactly one module,
Pragya's tray delivery (``genui/channel.py``), and an import-boundary test
fails the build on any other import (the ``pragya/acting.py`` precedent).
**A push is a tray or it does not exist**: the payload type carries only
``tray_id`` and ``one_sentence``, so a digest path, an engagement path or an
"N updates" path is not forbidden — it is unimplementable.

The wire call itself rides behind an injectable transport (the FLEET/TWIN/
LIB precedent: no test may reach a live endpoint); the default transport is
``pywebpush``. A 404/410 from a push service means the browser forgot the
subscription — the row is revoked in place, because a dead endpoint that
stays "active" is a silent, permanent notification outage for that device.

Stated ceiling (D5 §7): on iOS, push exists only after the PWA is
installed; an uninstalled visitor gets the thread without notifications.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.genui.models import PushSubscription
from src.common.config import settings

logger = logging.getLogger(__name__)

#: transport(endpoint, keys, payload_json, vapid_private_key, vapid_claims)
#: -> HTTP status code. Injectable; the default wraps pywebpush.
PushTransport = Callable[[str, dict[str, str], str, str, dict[str, str]], int]


async def subscribe(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    ua: str | None = None,
) -> PushSubscription:
    """Idempotent on the endpoint: a browser re-subscribing (or a revoked
    endpoint coming back) revives and re-keys the existing row rather than
    erroring — the browser owns the endpoint's identity, not us."""
    existing = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == endpoint))
    ).scalar_one_or_none()
    if existing is not None:
        existing.company_id = company_id
        existing.user_id = user_id
        existing.p256dh = p256dh
        existing.auth = auth
        existing.ua = ua
        existing.revoked_at = None
        await db.commit()
        await db.refresh(existing)
        return existing

    subscription = PushSubscription(
        company_id=company_id, user_id=user_id,
        endpoint=endpoint, p256dh=p256dh, auth=auth, ua=ua)
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return subscription


async def unsubscribe(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    subscription_id: uuid.UUID,
) -> bool:
    """Revoke one of *this user's* subscriptions. False for unknown and
    foreign ids alike — the probe rule."""
    row = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.id == subscription_id,
                PushSubscription.company_id == company_id,
                PushSubscription.user_id == user_id,
            ))
    ).scalar_one_or_none()
    if row is None:
        return False
    row.revoked_at = datetime.utcnow()
    await db.commit()
    return True


async def send_tray_push(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    tray_id: str,
    one_sentence: str,
    transport: PushTransport | None = None,
) -> int:
    """Deliver one tray to every live device of one user. Returns the number
    of devices reached. **The only sender** — see the module docstring; a
    new caller is a build failure, not a review comment."""
    import json

    transport = transport or _pywebpush_transport
    claims = {"sub": settings.VIHARA_VAPID_SUBJECT}
    payload = json.dumps({"tray_id": tray_id, "one_sentence": one_sentence})

    rows = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.company_id == company_id,
                PushSubscription.user_id == user_id,
                PushSubscription.revoked_at.is_(None),
            ))
    ).scalars().all()

    delivered = 0
    for row in rows:
        try:
            status = transport(
                row.endpoint, {"p256dh": row.p256dh, "auth": row.auth},
                payload, settings.VIHARA_VAPID_PRIVATE_KEY, claims)
        except Exception:  # noqa: BLE001 — one dead device must not stop the rest
            logger.warning("push delivery failed for %s", row.id, exc_info=True)
            continue
        if status in (404, 410):
            # The push service forgot this subscription; an "active" row for
            # a dead endpoint is a silent permanent outage for that device.
            row.revoked_at = datetime.utcnow()
        elif 200 <= status < 300:
            delivered += 1
    await db.commit()
    return delivered


def _pywebpush_transport(
    endpoint: str,
    keys: dict[str, str],
    payload: str,
    vapid_private_key: str,
    vapid_claims: dict[str, str],
) -> int:
    from pywebpush import WebPushException, webpush

    try:
        response = webpush(
            subscription_info={"endpoint": endpoint, "keys": keys},
            data=payload,
            vapid_private_key=vapid_private_key,
            vapid_claims=dict(vapid_claims),
        )
        return int(response.status_code)
    except WebPushException as exc:  # pragma: no cover — wire-level only
        if exc.response is not None:
            return int(exc.response.status_code)
        raise
