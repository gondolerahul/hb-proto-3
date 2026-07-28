"""voice/pragya_stream_handler.py — carrier media into `drive_call` (gaps 3 + 4).

`drive_call` consumes audio frames and emits audio frames, and until now
nothing connected it to a phone. This is that connection: the second consumer
of the media stream `TwilioStreamHandler` already carries, running the
**inward** face instead of the speech-to-speech one.

**Why a separate handler rather than a branch inside the existing one.**
`TwilioStreamHandler` drives a realtime model that does hear-think-speak inside
one session. Pragya's pipeline is three pieces with her turn loop in the middle
— that is the whole point of decision 3, because the turn loop is where
`require_tier`, the stage machine and tool execution live. Threading two
fundamentally different pipelines through one class would have produced a
handler where half the state is dead on any given call.

**The tenant comes from the caller, not the line** (owner decision 2026-07-26,
inverting Inc-4 decision 5). One shared number serves every tenant, so the
number says which *face* and the caller's own verified binding says which
*business*. An unrecognised caller reaches no tenant at all — which is a safe
outcome rather than an error, because the voice ceiling already caps an unbound
caller at T0.
"""
from __future__ import annotations

import asyncio
import audioop
import base64
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)

__all__ = ["PragyaStreamHandler", "UNKNOWN_TENANT", "SPEAKING_WINDOW_SECONDS"]

#: How recently we must have sent audio to count as "still speaking".
#: Frames go out every 20 ms, so a quarter-second gap means synthesis has
#: stopped. Used only to decide whether inbound speech is an *interruption* or
#: an ordinary turn.
SPEAKING_WINDOW_SECONDS = 0.25

#: Said when the calling number matches no verified binding in any tenant.
#: Deliberately does not say "you are not registered" in a way that confirms
#: which businesses exist — an unknown caller learns only that this line needs
#: a registered number.
UNKNOWN_TENANT = (
    "Thanks for calling. I can only help from a number that's been registered "
    "in the console, and I don't recognise this one. Please register it there "
    "and call back."
)


