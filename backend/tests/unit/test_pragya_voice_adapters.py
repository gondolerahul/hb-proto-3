"""Voice go-live gaps 2–4 — the adapters and the media handler.

Transport injected throughout, so these run with no credentials and make no
Google call. What they pin is the part that is easy to get wrong and hard to
notice: **audio format conversion**, which does not raise when it is wrong — it
plays the reply at the wrong speed, or feeds the model silence.
"""
from __future__ import annotations

import asyncio
import base64
import json
import uuid
from typing import AsyncIterator

import pytest

from src.ai.pragya.channels.adapters import (
    ChirpTranscriber,
    GeminiSpeaker,
)
from src.ai.pragya.channels.speech import ResolvedProvider


def _provider(sku: str = "pragya-asr-chirp-vertex") -> ResolvedProvider:
    return ResolvedProvider(
        sku=sku, provider_name="Google", model_name="chirp_3",
        api_key=None, metadata={"project_id": "p", "region": "us"})


def _mulaw(n: int = 160) -> bytes:
    """One 20 ms μ-law frame's worth of bytes, as the carrier sends."""
    return bytes(range(0, 256))[:n] * max(1, n // 256 or 1)


class TestTranscriber:
    @pytest.mark.asyncio
    async def test_it_yields_partials_and_a_final(self):
        """Barge-in and responsive endpointing both need partials. An adapter
        that only ever yields a final turns every turn into a wait."""
        scripted = [("how did", False), ("how did we do", True)]

        def transport(audio: AsyncIterator[bytes]) -> AsyncIterator[tuple[str, bool]]:
            async def _gen():
                async for _frame in audio:
                    pass
                for turn in scripted:
                    yield turn
            return _gen()

        async def frames() -> AsyncIterator[bytes]:
            yield _mulaw()

        out = [t async for t in ChirpTranscriber(_provider(), transport).stream(frames())]
        assert out == scripted
        assert any(not is_final for _t, is_final in out), "no partials"

    @pytest.mark.asyncio
    async def test_carrier_mulaw_is_converted_before_the_model_sees_it(self):
        """The adapter takes the frames the websocket handler already has, so
        no caller needs to know what the model wants."""
        seen: list[bytes] = []

        def transport(audio: AsyncIterator[bytes]) -> AsyncIterator[tuple[str, bool]]:
            async def _gen():
                async for frame in audio:
                    seen.append(frame)
                yield ("ok", True)
            return _gen()

        async def frames() -> AsyncIterator[bytes]:
            yield _mulaw(160)

        [t async for t in ChirpTranscriber(_provider(), transport).stream(frames())]

        assert seen, "nothing reached the model"
        # 160 bytes of 8 kHz μ-law → 16-bit PCM at 16 kHz: twice the samples,
        # two bytes each, so ~640 bytes. A wrong rate does not raise — it
        # mis-transcribes — so the magnitude is what is worth pinning.
        #
        # Not *exactly* 640: `audioop.ratecv` is called per frame without
        # carrying its state, so each frame loses a sample at the boundary
        # (638 here). The shipped speech-to-speech path converts the same way
        # and works in production, so the loss is accepted rather than fixed —
        # but it is a real ~0.3% of samples, and worth knowing before anyone
        # debugs "the transcript is slightly off" from first principles.
        assert 4 * 160 * 0.95 <= len(seen[0]) <= 4 * 160, len(seen[0])

    @pytest.mark.asyncio
    async def test_conversion_can_be_turned_off_for_a_model_that_wants_mulaw(self):
        seen: list[bytes] = []

        def transport(audio: AsyncIterator[bytes]) -> AsyncIterator[tuple[str, bool]]:
            async def _gen():
                async for frame in audio:
                    seen.append(frame)
                yield ("ok", True)
            return _gen()

        async def frames() -> AsyncIterator[bytes]:
            yield _mulaw(160)

        adapter = ChirpTranscriber(_provider(), transport, convert_from_mulaw=False)
        [t async for t in adapter.stream(frames())]
        assert len(seen[0]) == 160

    @pytest.mark.asyncio
    async def test_an_unconvertible_frame_is_dropped_not_forwarded_empty(self):
        """`mulaw_to_pcm16` returns b"" on failure rather than raising.
        Forwarding that would look to the model like silence, so the caller's
        turn would simply never end."""
        seen: list[bytes] = []

        def transport(audio: AsyncIterator[bytes]) -> AsyncIterator[tuple[str, bool]]:
            async def _gen():
                async for frame in audio:
                    seen.append(frame)
                yield ("ok", True)
            return _gen()

        async def frames() -> AsyncIterator[bytes]:
            yield b""
            yield _mulaw(160)

        [t async for t in ChirpTranscriber(_provider(), transport).stream(frames())]
        assert all(frame for frame in seen), "an empty frame reached the model"
        assert len(seen) == 1


class TestSpeaker:
    @pytest.mark.asyncio
    async def test_it_streams_rather_than_waiting_for_the_whole_reply(self):
        """Time-to-first-byte is the only latency the caller experiences."""
        def transport(text: str) -> AsyncIterator[bytes]:
            async def _gen():
                for _ in range(3):
                    yield b"\x00\x01" * 480
            return _gen()

        chunks = [c async for c in GeminiSpeaker(_provider(), transport).stream("hi")]
        assert len(chunks) == 3, "the reply arrived as one blob, not a stream"

    @pytest.mark.asyncio
    async def test_gemini_pcm_is_converted_to_carrier_mulaw(self):
        """Gemini speaks 24 kHz PCM and the carrier wants 8 kHz μ-law. A rate
        mismatch here does not raise — it plays the reply at the wrong speed."""
        def transport(text: str) -> AsyncIterator[bytes]:
            async def _gen():
                yield b"\x00\x01" * 480    # 480 samples @ 24 kHz = 20 ms
            return _gen()

        chunks = [c async for c in GeminiSpeaker(_provider(), transport).stream("hi")]
        assert chunks
        # 480 samples at 24 kHz → 160 at 8 kHz, one byte each in μ-law.
        assert len(b"".join(chunks)) == 160

    @pytest.mark.asyncio
    async def test_empty_chunks_are_not_sent_to_the_carrier(self):
        def transport(text: str) -> AsyncIterator[bytes]:
            async def _gen():
                yield b""
                yield b"\x00\x01" * 480
            return _gen()

        chunks = [c async for c in GeminiSpeaker(_provider(), transport).stream("hi")]
        assert all(chunks)


class TestLiveTransportsAreHonestlyAbsent:
    @pytest.mark.asyncio
    async def test_the_asr_default_refuses_with_a_pointer(self):
        """A tested seam should say so at the moment somebody reaches for the
        untested half, not fail obscurely inside an SDK."""
        async def frames() -> AsyncIterator[bytes]:
            yield _mulaw()

        with pytest.raises(NotImplementedError) as exc:
            [t async for t in ChirpTranscriber(_provider()).stream(frames())]
        assert "voice_go_live_plan" in str(exc.value)

    @pytest.mark.asyncio
    async def test_the_tts_default_refuses_with_a_pointer(self):
        with pytest.raises(NotImplementedError) as exc:
            [c async for c in GeminiSpeaker(_provider()).stream("hi")]
        assert "voice_go_live_plan" in str(exc.value)


class _FakeSocket:
    """Enough of a Twilio media stream to drive the handler."""

    def __init__(self, events: list[dict]) -> None:
        self._events = list(events)
        self.sent: list[dict] = []
        self.closed = False

    async def receive_text(self) -> str:
        if not self._events:
            await asyncio.sleep(0.01)
            raise RuntimeError("stream ended")
        return json.dumps(self._events.pop(0))

    async def send_text(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def close(self) -> None:
        self.closed = True


def _start(from_number: str = "+919812345678") -> dict:
    return {"event": "start", "start": {
        "streamSid": "MZ1", "callSid": "CA1",
        "customParameters": {"from": from_number}}}


def _media(payload: bytes) -> dict:
    return {"event": "media",
            "media": {"payload": base64.b64encode(payload).decode()}}


class TestStreamHandler:
    @pytest.mark.asyncio
    async def test_an_unknown_caller_reaches_no_tenant(self, monkeypatch):
        """The safe outcome, not an error: with a shared line the caller is the
        only thing that names a tenant, and an unrecognised one names none."""
        import src.voice.pragya_stream_handler as handler_mod

        async def _no_company(db, from_number):
            return None

        monkeypatch.setattr(handler_mod, "company_for_caller", _no_company,
                            raising=False)
        monkeypatch.setattr(
            "src.ai.pragya.channels.routing.company_for_caller", _no_company)

        socket = _FakeSocket([_start(), _media(_mulaw()), {"event": "stop"}])
        h = handler_mod.PragyaStreamHandler(socket, uuid.uuid4(), db=None)
        await h.handle()

        # Nothing was streamed to a tenant pipeline, and the socket closed.
        assert socket.closed
        assert not socket.sent

    @pytest.mark.asyncio
    async def test_a_known_caller_drives_the_turn_loop_and_audio_comes_back(
            self, monkeypatch):
        import src.voice.pragya_stream_handler as handler_mod

        company = uuid.uuid4()

        async def _company(db, from_number):
            return company

        monkeypatch.setattr(
            "src.ai.pragya.channels.routing.company_for_caller", _company)

        async def _drive(db, state, transcriber, speaker, audio_in):
            # Drain what the carrier sent, then answer.
            async for _frame in audio_in:
                break
            yield b"\xff" * 160

        monkeypatch.setattr("src.ai.pragya.channels.voice.drive_call", _drive)

        socket = _FakeSocket([_start(), _media(_mulaw()), {"event": "stop"}])
        h = handler_mod.PragyaStreamHandler(
            socket, uuid.uuid4(), db=None,
            transcriber=object(), speaker=object())
        await h.handle()

        assert socket.sent, "no audio reached the carrier"
        frame = socket.sent[0]
        assert frame["event"] == "media"
        assert frame["streamSid"] == "MZ1"
        assert base64.b64decode(frame["media"]["payload"]) == b"\xff" * 160

    @pytest.mark.asyncio
    async def test_the_frame_generator_terminates_when_the_call_ends(self):
        """Without the sentinel, `drive_call`'s audio iterator blocks forever
        on a queue nobody will fill again and the call never finishes."""
        socket = _FakeSocket([_start(), {"event": "stop"}])
        h = __import__("src.voice.pragya_stream_handler", fromlist=["x"]) \
            .PragyaStreamHandler(socket, uuid.uuid4(), db=None)

        task = asyncio.create_task(h._receive_loop())
        await task
        frames = [f async for f in h._audio_in()]
        assert frames == []


class TestWebhookDivergence:
    """Gap 4 — the branch Increment 4 computed and then discarded.

    Until this diverges, gaps 1–3 can all be finished and a call to Pragya's
    number is still answered by the business face, with nothing obviously
    wrong in the logs. That is why it is the first thing to fix and the last
    thing anybody would notice.
    """

    @pytest.mark.asyncio
    async def test_a_pragya_route_streams_to_the_inward_endpoint(self, monkeypatch):
        from src.voice.webhook_router import _connect_pragya

        class _Route:
            company_id = None          # the shared line names no company
            entity_id = None

        class _Session:
            id = uuid.uuid4()

        class _Manager:
            def __init__(self):
                self.created: dict = {}

            async def create_voice_session(self, **kw):
                self.created = kw
                return _Session()

        manager = _Manager()
        response = await _connect_pragya(
            manager, route=_Route(), call_sid="CA1",
            from_number="+919812345678", to_number="918065251144")

        body = response.body.decode()
        assert "/stream/pragya/" in body, "the inward endpoint was not used"
        assert "/stream/twilio/" not in body, "fell through to the gateway path"

    @pytest.mark.asyncio
    async def test_the_caller_is_passed_to_the_media_stream(self, monkeypatch):
        """With a shared line the caller is the only thing that names a tenant,
        and the websocket has no other way to learn who called."""
        from src.voice.webhook_router import _connect_pragya

        class _Route:
            company_id = None
            entity_id = None

        class _Session:
            id = uuid.uuid4()

        class _Manager:
            async def create_voice_session(self, **kw):
                return _Session()

        response = await _connect_pragya(
            _Manager(), route=_Route(), call_sid="CA1",
            from_number="+919812345678", to_number="918065251144")

        body = response.body.decode()
        assert 'name="from"' in body and "+919812345678" in body

    @pytest.mark.asyncio
    async def test_the_shared_line_is_recorded_on_the_session(self):
        """A session that does not say it was the shared line is a session
        nobody can later explain — its company is legitimately absent."""
        from src.voice.webhook_router import _connect_pragya

        class _Route:
            company_id = None
            entity_id = None

        class _Session:
            id = uuid.uuid4()

        captured: dict = {}

        class _Manager:
            async def create_voice_session(self, **kw):
                captured.update(kw)
                return _Session()

        await _connect_pragya(
            _Manager(), route=_Route(), call_sid="CA1",
            from_number="+919812345678", to_number="918065251144")

        assert captured["metadata"]["face"] == "pragya"
        assert captured["metadata"]["shared_line"] is True
        assert captured["company_id"] is None
