"""Inc 2 / RETR — the lazy chunk upgrade against a live DB (T2, decision 1).

What is pinned here is that the upgrade is *lazy and safe*: it finds only stale
documents, it reconstructs the source losslessly from the old contiguous slices,
it swaps atomically (never leaving a document with fewer chunks than it started
with), and it parks rather than spending when B13's platform envelope is full.

``needs_db``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.memory.chunking import CURRENT_CHUNK_VERSION
from src.ai.memory.rechunk import (
    find_stale_documents,
    rechunk_document,
    rechunk_sweep,
)

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

DIM = 768

# Long enough to span several v1 500-char slices, with real structure the new
# chunker can find once the slices are re-joined.
SOURCE = (
    "# Handbook\n\n"
    + ("Introductory prose about the company and its practices. " * 12)
    + "\n\n## Expenses\n\n"
    + ("Expense claims must be filed within thirty days of the spend. " * 12)
    + "\n\n## Travel\n\n"
    + ("Travel is booked through the approved agent only. " * 12)
)


@pytest_asyncio.fixture
async def stale_doc():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, did = uuid.uuid4(), uuid.uuid4()
    # Exactly how v1 chunked: contiguous 500-char slices, no heading, version 1.
    slices = [SOURCE[i:i + 500] for i in range(0, len(SOURCE), 500)]
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"rechunk-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO documents (id, company_id, filename, file_type, "
                 " upload_status, created_at, updated_at) "
                 "VALUES (:id, :c, 'handbook.md', 'md', 'completed', now(), now())"),
            {"id": str(did), "c": str(cid)})
        for idx, body in enumerate(slices):
            await s.execute(
                text("INSERT INTO document_chunks (id, document_id, chunk_index, content, "
                     " embedding, chunk_version, created_at) "
                     "VALUES (:id, :d, :i, :c, NULL, 1, now())"),
                {"id": str(uuid.uuid4()), "d": str(did), "i": str(idx), "c": body})
        await s.commit()
    try:
        yield cid, did, len(slices)
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM document_chunks WHERE document_id = :d"),
                            {"d": str(did)})
            await s.execute(text("DELETE FROM documents WHERE id = :d"), {"d": str(did)})
            for tbl in ("budget_envelopes", "usage_logs"):
                await s.execute(text(f"DELETE FROM {tbl} WHERE company_id = :c"),
                                {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


class TestFindingStaleWork:
    async def test_a_v1_document_is_stale(self, stale_doc):
        from src.common.database import AsyncSessionLocal
        cid, did, _n = stale_doc
        async with AsyncSessionLocal() as db:
            found = await find_stale_documents(db, company_id=cid)
        assert [c.document_id for c in found] == [did]

    async def test_a_current_document_is_not_stale(self, stale_doc):
        from src.common.database import AsyncSessionLocal
        cid, did, _n = stale_doc
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("UPDATE document_chunks SET chunk_version = :v WHERE document_id = :d"),
                {"v": CURRENT_CHUNK_VERSION, "d": str(did)})
            await db.commit()
            assert await find_stale_documents(db, company_id=cid) == []

    async def test_the_batch_is_bounded(self, stale_doc):
        """The sweep must not try to drain a whole corpus in one tick."""
        from src.common.database import AsyncSessionLocal
        cid, _did, _n = stale_doc
        async with AsyncSessionLocal() as db:
            assert len(await find_stale_documents(db, limit=1, company_id=cid)) <= 1


class TestRechunking:
    async def test_source_is_reconstructed_and_recut_on_structure(self, stale_doc, monkeypatch):
        from src.ai.memory.embedding_service import EmbeddingService
        from src.common.database import AsyncSessionLocal

        async def fake_embed(self, text_, task_type=None):
            return [0.01] * DIM
        monkeypatch.setattr(EmbeddingService, "embed_text", fake_embed)

        cid, did, before = stale_doc
        async with AsyncSessionLocal() as db:
            candidate = (await find_stale_documents(db, company_id=cid))[0]
            result = await rechunk_document(db, candidate)
            await db.commit()
        assert result["before"] == before

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(text(
                "SELECT content, heading_path, chunk_version FROM document_chunks "
                "WHERE document_id = :d ORDER BY chunk_index::int"),
                {"d": str(did)})).fetchall()

        assert rows
        assert all(r[2] == CURRENT_CHUNK_VERSION for r in rows)
        # The structure the flat slicing destroyed is now recovered.
        headings = {r[1] for r in rows if r[1]}
        assert any("Expenses" in h for h in headings)
        assert any("Travel" in h for h in headings)
        # And the heading rides inside the indexed content, not beside it.
        expenses = [r[0] for r in rows if r[1] and "Expenses" in r[1]][0]
        assert "Expenses" in expenses

    async def test_total_embeddings_failing_keeps_the_old_chunks(self, stale_doc, monkeypatch):
        """A half-finished swap would leave the document worse than stale."""
        from src.ai.memory.embedding_service import EmbeddingService
        from src.common.database import AsyncSessionLocal

        async def no_embed(self, text_, task_type=None):
            return None
        monkeypatch.setattr(EmbeddingService, "embed_text", no_embed)

        cid, did, before = stale_doc
        async with AsyncSessionLocal() as db:
            candidate = (await find_stale_documents(db, company_id=cid))[0]
            result = await rechunk_document(db, candidate)
            await db.commit()
        assert "skipped" in result

        async with AsyncSessionLocal() as db:
            count = (await db.execute(text(
                "SELECT count(*) FROM document_chunks WHERE document_id = :d"),
                {"d": str(did)})).scalar_one()
        assert count == before  # untouched


class TestSweepRespectsPlatformBudget:
    async def test_over_cap_the_sweep_parks_instead_of_spending(self, stale_doc, monkeypatch):
        """Re-embedding is platform-initiated work — B13's class exactly."""
        from src.common.database import AsyncSessionLocal
        import src.ai.loop.platform_budget as pb

        async def exhausted(db, company_id, prospective_usd=None):
            return False
        monkeypatch.setattr(pb, "platform_work_admitted", exhausted)

        cid, did, before = stale_doc
        async with AsyncSessionLocal() as db:
            result = await rechunk_sweep(db, limit=5)

        assert result["parked"] >= 1
        assert result["upgraded"] == 0
        async with AsyncSessionLocal() as db:
            still_v1 = (await db.execute(text(
                "SELECT count(*) FROM document_chunks "
                "WHERE document_id = :d AND chunk_version = 1"),
                {"d": str(did)})).scalar_one()
        assert still_v1 == before
