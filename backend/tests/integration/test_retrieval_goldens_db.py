"""Inc 2 / RETR — the retrieval golden gate (T5).

This is where T1's acceptance ("hybrid beats pure-cosine on the golden set") is
actually adjudicated, over a corpus rather than a single lucky query, and where
future chunking/fusion changes get regression-gated.

Three claims, in order of what each protects:

1. **Hybrid beats pure-cosine overall** — the whole justification for T1.
2. **It wins where it should** — the exact-token queries, where a dense
   retriever is structurally weak.
3. **It does not lose where it shouldn't** — the paraphrase queries. This is the
   one that would otherwise rot silently: adding a lexical retriever can push a
   semantically-correct answer down, and an aggregate improvement would hide it.

``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.memory.hybrid_retrieval import hybrid_search
from tests.eval.retrieval_corpus import (
    EXACT_TOKEN_QUERIES,
    PASSAGES,
    QUERIES,
    SEMANTIC_QUERIES,
)
from tests.eval.retrieval_metrics import score_rankings

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

TOP_K = 5

# Regression floors. The corpus and the fusion are both deterministic, so there
# is no run-to-run noise to absorb and the floors can sit close to the measured
# result. As built (2026-07-22), over all 8 golden queries:
#
#     cosine   recall@5=1.000  mrr=0.812  ndcg@5=0.862
#     hybrid   recall@5=1.000  mrr=1.000  ndcg@5=1.000
#
# The entire gain is on the exact-token queries (mrr 0.700 → 1.000); the
# paraphrase queries are 1.000 under both, which is the no-regression result.
MIN_HYBRID_RECALL = 0.95
MIN_HYBRID_MRR = 0.95


@pytest_asyncio.fixture
async def golden_corpus():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, eid = uuid.uuid4(), uuid.uuid4()
    # One document per passage, so a passage's key maps to a document and the
    # domain-viewport golden can tag them independently.
    keys_to_chunk: dict[str, str] = {}

    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"golden-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO hierarchical_entities (id, company_id, name, type, status, "
                 " created_at, updated_at) "
                 "VALUES (:id, :c, 'KB', 'AGENT', 'ACTIVE', now(), now())"),
            {"id": str(eid), "c": str(cid)})
        for passage in PASSAGES:
            did, chunk_id = uuid.uuid4(), uuid.uuid4()
            await s.execute(
                text("INSERT INTO documents (id, company_id, entity_id, filename, file_type, "
                     " upload_status, memory_domain, created_at, updated_at) "
                     "VALUES (:id, :c, :e, :f, 'txt', 'completed', :m, now(), now())"),
                {"id": str(did), "c": str(cid), "e": str(eid),
                 "f": f"{passage.key}.txt", "m": passage.memory_domain})
            await s.execute(
                text("INSERT INTO document_chunks (id, document_id, chunk_index, content, "
                     " embedding, chunk_version, created_at) "
                     "VALUES (:id, :d, '0', :c, CAST(:v AS vector), 2, now())"),
                {"id": str(chunk_id), "d": str(did), "c": passage.text,
                 "v": str(passage.embedding)})
            keys_to_chunk[passage.key] = str(chunk_id)
        await s.commit()
    try:
        yield cid, eid, keys_to_chunk
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text(
                "DELETE FROM document_chunks WHERE document_id IN "
                "(SELECT id FROM documents WHERE company_id = :c)"), {"c": str(cid)})
            await s.execute(text("DELETE FROM documents WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM hierarchical_entities WHERE id = :e"),
                            {"e": str(eid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


async def _cosine_ranking(db, entity_id, query, keys) -> list[str]:
    """The v1 retriever: pure cosine, top-k. The baseline being beaten."""
    rows = (await db.execute(text("""
        SELECT dc.id::text FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE d.entity_id = CAST(:e AS uuid) AND dc.embedding IS NOT NULL
        ORDER BY dc.embedding <=> CAST(:v AS vector) LIMIT :k
    """), {"e": str(entity_id), "v": str(query.embedding), "k": TOP_K})).fetchall()
    return [r[0] for r in rows]


async def _hybrid_ranking(db, entity_id, query, keys) -> list[str]:
    hits = await hybrid_search(
        db, query.query, query_vector=query.embedding,
        entity_id=entity_id, top_k=TOP_K)
    return [h.chunk_id for h in hits]


async def _score(db, entity_id, keys, queries, ranker, label):
    rankings = []
    for q in queries:
        retrieved = await ranker(db, entity_id, q, keys)
        rankings.append((retrieved, [keys[k] for k in q.relevant]))
    return score_rankings(label, rankings, k=TOP_K)


class TestHybridBeatsCosineOnTheGoldenSet:
    async def test_overall(self, golden_corpus):
        """T1's acceptance criterion, over the corpus rather than one query."""
        from src.common.database import AsyncSessionLocal
        _cid, eid, keys = golden_corpus
        async with AsyncSessionLocal() as db:
            cosine = await _score(db, eid, keys, QUERIES, _cosine_ranking, "cosine")
            hybrid = await _score(db, eid, keys, QUERIES, _hybrid_ranking, "hybrid")

        assert hybrid.mrr > cosine.mrr, f"{hybrid.summary()} vs {cosine.summary()}"
        assert hybrid.recall_at_k >= cosine.recall_at_k
        assert hybrid.ndcg_at_k > cosine.ndcg_at_k

    async def test_it_wins_on_exact_token_queries(self, golden_corpus):
        """Where a dense retriever is structurally weak: ids, codes, part numbers."""
        from src.common.database import AsyncSessionLocal
        _cid, eid, keys = golden_corpus
        exact = [q for q in QUERIES if q.query in EXACT_TOKEN_QUERIES]
        async with AsyncSessionLocal() as db:
            cosine = await _score(db, eid, keys, exact, _cosine_ranking, "cosine/exact")
            hybrid = await _score(db, eid, keys, exact, _hybrid_ranking, "hybrid/exact")
        assert hybrid.mrr > cosine.mrr, f"{hybrid.summary()} vs {cosine.summary()}"

    async def test_it_does_not_regress_paraphrase_queries(self, golden_corpus):
        """The failure mode an aggregate win would hide: adding a lexical
        retriever pushing a semantically-correct answer down."""
        from src.common.database import AsyncSessionLocal
        _cid, eid, keys = golden_corpus
        semantic = [q for q in QUERIES if q.query in SEMANTIC_QUERIES]
        async with AsyncSessionLocal() as db:
            cosine = await _score(db, eid, keys, semantic, _cosine_ranking, "cosine/para")
            hybrid = await _score(db, eid, keys, semantic, _hybrid_ranking, "hybrid/para")
        assert hybrid.mrr >= cosine.mrr, f"{hybrid.summary()} vs {cosine.summary()}"
        assert hybrid.recall_at_k >= cosine.recall_at_k


