"""STEWARD S4 — the browser voice leg, driven entirely against fakes.

The rules under test: readiness settled before the first frame; a spoken
final goes through the SAME turn path as a typed one; synthesis streams to
every device and stops on the client's barge-in signal; a broken leg fails
visible and the text channel survives; and — the tier rule stated in the
design — **nothing here touches a ceiling**: the phone's T1 cap is caller-
ID's, not voice's, and the module must not import it.
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from src.ai.genui import channel as ch
from src.ai.genui import voice_channel as vc

COMPANY = uuid.uuid4()
USER = uuid.uuid4()
SESSION = uuid.uuid4()


class FakeSocket:
    def __init__(self):
        self.sent: list[dict] = []
        self.audio: list[bytes] = []

    async def send_json(self, data):
        self.sent.append(data)

    async def send_bytes(self, data):
        self.audio.append(data)


class FakeTranscriber:
    """Yields scripted (text, is_final) pairs after draining the frames."""

    def __init__(self, turns):
        self.turns = turns
        self.heard_frames: list[bytes] = []

    def stream(self, audio):
        async def _run():
            async for frame in audio:
                self.heard_frames.append(frame)
            for text, final in self.turns:
                yield text, final
        return _run()


class FakeSpeaker:
    def __init__(self, chunks=(b"pcm-1", b"pcm-2")):
        self.chunks = list(chunks)
        self.spoke: list[str] = []

    def stream(self, text):
        self.spoke.append(text)

        async def _run():
            for chunk in self.chunks:
                yield chunk
        return _run()


@pytest.fixture()
def hub(monkeypatch):
    fresh = ch.ChannelHub()
    monkeypatch.setattr(ch, "_hub", fresh)
    return fresh


def _turn_stub(replies: dict[str, str]):
    heard: list[str] = []

    async def turn(state, company_id, user_id, text):
        heard.append(text)
        return replies.get(text)

    return turn, heard


async def _open(state, transcriber, speaker, turn):
    reply = await vc.open_mic(
        None, state, COMPANY, USER,
        transcriber=transcriber, speaker=speaker, turn=turn)
    assert reply is None
    return state.voice


@pytest.mark.asyncio
async def test_a_final_becomes_a_turn_and_the_reply_becomes_audio(hub):
    socket = FakeSocket()
    state = hub.join(SESSION, COMPANY, USER, socket)
    transcriber = FakeTranscriber([("approve", False), ("approve it", True)])
    speaker = FakeSpeaker()
    turn, heard = _turn_stub({"approve it": "Done — it's approved."})

    leg = await _open(state, transcriber, speaker, turn)
    await vc.feed_audio(state, b"frame-1")
    await vc.feed_audio(state, b"frame-2")
    await vc.close_mic(state)
    await leg.drive_task  # graceful close does not wait — the test must

    assert transcriber.heard_frames == [b"frame-1", b"frame-2"]
    assert heard == ["approve it"]  # the interim never became a turn
    assert speaker.spoke == ["Done — it's approved."]
    assert socket.audio == [b"pcm-1", b"pcm-2"]
    transcripts = [m for m in socket.sent if m["type"] == "transcript"]
    assert [(t["text"], t["final"]) for t in transcripts] == [
        ("approve", False), ("approve it", True)]
    presence = [m["state"] for m in socket.sent if m["type"] == "presence"]
    assert "speaking" in presence
    assert presence[-1] == "listening"
    assert leg.closed and state.voice is None


@pytest.mark.asyncio
async def test_audio_reaches_every_device_in_the_session(hub):
    desk, phone = FakeSocket(), FakeSocket()
    state = hub.join(SESSION, COMPANY, USER, desk)
    hub.join(SESSION, COMPANY, USER, phone)
    transcriber = FakeTranscriber([("hello", True)])
    turn, _ = _turn_stub({"hello": "Good morning."})

    leg = await _open(state, transcriber, FakeSpeaker(), turn)
    await vc.close_mic(state)
    await leg.drive_task

    assert desk.audio == [b"pcm-1", b"pcm-2"]
    assert phone.audio == [b"pcm-1", b"pcm-2"]


@pytest.mark.asyncio
async def test_a_second_mic_open_is_the_barge_in_signal(hub):
    """The client stops playback locally and re-opens the mic; the server
    stops synthesis at the next chunk — the phone leg's own pattern."""
    socket = FakeSocket()
    state = hub.join(SESSION, COMPANY, USER, socket)

    interrupted_speaker = FakeSpeaker(chunks=[b"c1", b"c2", b"c3"])
    original_stream = interrupted_speaker.stream

    def stream_and_interrupt(text):
        gen = original_stream(text)

        async def _run():
            count = 0
            async for chunk in gen:
                count += 1
                if count == 2:
                    # The human heard the first chunk and starts talking.
                    # The re-open interrupts her AND opens a fresh leg (the
                    # old frame stream has ended) — fakes injected always.
                    await vc.open_mic(
                        None, state, COMPANY, USER,
                        transcriber=FakeTranscriber([]),
                        speaker=FakeSpeaker(), turn=turn)
                yield chunk
        return _run()

    interrupted_speaker.stream = stream_and_interrupt
    transcriber = FakeTranscriber([("go on", True)])
    turn, _ = _turn_stub({"go on": "A long reply."})

    leg = await _open(state, transcriber, interrupted_speaker, turn)
    await vc.close_mic(state)
    await leg.drive_task

    # The first chunk went out; the interrupt stopped the rest.
    assert socket.audio == [b"c1"]
    # The re-open left a fresh leg listening for the human's next words.
    assert state.voice is not None and state.voice is not leg
    await vc.close_mic(state, abort=True)


