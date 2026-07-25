"""Increment 6 / LIB T1+T2 — provenance vocabularies and the usage log's contract.

The load-bearing test here is `test_a_failing_log_never_breaks_retrieval`:
decision 2 says a library-analytics feature must not be able to fail the answer
path, and that is a claim only a test that actually breaks the log can make.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.library.provenance import (
    SOURCE_KINDS,
    STALENESS_STATES,
    SourceKind,
    StalenessState,
    content_hash,
)
from src.ai.library.usage_log import log_retrieval_usage, query_hash


# ── T1: the provenance vocabularies ──────────────────────────────────


def test_source_kinds_are_a_closed_set() -> None:
    """The point of provenance is that every document can answer "where did
    you come from". An open string field answers it with whatever the last
    caller happened to type."""
    assert SOURCE_KINDS == {
        "upload", "connected_drive", "generated_artifact", "conversation_derived"}


def test_staleness_states_are_a_closed_set() -> None:
    assert STALENESS_STATES == {
        "fresh", "aging", "stale", "superseded", "contradicted"}


def test_the_orm_default_matches_the_backfill() -> None:
    """A fresh insert and a row backfilled by lib001 must agree, or existing
    and new documents sort differently for no reason a user could explain."""
    from src.ai.orm.document import Document

    assert Document.__table__.c.source_kind.server_default.arg == SourceKind.UPLOAD
    assert (Document.__table__.c.staleness_state.server_default.arg
            == StalenessState.FRESH)


def test_content_hash_ignores_whitespace_reformatting() -> None:
    """A drive sync that re-exports the same file with different line endings
    is not a change, and must not trigger a re-chunk and re-embed of the whole
    document."""
    assert content_hash("the price is 10\r\n\r\nper unit") == content_hash(
        "the price is 10 per unit")


def test_content_hash_notices_a_real_change() -> None:
    assert content_hash("the price is 10") != content_hash("the price is 20")


# ── T2: the query hash ───────────────────────────────────────────────


def test_the_same_question_asked_twice_collapses() -> None:
    """Counting "What is our refund policy?" and "what is our  refund policy?"
    separately would understate a document's influence."""
    assert query_hash("What is our refund policy?") == query_hash(
        "what is our  refund policy?")


def test_different_questions_do_not_collapse() -> None:
    assert query_hash("refund policy") != query_hash("returns policy")


def test_the_query_text_is_not_recoverable_from_the_row() -> None:
    """Not an anonymity claim — a hash is reversible for short guessable
    queries, and the design says so. The narrower true statement is that the
    text is not stored, which is what this asserts."""
    from src.ai.library.models import RetrievalUsage

    columns = set(RetrievalUsage.__table__.c.keys())
    assert "query" not in columns
    assert "query_text" not in columns
    assert "query_hash" in columns


# ── T2: the write contract ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_hits_writes_nothing() -> None:
    assert await log_retrieval_usage(uuid.uuid4(), "q", []) == 0


@pytest.mark.asyncio
async def test_a_missing_company_writes_nothing() -> None:
    assert await log_retrieval_usage(None, "q", [{"chunk_id": str(uuid.uuid4())}]) == 0


@pytest.mark.asyncio
async def test_a_hit_that_cannot_name_its_document_is_skipped(monkeypatch) -> None:
    """A row with a null document_id would silently distort every rollup that
    groups by it, so an unattributable hit is dropped rather than stored."""
    captured: list = []

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def add_all(self, rows):
            captured.extend(rows)

        async def commit(self):
            pass

    import src.common.database as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: _Session())

    good_chunk, good_doc = str(uuid.uuid4()), str(uuid.uuid4())
    written = await log_retrieval_usage(
        uuid.uuid4(), "q",
        [
            {"chunk_id": good_chunk, "document_id": good_doc},
            {"chunk_id": str(uuid.uuid4())},          # no document_id
            {"document_id": str(uuid.uuid4())},        # no chunk_id
        ],
    )
    assert written == 1
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_rank_is_the_position_the_agent_received(monkeypatch) -> None:
    """1-based, and in the post-rerank order — the rank a document was actually
    presented at, not where the fusion happened to put it."""
    captured: list = []

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def add_all(self, rows):
            captured.extend(rows)

        async def commit(self):
            pass

    import src.common.database as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: _Session())

    hits = [
        {"chunk_id": str(uuid.uuid4()), "document_id": str(uuid.uuid4())}
        for _ in range(3)
    ]
    await log_retrieval_usage(uuid.uuid4(), "q", hits)
    assert [r.rank for r in captured] == [1, 2, 3]


@pytest.mark.asyncio
async def test_a_failing_log_never_raises(monkeypatch) -> None:
    """Decision 2, at the function boundary.

    The end-to-end half — that a failing log still lets *retrieval* return —
    is in tests/integration/test_library_usage_db.py, where a real
    `search_semantic` runs.
    """
    import src.common.database as db_module

    def boom():
        raise RuntimeError("database on fire")

    monkeypatch.setattr(db_module, "AsyncSessionLocal", boom)

    written = await log_retrieval_usage(
        uuid.uuid4(), "q",
        [{"chunk_id": str(uuid.uuid4()), "document_id": str(uuid.uuid4())}])
    assert written == 0
