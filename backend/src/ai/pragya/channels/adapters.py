"""pragya/channels/adapters.py — concrete ASR and TTS behind the Protocols (gap 2).

`speech.py` declared `Transcriber` and `Speaker` in Increment 4 and nothing ever
implemented them, which is what made voice "a tested seam, not a live call".
These are the implementations.

**Tested seam, not a live integration** — the FLEET / Zoho `MCPClient` pattern.
Both adapters take an *injectable* `transport`, so every test drives them
against fakes and **no live Google call is made here**. Building the live
transport needs credentials in hand and is deliberately the last step, not a
guess baked into the pipeline.

**Both stream, and the reasons differ.** A non-streaming TTS makes a call feel
broken regardless of model speed: the caller hears nothing until the whole
reply is synthesised, and time-to-first-byte is the only latency they
experience. A non-streaming ASR is worse — without interim results there is no
barge-in and no responsive endpointing, so every turn becomes a wait for
silence.

**Audio formats are the carrier's, not the model's.** Twilio and Tata both
speak 8 kHz μ-law; the models do not. Conversion lives in the shipped
`AudioProcessor` (`mulaw_to_pcm16`, `pcm24_to_mulaw`) rather than being
reinvented here — it already handles the 20 ms frame alignment that stops
audible clicks at frame edges.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from src.ai.pragya.channels.speech import ResolvedProvider

logger = logging.getLogger(__name__)


class SpeechConfigNotUsable(RuntimeError):
    """The registry row exists but cannot be used to build a client.

    Distinct from `SpeechConfigError`, which means *no row*. This one means a
    row that is present and wrong — and the two want different fixes, so
    collapsing them would send an operator looking for a missing row that is
    right there.
    """


__all__ = [
    "SpeechConfigNotUsable",
    "AsrTransport",
    "TtsTransport",
    "ChirpTranscriber",
    "GeminiSpeaker",
    "build_transcriber",
    "build_speaker",
]

#: ``(audio_frames) -> yields (text, is_final)``. The live implementation wraps
#: Google Cloud Speech-to-Text v2 `StreamingRecognize`; a fake yields scripted
#: turns.
AsrTransport = Callable[[AsyncIterator[bytes]], AsyncIterator[tuple[str, bool]]]

#: ``(text) -> yields PCM audio chunks``. The live implementation wraps Gemini
#: TTS streaming synthesis.
TtsTransport = Callable[[str], AsyncIterator[bytes]]

#: Gemini emits 24 kHz PCM; the carrier wants 8 kHz μ-law. Named rather than
#: inlined because getting it wrong produces audio that plays at the wrong
#: speed rather than an error, which is a slow thing to notice.
GEMINI_TTS_SAMPLE_RATE = 24000


class ChirpTranscriber:
    """Streaming speech-to-text over Chirp 3.

    Satisfies `speech.Transcriber`. Owner decision 2026-07-26: Chirp rather
    than Whisper — Whisper on Vertex Model Garden is a self-deployed endpoint
    billed per node-hour, a standing charge for a line that is idle most of the
    day, while Chirp 3 is managed, supports `StreamingRecognize` and bills per
    minute of audio.

    **Carrier μ-law is converted before it reaches the model.** The adapter
    takes the frames the websocket handler already has (8 kHz μ-law) so no
    caller has to know what the model wants, and converts once here.
    """

    def __init__(
        self,
        provider: ResolvedProvider,
        transport: Optional[AsrTransport] = None,
        *,
        convert_from_mulaw: bool = True,
    ) -> None:
        self.provider = provider
        self._transport = transport or _live_asr_transport(provider)
        self._convert = convert_from_mulaw

    def stream(
        self, audio: AsyncIterator[bytes],
    ) -> AsyncIterator[tuple[str, bool]]:
        """Yield ``(text, is_final)`` as the caller speaks.

        A plain ``def`` returning an ``AsyncIterator``, matching the Protocol:
        an async *generator* method is not a coroutine, and typing it
        ``async def`` would oblige every caller to await before iterating.
        """
        return self._transport(self._prepared(audio) if self._convert else audio)

    async def _prepared(self, audio: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        """8 kHz μ-law from the carrier → 16 kHz PCM16 for the model."""
        from src.voice.audio_processor import AudioProcessor

        async for frame in audio:
            if not frame:
                continue
            converted = AudioProcessor.mulaw_to_pcm16(frame)
            # `mulaw_to_pcm16` returns b"" on a conversion failure rather than
            # raising. Forwarding empty frames would look to the model like
            # silence, so the caller's turn would simply never end — drop them
            # and let the next frame carry the audio.
            if converted:
                yield converted


class GeminiSpeaker:
    """Streaming text-to-speech over Gemini TTS.

    Satisfies `speech.Speaker`. Emits **8 kHz μ-law frames ready for the
    carrier**, because the alternative is every call site knowing that Gemini
    speaks 24 kHz PCM — and a rate mismatch here does not raise, it just plays
    the reply at the wrong speed.
    """

    def __init__(
        self,
        provider: ResolvedProvider,
        transport: Optional[TtsTransport] = None,
        *,
        convert_to_mulaw: bool = True,
    ) -> None:
        self.provider = provider
        self._transport = transport or _live_tts_transport(provider)
        self._convert = convert_to_mulaw

    def stream(self, text: str) -> AsyncIterator[bytes]:
        return self._converted(text) if self._convert else self._transport(text)

    async def _converted(self, text: str) -> AsyncIterator[bytes]:
        from src.voice.audio_processor import AudioProcessor

        async for chunk in self._transport(text):
            if not chunk:
                continue
            mulaw = AudioProcessor.pcm24_to_mulaw(chunk)
            if mulaw:
                yield mulaw


def _live_asr_transport(provider: ResolvedProvider) -> AsrTransport:
    """Chirp 3 over Cloud Speech-to-Text v2 streaming.

    **Never exercised by a test** — every test injects a transport. Built
    lazily so importing this module needs no credentials, the same shape
    FLEET's adapter uses, and the reason the rest of the pipeline could be
    finished and proven before the account was live.

    Owner answers (Phase 1, 2026-07-28): the **`us` multi-region**, and
    **ADC / service account** rather than an API key — so no key is read from
    the registry row here, and the client picks up the ambient credentials.

    The recognizer path ends in ``_``, which is Speech-v2's "configure inline"
    form: the config travels in the first request rather than being a
    pre-created recognizer resource somebody has to provision separately.
    """

    async def _transport(audio: AsyncIterator[bytes]) -> AsyncIterator[tuple[str, bool]]:
        from google.cloud.speech_v2 import SpeechAsyncClient
        from google.cloud.speech_v2.types import cloud_speech
        from google.api_core.client_options import ClientOptions

        project = provider.project_id
        if not project:
            raise SpeechConfigNotUsable(
                f"{provider.sku!r} has no project_id in service_metadata")
        region = provider.region

        client = SpeechAsyncClient(client_options=ClientOptions(
            api_endpoint=f"{region}-speech.googleapis.com"))
        recognizer = f"projects/{project}/locations/{region}/recognizers/_"

        config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=[provider.metadata.get("language_code", "en-US")],
            model=provider.model_name or "chirp_3",
        )
        streaming_config = cloud_speech.StreamingRecognitionConfig(config=config)

        async def _requests() -> AsyncIterator[Any]:
            yield cloud_speech.StreamingRecognizeRequest(
                recognizer=recognizer, streaming_config=streaming_config)
            async for frame in audio:
                yield cloud_speech.StreamingRecognizeRequest(audio=frame)

        # `streaming_recognize` returns an awaitable that resolves to an async
        # iterable in some versions of the SDK and the iterable directly in
        # others. Tolerating both is not defensive clutter: **this line has
        # never run against a live endpoint** (no test may reach it — see
        # tests/unit/test_pragya_voice_adapters.py), so guessing one shape
        # would turn a version difference into a failed first call with a
        # confusing `TypeError`.
        pending = client.streaming_recognize(requests=_requests())
        responses = await pending if inspect.isawaitable(pending) else pending

        async for response in responses:
            for result in response.results:
                if not result.alternatives:
                    continue
                # Chirp 3 emits **no interim results** (owner, Phase 1), so
                # `is_final` is read from the response rather than assumed —
                # it will be True on every result today, and an ASR that gains
                # interims later starts working without a change here.
                yield (result.alternatives[0].transcript, bool(result.is_final))

    return _transport


def _live_tts_transport(provider: ResolvedProvider) -> TtsTransport:
    """Gemini TTS streaming synthesis over Vertex.

    **Never exercised by a test.** ADC / service account (Phase 1), so the
    client is built with ``vertexai=True`` and no API key.

    Yields raw PCM; `GeminiSpeaker` converts to carrier μ-law.
    """

    async def _transport(text: str) -> AsyncIterator[bytes]:
        from google import genai
        from google.genai import types as genai_types

        project = provider.project_id
        if not project:
            raise SpeechConfigNotUsable(
                f"{provider.sku!r} has no project_id in service_metadata")

        client = genai.Client(vertexai=True, project=project,
                              location=provider.region)
        voice = provider.metadata.get("voice_name", "Kore")

        stream = await client.aio.models.generate_content_stream(
            model=provider.model_name or "gemini-3.1-flash-tts-preview",
            contents=text,
            config=genai_types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=genai_types.SpeechConfig(
                    voice_config=genai_types.VoiceConfig(
                        prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                            voice_name=voice))),
            ),
        )
        async for chunk in stream:
            for candidate in (chunk.candidates or []):
                for part in (candidate.content.parts or []):
                    data = getattr(getattr(part, "inline_data", None), "data", None)
                    if data:
                        yield data

    return _transport


async def build_transcriber(
    db: Any, company_id: Any, *, transport: Optional[AsrTransport] = None,
) -> ChirpTranscriber:
    """Resolve the ASR provider for a tenant and build its transcriber.

    Raises `SpeechConfigError` when the tenant has no ASR row — which the
    caller should have checked with `voice_ready` *before* answering, because a
    caller who hears silence has been failed worse than one who is told.
    """
    from src.ai.pragya.channels.speech import resolve_asr

    return ChirpTranscriber(await resolve_asr(db, company_id), transport)


async def build_speaker(
    db: Any, company_id: Any, *, transport: Optional[TtsTransport] = None,
) -> GeminiSpeaker:
    """Resolve the TTS provider for a tenant and build its speaker."""
    from src.ai.pragya.channels.speech import resolve_tts

    return GeminiSpeaker(await resolve_tts(db, company_id), transport)