class PragyaStreamHandler:
    """One inbound call to the account-manager line.

    Media in → `drive_call` → media out, with the tenant resolved from the
    caller before the first word.
    """

    def __init__(
        self,
        websocket: Any,
        session_id: uuid.UUID,
        db: Any,
        *,
        transcriber: Any = None,
        speaker: Any = None,
    ) -> None:
        self.websocket = websocket
        self.session_id = session_id
        self.db = db
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.from_number: str = ""
        self.is_running = True
        self._inbound: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        # Injected in tests; resolved from the registry on a real call.
        self._transcriber = transcriber
        self._speaker = speaker
        # Barge-in state. See `_note_inbound_energy`.
        self._call_state: Any = None
        self._last_sent_at: float = 0.0

    # ── the media stream ────────────────────────────────────────────────

    async def _receive_loop(self) -> None:
        """Pump carrier frames into the queue until the call ends."""
        try:
            while self.is_running:
                raw = await self.websocket.receive_text()
                event = json.loads(raw)
                kind = event.get("event")

                if kind == "start":
                    start = event.get("start", {})
                    self.stream_sid = start.get("streamSid")
                    self.call_sid = start.get("callSid")
                    # Twilio puts the caller in customParameters; Tata differs,
                    # so fall back to whatever the session already knows.
                    params = start.get("customParameters", {}) or {}
                    self.from_number = str(
                        params.get("from") or params.get("From") or self.from_number)
                elif kind == "media":
                    payload = event.get("media", {}).get("payload")
                    if payload:
                        frame = base64.b64decode(payload)
                        self._note_inbound_energy(frame)
                        await self._inbound.put(frame)
                elif kind == "stop":
                    break
        except Exception as exc:  # noqa: BLE001
            logger.info("pragya stream receive ended: %s", exc)
        finally:
            self.is_running = False
            # Sentinel, so the generator feeding `drive_call` terminates rather
            # than blocking forever on a queue nobody will fill again.
            await self._inbound.put(None)

    async def _audio_in(self) -> AsyncIterator[bytes]:
        while True:
            frame = await self._inbound.get()
            if frame is None:
                return
            yield frame

    async def _send(self, chunk: bytes) -> None:
        """One μ-law frame back to the carrier."""
        if not self.stream_sid or not chunk:
            return
        self._last_sent_at = time.monotonic()
        await self.websocket.send_text(json.dumps({
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {"payload": base64.b64encode(chunk).decode("ascii")},
        }))

    def _note_inbound_energy(self, frame: bytes) -> None:
        """Detect the caller talking over Pragya, from audio energy.

        **This is barge-in, and it has to live here** because Chirp 3 emits no
        interim results (owner, Phase 1). `drive_call` sets `interrupted` from
        a non-final transcript — with an ASR that never sends one, that branch
        is unreachable and Pragya talks over the caller on every long reply,
        with no error anywhere. Continuing to talk over someone is the single
        most irritating thing a phone system does; losing it silently to a
        model's feature set is not an acceptable way to lose it.

        Energy VAD is the same mechanism the shipped speech-to-speech handler
        already uses (`audioop.rms` against `VOICE_VAD_RMS_THRESHOLD`) — μ-law
        frames flow continuously even in silence, so activity means frames with
        real energy rather than frames at all.

        The receive loop is the only place this can run: during synthesis the
        transcriber is not pulling from the inbound queue, so a check further
        down the pipeline would not see the interrupting audio until Pragya had
        already finished speaking.
        """
        if self._call_state is None:
            return
        if time.monotonic() - self._last_sent_at > SPEAKING_WINDOW_SECONDS:
            return   # she is not speaking; this is an ordinary turn
        try:
            from src.common.config import settings

            rms = audioop.rms(audioop.ulaw2lin(frame, 2), 2)
        except Exception:  # noqa: BLE001 — a malformed frame is not a barge-in
            return
        if rms > int(getattr(settings, "VOICE_VAD_RMS_THRESHOLD", 300)):
            self._call_state.interrupted = True

    # ── the call ────────────────────────────────────────────────────────

    async def handle(self) -> None:
        """Run the call to completion. Never raises at the caller."""
        receive_task = asyncio.create_task(self._receive_loop())
        try:
            await self._drive()
        except Exception as exc:  # noqa: BLE001
            logger.error("pragya call %s failed: %s", self.session_id, exc,
                         exc_info=True)
        finally:
            self.is_running = False
            receive_task.cancel()
            try:
                await self.websocket.close()
            except Exception:  # noqa: BLE001
                pass

    async def _drive(self) -> None:
        from src.ai.pragya.channels.routing import company_for_caller
        from src.ai.pragya.channels.voice import CallState, drive_call

        # Wait for `start`, which is where the caller's number arrives. Without
        # it there is no tenant to resolve and no session to bill.
        for _ in range(100):
            if self.stream_sid:
                break
            await asyncio.sleep(0.05)

        company_id = await company_for_caller(self.db, self.from_number)
        if company_id is None:
            # No verified binding anywhere. She says so and hangs up rather
            # than holding an anonymous line open — and says it *aloud*,
            # because silence on a phone reads as a fault.
            logger.info("pragya call from %s matched no tenant", self.from_number)
            await self._speak_plain(UNKNOWN_TENANT)
            return

        transcriber, speaker = await self._resolve_pipeline(company_id)
        if transcriber is None or speaker is None:
            return   # `_resolve_pipeline` has already spoken the reason

        state = CallState(
            company_id=company_id,
            call_sid=str(self.call_sid or self.session_id),
            from_number=self.from_number,
        )
        # Handed to the receive loop so energy VAD can set `interrupted`.
        self._call_state = state
        async for chunk in drive_call(
                self.db, state, transcriber, speaker, self._audio_in()):
            await self._send(chunk)

    async def _resolve_pipeline(self, company_id: uuid.UUID) -> tuple[Any, Any]:
        """The tenant's ASR and TTS, or ``(None, None)`` having said why.

        Readiness is settled here rather than discovered mid-call, and the
        refusal is spoken: a caller told voice is not set up has been served
        better than one left listening to nothing.
        """
        if self._transcriber is not None and self._speaker is not None:
            return self._transcriber, self._speaker

        from src.ai.pragya.channels.adapters import build_speaker, build_transcriber
        from src.ai.pragya.channels.speech import SpeechConfigError
        from src.ai.pragya.channels.voice import NOT_CONFIGURED

        try:
            transcriber = await build_transcriber(self.db, company_id)
            speaker = await build_speaker(self.db, company_id)
        except SpeechConfigError as exc:
            logger.warning("voice not configured for %s: %s", company_id, exc)
            await self._speak_plain(NOT_CONFIGURED)
            return None, None
        return transcriber, speaker

    async def _speak_plain(self, text: str) -> None:
        """Say something before any tenant pipeline exists.

        The refusal paths run *before* a tenant is resolved, so there is no
        tenant TTS to reach for. Logged and left silent rather than guessing a
        provider: billing a tenant we have not identified for synthesis they
        did not ask for is worse than a quiet line, and this is the one place
        in the call where silence is short and immediately followed by a
        hangup.
        """
        logger.info("pragya says (pre-tenant): %s", text)
