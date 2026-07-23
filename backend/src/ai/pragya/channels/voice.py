"""pragya/channels/voice.py — Pragya on the phone (Inc-4 T5).

An ASR-LLM-TTS pipeline, deliberately not a realtime speech-to-speech model
(decision 3). Two reasons, and the second is the architectural one:

* **Session caps.** Realtime sessions run out well short of a months-long
  relationship, and a mid-conversation reconnect with your account manager is
  a bad experience.
* **A gateable turn boundary.** ASR-LLM-TTS produces a discrete text-in /
  text-out unit, so the tier classifier, the PolicyGate and the artifact
  extractor all work on a voice turn *unchanged*. A realtime model owns the
  conversation and never surfaces a boundary to gate — voice would have become
  a parallel universe with its own rules.

So this module contains **no policy at all**. It turns audio into a
``TurnRequest``, calls the one turn loop, and speaks the ``TurnOutcome`` back.
Every authorisation question is answered where it already was.

**The latency tax is real and is paid deliberately** (§6.2): roughly 0.8–1.4 s
to first audio against ~300 ms for realtime. Three mitigations are structural
rather than optional — stream the ASR, stream the TTS, and support barge-in.
A non-streaming TTS makes a call feel broken however fast the model is.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.inward_auth.models import ChannelKind
from src.ai.pragya.channels.speech import (
    Speaker,
    SpeechConfigError,
    Transcriber,
    voice_ready,
)
from src.ai.pragya.runtime import TurnOutcome, TurnRequest, run_turn
from src.ai.voice_loop.identity import UNKNOWN_CALLER_GREETING, identify_caller

logger = logging.getLogger(__name__)

__all__ = [
    "VoiceTurn",
    "CallState",
    "NOT_CONFIGURED",
    "THINKING_FILLER",
    "handle_voice_turn",
    "drive_call",
]


NOT_CONFIGURED = (
    "Sorry — voice isn't set up on this account yet, so I can't help over the "
    "phone. Everything still works in the web console."
)

#: Said while the model is thinking, when a turn looks like it will run long.
#: Not decoration: ~1 s of silence on a phone reads as a dropped call, and a
#: caller who thinks the line died hangs up mid-turn.
THINKING_FILLER = "Let me check that for you."

#: How long to wait before filling. Below this the reply usually arrives first
#: and the filler would talk over it.
FILLER_AFTER_SECONDS = 1.2


@dataclass
class CallState:
    """One call in flight."""

    company_id: uuid.UUID
    call_sid: str
    from_number: str
    user_id: uuid.UUID | None = None
    bound: bool = False
    transcript: list[dict[str, str]] = field(default_factory=list)
    #: Set when the caller speaks over Pragya — synthesis stops immediately.
    interrupted: bool = False

    def record(self, role: str, content: str) -> None:
        self.transcript.append({"role": role, "content": content})


@dataclass
class VoiceTurn:
    """What one spoken turn produced."""

    said: str
    outcome: TurnOutcome | None = None
    ended_call: bool = False


async def handle_voice_turn(
    db: AsyncSession,
    state: CallState,
    heard: str,
) -> VoiceTurn:
    """One spoken turn: transcript in, words to speak out.

    Contains no authorisation logic. ``run_turn`` classifies, authorises,
    acts and meters exactly as it does for the console — which is the entire
    point of choosing a pipeline that yields a text turn.
    """
    state.record("caller", heard)

    outcome = await run_turn(db, TurnRequest(
        company_id=state.company_id,
        text=heard,
        user_id=state.user_id,
        channel_kind=ChannelKind.VOICE,
        channel_address=state.from_number,
    ))

    reply = outcome.reply

    # A T2/T3 command cannot be completed by voice: the ceiling refuses it and
    # step-up is a console ceremony. Say where it went rather than trailing
    # off — a caller told "I can't" with no path finds a way around the system
    # instead of through it.
    if outcome.needs_step_up or outcome.needs_oob:
        reply = (f"{reply} I've sent a link to your registered channel — "
                 f"approve it there and I'll have it done in seconds.")

    state.record("pragya", reply)
    return VoiceTurn(said=reply, outcome=outcome)


async def _speak(
    speaker: Speaker, state: CallState, text: str,
) -> AsyncIterator[bytes]:
    """Stream synthesis, stopping the moment the caller speaks.

    Barge-in is not a nicety. Continuing to talk over someone is the single
    most irritating thing a phone system does, and on a long reply it makes
    the call unusable.
    """
    async for chunk in speaker.stream(text):
        if state.interrupted:
            logger.debug("barge-in on call %s — stopping synthesis", state.call_sid)
            break
        yield chunk


async def drive_call(
    db: AsyncSession,
    state: CallState,
    transcriber: Transcriber,
    speaker: Speaker,
    audio_in: AsyncIterator[bytes],
) -> AsyncIterator[bytes]:
    """Drive a whole call: inbound audio in, outbound audio out.

    Readiness and identity are settled **before** the first word, not
    discovered mid-call. A caller who hears silence has been failed worse than
    one who is told voice is not set up.
    """
    ready, why = await voice_ready(db, state.company_id)
    if not ready:
        logger.warning("voice call refused for %s: %s", state.company_id, why)
        async for chunk in speaker.stream(NOT_CONFIGURED):
            yield chunk
        return

    caller = await identify_caller(
        db, company_id=state.company_id, from_number=state.from_number)
    state.user_id = caller.user_id
    state.bound = caller.bound

    if not caller.bound:
        # An unregistered number gets help, not an account. She must not
        # confirm whose account it might be either.
        state.record("pragya", UNKNOWN_CALLER_GREETING)
        async for chunk in _speak(speaker, state, UNKNOWN_CALLER_GREETING):
            yield chunk
        return

    async for text, is_final in transcriber.stream(audio_in):
        if not is_final:
            # A partial while Pragya is speaking is the caller interrupting.
            if text.strip():
                state.interrupted = True
            continue

        heard = text.strip()
        if not heard:
            continue

        state.interrupted = False
        turn = await handle_voice_turn(db, state, heard)

        async for chunk in _speak(speaker, state, turn.said):
            yield chunk

        if turn.ended_call:
            return
