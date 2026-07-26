"""Inc 6 / LIB T6 — the citation shape, pure.

A citation is only worth having if it can be opened, so the two properties
pinned here are: it carries what `read_passage` needs, and it refuses to emit
one that cannot be opened at all.
"""
from __future__ import annotations

from src.ai.library.citations import Citation, citations_from_hits
from src.ai.library.filing import CHUNKABLE_CATEGORIES, is_chunkable


def _hit(**kw):
    base = {
        "chunk_id": "c1", "document_id": "d1", "content": "…",
        "chunk_index": "3", "filename": "pricing.md",
        "heading_path": "Pricing > Enterprise", "staleness_state": "aging",
    }
    base.update(kw)
    return base


class TestCitationsFromHits:
    def test_rank_is_the_position_the_agent_received(self):
        cites = citations_from_hits([_hit(chunk_id="a"), _hit(chunk_id="b")])
        assert [c.rank for c in cites] == [1, 2]

    def test_it_carries_what_read_passage_needs(self):
        """Without chunk_index a citation has nothing to open at."""
        cite = citations_from_hits([_hit()])[0]
        assert cite.chunk_index == "3"
        assert cite.document_id == "d1"

    def test_it_carries_staleness(self):
        """The difference between 'here is your source' and 'here is your
        source, and nobody has confirmed it in fourteen months'."""
        assert citations_from_hits([_hit()])[0].staleness_state == "aging"

    def test_a_hit_with_no_document_is_skipped_not_nulled(self):
        """A citation nobody can open is worse than no citation, because it
        looks like evidence."""
        cites = citations_from_hits([_hit(), _hit(document_id=None), _hit(chunk_id=None)])
        assert len(cites) == 1

    def test_skipping_does_not_renumber_the_survivors_ranks_to_lie(self):
        # Rank is the position in what was *received*, so a skipped hit still
        # consumed a slot — the surviving second hit is rank 2, not rank 1.
        cites = citations_from_hits([_hit(document_id=None), _hit(chunk_id="b")])
        assert [c.rank for c in cites] == [2]

    def test_v2_graph_hits_produce_no_citations(self):
        """The v2 semantic-graph path returns summaries with no document or
        chunk id at all. It must degrade to zero citations rather than to
        broken ones."""
        graph_hits = [{"content": "…", "score": 0.9, "node_type": "entity",
                       "memory_domain": "crm", "source": "semantic"}]
        assert citations_from_hits(graph_hits) == []

    def test_as_dict_is_json_shaped(self):
        payload = Citation(document_id="d", chunk_id="c", rank=1).as_dict()
        assert payload["document_id"] == "d"
        assert payload["staleness_state"] is None
        assert set(payload) >= {"document_id", "chunk_id", "rank",
                                "heading_path", "chunk_index", "staleness_state"}


class TestChunkableCategories:
    def test_text_shaped_artifacts_are_chunked(self):
        assert is_chunkable("documents")
        assert is_chunkable("text")

    def test_media_is_filed_but_not_chunked(self):
        """There is no honest text to embed. A transcript is a *different*
        artifact and gets filed on its own merits."""
        for category in ("recordings", "images", "videos"):
            assert not is_chunkable(category)

    def test_unknown_and_missing_categories_are_not_chunked(self):
        assert not is_chunkable(None)
        assert not is_chunkable("")
        assert not is_chunkable("something_new")

    def test_the_set_is_case_insensitive(self):
        assert is_chunkable("Documents")

    def test_no_media_category_leaked_into_the_set(self):
        assert CHUNKABLE_CATEGORIES.isdisjoint({"recordings", "images", "videos"})
