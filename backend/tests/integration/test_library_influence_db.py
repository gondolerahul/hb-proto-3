"""Inc 6 / LIB T3 — the influence rollup and the reaper. ``needs_db``.

Two claims are load-bearing here and neither could be made without a database:

1. **`distinct_queries` is not `retrievals`.** A single question returns up to
   `top_k` chunks and several can come from one document, so counting rows
   overstates a chunky document's influence in proportion to how finely the
   chunker happened to split it. The design's own headline sentence ("this
   pricing sheet answered 40 customer questions") is a count of *questions*.

2. **The reaper cannot outrun the rollup.** Its cutoff is clamped to the last
   rolled-up day whatever the retention setting says, so a worker that missed
   a fortnight keeps raw rows rather than destroying a fortnight of influence
   history nothing ever aggregated.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.library.influence import (
    influence_for_document,
    reap_usage_log,
    roll_up_day,
    roll_up_pending,
)

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

TODAY = date(2026, 7, 26)


@pytest_asyncio.fixture
async def influence_fixture():
    """A company, two entities, two documents with two chunks each."""
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid = uuid.uuid4()
    entities = [uuid.uuid4(), uuid.uuid4()]
    docs = [uuid.uuid4(), uuid.uuid4()]
    chunks = {d: [uuid.uuid4(), uuid.uuid4()] for d in docs}

    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"lib-infl-{cid.hex[:8]}"})
        for eid in entities:
            await s.execute(
                text("INSERT INTO hierarchical_entities "
                     "(id, company_id, name, type, status, created_at, updated_at) "
                     "VALUES (:id, :c, :n, 'AGENT', 'ACTIVE', now(), now())"),
                {"id": str(eid), "c": str(cid), "n": f"agent-{eid.hex[:6]}"})
        for did in docs:
            await s.execute(
                text("INSERT INTO documents (id, company_id, filename, file_type, "
                     " upload_status, created_at, updated_at) "
                     "VALUES (:id, :c, :f, 'md', 'completed', now(), now())"),
                {"id": str(did), "c": str(cid), "f": f"doc-{did.hex[:6]}.md"})
            for i, chunk_id in enumerate(chunks[did]):
                await s.execute(
                    text("INSERT INTO document_chunks "
                         "(id, document_id, chunk_index, content, created_at) "
                         "VALUES (:id, :d, :i, 'body', now())"),
                    {"id": str(chunk_id), "d": str(did), "i": str(i)})
        await s.commit()
    try:
        yield {"company": cid, "entities": entities, "documents": docs,
               "chunks": chunks}
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM document_influence_daily WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM retrieval_usages WHERE company_id = :c"),
                            {"c": str(cid)})
            for did in docs:
                await s.execute(text("DELETE FROM document_chunks WHERE document_id = :d"),
                                {"d": str(did)})
            await s.execute(text("DELETE FROM documents WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM hierarchical_entities WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


async def _usage(s, *, company, document, chunk, entity, query_hash, when):
    await s.execute(text("""
        INSERT INTO retrieval_usages
            (id, company_id, document_id, chunk_id, entity_id, query_hash, rank, used_at)
        VALUES (:id, :c, :d, :ch, :e, :q, 1, :t)
    """), {"id": str(uuid.uuid4()), "c": str(company), "d": str(document),
           "ch": str(chunk), "e": str(entity) if entity else None,
           "q": query_hash, "t": when})


class TestRollupCounters:
    async def test_one_question_returning_two_chunks_is_one_question(
            self, influence_fixture):
        """The counter that matters. Two rows, one query — `retrievals` is 2
        and `distinct_queries` is 1, and only the second is what "questions
        answered" means."""
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        doc = f["documents"][0]
        when = datetime.combine(TODAY - timedelta(days=1), datetime.min.time())
        async with AsyncSessionLocal() as s:
            for chunk in f["chunks"][doc]:
                await _usage(s, company=f["company"], document=doc, chunk=chunk,
                             entity=f["entities"][0], query_hash="q-same", when=when)
            await s.commit()

            await roll_up_day(s, when.date())
            await s.commit()

            row = (await s.execute(text("""
                SELECT retrievals, distinct_queries, distinct_entities
                FROM document_influence_daily
                WHERE document_id = :d AND day = :day
            """), {"d": str(doc), "day": when.date()})).mappings().one()

        assert row["retrievals"] == 2
        assert row["distinct_queries"] == 1
        assert row["distinct_entities"] == 1

    async def test_distinct_entities_ignores_a_null_entity(self, influence_fixture):
        """A Pragya turn has no colleague. Counting NULL as one would invent
        a colleague that does not exist."""
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        doc = f["documents"][0]
        when = datetime.combine(TODAY - timedelta(days=1), datetime.min.time())
        async with AsyncSessionLocal() as s:
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][0], entity=f["entities"][0],
                         query_hash="q1", when=when)
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][1], entity=None,
                         query_hash="q2", when=when)
            await s.commit()
            await roll_up_day(s, when.date())
            await s.commit()

            row = (await s.execute(text("""
                SELECT retrievals, distinct_queries, distinct_entities
                FROM document_influence_daily WHERE document_id = :d
            """), {"d": str(doc)})).mappings().one()

        assert row["retrievals"] == 2
        assert row["distinct_queries"] == 2
        assert row["distinct_entities"] == 1

    async def test_rerunning_a_day_corrects_rather_than_doubles(self, influence_fixture):
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        doc = f["documents"][0]
        when = datetime.combine(TODAY - timedelta(days=1), datetime.min.time())
        async with AsyncSessionLocal() as s:
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][0], entity=f["entities"][0],
                         query_hash="q1", when=when)
            await s.commit()
            await roll_up_day(s, when.date())
            await s.commit()

            # A late row lands for the same day, then the day is re-rolled.
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][1], entity=f["entities"][1],
                         query_hash="q2", when=when)
            await s.commit()
            await roll_up_day(s, when.date())
            await s.commit()

            rows = (await s.execute(text("""
                SELECT retrievals, distinct_queries FROM document_influence_daily
                WHERE document_id = :d
            """), {"d": str(doc)})).mappings().all()

        assert len(rows) == 1, "the upsert must correct the day in place"
        assert rows[0]["retrievals"] == 2
        assert rows[0]["distinct_queries"] == 2

    async def test_documents_roll_up_separately(self, influence_fixture):
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        when = datetime.combine(TODAY - timedelta(days=1), datetime.min.time())
        async with AsyncSessionLocal() as s:
            for doc in f["documents"]:
                await _usage(s, company=f["company"], document=doc,
                             chunk=f["chunks"][doc][0], entity=f["entities"][0],
                             query_hash="q-shared", when=when)
            await s.commit()
            await roll_up_day(s, when.date())
            await s.commit()
            count = (await s.execute(text(
                "SELECT COUNT(*) FROM document_influence_daily WHERE company_id = :c"),
                {"c": str(f["company"])})).scalar()
        assert count == 2

    async def test_today_is_not_rolled_up(self, influence_fixture):
        """A day cannot be aggregated until it is over — LEARN's pooling rule."""
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        doc = f["documents"][0]
        async with AsyncSessionLocal() as s:
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][0], entity=f["entities"][0],
                         query_hash="q1",
                         when=datetime.combine(TODAY, datetime.min.time()))
            await s.commit()
            await roll_up_pending(s, lookback_days=7, now=TODAY)
            await s.commit()
            rolled = (await s.execute(text(
                "SELECT COUNT(*) FROM document_influence_daily WHERE day = :d"),
                {"d": TODAY})).scalar()
        assert rolled == 0

    async def test_the_lookback_window_catches_a_missed_night(self, influence_fixture):
        """A worker down for three days must not lose those three days."""
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        doc = f["documents"][0]
        async with AsyncSessionLocal() as s:
            for offset in (1, 2, 3):
                await _usage(
                    s, company=f["company"], document=doc,
                    chunk=f["chunks"][doc][0], entity=f["entities"][0],
                    query_hash=f"q{offset}",
                    when=datetime.combine(TODAY - timedelta(days=offset),
                                          datetime.min.time()))
            await s.commit()
            await roll_up_pending(s, lookback_days=7, now=TODAY)
            await s.commit()
            days = (await s.execute(text(
                "SELECT COUNT(*) FROM document_influence_daily WHERE document_id = :d"),
                {"d": str(doc)})).scalar()
        assert days == 3


