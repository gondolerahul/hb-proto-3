"""Inc 6 / LIB T1+T2 — provenance columns and the usage log, end to end. ``needs_db``.

The load-bearing test is `test_a_broken_usage_log_still_returns_an_answer`: it
makes the log raise and asserts a real `search_semantic` still returns its
hits. Decision 2 says a library-analytics feature must not be able to fail the
answer path, and that is a claim only a test that actually breaks it can make.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.ai.library.models import RetrievalUsage
from src.ai.library.provenance import SourceKind, StalenessState

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def library():
    """A company with one entity and a two-chunk document."""
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, eid, did = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chunk_ids = [uuid.uuid4(), uuid.uuid4()]
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"lib-test-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO hierarchical_entities "
                 "(id, company_id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :c, :n, 'AGENT', 'ACTIVE', now(), now())"),
            {"id": str(eid), "c": str(cid), "n": "lib-agent"})
        await s.execute(
            text("INSERT INTO documents "
                 "(id, company_id, entity_id, filename, file_type, upload_status, "
                 " created_at, updated_at) "
                 "VALUES (:id, :c, :e, 'pricing.md', 'md', 'completed', now(), now())"),
            {"id": str(did), "c": str(cid), "e": str(eid)})
        for i, chunk_id in enumerate(chunk_ids):
            await s.execute(
                text("INSERT INTO document_chunks "
                     "(id, document_id, chunk_index, content, created_at) "
                     "VALUES (:id, :d, :i, :body, now())"),
                {"id": str(chunk_id), "d": str(did), "i": str(i),
                 "body": f"our enterprise refund policy allows returns section {i}"})
        await s.commit()
    try:
        yield {"company": cid, "entity": eid, "document": did, "chunks": chunk_ids}
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM retrieval_usages WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM document_chunks WHERE document_id = :d"),
                            {"d": str(did)})
            await s.execute(text("DELETE FROM documents WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


class TestProvenanceBackfill:
    async def test_an_existing_document_reads_as_an_upload(self, library):
        """lib001's backfill. Honest rather than clever: we do not know where
        pre-LIB documents came from, so everything but source_kind stays NULL —
        and SEGA's taint ladder reads absent provenance as `external_verified`
        rather than `internal` for exactly that reason."""
        from src.ai.orm.document import Document
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            doc = (await db.execute(
                select(Document).where(Document.id == library["document"]))).scalar_one()
        assert doc.source_kind == SourceKind.UPLOAD
        assert doc.staleness_state == StalenessState.FRESH
        assert doc.source_uri is None
        assert doc.content_hash is None
        assert doc.effective_from is None
        assert doc.superseded_by_id is None

    async def test_effective_from_is_distinct_from_created_at(self, library):
        """The column that earns its place: a price list uploaded today may
        describe last year, and staleness computed from created_at would call
        it fresh."""
        import datetime

        from src.ai.orm.document import Document
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            doc = (await db.execute(
                select(Document).where(Document.id == library["document"]))).scalar_one()
            doc.effective_from = datetime.date(2024, 1, 1)
            await db.commit()

        async with AsyncSessionLocal() as db:
            doc = (await db.execute(
                select(Document).where(Document.id == library["document"]))).scalar_one()
        assert doc.effective_from == datetime.date(2024, 1, 1)
        assert doc.created_at.date() != doc.effective_from

    async def test_a_superseded_document_is_kept_not_deleted(self, library):
        """Decision 3 — this is what makes "was this true in March?"
        answerable at all."""
        from src.ai.orm.document import Document
        from src.common.database import AsyncSessionLocal

        newer = uuid.uuid4()
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("INSERT INTO documents "
                     "(id, company_id, filename, file_type, upload_status, "
                     " created_at, updated_at) "
                     "VALUES (:id, :c, 'pricing-v2.md', 'md', 'completed', now(), now())"),
                {"id": str(newer), "c": str(library["company"])})
            doc = (await db.execute(
                select(Document).where(Document.id == library["document"]))).scalar_one()
            doc.superseded_by_id = newer
            doc.staleness_state = StalenessState.SUPERSEDED
            doc.staleness_reason = "replaced by pricing-v2.md"
            await db.commit()

        async with AsyncSessionLocal() as db:
            old = (await db.execute(
                select(Document).where(Document.id == library["document"]))).scalar_one()
        assert old is not None                       # kept
        assert old.superseded_by_id == newer
        assert old.staleness_reason == "replaced by pricing-v2.md"


class TestUsageLog:
    async def test_retrieval_records_what_the_agent_received(self, library):
        """The whole point of T2, through the real memory service."""
        from src.ai.memory.memory_service import MemoryRouter
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            hits = await MemoryRouter(db).search_semantic(
                library["entity"], "enterprise refund policy", top_k=5)

        assert hits, "the fixture document should be retrievable lexically"

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(RetrievalUsage).where(
                    RetrievalUsage.company_id == library["company"]))).scalars().all()

        assert len(rows) == len(hits)
        assert {r.document_id for r in rows} == {library["document"]}
        assert sorted(r.rank for r in rows) == list(range(1, len(hits) + 1))
        assert all(r.entity_id == library["entity"] for r in rows)
        # The query text is not here — only its hash.
        assert all(len(r.query_hash) == 64 for r in rows)

    async def test_the_same_question_twice_shares_a_hash(self, library):
        from src.ai.memory.memory_service import MemoryRouter
        from src.common.database import AsyncSessionLocal

        for _ in range(2):
            async with AsyncSessionLocal() as db:
                await MemoryRouter(db).search_semantic(
                    library["entity"], "enterprise refund policy", top_k=5)

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(RetrievalUsage).where(
                    RetrievalUsage.company_id == library["company"]))).scalars().all()
        assert len({r.query_hash for r in rows}) == 1

    async def test_a_broken_usage_log_still_returns_an_answer(self, library, monkeypatch):
        """**The mutation test this workstream turns on.**

        Decision 2: a library-analytics feature must not be able to break the
        answer path. Making the log raise and asserting retrieval still returns
        is the only way to say that honestly — the alternative is a
        try/except nobody has ever seen execute.
        """
        import src.ai.library.usage_log as usage_log

        async def boom(*args, **kwargs):
            raise RuntimeError("usage log exploded")

        monkeypatch.setattr(usage_log, "log_retrieval_usage", boom)

        from src.ai.memory.memory_service import MemoryRouter
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            hits = await MemoryRouter(db).search_semantic(
                library["entity"], "enterprise refund policy", top_k=5)

        assert hits, "retrieval must survive a failing usage log"

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(RetrievalUsage).where(
                    RetrievalUsage.company_id == library["company"]))).scalars().all()
        assert rows == []   # nothing logged, and nothing broken


class TestRetrievalCarriesTheDocument:
    async def test_a_hit_knows_which_document_it_came_from(self, library):
        """Without this the usage log cannot attribute anything, and citations
        (T6) have nothing to open."""
        from src.ai.memory.memory_service import MemoryRouter
        from src.common.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            hits = await MemoryRouter(db).search_semantic(
                library["entity"], "enterprise refund policy", top_k=5)

        assert hits
        assert all(h.get("document_id") == str(library["document"]) for h in hits)
