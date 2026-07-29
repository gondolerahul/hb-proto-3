"""STEWARD S2 — the recommendation writer, driven against a fake router.

The properties that matter: the prompt is built from the gate's own facts
and nothing else; the reply is trimmed to one line or to nothing (an empty
recommendation must render as no line, never an empty one); every failure
path returns None (advice lost, never work); and the attribution is
classified on the tenant side of B13 — pinned here so a careless edit to
the platform set fails a named test, not the parity canary alone.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.ai.genui.recommendation import (
    MAX_SENTENCE_CHARS,
    build_recommendation_prompt,
    recommend_for_tray,
    trim_to_sentence,
)
from src.ai.services.cost_attribution import (
    PLATFORM_INITIATED_ATTRIBUTIONS,
    VALID_ATTRIBUTIONS,
    CostAttribution,
)

COMPANY = uuid.uuid4()

TRAY = {
    "checkpoint_key": "before_outbound_payout_above_band",
    "what_happened": {"sentence": "Payout above the A2 band"},
    "certified": {"props": {
        "summary": "an outbound payout", "amount": 84200.0}},
    "paths": [
        {"key": "approve",
         "cost": {"amount": 84200.0, "basis": "the amount itself"}},
        {"key": "decline", "cost": None},
    ],
    "sla": {"seconds_left": 3600, "on_timeout": "deny"},
    "prepared_by": {"entity_id": "e1", "name": "Quote Drafter"},
}


class FakeRouter:
    def __init__(self, output: str = "Lean approve — it sits inside the band."):
        self.calls: list[dict] = []
        self._output = output

    async def call_llm(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output=self._output, model_name="fake-model",
            prompt_tokens=0, completion_tokens=0)


# ── the prompt is the gate's telling ─────────────────────────────────────────

def test_the_prompt_carries_the_gates_facts_and_only_those():
    prompt = build_recommendation_prompt(TRAY)
    assert "Payout above the A2 band" in prompt
    assert "84200.0" in prompt
    assert "Quote Drafter" in prompt
    assert "3600 seconds" in prompt
    # The decline path has no cost — no invented line for it.
    assert "Cost of 'decline'" not in prompt


def test_an_empty_tray_still_builds_a_prompt():
    prompt = build_recommendation_prompt({})
    assert "An approval is waiting." in prompt


# ── trimming ─────────────────────────────────────────────────────────────────

def test_a_paragraph_keeps_its_first_line_only():
    assert trim_to_sentence(
        "Approve it.\nAlso, here are three more thoughts…") == "Approve it."


def test_a_long_line_is_capped():
    trimmed = trim_to_sentence("x" * 1000)
    assert trimmed is not None and len(trimmed) == MAX_SENTENCE_CHARS


@pytest.mark.parametrize("raw", ["", "   ", "\n\n", '""'])
def test_nothing_usable_is_none_not_an_empty_line(raw):
    assert trim_to_sentence(raw) is None


# ── the writer over the seam ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_reply_becomes_a_draft_with_the_model_named():
    router = FakeRouter()
    draft = await recommend_for_tray(
        None, COMPANY, TRAY, router_factory=lambda db, cid: router)
    assert draft is not None
    assert draft.sentence == "Lean approve — it sits inside the band."
    assert draft.model_used == "fake-model"
    assert router.calls[0]["max_tokens"] == 120


@pytest.mark.asyncio
async def test_an_empty_reply_is_no_draft():
    router = FakeRouter(output="")
    draft = await recommend_for_tray(
        None, COMPANY, TRAY, router_factory=lambda db, cid: router)
    assert draft is None


@pytest.mark.asyncio
async def test_a_raising_router_loses_advice_never_raises():
    class BrokenRouter:
        async def call_llm(self, **kwargs):
            raise RuntimeError("provider down")

    draft = await recommend_for_tray(
        None, COMPANY, TRAY, router_factory=lambda db, cid: BrokenRouter())
    assert draft is None


# ── the B13 classification (the repo rule: classify, don't just add) ─────────

def test_tray_recommendation_is_registered_and_tenant_initiated():
    assert CostAttribution.TRAY_RECOMMENDATION.value in VALID_ATTRIBUTIONS
    assert (CostAttribution.TRAY_RECOMMENDATION.value
            not in PLATFORM_INITIATED_ATTRIBUTIONS)
