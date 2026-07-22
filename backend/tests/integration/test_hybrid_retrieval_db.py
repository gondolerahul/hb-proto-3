"""Inc 2 / RETR — hybrid retrieval against a live DB (T1).

T1's acceptance is "hybrid beats pure-cosine", and this is where that is
actually shown: a corpus where the exact-term answer is *not* the nearest
neighbour, so cosine alone ranks it below a semantically-similar decoy and the
lexical half is what rescues it. Embeddings are hand-written here rather than
generated — the claim is about fusion, not about any embedding model.

``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.memory.hybrid_retrieval import hybrid_search
from src.ai.memory.retrieval_filters import ChunkFilters

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

DIM = 768


def vec(*leading: float) -> list[float]:
    """A 768-dim vector with the given leading components, zero elsewhere."""
    v = [0.0] * DIM
    for i, x in enumerate(leading):
        v[i] = x
    return v


# The query sits near the "decoy" direction: a naive cosine ranking puts the
# semantically-similar-but-wrong chunk first, and the exact-term answer second.
QUERY_VEC = vec(1.0, 0.10)
DECOY_VEC = vec(1.0, 0.0)      # nearest neighbour, does NOT contain the term
ANSWER_VEC = vec(0.60, 0.30)   # further away, contains the exact invoice id
NOISE_VEC = vec(0.0, 0.0, 1.0)

ANSWER_TEXT = "Remittance for invoice INV-4417 was received on 12 March."
DECOY_TEXT = "Payment remittances and receipts are reconciled every month."
NOISE_TEXT = "The office plant watering rota is published on Mondays."


@pytest_asyncio.fixture
async def corpus():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, eid, did = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"retr-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO hierarchical_entities (id, company_id, name, type, status, "
                 " created_at, updated_at) "
                 "VALUES (:id, :c, 'KB Agent', 'AGENT', 'ACTIVE', now(), now())"),
            {"id": str(eid), "c": str(cid)})
        await s.execute(
            text("INSERT INTO documents (id, company_id, entity_id, filename, file_type, "
                 " upload_status, created_at, updated_at) "
                 "VALUES (:id, :c, :e, 'ledger.pdf', 'pdf', 'completed', now(), now())"),
            {"id": str(did), "c": str(cid), "e": str(eid)})
        for idx, (body, embedding) in enumerate((
            (ANSWER_TEXT, ANSWER_VEC), (DECOY_TEXT, DECOY_VEC), (NOISE_TEXT, NOISE_VEC),
        )):
            await s.execute(
                text("INSERT INTO document_chunks (id, document_id, chunk_index, content, "
                     " embedding, created_at) "
                     "VALUES (:id, :d, :i, :c, CAST(:v AS vector), now())"),
                {"id": str(uuid.uuid4()), "d": str(did), "i": str(idx),
                 "c": body, "v": str(embedding)})
        await s.commit()
    try:
        yield cid, eid, did
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM document_chunks WHERE document_id = :d"),
                            {"d": str(did)})
            await s.execute(text("DELETE FROM documents WHERE id = :d"), {"d": str(did)})
            await s.execute(text("DELETE FROM hierarchical_entities WHERE id = :e"),
                            {"e": str(eid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


async def _cosine_only(db, entity_id, top_k=3):
    """The v1 ranking, for the beats-pure-cosine comparison."""
    rows = (await db.execute(text("""
        SELECT dc.content FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE d.entity_id = CAST(:e AS uuid) AND dc.embedding IS NOT NULL
        ORDER BY dc.embedding <=> CAST(:v AS vector) LIMIT :k
    """), {"e": str(entity_id), "v": str(QUERY_VEC), "k": top_k})).fetchall()
    return [r[0] for r in rows]


class TestHybridBeatsPureCosine:
    async def test_cosine_alone_ranks_the_decoy_first(self, corpus):
        """Establishes the premise — without it the next test proves nothing."""
        from src.common.database import AsyncSessionLocal
        _cid, eid, _did = corpus
        async with AsyncSessionLocal() as db:
            assert (await _cosine_only(db, eid))[0] == DECOY_TEXT

    async def test_hybrid_promotes_the_exact_term_answer(self, corpus):
        from src.common.database import AsyncSessionLocal
        _cid, eid, _did = corpus
        async with AsyncSessionLocal() as db:
            hits = await hybrid_search(
                db, "invoice INV-4417", query_vector=QUERY_VEC,
                entity_id=eid, top_k=3)
        assert hits[0].content == ANSWER_TEXT
        assert "lexical" in hits[0].sources


class TestDegradation:
    async def test_no_embedding_degrades_to_lexical(self, corpus):
        """A failed embedding used to mean an empty result and no context."""
        from src.common.database import AsyncSessionLocal
        _cid, eid, _did = corpus
        async with AsyncSessionLocal() as db:
            hits = await hybrid_search(
                db, "invoice INV-4417", query_vector=None, entity_id=eid, top_k=3)
        assert hits and hits[0].content == ANSWER_TEXT
        assert hits[0].sources == ("lexical",)

    async def test_query_matching_nothing_lexically_still_returns_semantic(self, corpus):
        from src.common.database import AsyncSessionLocal
        _cid, eid, _did = corpus
        async with AsyncSessionLocal() as db:
            hits = await hybrid_search(
                db, "zzzzqqq", query_vector=QUERY_VEC, entity_id=eid, top_k=3)
        assert hits
        assert all(h.sources == ("semantic",) for h in hits)


class TestScoping:
    async def test_unscoped_search_is_refused(self, corpus):
        """A KB query that could span tenants is a bug, not a broad search."""
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            with pytest.raises(ValueError):
                await hybrid_search(db, "anything", query_vector=QUERY_VEC)

    async def test_company_scope_finds_the_corpus(self, corpus):
        from src.common.database import AsyncSessionLocal
        cid, _eid, _did = corpus
        async with AsyncSessionLocal() as db:
            hits = await hybrid_search(
                db, "remittance", query_vector=QUERY_VEC, company_id=cid, top_k=3)
        assert hits

    async def test_another_tenant_sees_nothing(self, corpus):
        from src.common.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            hits = await hybrid_search(
                db, "remittance", query_vector=QUERY_VEC,
                company_id=uuid.uuid4(), top_k=3)
        assert hits == []


class TestFiltersApplyBeforeRanking:
    async def test_matching_file_type_keeps_results(self, corpus):
        from src.common.database import AsyncSessionLocal
        _cid, eid, _did = corpus
        async with AsyncSessionLocal() as db:
            hits = await hybrid_search(
                db, "invoice INV-4417", query_vector=QUERY_VEC, entity_id=eid,
                top_k=3, filters=ChunkFilters(file_types=["pdf"]))
        assert hits and hits[0].content == ANSWER_TEXT

    async def test_excluding_file_type_removes_them_from_both_retrievers(self, corpus):
        from src.common.database import AsyncSessionLocal
        _cid, eid, _did = corpus
        async with AsyncSessionLocal() as db:
            hits = await hybrid_search(
                db, "invoice INV-4417", query_vector=QUERY_VEC, entity_id=eid,
                top_k=3, filters=ChunkFilters(file_types=["txt"]))
        assert hits == []

    async def test_document_id_predicate(self, corpus):
        from src.common.database import AsyncSessionLocal
        _cid, eid, did = corpus
        async with AsyncSessionLocal() as db:
            kept = await hybrid_search(
                db, "remittance", query_vector=QUERY_VEC, entity_id=eid,
                top_k=3, filters=ChunkFilters(document_ids=[did]))
            dropped = await hybrid_search(
                db, "remittance", query_vector=QUERY_VEC, entity_id=eid,
                top_k=3, filters=ChunkFilters(document_ids=[uuid.uuid4()]))
        assert kept and dropped == []
