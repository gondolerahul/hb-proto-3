"""genui/echo.py — the echo bus (L10, VG-06).

Every manual act emits its sentence; Pragya sees what the user did, and the
pair ``(manifest_hash, component_id)`` answers "what was on screen when they
did it" — the audit question D4 §5.1 declined to build a table for.

**Echoes are not commands.** ``record_echo`` takes no authority, raises no
PolicyGate decision and triggers nothing. A failure here loses training
data, never work — which is why the router treats it as an ordinary write
and the *client* fires and forgets.

**The reaper lives in the producer's path.** Each write sweeps this
company's rows past the retention window — bounded by the company index,
and structurally incapable of the LIB T3 failure (a reaper on its own
schedule that outruns or outlives its producer). No echoes, no reaping;
which is correct, because an inactive tenant's ninety days of history is
ninety days of history either way.

Fan-out to the Pragya channel lands with the channel itself (T8) — the
seam is ``_FANOUT``, a module hook the channel registers into, so this
module never imports toward its consumer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.genui.models import UiEcho

ECHO_RETENTION_DAYS = 90

#: The channel (T8) registers its delivery here; None means "no listener yet".
_FANOUT: Callable[[UiEcho], Awaitable[None]] | None = None


def install_echo_fanout(fn: Callable[[UiEcho], Awaitable[None]] | None) -> None:
    global _FANOUT
    _FANOUT = fn


def validate_echo(payload: dict[str, Any]) -> str | None:
    """The reason this payload is not an echo, or None when it is one.

    Pure, so the rules are testable without a router: a sentence (the whole
    point of L10 is the sentence), bounded length, and an ``action_ref``
    with a ``kind`` — an echo that cannot say what kind of act it describes
    trains nothing.
    """
    sentence = payload.get("sentence")
    if not isinstance(sentence, str) or not sentence.strip():
        return "an echo is a sentence; this one has none"
    if len(sentence) > 500:
        return "sentence exceeds 500 characters"
    action_ref = payload.get("action_ref")
    if not isinstance(action_ref, dict) or not action_ref.get("kind"):
        return "action_ref.kind is required"
    return None


async def record_echo(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID | None,
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> UiEcho:
    """Store the echo, reap this company's expired rows, fan out if anyone
    is listening. Caller validates first (`validate_echo`)."""
    now = now or datetime.utcnow()
    occurred_raw = payload.get("occurred_at")
    occurred = now
    if isinstance(occurred_raw, str):
        try:
            occurred = datetime.fromisoformat(occurred_raw.replace("Z", "+00:00"))
            occurred = occurred.replace(tzinfo=None)
        except ValueError:
            occurred = now

    echo = UiEcho(
        company_id=company_id,
        user_id=user_id,
        sentence=str(payload["sentence"]).strip(),
        action_ref=dict(payload["action_ref"]),
        manifest_hash=payload.get("manifest_hash"),
        component_id=payload.get("component_id"),
        occurred_at=occurred,
    )
    db.add(echo)

    cutoff = now - timedelta(days=ECHO_RETENTION_DAYS)
    await db.execute(
        delete(UiEcho).where(
            UiEcho.company_id == company_id,
            UiEcho.created_at < cutoff,
        ))
    await db.commit()
    await db.refresh(echo)

    if _FANOUT is not None:
        await _FANOUT(echo)
    return echo
