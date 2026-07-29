"""genui/morning_job.py — the daily morning job (LINE L2, decisions 2 & 3).

One cron, four steps per tenant: **compose** (the shared composition —
this job and the endpoint cannot count differently), **synthesize** one
clip per card through the shipped ``GeminiSpeaker`` with conversion off
(24 kHz PCM in a RIFF header — twelve lines buy native ``<audio>``
playback, no codec dependency), **store** the telling on its
``morning_stories`` row, and **send the WhatsApp summary** (the mirror's
read half) to every verified binding. Retention is reaped **in this same
job** — the LIB rule.

**Every failure degrades to text and says so.** A missing speech row, an
empty wallet, a broken TTS: the story is still written, its cards still
read, and ``degraded_reason`` names what is missing. A morning that
silently vanished would be the "nothing happened" failure this repo keeps
finding.

**Cost, honestly.** ``CostAttribution.MORNING_STORY`` is registered and
classified **tenant-side of B13** (a standing instruction, like a
scheduled campaign — a per-tenant daily benefit must not live on the cap
that protects tenants *from* platform work), and the wallet gates
synthesis. But speech minutes are **not yet metered on any leg** —
VG-08's own limit, unchanged here — so the attribution is registered and
waiting, exactly like ``MANIFEST_GENERATION`` was. The gate is real; the
meter is the debt.

**Tested seam, no live call**: the speaker and the mirror transport are
injectable; no test synthesizes through Vertex or sends a message.
"""
from __future__ import annotations

import base64
import logging
import struct
import uuid
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.genui.models import MorningStory
from src.ai.genui.morning import compose_for_company
from src.ai.genui.watcher import _whatsapp_users
from src.ai.genui.whatsapp_mirror import MirrorTransport, send_morning_summary

logger = logging.getLogger(__name__)

__all__ = [
    "RETENTION_DAYS",
    "wav_wrap",
    "spoken_text",
    "summary_lines",
    "generate_for_company",
    "morning_story_sweep",
]

RETENTION_DAYS = 30

#: Synthesis output — Gemini's native rate, mono, 16-bit.
WAV_SAMPLE_RATE = 24000


def wav_wrap(pcm: bytes, *, sample_rate: int = WAV_SAMPLE_RATE) -> bytes:
    """A RIFF/WAVE header around 16-bit mono PCM. A wrong rate here does
    not raise — it plays at the wrong speed — which is why the constant is
    named once and shared with the speaker's contract."""
    byte_rate = sample_rate * 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, 1, sample_rate, byte_rate, 2, 16,
        b"data", len(pcm),
    )
    return header + pcm


def spoken_text(card: dict[str, Any]) -> str:
    """What she says over one card — the name, then the sentences, exactly
    as written. Nothing is generated here; her written and spoken telling
    are the same telling."""
    return f"{card.get('name')}. " + " ".join(card.get("sentences", []))


def summary_lines(cards: list[dict[str, Any]]) -> list[str]:
    """The WhatsApp summary — whoever needs the owner, then the notable;
    quiet cards stay out of the pocket message entirely."""
    lines: list[str] = []
    for card in cards:
        sentences = card.get("sentences") or []
        first = str(sentences[0]) if sentences else ""
        if card.get("waiting"):
            lines.append(f"{card.get('name')} is waiting on you.")
        elif first and "quiet day" not in first:
            lines.append(f"{card.get('name')}: {first}")
    return lines[:4]


async def _default_wallet_allows(db: AsyncSession, company_id: uuid.UUID) -> bool:
    try:
        from src.billing.credit_service import CreditService

        balance = await CreditService(db).get_balance(company_id)
        return float(balance.get("total_available", 0) or 0) > 0
    except Exception:  # noqa: BLE001 — cannot read the wallet → do not spend
        logger.warning("wallet read failed for %s", company_id, exc_info=True)
        return False


