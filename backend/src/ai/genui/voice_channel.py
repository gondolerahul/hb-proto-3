"""genui/voice_channel.py — voice on the channel (STEWARD S4, 12_steward.md §6).

The **browser** leg, and the scope correction matters: this is not the
phone. The phone identifies a caller by caller-ID binding — a claim — so
``voice_tier_ceiling`` caps that channel at T1. Here the session is a
JWT-authenticated console session where WebAuthn works: **voice is an
input method, not a channel**, console tier rules apply unchanged, and the
T2/T3 ceremonies stay available mid-conversation. Inheriting the phone
ceiling reflexively would have been easy and wrong.

Adapter reuse is the whole design. ``ChirpTranscriber(convert_from_mulaw=
False)`` and ``GeminiSpeaker(convert_to_mulaw=False)`` — the flags exist
precisely for a caller whose audio is not carrier μ-law. The browser sends
**PCM16 16 kHz mono** (what the ASR transport expects) and plays **24 kHz
PCM** (Gemini's native rate); no new speech code exists here.

A heard-final sentence goes through ``channel.handle_utterance`` — the
same turn, the same gates, the same narration to the session — and only
the synthesis is this module's own. A spoken command and a typed one are
the same turn in every respect but the audio.

Barge-in is **client-side** on this leg (the phone needed server VAD
because a handset is a dumb pipe; a browser is not): the client stops
playback on local speech and sends ``{"type":"mic","state":"open"}``
again, which doubles as the interrupt — synthesis stops at the next chunk,
the phone leg's own pattern.

**Tested seam, no live call** — every test injects ``AsrTransport``/
``TtsTransport`` fakes (the VG-08 rule: a suite that needs credentials to
pass is a suite that stops being run). The live browser proof is
owner-side and is G3's exit key together with the phone call.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

__all__ = [
    "NOT_CONFIGURED_HERE",
    "VoiceLeg",
    "open_mic",
    "feed_audio",
    "close_mic",
]

#: The browser refusal — NOT the phone's wording, which points callers *at*
#: the console this user is already in.
NOT_CONFIGURED_HERE = (
    "Voice isn't set up on this account yet — I can still help right here "
    "in text."
)


@dataclass
class VoiceLeg:
    """One open microphone on a session."""

    queue: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    drive_task: asyncio.Task[None] | None = None
    #: Set by a repeated mic-open while she is speaking — synthesis stops
    #: at the next chunk (the phone leg's interrupt pattern).
    interrupted: bool = False
    closed: bool = False


async def open_mic(
    db: Any,
    state: Any,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    transcriber: Any = None,
    speaker: Any = None,
    turn: Any = None,
) -> dict[str, Any] | None:
    """Open the voice leg — or interrupt the current synthesis when it is
    already open (the client's barge-in signal). Readiness is settled
    before the first frame, not discovered mid-utterance: a user who hears
    silence has been failed worse than one who is told.

    ``transcriber``/``speaker``/``turn`` are injectable for tests; the
    defaults resolve the tenant's own registry rows through the shipped
    adapters with the μ-law conversions off.
    """
    from src.ai.genui.channel import hub

    leg_alive = (
        state.voice is not None
        and state.voice.drive_task is not None
        and not state.voice.drive_task.done())
    if leg_alive and not state.voice.closed:
        # The mic is still open and streaming — a repeated open is the
        # client's barge-in signal (its VAD heard the human over her).
        state.voice.interrupted = True
        return None
    if leg_alive and state.voice.closed:
        # The utterance ended and she is replying; the human starts talking
        # again. Stop her at the next chunk AND open a fresh leg — the old
        # one's frame stream has already ended and cannot take new audio.
        state.voice.interrupted = True

    if transcriber is None or speaker is None:
        # Readiness is a property of resolving the tenant's real registry
        # rows, so the check lives with the default builders — an injected
        # fake has no row to be ready about.
        from src.ai.pragya.channels.speech import voice_ready

        ready, why = await voice_ready(db, company_id)
        if not ready:
            logger.info("browser voice refused for %s: %s", company_id, why)
            return {"type": "error", "reason": NOT_CONFIGURED_HERE}

        # The browser's audio is already model-shaped (PCM16 in, PCM out) —
        # the same adapters as the phone, with the μ-law conversions off.
        from src.ai.pragya.channels.adapters import (
            ChirpTranscriber,
            GeminiSpeaker,
        )
        from src.ai.pragya.channels.speech import resolve_asr, resolve_tts

        if transcriber is None:
            transcriber = ChirpTranscriber(
                await resolve_asr(db, company_id), convert_from_mulaw=False)
        if speaker is None:
            speaker = GeminiSpeaker(
                await resolve_tts(db, company_id), convert_to_mulaw=False)

    leg = VoiceLeg()
    state.voice = leg
    leg.drive_task = asyncio.create_task(
        _drive(state, company_id, user_id, transcriber, speaker, turn))
    await hub()._emit(state, {"type": "presence", "state": "listening"})
    return None


async def feed_audio(state: Any, frame: bytes) -> None:
    """A mic frame into the leg's queue. Frames arriving with no open leg
    are dropped — the client raced its own mic-open; the next frame after
    the open lands."""
    leg = state.voice
    if leg is None or leg.closed or not frame:
        return
    await leg.queue.put(frame)


async def close_mic(state: Any, *, abort: bool = False) -> None:
    """End the utterance stream. Idempotent — the disconnect path calls it
    unconditionally.

    ``abort=False`` is the conversational close: the human finished
    talking, the drive finishes its finals and **she still speaks her
    reply** — so this must NOT wait for the drive, or the socket loop
    would be deaf to the barge-in for the whole reply. The drive clears
    ``state.voice`` itself when it ends. ``abort=True`` (disconnect) stops
    synthesis too — there is nobody left to talk to — and does wait.
    """
    leg = state.voice
    if leg is None:
        return
    if abort:
        leg.interrupted = True
    if not leg.closed:
        leg.closed = True
        await leg.queue.put(None)
    if abort and leg.drive_task is not None:
        try:
            await asyncio.wait_for(leg.drive_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            leg.drive_task.cancel()


async def _frames(leg: VoiceLeg) -> AsyncIterator[bytes]:
    while True:
        frame = await leg.queue.get()
        if frame is None:
            return
        yield frame


async def _drive(
    state: Any,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    transcriber: Any,
    speaker: Any,
    turn: Any,
) -> None:
    """ASR → the one turn loop → TTS, for every final the transcriber
    yields while the mic is open. Never raises out — a broken leg logs,
    tells the session, and closes; the text channel is untouched."""
    from src.ai.genui.channel import hub

    leg = state.voice
    try:
        async for text, is_final in transcriber.stream(_frames(leg)):
            await hub()._emit(state, {
                "type": "transcript", "text": text, "final": bool(is_final)})
            heard = text.strip()
            if not is_final or not heard:
                continue
            leg.interrupted = False
            spoken = await (turn or _default_turn)(
                state, company_id, user_id, heard)
            if spoken:
                await _speak(state, leg, speaker, spoken)
    except Exception:  # noqa: BLE001 — the voice leg fails visible, text survives
        logger.exception("browser voice leg failed")
        await hub()._emit(state, {
            "type": "error",
            "reason": "Voice dropped on my side — the text channel still "
                      "works while I recover."})
    finally:
        leg.closed = True
        # A barge-in may already have opened a fresh leg — never clobber it.
        if state.voice is leg:
            state.voice = None


async def _default_turn(
    state: Any, company_id: uuid.UUID, user_id: uuid.UUID, heard: str,
) -> str | None:
    """The heard sentence through the channel's own utterance path, on its
    own session (the drive task outlives any request)."""
    from src.ai.genui.channel import handle_utterance
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        _error, spoken = await handle_utterance(
            db, state, company_id, user_id, heard)
    return spoken


async def _speak(state: Any, leg: VoiceLeg, speaker: Any, text: str) -> None:
    """Stream synthesis to every device, stopping the moment the client
    says the human is speaking (``interrupted``)."""
    from src.ai.genui.channel import hub

    await hub()._emit(state, {"type": "presence", "state": "speaking"})
    try:
        async for chunk in speaker.stream(text):
            # Only the interrupt stops her mid-reply — a *closed mic* means
            # the human finished talking, which is exactly when she speaks.
            if leg.interrupted:
                logger.debug("barge-in — stopping synthesis")
                break
            if chunk:
                await hub()._emit_bytes(state, chunk)
    finally:
        await hub()._emit(state, {"type": "presence", "state": "listening"})