class TestRegressionFloors:
    """The gate future chunking/fusion changes have to clear."""

    async def test_hybrid_clears_the_floors(self, golden_corpus):
        from src.common.database import AsyncSessionLocal
        _cid, eid, keys = golden_corpus
        async with AsyncSessionLocal() as db:
            hybrid = await _score(db, eid, keys, QUERIES, _hybrid_ranking, "hybrid")
        assert hybrid.recall_at_k >= MIN_HYBRID_RECALL, hybrid.summary()
        assert hybrid.mrr >= MIN_HYBRID_MRR, hybrid.summary()

    async def test_every_golden_query_finds_its_answer(self, golden_corpus):
        """Named per-query, so a failure says which one rather than a mean."""
        from src.common.database import AsyncSessionLocal
        _cid, eid, keys = golden_corpus
        missed = []
        async with AsyncSessionLocal() as db:
            for q in QUERIES:
                retrieved = await _hybrid_ranking(db, eid, q, keys)
                if not any(keys[k] in retrieved for k in q.relevant):
                    missed.append(q.query)
        assert not missed, f"queries with no relevant hit in top-{TOP_K}: {missed}"


class TestViewportAppliesToTheGoldenSet:
    async def test_a_payroll_scoped_passage_is_hidden(self, golden_corpus):
        from src.common.database import AsyncSessionLocal
        _cid, eid, keys = golden_corpus
        async with AsyncSessionLocal() as db:
            hits = await hybrid_search(
                db, "March payroll run", query_vector=None, entity_id=eid,
                top_k=TOP_K, allowed_domains=frozenset({"crm", "general"}))
        assert keys["payroll_run"] not in [h.chunk_id for h in hits]

    async def test_it_is_reachable_without_a_viewport(self, golden_corpus):
        from src.common.database import AsyncSessionLocal
        _cid, eid, keys = golden_corpus
        async with AsyncSessionLocal() as db:
            hits = await hybrid_search(
                db, "March payroll run", query_vector=None, entity_id=eid, top_k=TOP_K)
        assert keys["payroll_run"] in [h.chunk_id for h in hits]
