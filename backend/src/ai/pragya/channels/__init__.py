"""pragya/channels — the transports Pragya is reachable on (Inc-4 T5).

A channel is a *transport*, not a policy. Each adapter normalises whatever it
receives into a ``TurnRequest``, hands it to the one turn loop
(``runtime.run_turn``), and renders the ``TurnOutcome`` back in its own medium.

That is the whole reason decision 3 chose an ASR-LLM-TTS pipeline for voice
over a realtime speech-to-speech model: a text-boundaried turn is the only
kind the tier classifier, the PolicyGate and the artifact extractor can see.
A realtime model owns the conversation and never surfaces a gateable
boundary, which would have made voice a parallel universe with its own rules.

* ``speech``  — ASR and TTS, resolved through the IntegrationRegistry.
* ``voice``   — the call pipeline: audio → ASR → turn → TTS → audio.
* ``routing`` — which inbound number belongs to Pragya rather than KAR-01.
"""
from __future__ import annotations

__all__ = ["ASR_SKU", "TTS_SKU_IN", "TTS_SKU_OUT", "TTS_SKUS"]

from src.ai.pragya.channels.speech import (
    ASR_SKU, TTS_SKU_IN, TTS_SKU_OUT, TTS_SKUS,
)
