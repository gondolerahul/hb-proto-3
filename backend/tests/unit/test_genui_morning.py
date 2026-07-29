"""LINE L1 — the Morning Story composition, pure.

The Standup's sentences ported server-side: if these and
``StandupSurface.tsx`` ever tell yesterday differently, the phone and the
desk disagree — the frontend goldens pin that side, these pin this one.
"""
from __future__ import annotations

from datetime import datetime

from src.ai.genui.morning import compose_morning_story

NOW = datetime(2026, 7, 29, 6, 0)


def _estate(colleagues):
    return {
        "districts": [
            {
                "process_code": "P03",
                "colleagues": [
                    {"entity_id": cid, "name": name} for cid, name in colleagues
                ],
            }
        ]
    }


def test_a_busy_colleague_gets_the_full_telling():
    cards = compose_morning_story(
        _estate([("e1", "Ravi")]),
        runs=[("e1", "COMPLETED"), ("e1", "COMPLETED"), ("e1", "FAILED"),
              ("e1", "RUNNING")],
        waiting_entity_ids={"e1"},
        now=NOW,
    )
    assert len(cards) == 1
    card = cards[0]
    assert card["name"] == "Ravi"
    assert card["district"] == "P03"
    assert card["waiting"] is True
    assert card["sentences"] == [
        "Finished 2 pieces of work since yesterday.",
        "One thing went wrong — it is in the trace.",
        "Is working on something right now.",
        "Is waiting on you.",
    ]
    assert card["audio"] is None


def test_a_quiet_day_says_so_rather_than_vanishing():
    cards = compose_morning_story(
        _estate([("e1", "Meera")]), runs=[], waiting_entity_ids=set(), now=NOW)
    assert cards[0]["sentences"] == ["A quiet day — nothing to report."]


def test_whoever_needs_the_owner_comes_first():
    cards = compose_morning_story(
        _estate([("e1", "Quiet"), ("e2", "Waiting")]),
        runs=[],
        waiting_entity_ids={"e2"},
        now=NOW,
    )
    assert [card["name"] for card in cards] == ["Waiting", "Quiet"]


def test_singular_and_plural_read_like_a_person_wrote_them():
    cards = compose_morning_story(
        _estate([("e1", "Solo")]),
        runs=[("e1", "COMPLETED"), ("e1", "FAILED"), ("e1", "FAILED")],
        waiting_entity_ids=set(),
        now=NOW,
    )
    assert cards[0]["sentences"][0] == "Finished one piece of work since yesterday."
    assert cards[0]["sentences"][1] == "2 things went wrong — they are in the traces."
