"""Inc 2 / RETR — the IR metrics behind the retrieval goldens (T5).

Pure maths, so it belongs in the unit gate: if these are wrong, the golden set's
verdict on hybrid-vs-cosine is meaningless.
"""
from __future__ import annotations

import math

import pytest

from tests.eval.retrieval_metrics import (
    mean_reciprocal_rank,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    score_rankings,
)


class TestRecall:
    def test_all_relevant_in_top_k(self):
        assert recall_at_k(["a", "b", "c"], ["a", "b"], 3) == 1.0

    def test_partial(self):
        assert recall_at_k(["a", "x", "y"], ["a", "b"], 3) == 0.5

    def test_relevant_below_the_cut_does_not_count(self):
        """A passage outside top-k never reaches the prompt."""
        assert recall_at_k(["x", "y", "a"], ["a"], 2) == 0.0

    def test_no_relevant_items_scores_one(self):
        """Nothing was required, so nothing was missed."""
        assert recall_at_k(["a"], [], 5) == 1.0

    def test_duplicates_do_not_inflate(self):
        assert recall_at_k(["a", "a", "a"], ["a", "b"], 3) == 0.5


class TestReciprocalRank:
    @pytest.mark.parametrize("retrieved,expected", [
        (["a", "x", "y"], 1.0),
        (["x", "a", "y"], 0.5),
        (["x", "y", "a"], 1 / 3),
        (["x", "y", "z"], 0.0),
    ])
    def test_first_hit_position(self, retrieved, expected):
        assert reciprocal_rank(retrieved, ["a"]) == pytest.approx(expected)

    def test_only_the_first_hit_counts(self):
        assert reciprocal_rank(["x", "a", "b"], ["a", "b"]) == 0.5

    def test_mean_over_queries(self):
        assert mean_reciprocal_rank([
            (["a"], ["a"]), (["x", "b"], ["b"]),
        ]) == pytest.approx((1.0 + 0.5) / 2)

    def test_empty_is_zero_not_an_error(self):
        assert mean_reciprocal_rank([]) == 0.0


class TestNDCG:
    def test_perfect_ordering_scores_one(self):
        gains = {"a": 3.0, "b": 2.0, "c": 1.0}
        assert ndcg_at_k(["a", "b", "c"], gains, 3) == pytest.approx(1.0)

    def test_reversed_ordering_scores_less(self):
        gains = {"a": 3.0, "b": 2.0, "c": 1.0}
        assert ndcg_at_k(["c", "b", "a"], gains, 3) < 1.0

    def test_discount_is_logarithmic(self):
        # One relevant item at rank 2: DCG = 1/log2(3), IDCG = 1/log2(2) = 1.
        assert ndcg_at_k(["x", "a"], {"a": 1.0}, 2) == pytest.approx(1 / math.log2(3))

    def test_fewer_relevant_than_k_can_still_reach_one(self):
        """Ideal DCG uses the best available gains, not a k-sized denominator."""
        assert ndcg_at_k(["a", "x", "y", "z", "w"], {"a": 1.0}, 5) == pytest.approx(1.0)

    def test_no_gains_scores_one(self):
        assert ndcg_at_k(["a"], {}, 5) == 1.0


class TestScoreRankings:
    def test_aggregates_all_three_metrics(self):
        score = score_rankings("hybrid", [
            (["a", "x"], ["a"]),
            (["y", "b"], ["b"]),
        ], k=2)
        assert score.queries == 2
        assert score.recall_at_k == 1.0
        assert score.mrr == pytest.approx(0.75)
        assert 0.0 < score.ndcg_at_k <= 1.0

    def test_a_worse_retriever_scores_lower_on_every_metric(self):
        good = score_rankings("good", [(["a", "x", "y"], ["a"])], k=3)
        bad = score_rankings("bad", [(["x", "y", "a"], ["a"])], k=3)
        assert good.mrr > bad.mrr
        assert good.ndcg_at_k > bad.ndcg_at_k

    def test_empty_input_is_zeroed_not_an_error(self):
        assert score_rankings("none", [], k=5).queries == 0

    def test_summary_is_readable(self):
        text = score_rankings("hybrid", [(["a"], ["a"])], k=5).summary()
        assert "hybrid" in text and "recall@5" in text and "mrr" in text
