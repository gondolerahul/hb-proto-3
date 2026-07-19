"""signals/email_poll.py — the first channel producer: inbound email (§18.2).

Cron that polls each subscribed company's active IMAP connections for
UNSEEN messages and emits one ``email.inbound`` signal per message, with
``dedupe_key`` = RFC Message-ID — so IMAP re-polls, flag resets, or
overlapping cron firings can never double-process an email.

Subscription-gated: a company's inboxes are only polled when at least one
enabled trigger registration matches ``email.inbound``. Without an owner
every email would park then escalate — sensing something nothing
subscribes to is noise, not coverage. (Emails stay UNSEEN-tracked in the
inbox either way; nothing is dropped.)
"""
from __future__ import annotations

import asyncio
import email as email_lib
import imaplib
import logging
import uuid
from datetime import datetime
from typing import Any, TypedDict

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

POLL_FETCH_LIMIT = 20        # max messages per connection per poll
BODY_TRUNCATE_CHARS = 5000   # match the email_ingest tool's context cap

__all__ = ["email_inbound_poll"]


class _InboundEmail(TypedDict):
    uid: str
    message_id: str
    from_addr: str
    to_addr: str
    subject: str
    date: str
    body: str


async def email_inbound_poll(ctx: dict[str, Any]) -> dict[str, Any]:
    """Arq cron: poll subscribed companies' inboxes → ``email.inbound`` signals."""
    from src.common.database import AsyncSessionLocal

    redis = ctx.get("redis")
    emitted = deduped = connections_polled = 0
    try:
        async with AsyncSessionLocal() as db:
            company_ids = await _subscribed_company_ids(db)
            for company_id in company_ids:
                connections = await _active_connections(db, company_id)
                for conn in connections:
                    connections_polled += 1
                    try:
                        e, d = await _poll_one_connection(db, redis, conn)
                        emitted += e
                        deduped += d
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "email poll failed for connection %s (%s): %s",
                            conn.id, conn.email_address, exc,
                        )
        result = {
            "connections_polled": connections_polled,
            "signals_emitted": emitted,
            "deduped": deduped,
        }
        if emitted:
            logger.info("email poll: %s", result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("email_inbound_poll failed: %s", exc, exc_info=True)
        return {"error": str(exc)}


async def _subscribed_company_ids(db: AsyncSession) -> list[uuid.UUID]:
    """Companies with an enabled trigger covering ``email.inbound``."""
    rows = (await db.execute(
        select(TriggerRegistration).where(TriggerRegistration.enabled.is_(True))
    )).scalars().all()
    return sorted({
        r.company_id for r in rows
        if pattern_matches(r.type_pattern, SignalTypes.EMAIL_INBOUND)
    }, key=str)


async def _active_connections(db: AsyncSession, company_id: uuid.UUID) -> list[Any]:
    from src.ai.email_models import EmailConnection

    rows = (await db.execute(
        select(EmailConnection).where(
            EmailConnection.company_id == company_id,
            EmailConnection.is_active.is_(True),
            EmailConnection.status == "active",
        )
    )).scalars().all()
    return list(rows)


async def _poll_one_connection(
    db: AsyncSession, redis: Any, conn: Any,
) -> tuple[int, int]:
    """Fetch UNSEEN messages for one connection and emit signals.

    Returns ``(emitted, deduped)``. Commits per connection.
    """
    from src.common.security import decrypt_api_key

    password = decrypt_api_key(conn.encrypted_app_password)
    messages = await asyncio.to_thread(
        _fetch_unseen_messages,
        str(conn.imap_host), int(conn.imap_port),
        str(conn.email_address), password, POLL_FETCH_LIMIT,
    )

    emitted_ids: list[uuid.UUID] = []
    deduped = 0
    for msg in messages:
        dedupe = msg["message_id"] or f"email:{conn.id}:{msg['uid']}:{msg['date']}"
        signal_id = await emit_signal(
            db,
            company_id=conn.company_id,
            source=SignalSource.CONNECTOR,
            type=SignalTypes.EMAIL_INBOUND,
            trust=SignalTrust.COUNTERPARTY,
            payload={
                "channel": "email",
                "connection_id": str(conn.id),
                "mailbox": str(conn.email_address),
                "message_id": msg["message_id"],
                "from": msg["from_addr"],
                "to": msg["to_addr"],
                "subject": msg["subject"],
                "date": msg["date"],
                "body": msg["body"][:BODY_TRUNCATE_CHARS],
            },
            dedupe_key=dedupe,
        )
        if signal_id is None:
            deduped += 1
        else:
            emitted_ids.append(signal_id)

    conn.last_connected_at = datetime.utcnow()
    await db.commit()

    for signal_id in emitted_ids:
        await enqueue_dispatch(redis, signal_id)
    return len(emitted_ids), deduped


def _fetch_unseen_messages(
    imap_host: str, imap_port: int, email_address: str, password: str, limit: int,
) -> list[_InboundEmail]:
    """Blocking IMAP fetch (run via ``asyncio.to_thread``).

    Reuses the email tool's MIME parsing so signal payloads match what
    agents see through ``email_ingest``.
    """
    from src.ai.tools.email.email_tool import _parse_email_body

    conn = imaplib.IMAP4_SSL(imap_host, imap_port)
    try:
        conn.login(email_address, password)
        conn.select("INBOX")
        status, message_ids = conn.search(None, "UNSEEN")
        if status != "OK":
            return []
        ids = message_ids[0].split()
        results: list[_InboundEmail] = []
        for uid in ids[-limit:]:
            status, msg_data = conn.fetch(uid, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw = msg_data[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email_lib.message_from_bytes(bytes(raw))
            body = str(_parse_email_body(msg))
            results.append(_InboundEmail(
                uid=uid.decode(),
                message_id=str(msg.get("Message-ID", "") or "").strip(),
                from_addr=str(msg.get("From", "") or ""),
                to_addr=str(msg.get("To", "") or ""),
                subject=str(msg.get("Subject", "") or ""),
                date=str(msg.get("Date", "") or ""),
                body=body,
            ))
        return results
    finally:
        try:
            conn.logout()
        except Exception:  # pragma: no cover  # noqa: BLE001
            pass
