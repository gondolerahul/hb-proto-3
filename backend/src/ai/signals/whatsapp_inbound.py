"""signals/whatsapp_inbound.py — the WhatsApp channel producer (§18.2, KAR).

The messaging counterpart to ``email_poll``: an inbound WhatsApp message becomes
a ``message.inbound`` signal (``trust: counterparty``) so the KAR-03 gateway can
parse it as data and route it into the governed loop — instead of the legacy
direct-Gemini reply.

**Subscription-gated**, exactly like the email poller: a tenant's messages only
enter the bus when it has an enabled trigger covering ``message.inbound`` (i.e.
the Solo Pack / a bundle is activated). A tenant not on SIG falls through to the
legacy path untouched — this is the cutover seam, not a rewrite. **SID dedupe**:
``dedupe_key`` = the provider message id, so webhook retries never double-emit.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.signals.models import (
    SignalSource,
    SignalTrust,
    SignalTypes,
    TriggerRegistration,
)
from src.ai.signals.service import emit_signal, enqueue_dispatch
from src.ai.signals.triggers import pattern_matches

logger = logging.getLogger(__name__)

BODY_TRUNCATE_CHARS = 5000  # match the email producer's context cap

__all__ = ["emit_whatsapp_inbound", "company_subscribes"]


def _clean_number(number: str) -> str:
    """Normalise a channel address: Twilio sends ``whatsapp:+1…``, Tata ``1…``."""
    return (number or "").replace("whatsapp:", "").lstrip("+").strip()


async def company_subscribes(
    db: AsyncSession, company_id: uuid.UUID, signal_type: str,
) -> bool:
    """True when the company has an enabled trigger covering ``signal_type``."""
    rows = (await db.execute(
        select(TriggerRegistration).where(
            TriggerRegistration.company_id == company_id,
            TriggerRegistration.enabled.is_(True),
        )
    )).scalars().all()
    return any(pattern_matches(r.type_pattern, signal_type) for r in rows)


async def emit_whatsapp_inbound(
    db: AsyncSession, company_id: uuid.UUID, *, from_number: str, to_number: str,
    body: Optional[str], message_sid: Optional[str] = None, provider: str = "twilio",
    redis: Any = None,
) -> Optional[uuid.UUID]:
    """Emit ``message.inbound`` for an inbound WhatsApp message, if subscribed.

    Returns the signal id (the message entered the governed bus) or ``None``
    (the tenant isn't on SIG for messaging → the caller keeps its legacy path,
    or the message deduped). Commits on emit and enqueues dispatch.
    """
    if not await company_subscribes(db, company_id, SignalTypes.MESSAGE_INBOUND):
        return None

    customer = _clean_number(from_number)
    business = _clean_number(to_number)
    dedupe = (f"whatsapp:{provider}:{message_sid}" if message_sid
              else f"whatsapp:{provider}:{customer}:{business}")
    signal_id = await emit_signal(
        db,
        company_id=company_id,
        source=SignalSource.CONNECTOR,
        type=SignalTypes.MESSAGE_INBOUND,
        trust=SignalTrust.COUNTERPARTY,
        payload={
            "channel": "whatsapp",
            "provider": provider,
            "from": customer,
            "to": business,
            "message_sid": message_sid,
            "body": (body or "")[:BODY_TRUNCATE_CHARS],
        },
        dedupe_key=dedupe,
    )
    await db.commit()
    if signal_id is None:
        return None  # deduped (webhook retry)

    if redis is not None:
        await enqueue_dispatch(redis, signal_id)
    else:
        await _enqueue_own(signal_id)
    logger.info("WhatsApp inbound → message.inbound signal %s (company %s)",
                signal_id, company_id)
    return signal_id


async def _enqueue_own(signal_id: uuid.UUID) -> None:
    """Enqueue dispatch on a short-lived Redis connection (webhook has none)."""
    import redis.asyncio as aioredis

    from src.common.config import settings

    redis_pool = aioredis.from_url(  # type: ignore[no-untyped-call]
        settings.REDIS_URL or "redis://localhost:6379")
    try:
        await enqueue_dispatch(redis_pool, signal_id)
    finally:
        await redis_pool.aclose()