@pytest.mark.asyncio
async def test_an_unready_tenant_is_told_not_silenced(hub, monkeypatch):
    async def not_ready(db, company_id):
        return False, "no ASR row"

    import src.ai.pragya.channels.speech as speech

    monkeypatch.setattr(speech, "voice_ready", not_ready)
    state = hub.join(SESSION, COMPANY, USER, FakeSocket())
    reply = await vc.open_mic(None, state, COMPANY, USER)
    assert reply == {"type": "error", "reason": vc.NOT_CONFIGURED_HERE}
    assert state.voice is None


@pytest.mark.asyncio
async def test_a_broken_leg_fails_visible_and_text_survives(hub):
    socket = FakeSocket()
    state = hub.join(SESSION, COMPANY, USER, socket)

    class BrokenTranscriber:
        def stream(self, audio):
            async def _run():
                raise RuntimeError("ASR fell over")
                yield  # pragma: no cover
            return _run()

    await vc.open_mic(
        None, state, COMPANY, USER,
        transcriber=BrokenTranscriber(), speaker=FakeSpeaker(),
        turn=_turn_stub({})[0])
    await asyncio.sleep(0.05)
    errors = [m for m in socket.sent if m["type"] == "error"]
    assert errors and "text channel" in errors[0]["reason"]
    assert state.voice is None
    # The session itself is untouched — a typed message still dispatches.
    reply = await ch.dispatch_message(
        None, state, COMPANY, USER, {"type": "viewport", "context_ref": {}})
    assert reply is None


@pytest.mark.asyncio
async def test_frames_with_no_open_leg_are_dropped_not_queued(hub):
    state = hub.join(SESSION, COMPANY, USER, FakeSocket())
    await vc.feed_audio(state, b"early")  # must simply not raise
    assert state.voice is None


def test_the_phone_ceiling_is_not_imported_here():
    """Voice on this channel is an input method, not a channel: console
    tier rules apply, and the module must not quietly borrow the phone's
    T1 cap. Pinned by AST — the design section says why."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(vc))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names}
    assert "voice_tier_ceiling" not in imported
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module}
    assert not any("voice_loop" in m for m in modules)
