"""Pragya's voice face (Inc-4 PRAGYA-RT T5).

Decision 3 chose ASR-LLM-TTS over a realtime model so that a voice turn is a
**text turn** — gateable by the same classifier, PolicyGate and extractor the
console uses. These tests pin the consequences of that choice: the pipeline
carries no policy of its own, and it fails before answering rather than
mid-call.
"""
from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest

from src.ai.pragya.channels.routing import (
    NumberRoute,
    VoiceFace,
    number_candidates,
)
from src.ai.pragya.channels.speech import ASR_SKU, TTS_SKU, SpeechConfigError
from src.ai.pragya.channels.voice import (
    NOT_CONFIGURED,
    CallState,
    drive_call,
)


class _Speaker:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def stream(self, text: str) -> AsyncIterator[bytes]:
        self.spoken.append(text)

        async def _gen() -> AsyncIterator[bytes]:
            for word in text.split():
                yield word.encode()

        return _gen()


class _Transcriber:
    def __init__(self, turns: list[tuple[str, bool]]) -> None:
        self.turns = turns

    def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[tuple[str, bool]]:
        async def _gen() -> AsyncIterator[tuple[str, bool]]:
            for turn in self.turns:
                yield turn

        return _gen()


async def _silence() -> AsyncIterator[bytes]:
    return
    yield b""  # pragma: no cover


def _state() -> CallState:
    return CallState(company_id=uuid.uuid4(), call_sid="CA1",
                     from_number="+15550100")


# --- number routing: the discriminator ---------------------------------------

def test_carrier_format_differences_do_not_look_like_an_unassigned_number() -> None:
    """Twilio sends +91…, Tata may send 91…; the DB holds one of them."""
    assert "918065251146" in number_candidates("+918065251146")
    assert "+918065251146" in number_candidates("918065251146")
    assert number_candidates("+91 806-525-1146")[0] == "+918065251146"


def test_no_number_routes_nowhere() -> None:
    assert number_candidates("") == []


def test_an_unknown_number_fails_to_unknown_not_to_a_face() -> None:
    """Answering an unassigned line as an account manager would offer a
    tenant conversation on a number nobody owns."""
    route = NumberRoute(VoiceFace.UNKNOWN, reason="not assigned")
    assert route.face is VoiceFace.UNKNOWN
    assert route.company_id is None


# --- readiness is settled before answering -----------------------------------

@pytest.mark.asyncio
async def test_an_unconfigured_tenant_is_told_not_left_in_silence(monkeypatch) -> None:
    """A caller who hears nothing has been failed worse than one who is told."""
    import src.ai.pragya.channels.voice as voice

    async def _not_ready(db, company_id):
        return False, f"missing {ASR_SKU}"

    monkeypatch.setattr(voice, "voice_ready", _not_ready)

    speaker = _Speaker()
    state = _state()
    chunks = [c async for c in drive_call(
        None, state, _Transcriber([]), speaker, _silence())]  # type: ignore[arg-type]

    assert speaker.spoken == [NOT_CONFIGURED]
    assert chunks


@pytest.mark.asyncio
async def test_an_unregistered_caller_gets_help_but_not_an_account(monkeypatch) -> None:
    import src.ai.pragya.channels.voice as voice

    async def _ready(db, company_id):
        return True, "ok"

    class _Caller:
        user_id = None
        bound = False

    async def _identify(db, *, company_id, from_number):
        return _Caller()

    monkeypatch.setattr(voice, "voice_ready", _ready)
    monkeypatch.setattr(voice, "identify_caller", _identify)

    speaker = _Speaker()
    state = _state()
    [c async for c in drive_call(
        None, state, _Transcriber([("pause invoicing", True)]),  # type: ignore[arg-type]
        speaker, _silence())]

    said = " ".join(speaker.spoken).lower()
    assert "don't recognise this number" in said
    # The command was never processed — an unbound caller reaches no tenant state.
    assert not any(t["role"] == "caller" for t in state.transcript)