class TestReaperClamp:
    """The guarantee: the reaper cannot outrun the rollup."""

    async def test_it_refuses_entirely_when_nothing_has_been_rolled_up(
            self, influence_fixture):
        """Every raw row is then the only copy of itself. Refusing here is
        what makes the guarantee unconditional rather than usually-true."""
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        doc = f["documents"][0]
        ancient = datetime.combine(TODAY - timedelta(days=200), datetime.min.time())
        async with AsyncSessionLocal() as s:
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][0], entity=f["entities"][0],
                         query_hash="q1", when=ancient)
            await s.commit()

            result = await reap_usage_log(s, retention_days=30, now=TODAY)
            await s.commit()

            survivors = (await s.execute(text(
                "SELECT COUNT(*) FROM retrieval_usages WHERE company_id = :c"),
                {"c": str(f["company"])})).scalar()

        assert result["deleted"] == 0
        assert result["clamped"] is True
        assert survivors == 1, "un-aggregated rows are the only copy and must survive"

    async def test_it_clamps_to_the_last_rolled_up_day(self, influence_fixture):
        """The rollup is behind. Retention says delete 200 days; the reaper
        deletes only what has actually been aggregated."""
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        doc = f["documents"][0]
        rolled_day = TODAY - timedelta(days=100)
        unrolled_day = TODAY - timedelta(days=50)
        async with AsyncSessionLocal() as s:
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][0], entity=f["entities"][0],
                         query_hash="old",
                         when=datetime.combine(rolled_day, datetime.min.time()))
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][1], entity=f["entities"][0],
                         query_hash="newer",
                         when=datetime.combine(unrolled_day, datetime.min.time()))
            await s.commit()

            await roll_up_day(s, rolled_day)   # only the older day is aggregated
            await s.commit()

            result = await reap_usage_log(s, retention_days=30, now=TODAY)
            await s.commit()

            remaining = (await s.execute(text(
                "SELECT query_hash FROM retrieval_usages WHERE company_id = :c"),
                {"c": str(f["company"])})).scalars().all()

        assert result["clamped"] is True
        assert result["deleted"] == 1
        assert remaining == ["newer"], "the un-aggregated day must survive the reaper"

    async def test_it_deletes_normally_when_the_rollup_has_kept_up(
            self, influence_fixture):
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        doc = f["documents"][0]
        old = TODAY - timedelta(days=60)
        recent = TODAY - timedelta(days=2)
        async with AsyncSessionLocal() as s:
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][0], entity=f["entities"][0],
                         query_hash="old",
                         when=datetime.combine(old, datetime.min.time()))
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][1], entity=f["entities"][0],
                         query_hash="recent",
                         when=datetime.combine(recent, datetime.min.time()))
            await s.commit()

            await roll_up_pending(s, lookback_days=90, now=TODAY)
            await s.commit()

            result = await reap_usage_log(s, retention_days=30, now=TODAY)
            await s.commit()

            remaining = (await s.execute(text(
                "SELECT query_hash FROM retrieval_usages WHERE company_id = :c"),
                {"c": str(f["company"])})).scalars().all()

        assert result["clamped"] is False
        assert remaining == ["recent"]

    async def test_the_rollup_survives_the_reaper(self, influence_fixture):
        """The whole point: the raw rows go, the influence history stays."""
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        doc = f["documents"][0]
        old = TODAY - timedelta(days=60)
        async with AsyncSessionLocal() as s:
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][0], entity=f["entities"][0],
                         query_hash="old",
                         when=datetime.combine(old, datetime.min.time()))
            await s.commit()
            await roll_up_pending(s, lookback_days=90, now=TODAY)
            await s.commit()
            await reap_usage_log(s, retention_days=30, now=TODAY)
            await s.commit()

            raw = (await s.execute(text(
                "SELECT COUNT(*) FROM retrieval_usages WHERE company_id = :c"),
                {"c": str(f["company"])})).scalar()
            rolled = (await s.execute(text(
                "SELECT retrievals FROM document_influence_daily WHERE document_id = :d"),
                {"d": str(doc)})).scalars().all()

        assert raw == 0
        assert rolled == [1]


