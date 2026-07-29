"""genui/whatsapp_mirror.py — the WhatsApp read-mirror (LINE L3, spec §14.3).

**Read + notify only, never approvals.** A mirror message carries a
sentence and the instruction to open the Line — never a button, never a
reply path. An inbound WhatsApp reply routes to the existing KAR-03
gateway like any message, and nothing in it can approve; certified
surfaces exist only where step-up is possible.

Three refusals stand in front of every send, in order:

1. **A verified binding or nothing.** The address comes from AUTH's
   ``channel_bindings`` — verified, unrevoked, this user, this company.
   An unverified row is a claim, not a binding (the AUTH rule), and the
   mirror never sends to a claim.
2. **The preference.** ``notify.whatsapp_mirror`` set to ``"off"`` keeps
   the mirror silent for that user (VG-21's store; default is on — the
   verified binding itself is the enrolment intent, decision 1).
3. **The transport is injectable and no test sends a live message** (the
   KAR/GATE precedent). The default wraps the shipped
   ``WhatsAppMessagingService``; unconfigured means "not reached", never
   an error that blocks the door.

Two senders, two single-writer boundaries (the L8 pattern applied twice):
``send_tray_notice`` may be imported only by ``genui/channel.py`` (the one
delivery door — decision 1 makes the mirror its LAST resort), and
``send_morning_summary`` only by ``genui/morning_job.py`` (decision 3's
read half). Both boundaries are import-tested.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.models import ChannelBinding, ChannelKind

logger = logging.getLogger(__name__)

__all__ = [
    "MirrorTransport",
    "send_tray_notice",
    "send_morning_summary",
]

#: ``(to_address, message) -> sent``. Injectable; the default wraps the
#: shipped WhatsAppMessagingService.
MirrorTransport = Callable[[str, str], Awaitable[bool]]

TRAY_SUFFIX = "Open the Line to decide — this thread can't approve."


async def _verified_address(
    db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID,
) -> str | None:
    row = (
        await db.execute(
            select(ChannelBinding.address)
            .where(
                ChannelBinding.company_id == company_id,
                ChannelBinding.user_id == user_id,
                ChannelBinding.channel_kind == ChannelKind.WHATSAPP,
                ChannelBinding.verified_at.is_not(None),
                ChannelBinding.revoked_at.is_(None),
            )
            .limit(1))
    ).scalar_one_or_none()
    return str(row) if row else None


async def _mirror_enabled(db: AsyncSession, user_id: uuid.UUID) -> bool:
    from src.ai.learning.preferences import get_preferences

    prefs = await get_preferences(db, user_id, prefix="notify.whatsapp_mirror")
    value = prefs.get("notify.whatsapp_mirror", {}).get("value")
    return value not in ("off", False)


async def _deliver(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    message: str,
    transport: MirrorTransport | None,
) -> bool:
    address = await _verified_address(db, company_id, user_id)
    if address is None:
        return False
    if not await _mirror_enabled(db, user_id):
        return False
    send = transport or _default_transport
    try:
        return await send(f"+{address}", message)
    except Exception:  # noqa: BLE001 — a failed mirror loses a notice, never work
        logger.warning("whatsapp mirror send failed", exc_info=True)
        return False


async def send_tray_notice(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    sentence: str,
    *,
    transport: MirrorTransport | None = None,
) -> bool:
    """The notify half — one tray's sentence, the door's last resort."""
    return await _deliver(
        db, company_id, user_id, f"{sentence}\n{TRAY_SUFFIX}", transport)


async def send_morning_summary(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    lines: list[str],
    *,
    transport: MirrorTransport | None = None,
) -> bool:
    """The read half (decision 3) — the morning's first lines, daily."""
    if not lines:
        return False
    body = "Good morning. " + " ".join(lines[:4])
    return await _deliver(db, company_id, user_id, body, transport)


async def _default_transport(to: str, message: str) -> bool:
    """The shipped messaging service. Unconfigured → not reached, honestly."""
    try:
        from src.voice.whatsapp_messaging import WhatsAppMessagingService

        service = WhatsAppMessagingService()
        result = await service.send_message(to=to, message=message)
        return bool(result.get("success"))
    except Exception:  # noqa: BLE001 — an unconfigured provider is "not reached"
        logger.info("whatsapp mirror transport unavailable", exc_info=True)
        return False
