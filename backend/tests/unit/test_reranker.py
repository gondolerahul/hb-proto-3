"""Inc 2 / RETR — the Growth+ LLM reranker (T4), the pure half.

Reranking spends the tenant's money on every query, so what is pinned here is
mostly about *not* spending it and *not* making things worse: the tier gate
fails closed, a malformed model reply leaves the fused order alone, and an
unscored candidate keeps its place rather than being dropped.
"""
from __future__ import annotations

import pytest

from src.ai.memory.hybrid_retrieval import RetrievedChunk
from src.ai.memory.reranker import (
    RERANK_TIERS,
    apply_scores,
    build_rerank_prompt,
    parse_rerank_scores,
    rerank_allowed,
)
from src.ai.services.cost_attribution import (
    PLATFORM_INITIATED_ATTRIBUTIONS,
    CostAttribution,
)


def chunks(*ids: str) -> list[RetrievedChunk]:
    return [RetrievedChunk(chunk_id=i, content=f"passage about {i}") for i in ids]


class TestTierGate:
    @pytest.mark.parametrize("tier", sorted(RERANK_TIERS))
    def test_paid_tiers_get_it(self, tier):
        assert rerank_allowed(tier)

    def test_tier_matching_is_case_insensitive(self):
        assert rerank_allowed("Growth") and rerank_allowed("  GROWTH  ")

    @pytest.mark.parametrize("tier", ["solo", "free", "starter", "", None])
    def test_everyone_else_does_not(self, tier):
        assert not rerank_allowed(tier)

    def test_an_unknown_tier_fails_closed(self):
        """Reranking costs the tenant money — an unrecognised plan must fall
        back to not spending, never to spending."""
        assert not rerank_allowed("some-new-plan-we-added")

    def test_the_kill_switch_wins_over_the_tier(self):
        assert not rerank_allowed("growth", enabled=False)


class TestPrompt:
    def test_passages_are_numbered_by_position(self):
        prompt = build_rerank_prompt("invoices", chunks("a", "b"))
        assert "1. passage about a" in prompt
        assert "2. passage about b" in prompt

    def test_chunk_ids_are_not_sent(self):
        """Ids are long, meaningless to the model, and billed as tokens."""
        prompt = build_rerank_prompt("q", chunks("deadbeef-uuid-like-id"))
        assert "deadbeef-uuid-like-id" not in prompt.split("passage about")[0]

    def test_long_passages_are_truncated(self):
        long_chunk = [RetrievedChunk("x", "y" * 5000)]
        assert len(build_rerank_prompt("q", long_chunk)) < 2000

    def test_the_query_is_included(self):
        assert "Query: how long is the warranty" in build_rerank_prompt(
            "how long is the warranty", chunks("a"))


class TestParsing:
    def test_plain_json(self):
        assert parse_rerank_scores('{"1": 8, "2": 3}', 2) == {1: 8.0, 2: 3.0}

    def test_fenced_json(self):
        raw = 'Here you go:\n```json\n{"1": 9, "2": 1}\n```\nHope that helps!'
        assert parse_rerank_scores(raw, 2) == {1: 9.0, 2: 1.0}

    def test_out_of_range_positions_are_dropped(self):
        assert parse_rerank_scores('{"1": 5, "99": 10}', 2) == {1: 5.0}

    def test_unparseable_values_are_dropped_not_fatal(self):
        assert parse_rerank_scores('{"1": "high", "2": 4}', 2) == {2: 4.0}

    def test_a_partial_answer_still_yields_what_is_there(self):
        assert parse_rerank_scores('{"1": 7}', 3) == {1: 7.0}

    @pytest.mark.parametrize("raw", [
        "", "no json here at all", "{not valid json}", "[1, 2, 3]", None,
    ])
    def test_garbage_yields_nothing(self, raw):
        assert parse_rerank_scores(raw, 3) == {}


class TestApplyScores:
    def test_reorders_by_score(self):
        result = apply_scores(chunks("a", "b", "c"), {1: 2.0, 2: 9.0, 3: 5.0})
        assert [c.chunk_id for c in result] == ["b", "c", "a"]

    def test_no_scores_keeps_the_fused_order(self):
        """A failed rerank must degrade to the fused order, which is already good."""
        result = apply_scores(chunks("a", "b", "c"), {})
        assert [c.chunk_id for c in result] == ["a", "b", "c"]

    def test_an_unscored_candidate_is_kept_not_dropped(self):
        """Silence about a passage is not a judgement that it is irrelevant."""
        result = apply_scores(chunks("a", "b"), {1: 5.0})
        assert {c.chunk_id for c in result} == {"a", "b"}
        assert [c.chunk_id for c in result] == ["a", "b"]

    def test_ties_fall_back_to_fused_order(self):
        result = apply_scores(chunks("a", "b", "c"), {1: 5.0, 2: 5.0, 3: 5.0})
        assert [c.chunk_id for c in result] == ["a", "b", "c"]

    def test_scores_are_recorded_for_debuggability(self):
        result = apply_scores(chunks("a", "b"), {1: 3.0, 2: 8.0})
        assert result[0].metadata["rerank_score"] == 8.0


class TestCostClass:
    def test_rerank_is_tenant_initiated_not_platform(self):
        """In the platform class it would let ordinary retrieval exhaust the cap
        that exists to protect tenants FROM platform work."""
        assert CostAttribution.RERANK.value not in PLATFORM_INITIATED_ATTRIBUTIONS
