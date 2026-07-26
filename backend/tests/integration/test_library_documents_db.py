"""Inc 6 / LIB T4–T6 — staleness, artifact filing, passage reads. ``needs_db``.

The three claims worth a database:

* the staleness sweep writes a **reason** as well as a state, and a raised
  contradiction survives it (the sticky rule, which is the only thing keeping
  contradictions from being silently resolved by the passage of time);
* filing an artifact is **idempotent and company-scoped** — filing another
  tenant's artifact would be a cross-tenant *write*, worse than the read-shaped
  disclosures VG-05 and SEGA T0 fixed;
* `read_passage` returns neighbours and **404s across tenants** rather than
  telling a prober that an id exists somewhere else.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.library.citations import read_passage
from src.ai.library.filing import file_artifact
from src.ai.library.provenance import SourceKind, StalenessState
from src.ai.library.staleness import (
    clear_contradiction,
    raise_contradiction,
    sweep_company,
)

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

TODAY = date(2026, 7, 26)


@pytest_asyncio.fixture
async def docs_fixture():
    """Two companies. The first holds three documents of different ages."""
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid, other_cid = uuid.uuid4(), uuid.uuid4()
    fresh_doc, old_doc, dated_doc = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chunk_ids = [uuid.uuid4() for _ in range(4)]
    artifact_id = uuid.uuid4()

    async with AsyncSessionLocal() as s:
        for company in (cid, other_cid):
            await s.execute(
                text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                     "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
                {"id": str(company), "n": f"lib-doc-{company.hex[:8]}"})

        async def _doc(did, *, created, kind=SourceKind.UPLOAD, effective=None,
                       company=cid):
            await s.execute(text("""
                INSERT INTO documents (id, company_id, filename, file_type,
                    upload_status, source_kind, effective_from, staleness_state,
                    created_at, updated_at)
                VALUES (:id, :c, :f, 'md', 'completed', :k, :eff, 'fresh', :ts, :ts)
            """), {"id": str(did), "c": str(company), "f": f"{did.hex[:6]}.md",
                   "k": kind, "eff": effective, "ts": created})

        await _doc(fresh_doc, created=datetime(2026, 7, 20))
        await _doc(old_doc, created=datetime(2024, 1, 1))
        # Uploaded today, describes 2023 — the case `effective_from` exists for.
        await _doc(dated_doc, created=datetime(2026, 7, 26),
                   effective=date(2023, 1, 1))

        for i, chunk_id in enumerate(chunk_ids):
            await s.execute(text("""
                INSERT INTO document_chunks
                    (id, document_id, chunk_index, content, heading_path, created_at)
                VALUES (:id, :d, :i, :body, :h, now())
            """), {"id": str(chunk_id), "d": str(fresh_doc), "i": str(i),
                   "body": f"passage number {i}", "h": f"Section {i}"})

        await s.execute(text("""
            INSERT INTO artifacts (id, company_id, origin, file_category,
                file_name, file_path, created_at)
            VALUES (:id, :c, 'system-generated', 'documents', 'report.txt',
                    '/nonexistent/report.txt', now())
        """), {"id": str(artifact_id), "c": str(cid)})
        await s.commit()

    try:
        yield {"company": cid, "other_company": other_cid,
               "fresh": fresh_doc, "old": old_doc, "dated": dated_doc,
               "chunks": chunk_ids, "artifact": artifact_id}
    finally:
        async with AsyncSessionLocal() as s:
            for company in (cid, other_cid):
                await s.execute(
                    text("DELETE FROM artifacts WHERE company_id = :c"),
                    {"c": str(company)})
                await s.execute(text(
                    "DELETE FROM document_chunks WHERE document_id IN "
                    "(SELECT id FROM documents WHERE company_id = :c)"),
                    {"c": str(company)})
                await s.execute(text("DELETE FROM documents WHERE company_id = :c"),
                                {"c": str(company)})
                await s.execute(text("DELETE FROM companies WHERE id = :c"),
                                {"c": str(company)})
            await s.commit()


class TestStalenessSweep:
    async def test_it_writes_a_state_and_a_reason(self, docs_fixture):
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            summary = await sweep_company(s, f["company"], now=TODAY)
            await s.commit()
            rows = {r["id"]: r for r in (await s.execute(text(
                "SELECT id, staleness_state, staleness_reason FROM documents "
                "WHERE company_id = :c"), {"c": str(f["company"])})).mappings().all()}

        assert summary["documents"] == 3
        assert rows[f["fresh"]]["staleness_state"] == StalenessState.FRESH
        assert rows[f["old"]]["staleness_state"] == StalenessState.STALE
        for row in rows.values():
            assert row["staleness_reason"], "a flag with no visible basis gets dismissed"

    async def test_effective_from_makes_a_new_upload_stale(self, docs_fixture):
        """Uploaded today, describes 2023. Age from created_at would call it
        fresh — the exact failure the column was added to prevent."""
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            await sweep_company(s, f["company"], now=TODAY)
            await s.commit()
            row = (await s.execute(text(
                "SELECT staleness_state, staleness_reason FROM documents WHERE id = :d"),
                {"d": str(f["dated"])})).mappings().one()

        assert row["staleness_state"] == StalenessState.STALE
        assert "effective from" in row["staleness_reason"]

    async def test_a_raised_contradiction_survives_the_sweep(self, docs_fixture):
        """The sticky rule. Without it every nightly sweep would silently
        resolve every contradiction nobody had got to yet."""
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            flagged = await raise_contradiction(
                s, f["company"], f["fresh"], "conflicts with the 2026 price list")
            await s.commit()
            assert flagged

            await sweep_company(s, f["company"], now=TODAY)
            await s.commit()
            state = (await s.execute(text(
                "SELECT staleness_state FROM documents WHERE id = :d"),
                {"d": str(f["fresh"])})).scalar()

        assert state == StalenessState.CONTRADICTED

    async def test_clearing_returns_it_to_the_age_rules(self, docs_fixture):
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            await raise_contradiction(s, f["company"], f["old"], "conflict")
            await s.commit()
            assert await clear_contradiction(s, f["company"], f["old"])
            await s.commit()
            await sweep_company(s, f["company"], now=TODAY)
            await s.commit()
            state = (await s.execute(text(
                "SELECT staleness_state FROM documents WHERE id = :d"),
                {"d": str(f["old"])})).scalar()

        assert state == StalenessState.STALE, "the age rules take over again"

    async def test_a_contradiction_cannot_be_raised_across_tenants(self, docs_fixture):
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            flagged = await raise_contradiction(
                s, f["other_company"], f["fresh"], "not mine to flag")
            await s.commit()
            state = (await s.execute(text(
                "SELECT staleness_state FROM documents WHERE id = :d"),
                {"d": str(f["fresh"])})).scalar()

        assert flagged is False
        assert state == StalenessState.FRESH

    async def test_the_sweep_is_scoped_to_one_tenant(self, docs_fixture):
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            summary = await sweep_company(s, f["other_company"], now=TODAY)
            await s.commit()
        assert summary["documents"] == 0


class TestArtifactFiling:
    async def test_it_creates_a_document_and_links_back(self, docs_fixture):
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            result = await file_artifact(s, f["artifact"], f["company"])
            await s.commit()

            row = (await s.execute(text(
                "SELECT document_id FROM artifacts WHERE id = :a"),
                {"a": str(f["artifact"])})).mappings().one()
            doc = (await s.execute(text(
                "SELECT source_kind, source_uri FROM documents WHERE id = :d"),
                {"d": str(row["document_id"])})).mappings().one()

        assert result["filed"] is True
        assert row["document_id"] is not None
        assert doc["source_kind"] == SourceKind.GENERATED_ARTIFACT
        assert doc["source_uri"] == "/nonexistent/report.txt"

    async def test_an_unreadable_file_still_files_unchunked(self, docs_fixture):
        """The provenance is real and useful even when the content is not
        reachable — refusing to file would lose both."""
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            result = await file_artifact(s, f["artifact"], f["company"])
            await s.commit()
        assert result["filed"] is True
        assert result["chunked"] is False

    async def test_filing_twice_is_a_no_op(self, docs_fixture):
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            first = await file_artifact(s, f["artifact"], f["company"])
            await s.commit()
            second = await file_artifact(s, f["artifact"], f["company"])
            await s.commit()
            count = (await s.execute(text(
                "SELECT COUNT(*) FROM documents WHERE company_id = :c "
                "AND source_kind = :k"),
                {"c": str(f["company"]), "k": SourceKind.GENERATED_ARTIFACT})).scalar()

        assert first["filed"] is True
        assert second["filed"] is False
        assert second["reason"] == "already filed"
        assert count == 1

    async def test_it_refuses_another_tenants_artifact(self, docs_fixture):
        """A cross-tenant *write* — worse than the read-shaped disclosures
        Increment 6 has already fixed."""
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            result = await file_artifact(s, f["artifact"], f["other_company"])
            await s.commit()
            linked = (await s.execute(text(
                "SELECT document_id FROM artifacts WHERE id = :a"),
                {"a": str(f["artifact"])})).scalar()

        assert result["filed"] is False
        assert linked is None


class TestPassageRead:
    async def test_it_returns_the_chunk_and_its_neighbours(self, docs_fixture):
        """A citation that opens at the top of a 40-page PDF has technically
        cited it and practically told you nothing."""
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            passage = await read_passage(
                s, f["company"], f["fresh"], chunk_index=2, context=1)

        assert passage is not None
        indices = [p["chunk_index"] for p in passage["passages"]]
        assert indices == ["1", "2", "3"]
        cited = [p for p in passage["passages"] if p["is_cited"]]
        assert len(cited) == 1 and cited[0]["chunk_index"] == "2"

    async def test_context_zero_returns_only_the_cited_chunk(self, docs_fixture):
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            passage = await read_passage(
                s, f["company"], f["fresh"], chunk_index=2, context=0)
        assert [p["chunk_index"] for p in passage["passages"]] == ["2"]

    async def test_it_clamps_at_the_start_of_the_document(self, docs_fixture):
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            passage = await read_passage(
                s, f["company"], f["fresh"], chunk_index=0, context=2)
        assert [p["chunk_index"] for p in passage["passages"]] == ["0", "1", "2"]

    async def test_it_carries_the_documents_provenance(self, docs_fixture):
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            await sweep_company(s, f["company"], now=TODAY)
            await s.commit()
            passage = await read_passage(
                s, f["company"], f["fresh"], chunk_index=1, context=1)

        assert passage["document"]["source_kind"] == SourceKind.UPLOAD
        assert passage["document"]["staleness_state"]
        assert passage["document"]["staleness_reason"]

    async def test_a_cross_tenant_read_returns_none(self, docs_fixture):
        """None, not a 403 — a probe must not learn that an id exists in
        another tenant (the VG-05 rule)."""
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            passage = await read_passage(
                s, f["other_company"], f["fresh"], chunk_index=1, context=1)
        assert passage is None

    async def test_an_out_of_range_chunk_returns_none(self, docs_fixture):
        from src.common.database import AsyncSessionLocal

        f = docs_fixture
        async with AsyncSessionLocal() as s:
            passage = await read_passage(
                s, f["company"], f["fresh"], chunk_index=99, context=0)
        assert passage is None
