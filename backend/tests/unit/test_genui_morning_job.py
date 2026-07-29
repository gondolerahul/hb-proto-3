"""LINE L2 — the morning job's pure parts and its failure postures.

What the unit layer proves: the WAV header is bit-correct (a wrong rate
plays at the wrong speed and raises nothing — the slowest bug to notice),
her spoken and written telling are the same telling, the summary puts
whoever-needs-you first and leaves quiet cards out of the pocket, a
broken voice loses audio never text, and MORNING_STORY is classified on
the tenant side of B13 by name.
"""
from __future__ import annotations

import struct

import pytest

from src.ai.genui.morning_job import (
    WAV_SAMPLE_RATE,
    _synthesize,
    spoken_text,
    summary_lines,
    wav_wrap,
)
from src.ai.services.cost_attribution import (
    PLATFORM_INITIATED_ATTRIBUTIONS,
    VALID_ATTRIBUTIONS,
    CostAttribution,
)


def test_the_wav_header_is_bit_correct():
    pcm = b"\x01\x02" * 100
    wav = wav_wrap(pcm)
    riff, size, wave = struct.unpack("<4sI4s", wav[:12])
    assert (riff, wave) == (b"RIFF", b"WAVE")
    assert size == 36 + len(pcm)
    fmt = struct.unpack("<4sIHHIIHH", wav[12:36])
    assert fmt[2] == 1          # PCM
    assert fmt[3] == 1          # mono
    assert fmt[4] == WAV_SAMPLE_RATE
    assert fmt[5] == WAV_SAMPLE_RATE * 2  # byte rate
    assert fmt[7] == 16         # bits per sample
    data, length = struct.unpack("<4sI", wav[36:44])
    assert (data, length) == (b"data", len(pcm))
    assert wav[44:] == pcm


def test_her_spoken_and_written_telling_are_the_same():
    card = {"name": "Ravi", "sentences": ["Finished one piece of work.",
                                          "Is waiting on you."]}
    assert spoken_text(card) == (
        "Ravi. Finished one piece of work. Is waiting on you.")


def test_the_summary_puts_whoever_needs_you_first_and_skips_the_quiet():
    lines = summary_lines([
        {"name": "Meera", "waiting": True,
         "sentences": ["Finished 3 pieces of work since yesterday.",
                       "Is waiting on you."]},
        {"name": "Ravi", "waiting": False,
         "sentences": ["Finished one piece of work since yesterday."]},
        {"name": "Quiet", "waiting": False,
         "sentences": ["A quiet day — nothing to report."]},
    ])
    assert lines == [
        "Meera is waiting on you.",
        "Ravi: Finished one piece of work since yesterday.",
    ]


class FakeSpeaker:
    def __init__(self, fail_on: str | None = None):
        self.fail_on = fail_on

    def stream(self, text):
        async def _run():
            if self.fail_on is not None and self.fail_on in text:
                raise RuntimeError("tts down")
            yield b"\x00\x01"
        return _run()


@pytest.mark.asyncio
async def test_synthesis_fills_cards_in_place():
    cards = [
        {"name": "A", "sentences": ["s"], "audio": None},
        {"name": "B", "sentences": ["s"], "audio": None},
    ]
    degraded = await _synthesize(cards, FakeSpeaker())
    assert degraded is None
    for card in cards:
        assert card["audio"]["mime"] == "audio/wav"
        assert len(card["audio"]["data_b64"]) > 0


@pytest.mark.asyncio
async def test_a_half_voiced_story_beats_a_silent_one():
    cards = [
        {"name": "A", "sentences": ["fine"], "audio": None},
        {"name": "B", "sentences": ["broken"], "audio": None},
        {"name": "C", "sentences": ["fine too"], "audio": None},
    ]
    degraded = await _synthesize(cards, FakeSpeaker(fail_on="broken"))
    assert degraded == "tts_failed"
    assert cards[0]["audio"] is not None   # the clip already made survives
    assert cards[1]["audio"] is None


def test_morning_story_is_registered_and_tenant_initiated():
    assert CostAttribution.MORNING_STORY.value in VALID_ATTRIBUTIONS
    assert (CostAttribution.MORNING_STORY.value
            not in PLATFORM_INITIATED_ATTRIBUTIONS)