async def _synthesize(
    cards: list[dict[str, Any]], speaker: Any,
) -> str | None:
    """Fill each card's audio in place. Returns a degraded reason or None.
    A failure mid-way keeps the clips already made — a half-voiced story
    beats a silent one, and the reason says why the rest is text."""
    for card in cards:
        try:
            chunks: list[bytes] = []
            async for chunk in speaker.stream(spoken_text(card)):
                if chunk:
                    chunks.append(chunk)
            pcm = b"".join(chunks)
            if pcm:
                card["audio"] = {
                    "mime": "audio/wav",
                    "data_b64": base64.b64encode(wav_wrap(pcm)).decode(),
                }
        except Exception:  # noqa: BLE001 — text survives a broken voice
            logger.warning("morning TTS failed", exc_info=True)
            return "tts_failed"
    return None


async def generate_for_company(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    now: datetime | None = None,
    speaker: Any = None,
    mirror_transport: MirrorTransport | None = None,
    wallet_allows: Callable[[AsyncSession, uuid.UUID], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """One tenant's morning: compose · synthesize · store · summarize.
    Commits — the sweep calls this per company so one failure rolls back
    one morning, never everyone's."""
    now = now or datetime.utcnow()
    story_date = now.date()
    cards = await compose_for_company(db, company_id, now=now)
    degraded: str | None = None

    if speaker is None:
        try:
            from src.ai.pragya.channels.adapters import GeminiSpeaker
            from src.ai.pragya.channels.speech import resolve_tts

            speaker = GeminiSpeaker(
                await resolve_tts(db, company_id), convert_to_mulaw=False)
        except Exception:  # noqa: BLE001 — no speech row is a text morning
            speaker = None
            degraded = "not_configured"

    if speaker is not None:
        allows = wallet_allows or _default_wallet_allows
        if not await allows(db, company_id):
            degraded = "wallet"
        else:
            degraded = await _synthesize(cards, speaker)

    existing = await db.get(MorningStory, (company_id, story_date))
    if existing is not None:
        existing.cards = cards
        existing.degraded_reason = degraded
        existing.generated_at = now
    else:
        db.add(MorningStory(
            company_id=company_id, story_date=story_date,
            cards=cards, degraded_reason=degraded, generated_at=now))
    await db.commit()

    summarized = 0
    lines = summary_lines(cards)
    if lines:
        for user_id in await _whatsapp_users(db, company_id):
            if await send_morning_summary(
                    db, company_id, user_id, lines,
                    transport=mirror_transport):
                summarized += 1

    voiced = sum(1 for card in cards if card.get("audio"))
    return {
        "cards": len(cards), "voiced": voiced,
        "degraded": degraded, "summarized": summarized,
    }


async def reap_old_stories(
    db: AsyncSession, *, now: datetime | None = None,
) -> int:
    now = now or datetime.utcnow()
    cutoff = now.date() - timedelta(days=RETENTION_DAYS)
    result = await db.execute(
        delete(MorningStory).where(MorningStory.story_date < cutoff))
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def morning_story_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron (02:25 UTC — after the pooling job's 02:10, inside the quiet
    hour): every active tenant's morning, one failure never stopping the
    rest, the reaper in this same job."""
    from sqlalchemy import text

    from src.common.database import AsyncSessionLocal

    generated = 0
    failed = 0
    try:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(text(
                "SELECT id FROM companies "
                "WHERE type = 'TENANT' AND status = 'active'"))).all()
            company_ids = [row[0] for row in rows]
        for company_id in company_ids:
            try:
                async with AsyncSessionLocal() as db:
                    await generate_for_company(db, company_id)
                generated += 1
            except Exception:  # noqa: BLE001 — one bad morning must not stop the rest
                logger.warning(
                    "morning story failed for %s", company_id, exc_info=True)
                failed += 1
        async with AsyncSessionLocal() as db:
            reaped = await reap_old_stories(db)
        return {"generated": generated, "failed": failed, "reaped": reaped}
    except Exception as exc:  # noqa: BLE001
        logger.error("morning_story_sweep failed: %s", exc)
        return {"error": str(exc)}
