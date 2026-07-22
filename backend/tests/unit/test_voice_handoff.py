"""Warm transfer inside a live call (Inc-3 VOICE V5, B7's second question).

The mechanism is a context-preserving agent switch on the same media session,
not a telephony bridge. Two properties are pinned here: continuity (the caller
never repeats themselves) and the ceiling direction (transfer can lower
authority, never raise it).
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.inward_auth.tiers import Tier
from src.ai.voice_loop.handoff import (
    TRANSCRIPT_SUMMARY_CHARS,
    _clamp_ceiling,
    opening_line,
    summarise_transcript,
)
from src.ai.voice_loop.models import VoiceHandoff


# --- the ceiling may only fall ------------------------------------------------

def test_a_handoff_cannot_raise_the_tier_ceiling() -> None:
    """If it could, 'put me through to someone senior' would be an escalation
    path for a caller whose number was spoofed."""
    assert _clamp_ceiling(Tier.T3, Tier.T1) is Tier.T1
    assert _clamp_ceiling(Tier.T2, Tier.T0) is Tier.T0


def test_a_handoff_may_lower_the_ceiling() -> None:
    assert _clamp_ceiling(Tier.T0, Tier.T1) is Tier.T0


def test_an_equal_ceiling_is_preserved() -> None:
    assert _clamp_ceiling(Tier.T1, Tier.T1) is Tier.T1


# --- context travels ----------------------------------------------------------

def test_the_summary_keeps_the_most_recent_turns() -> None:
    """What the caller just said is what the receiving agent must answer."""
    turns = [{"role": "caller", "content": f"turn {i}"} for i in range(50)]
    summary = summarise_transcript(turns, limit=60)
    assert "turn 49" in summary
    assert "turn 0" not in summary


def test_the_summary_preserves_conversation_order() -> None:
    turns = [
        {"role": "caller", "content": "my invoice is wrong"},
        {"role": "agent", "content": "which invoice?"},
        {"role": "caller", "content": "INV-42"},
    ]
    summary = summarise_transcript(turns)
    assert summary.index("my invoice is wrong") < summary.index("INV-42")


def test_the_summary_is_bounded() -> None:
    """A replay would consume the realtime context window and buy nothing."""
    turns = [{"role": "caller", "content": "x" * 500} for _ in range(20)]
    assert len(summarise_transcript(turns)) <= TRANSCRIPT_SUMMARY_CHARS


def test_empty_turns_are_dropped() -> None:
    turns = [{"role": "caller", "content": "   "},
             {"role": "caller", "content": "hello"}]
    assert summarise_transcript(turns).strip() == "caller: hello"


def test_an_empty_transcript_summarises_to_nothing() -> None:
    assert summarise_transcript([]) == ""


# --- continuity is audible ----------------------------------------------------

def _handoff(records: list | None = None) -> VoiceHandoff:
    return VoiceHandoff(
        company_id=uuid.uuid4(), call_sid="CA123",
        to_entity_id=uuid.uuid4(), reason="billing question",
        context_summary="", resolved_records=records or [],
        tier_ceiling="T1")


def test_the_opening_line_proves_continuity() -> None:
    """A handoff the caller has to repeat themselves through has failed."""
    line = opening_line(_handoff([{"label": "invoice INV-42"}]))
    assert "INV-42" in line
    assert "no need to go over it again" in line


def test_the_opening_line_works_without_resolved_records() -> None:
    line = opening_line(_handoff())
    assert line.strip()
    assert "no need to go over it again" in line
    # It must not promise records it doesn't have.
    assert "in front of me" not in line
