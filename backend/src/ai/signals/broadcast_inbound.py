"""signals/broadcast_inbound.py — the social/broadcast channel producer (KAR-05).

The third Karuna channel producer, written to the same shape as
``whatsapp_inbound`` and ``voice_inbound`` deliberately: an inbound mention,
public comment or platform DM becomes a ``broadcast.inbound`` signal
(``trust: counterparty``) so the KAR-05 gateway parses it as data and routes it
into the governed loop.

**Subscription-gated**, like every other producer: a tenant's social
interactions only enter the bus when it has an enabled trigger covering
``broadcast.inbound``. A tenant without one is untouched — this is a cutover
seam, not a rewrite.

**Dedupe on the platform's own item id.** Every one of the sixteen platforms
gives comments, mentions and DMs a stable id, and polling re-reads the same
window constantly, so without this the same comment becomes a lead every cycle.
The key is scoped by platform because two platforms can and do issue the same
numeric id.

**No live platform call is made here** (GATE decision 5). The producer takes
already-fetched items; fetching them is a transport the caller injects, the
same posture Zoho (Inc 4) and the expansion fleet (Inc 5) carry.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.signals.models import (
    SignalSource,
    SignalTrust,
    SignalTypes,
)
from src.ai.signals.service import emit_signal, enqueue_dispatch
from src.ai.signals.whatsapp_inbound import company_subscribes

logger = logging.getLogger(__name__)

BODY_TRUNCATE_CHARS = 5000  # match the email + WhatsApp producers' context cap

__all__ = [
    "emit_broadcast_inbound",
    "emit_broadcast_published",
    "INTERACTION_KINDS",
]

#: What arrives on a broadcast channel. Carried on the payload so the gateway
#: can tell a public statement from a private one without re-deriving it: a
#: reply to a public comment is visible to everyone, and that is a materially
#: different act from answering a DM.
INTERACTION_KINDS = ("mention", "comment", "direct_message", "review")


async def emit_broadcast_inbound(
    db: AsyncSession, company_id: uuid.UUID, *, platform: str, item_id: str,
    body: Optional[str], author_handle: Optional[str] = None,
    kind: str = "comment", permalink: Optional[str] = None,
    parent_id: Optional[str] = None, redis: Any = None,
) -> Optional[uuid.UUID]:
    """Emit ``broadcast.inbound`` for one inbound social interaction, if subscribed.

    Returns the signal id (it entered the governed bus) or ``None`` (the tenant
    is not subscribed, or the item deduped). Commits on emit and enqueues
    dispatch, exactly like the other channel producers.
    """
    if not await company_subscribes(db, company_id, SignalTypes.BROADCAST_INBOUND):
        return None

    signal_id = await emit_signal(
        db,
        company_id=company_id,
        source=SignalSource.CONNECTOR,
        type=SignalTypes.BROADCAST_INBOUND,
        trust=SignalTrust.COUNTERPARTY,
        payload={
            "channel": "broadcast",
            "platform": platform,
            "kind": kind if kind in INTERACTION_KINDS else "comment",
            "item_id": item_id,
            "author_handle": author_handle,
            "permalink": permalink,
            "parent_id": parent_id,
            "body": (body or "")[:BODY_TRUNCATE_CHARS],
        },
        dedupe_key=f"broadcast:{platform}:{item_id}",
    )
    await db.commit()
    if signal_id is None:
        return None  # deduped (the poller re-read the same window)

    if redis is not None:
        await enqueue_dispatch(redis, signal_id)
    logger.info(
        "Broadcast inbound (%s %s) → broadcast.inbound signal %s (company %s)",
        platform, kind, signal_id, company_id)
    return signal_id


async def emit_broadcast_published(
    db: AsyncSession, company_id: uuid.UUID, *, platform: str, tool_name: str,
    item_id: Optional[str] = None, permalink: Optional[str] = None,
    suppressed_count: int = 0,
) -> Optional[uuid.UUID]:
    """Record a successful publish on the bus (``trust: internal``).

    The outbound audit half. It matters independently of the inbound half:
    until GATE, a public post left no trace on the bus at all, so "what did our
    agents say in public last week" had no answer. This gives it one even on
    platforms nothing polls yet.

    Deliberately **not** subscription-gated. The inbound producer is, because a
    tenant that has not asked for social routing should not have its comments
    turned into leads. An audit record of something the platform actually did
    is not a routing decision, and a tenant should not be able to end up with
    agents publishing and no record of it.
    """
    signal_id = await emit_signal(
        db,
        company_id=company_id,
        source=SignalSource.AGENT,
        type=SignalTypes.BROADCAST_PUBLISHED,
        trust=SignalTrust.INTERNAL,
        payload={
            "channel": "broadcast",
            "platform": platform,
            "tool": tool_name,
            "item_id": item_id,
            "permalink": permalink,
            "audience_suppressed": suppressed_count,
        },
    )
    await db.commit()
    return signal_id