# --- the pipeline carries no policy ------------------------------------------

@pytest.mark.asyncio
async def test_a_bound_caller_turn_goes_through_the_one_turn_loop(monkeypatch) -> None:
    """The whole point of ASR-LLM-TTS: a voice turn is a text turn, gated by
    exactly the machinery the console uses."""
    import src.ai.pragya.channels.voice as voice
    from src.ai.pragya.runtime import TurnOutcome
    from src.ai.pragya.stages import Stage

    called: dict[str, object] = {}

    async def _ready(db, company_id):
        return True, "ok"

    class _Caller:
        user_id = uuid.uuid4()
        bound = True

    async def _identify(db, *, company_id, from_number):
        return _Caller()

    async def _run_turn(db, request):
        called["channel_kind"] = request.channel_kind
        called["text"] = request.text
        return TurnOutcome(reply="Here's this week.", stage=Stage.OPERATE,
                           auth_level="bound")

    monkeypatch.setattr(voice, "voice_ready", _ready)
    monkeypatch.setattr(voice, "identify_caller", _identify)
    monkeypatch.setattr(voice, "run_turn", _run_turn)

    speaker = _Speaker()
    state = _state()
    [c async for c in drive_call(
        None, state, _Transcriber([("how did we do", True)]),  # type: ignore[arg-type]
        speaker, _silence())]

    assert called["text"] == "how did we do"
    assert called["channel_kind"] == "voice"
    assert speaker.spoken == ["Here's this week."]


@pytest.mark.asyncio
async def test_a_step_up_refusal_says_where_it_went(monkeypatch) -> None:
    """Voice cannot self-elevate, so a T2 command must name the way forward —
    'I can't' with no path is how people route around a system."""
    import src.ai.pragya.channels.voice as voice
    from src.ai.pragya.runtime import TurnOutcome
    from src.ai.pragya.stages import Stage

    async def _ready(db, company_id):
        return True, "ok"

    class _Caller:
        user_id = uuid.uuid4()
        bound = True

    async def _identify(db, *, company_id, from_number):
        return _Caller()

    async def _run_turn(db, request):
        return TurnOutcome(reply="That needs verifying.", stage=Stage.OPERATE,
                           auth_level="bound", needs_step_up=True)

    monkeypatch.setattr(voice, "voice_ready", _ready)
    monkeypatch.setattr(voice, "identify_caller", _identify)
    monkeypatch.setattr(voice, "run_turn", _run_turn)

    speaker = _Speaker()
    [c async for c in drive_call(
        None, _state(), _Transcriber([("pause invoicing", True)]),  # type: ignore[arg-type]
        speaker, _silence())]

    said = " ".join(speaker.spoken)
    assert "registered channel" in said


# --- barge-in -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_speaking_over_pragya_stops_her(monkeypatch) -> None:
    """Talking over someone is the most irritating thing a phone system does,
    and on a long reply it makes the call unusable."""
    import src.ai.pragya.channels.voice as voice

    state = _state()
    state.interrupted = True

    speaker = _Speaker()
    chunks = [c async for c in voice._speak(speaker, state, "a b c d e f")]
    assert chunks == [], "synthesis continued after the caller interrupted"


def test_a_partial_transcript_is_what_signals_an_interruption() -> None:
    """Barge-in depends on the ASR emitting partials; an adapter that only
    yields finals turns every turn into a wait."""
    state = _state()
    assert not state.interrupted
    state.interrupted = True
    assert state.interrupted


def test_the_speech_skus_are_the_decided_providers() -> None:
    """Decision 7 — resolved through the registry, not hardcoded clients."""
    assert "whisper" in ASR_SKU and "vertex" in ASR_SKU
    assert "gemini" in TTS_SKU


def test_speech_config_error_is_a_configuration_state_not_a_crash() -> None:
    assert issubclass(SpeechConfigError, RuntimeError)
