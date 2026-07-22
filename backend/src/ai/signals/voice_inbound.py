"""signals/voice_inbound.py — the voice channel producer (§18.2, VOICE).

The telephony counterpart to ``whatsapp_inbound``: an inbound call becomes a
``voice.inbound`` signal (``trust: counterparty``) so the KAR-01 gateway can
treat what the caller says as *data* rather than instructions — the same
posture every Karuna gateway takes, and the reason a caller cannot talk the
platform into anything by asserting authority over the phone.

**Subscription-gated**, exactly like the email and WhatsApp producers: a
tenant's calls only enter the bus when it has an enabled trigger covering
``voice.inbound``. A tenant not on SIG keeps its legacy direct-to-realtime
path untouched. This is the cutover seam, not a rewrite.

**Call-SID dedupe**: a carrier retrying a webhook must not start two
conversations.

Note what this producer does *not* carry: it emits the call's *start*, not its
content. A live call's audio never becomes a signal — the realtime stack owns
the media, and the transcript reaches the loop through the deferred run
(``voice_loop.deferred``) once the call ends.
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
    SignalUrgency,
    TriggerRegistration,
)
from src.ai.signals.service import emit_signal, enqueue_dispatch
from src.ai.signals.triggers import pattern_matches

logger = logging.getLogger(__name__)

__all__ = ["emit_voice_inbound", "company_subscribes_voice"]


def _clean_number(number: str) -> str:
    """Digits-only, matching AUTH's voice binding normalisation."""
    return "".join(ch for ch in (number or "") if ch.isdigit())


async def company_subscribes_voice(
    db: AsyncSession, company_id: uuid.UUID,
    signal_type: str = SignalTypes.VOICE_INBOUND,
) -> bool:
    """True when the company has an enabled trigger covering ``signal_type``."""
    rows = (await db.execute(
        select(TriggerRegistration).where(
            TriggerRegistration.company_id == company_id,
            TriggerRegistration.enabled.is_(True),
        )
    )).scalars().all()
    return any(pattern_matches(r.type_pattern, signal_type) for r in rows)


async def emit_voice_inbound(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    from_number: str,
    to_number: str,
    call_sid: Optional[str] = None,
    provider: str = "twilio",
    direction: str = "inbound",
    redis: Any = None,
) -> Optional[uuid.UUID]:
    """Emit ``voice.inbound`` for a call that has just started, if subscribed.

    Returns the signal id, or ``None`` when the tenant is not on SIG for voice
    (the caller keeps its legacy path) or the webhook deduped.

    Urgency is ``high`` and not configurable: unlike an email or a message,
    there is a person holding a phone at the other end of this one.
    """
    if not await company_subscribes_voice(db, company_id):
        return None

    caller = _clean_number(from_number)
    business = _clean_number(to_number)
    dedupe = (f"voice:{provider}:{call_sid}" if call_sid
              else f"voice:{provider}:{caller}:{business}")

    signal_id = await emit_signal(
        db,
        company_id=company_id,
        source=SignalSource.CONNECTOR,
        type=SignalTypes.VOICE_INBOUND,
        trust=SignalTrust.COUNTERPARTY,
        urgency=SignalUrgency.HIGH,
        payload={
            "channel": "voice",
            "provider": provider,
            "from": caller,
            "to": business,
            "call_sid": call_sid,
            "direction": direction,
        },
        dedupe_key=dedupe,
    )
    await db.commit()
    if signal_id is None:
        return None  # deduped (carrier webhook retry)

    if redis is not None:
        await enqueue_dispatch(redis, signal_id)
    else:
        await _enqueue_own(signal_id)

    logger.info("voice inbound → voice.inbound signal %s (company %s)",
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