class TestInfluenceRead:
    async def test_it_is_scoped_by_company(self, influence_fixture):
        """A read that took only a document id would answer for another
        tenant's document exactly as SEGA T0's tool registry did."""
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        doc = f["documents"][0]
        when = datetime.combine(TODAY - timedelta(days=1), datetime.min.time())
        async with AsyncSessionLocal() as s:
            await _usage(s, company=f["company"], document=doc,
                         chunk=f["chunks"][doc][0], entity=f["entities"][0],
                         query_hash="q1", when=when)
            await s.commit()
            await roll_up_day(s, when.date())
            await s.commit()

            mine = await influence_for_document(
                s, f["company"], doc, days=30, now=TODAY)
            theirs = await influence_for_document(
                s, uuid.uuid4(), doc, days=30, now=TODAY)

        assert mine["questions_answered"] == 1
        assert theirs["questions_answered"] == 0
        assert theirs["retrievals"] == 0

    async def test_the_window_bounds_the_read(self, influence_fixture):
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        doc = f["documents"][0]
        async with AsyncSessionLocal() as s:
            for offset in (2, 45):
                await _usage(
                    s, company=f["company"], document=doc,
                    chunk=f["chunks"][doc][0], entity=f["entities"][0],
                    query_hash=f"q{offset}",
                    when=datetime.combine(TODAY - timedelta(days=offset),
                                          datetime.min.time()))
            await s.commit()
            await roll_up_pending(s, lookback_days=60, now=TODAY)
            await s.commit()

            short = await influence_for_document(s, f["company"], doc, days=7, now=TODAY)
            long = await influence_for_document(s, f["company"], doc, days=60, now=TODAY)

        assert short["questions_answered"] == 1
        assert long["questions_answered"] == 2
        assert short["active_days"] == 1
        assert long["active_days"] == 2

    async def test_an_untouched_document_reads_zero_not_an_error(
            self, influence_fixture):
        from src.common.database import AsyncSessionLocal

        f = influence_fixture
        async with AsyncSessionLocal() as s:
            result = await influence_for_document(
                s, f["company"], f["documents"][1], days=30, now=TODAY)
        assert result["retrievals"] == 0
        assert result["active_days"] == 0
