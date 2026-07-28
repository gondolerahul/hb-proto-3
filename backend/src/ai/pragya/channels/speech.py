"""pragya/channels/speech.py — ASR and TTS, via the IntegrationRegistry.

Decision 7: **Whisper on Vertex AI** for speech-to-text, **Google Gemini TTS**
for text-to-speech, both resolved as registry entries rather than hardcoded
clients.

That indirection is not ceremony. Going through the registry means a provider
carries its own credentials, its own ``internal_cost`` and ``cost_unit``, and
its own ``service_metadata`` — so voice minutes are metered and attributed
exactly like every other paid service, and swapping a provider is a row rather
than a deploy. A hardcoded client would have needed a second, private story
for all three.

**Both sides must stream.** A non-streaming TTS makes a call feel broken no
matter how fast the model is: the caller hears nothing until the whole reply
is synthesised. The protocols below are written around that, and an adapter
that cannot stream should say so rather than pretend.

Unconfigured is a first-class state. A tenant with no ASR entry cannot take
voice calls, and the honest response is to say so — not to fall back to a
provider they never chose and get billed for.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.models import IntegrationRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "ASR_SKU",
    "TTS_SKU_IN",
    "TTS_SKU_OUT",
    "TTS_SKUS",
    "SpeechConfigError",
    "ResolvedProvider",
    "Transcriber",
    "Speaker",
    "resolve_asr",
    "resolve_tts",
    "voice_ready",
]

#: The registry SKUs Pragya's voice face resolves. Seeded per tenant (or at
#: the platform company, which the usage service already falls back to).
#:
#: **ASR is one SKU, TTS is a pair, and that asymmetry is the billing model
#: rather than an inconsistency.** Chirp 3 bills per minute of audio, so one
#: row carries the whole cost. Gemini TTS bills per token in *and* per token
#: out, and this registry has always split a token-billed service into `-in`
#: and `-out` rows (`gemini-2.5-flash-in`/`-out`, `gpt-5.5-in`/`-out`). The
#: first version of this module assumed a single per-character TTS row and was
#: simply wrong about the product.
#:
#: Chirp rather than Whisper (owner decision, 2026-07-26): Whisper on Vertex
#: Model Garden is a self-deployed endpoint billed per node-hour, which for a
#: phone line idle most of the day is a standing charge for nothing. Chirp 3 is
#: managed, supports `StreamingRecognize`, and bills per minute.
ASR_SKU = "pragya-asr-chirp-vertex"
TTS_SKU_IN = "pragya-tts-gemini-in"
TTS_SKU_OUT = "pragya-tts-gemini-out"

#: What `voice_ready` and `resolve_tts` must find. Both halves, because a
#: tenant with only the input row configured would be billed silently wrong
#: rather than told they are not set up.
TTS_SKUS = (TTS_SKU_IN, TTS_SKU_OUT)


class SpeechConfigError(RuntimeError):
    """Voice is not configured for this tenant. Not an internal failure."""


@dataclass(frozen=True)
class ResolvedProvider:
    """A registry entry plus its decrypted key, ready to build a client from."""

    sku: str
    provider_name: str
    model_name: str | None
    api_key: str | None
    metadata: dict[str, Any]

    @property
    def project_id(self) -> str | None:
        return self.metadata.get("project_id")

    @property
    def region(self) -> str:
        return str(self.metadata.get("region") or "us-central1")


class Transcriber(Protocol):
    """Streaming speech-to-text.

    ``stream`` yields *partial* transcripts as they firm up and a final one
    when the speaker stops. Partials are what make barge-in and responsive
    endpointing possible; an adapter that only ever yields a final transcript
    turns every turn into a wait.
    """

    def stream(
        self, audio: AsyncIterator[bytes],
    ) -> AsyncIterator[tuple[str, bool]]:
        """Yield ``(text, is_final)``.

        Declared as a plain ``def`` returning an ``AsyncIterator``: an async
        *generator* method is not a coroutine, and typing it ``async def``
        would oblige every caller to await before iterating.
        """
        ...


class Speaker(Protocol):
    """Streaming text-to-speech.

    ``stream`` must begin emitting audio before the whole text is synthesised.
    Time-to-first-byte is what the caller experiences as responsiveness; total
    synthesis time is invisible to them.
    """

    def stream(self, text: str) -> AsyncIterator[bytes]:
        ...


async def _resolve(
    db: AsyncSession, company_id: uuid.UUID, sku: str,
) -> ResolvedProvider:
    """Load a SKU for a tenant, falling back to the platform-owned entry.

    Same fallback the usage service uses: cost-bearing services are owned by
    the APP company, and a tenant without its own entry should use the
    platform's rather than failing.
    """
    from src.ai.usage_service import UsageService
    from src.common.security import decrypt_api_key

    entry = (await db.execute(
        select(IntegrationRegistry).where(
            IntegrationRegistry.company_id == company_id,
            IntegrationRegistry.service_sku == sku,
            IntegrationRegistry.status == "active",
        ).limit(1)
    )).scalars().first()

    if entry is None:
        app_company_id = await UsageService(db)._get_app_company_id()
        if app_company_id is not None:
            entry = (await db.execute(
                select(IntegrationRegistry).where(
                    IntegrationRegistry.company_id == app_company_id,
                    IntegrationRegistry.service_sku == sku,
                    IntegrationRegistry.status == "active",
                ).limit(1)
            )).scalars().first()

    if entry is None:
        raise SpeechConfigError(
            f"no active '{sku}' entry in the integration registry — voice is "
            f"not configured for this tenant")

    # IntegrationRegistry is a legacy Column-style model, so its attributes
    # carry no static type — coerce at the boundary rather than threading
    # Any through everything downstream.
    encrypted = cast(Optional[str], entry.encrypted_api_key)
    key = decrypt_api_key(encrypted) if encrypted else None
    model_name = cast(Optional[str], entry.model_name)

    return ResolvedProvider(
        sku=sku,
        provider_name=str(entry.provider_name),
        model_name=model_name,
        api_key=key,
        metadata=dict(cast(Optional[dict[str, Any]], entry.service_metadata) or {}),
    )


async def resolve_asr(
    db: AsyncSession, company_id: uuid.UUID,
) -> ResolvedProvider:
    """Whisper on Vertex AI, per decision 7."""
    return await _resolve(db, company_id, ASR_SKU)


async def resolve_tts(
    db: AsyncSession, company_id: uuid.UUID,
) -> ResolvedProvider:
    """Gemini TTS — resolved from the **output** row.

    A token-billed service is two registry rows, and the adapter needs one set
    of credentials. The `-out` row is the authority because output tokens are
    where the synthesis cost actually lands; the `-in` row exists so the
    prompt side is metered and is validated by `voice_ready`, not read here.
    """
    return await _resolve(db, company_id, TTS_SKU_OUT)


async def voice_ready(
    db: AsyncSession, company_id: uuid.UUID,
) -> tuple[bool, str]:
    """Whether this tenant can take a voice call, and why not if it cannot.

    Checked *before* answering rather than discovered mid-call: a caller who
    hears silence has been failed worse than one who is told voice is not set
    up yet.
    """
    missing: list[str] = []
    # Every SKU, not just the two the adapters read: a tenant with the `-in`
    # row missing is configured wrongly rather than configured partially, and
    # the honest moment to say so is before the phone rings.
    for sku in (ASR_SKU, TTS_SKU_IN, TTS_SKU_OUT):
        try:
            await _resolve(db, company_id, sku)
        except SpeechConfigError:
            missing.append(sku)
    if missing:
        return False, f"voice is not configured: missing {', '.join(missing)}"
    return True, "voice is configured"
