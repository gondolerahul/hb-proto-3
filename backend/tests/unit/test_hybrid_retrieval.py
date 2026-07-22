"""Inc 2 / RETR — reciprocal-rank fusion (T1), the pure half.

RRF is the whole reason hybrid retrieval works without a shared score scale, so
what is pinned here is that it fuses on *rank* and nothing else: two retrievers
agreeing beats either alone, a runaway score cannot buy a position, and the
output order is deterministic (retrieval feeds an LLM prompt — it must not
reshuffle between identical calls). The SQL half is in the _db test.
"""
from __future__ import annotations

import pytest

from src.ai.memory.hybrid_retrieval import (
    RRF_K,
    RetrievedChunk,
    reciprocal_rank_fusion,
)
from src.ai.memory.retrieval_filters import ChunkFilters


def chunks(*ids: str) -> list[RetrievedChunk]:
    return [RetrievedChunk(chunk_id=i, content=f"content-{i}") for i in ids]


class TestFusion:
    def test_single_retriever_preserves_its_order(self):
        fused = reciprocal_rank_fusion({"lexical": chunks("a", "b", "c")})
        assert [c.chunk_id for c in fused] == ["a", "b", "c"]

    def test_agreement_beats_either_alone(self):
        """The core claim: what both retrievers rank highly wins."""
        fused = reciprocal_rank_fusion({
            "lexical":  chunks("shared", "lex_only"),
            "semantic": chunks("sem_only", "shared"),
        })
        assert fused[0].chunk_id == "shared"
        assert fused[0].sources == ("lexical", "semantic")

    def test_score_is_the_sum_of_reciprocal_ranks(self):
        fused = reciprocal_rank_fusion({
            "lexical": chunks("a"), "semantic": chunks("a"),
        })
        assert fused[0].score == pytest.approx(2 / (RRF_K + 1))

    def test_a_lone_first_place_still_ranks(self):
        """A term-exact hit only lexical found must not be discarded."""
        fused = reciprocal_rank_fusion({
            "lexical":  chunks("exact"),
            "semantic": chunks("s1", "s2", "s3"),
        })
        assert "exact" in [c.chunk_id for c in fused]

    def test_ranks_record_provenance(self):
        fused = reciprocal_rank_fusion({
            "lexical": chunks("x", "y"), "semantic": chunks("y", "x"),
        })
        by_id = {c.chunk_id: c for c in fused}
        assert by_id["x"].ranks == {"lexical": 1, "semantic": 2}
        assert by_id["y"].ranks == {"lexical": 2, "semantic": 1}

    def test_metadata_merges_across_retrievers(self):
        lex = [RetrievedChunk("a", "c", metadata={"lexical_rank": 0.9})]
        sem = [RetrievedChunk("a", "c", metadata={"cosine": 0.8})]
        fused = reciprocal_rank_fusion({"lexical": lex, "semantic": sem})
        assert fused[0].metadata == {"lexical_rank": 0.9, "cosine": 0.8}

    def test_top_k_truncates_after_fusing_not_before(self):
        fused = reciprocal_rank_fusion(
            {"lexical": chunks("a", "b", "c", "d")}, top_k=2)
        assert [c.chunk_id for c in fused] == ["a", "b"]

    def test_empty_input_is_empty_output(self):
        assert reciprocal_rank_fusion({}) == []
        assert reciprocal_rank_fusion({"lexical": []}) == []


class TestScaleIndependence:
    def test_raw_scores_cannot_buy_a_position(self):
        """A cosine of 0.99 and a ts_rank_cd of 0.01 are incomparable numbers —
        only the ordering each retriever committed to may count."""
        big = [RetrievedChunk("loser", "c", metadata={"cosine": 0.999})]
        small = chunks("winner", "loser")
        fused = reciprocal_rank_fusion({"semantic": big, "lexical": small})
        # "loser" is rank 1 semantic + rank 2 lexical; "winner" is rank 1 lexical
        # only. Agreement wins — but on ranks, not on that 0.999.
        assert fused[0].chunk_id == "loser"
        assert fused[0].score == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 2))


class TestDeterminism:
    def test_ties_break_stably_on_id(self):
        """Identical calls must not reorder — this feeds an LLM prompt."""
        rankings = {"lexical": chunks("b", "a"), "semantic": chunks("a", "b")}
        first = [c.chunk_id for c in reciprocal_rank_fusion(rankings)]
        for _ in range(5):
            assert [c.chunk_id for c in reciprocal_rank_fusion(rankings)] == first
        assert first == ["a", "b"]  # tied scores → id order


class TestWeights:
    def test_weighting_a_retriever_up_moves_its_hits(self):
        rankings = {"lexical": chunks("lex"), "semantic": chunks("sem")}
        neutral = reciprocal_rank_fusion(rankings)
        assert neutral[0].chunk_id == "lex"  # tie → id order

        weighted = reciprocal_rank_fusion(rankings, weights={"semantic": 5.0})
        assert weighted[0].chunk_id == "sem"

    def test_unlisted_retrievers_default_to_weight_one(self):
        fused = reciprocal_rank_fusion(
            {"lexical": chunks("a")}, weights={"semantic": 3.0})
        assert fused[0].score == pytest.approx(1 / (RRF_K + 1))


class TestFilters:
    def test_empty_filters_render_nothing(self):
        sql, params = ChunkFilters().to_sql()
        assert sql == "" and params == {}
        assert ChunkFilters().is_empty()

    def test_file_type_predicate(self):
        sql, params = ChunkFilters(file_types=["pdf", "docx"]).to_sql()
        assert sql.startswith("AND ")
        assert "d.file_type = ANY(:f_file_types)" in sql
        assert params["f_file_types"] == ["pdf", "docx"]

    def test_date_range_predicates_combine(self):
        from datetime import datetime
        sql, params = ChunkFilters(
            created_after=datetime(2026, 3, 1),
            created_before=datetime(2026, 4, 1),
        ).to_sql()
        assert "d.created_at >= :f_created_after" in sql
        assert "d.created_at <= :f_created_before" in sql
        assert sql.count(" AND ") == 1  # "AND a AND b" — one joiner

    def test_values_are_bound_never_interpolated(self):
        """A filename predicate must not put caller text into the SQL."""
        nasty = "'; DROP TABLE documents; --"
        sql, params = ChunkFilters(filename_contains=nasty).to_sql()
        assert nasty not in sql
        assert params["f_filename"] == f"%{nasty}%"

    def test_is_empty_is_false_once_any_predicate_is_set(self):
        assert not ChunkFilters(file_types=["pdf"]).is_empty()

    def test_heading_predicate_targets_the_chunk_not_the_document(self):
        sql, params = ChunkFilters(heading_contains="Payment Terms").to_sql()
        assert "dc.heading_path ILIKE :f_heading" in sql
        assert params["f_heading"] == "%Payment Terms%"

    def test_heading_predicate_counts_toward_emptiness(self):
        assert not ChunkFilters(heading_contains="x").is_empty()
