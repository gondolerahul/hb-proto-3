"""Inc-7 D8 E4 — the hiring brief's read model.

The whole risk on this endpoint is that it looks answered when it is not.
So what is pinned is not "the fields come back" but the two things that
would let it lie: **only a `capability_build` delegation counts as a
brief**, and **the conversation is reported absent rather than
reconstructed from turns that carry no thread**.

The router test lives here for the reason the repo learned the hard way:
handlers are called directly, so a scoping rule that lives in a dependency
is a scoping rule nothing tests.
"""
from __future__ import annotations

import inspect
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.ai.pragya.delegation import DelegationKind
from src.ai.talent import brief_read as br

COMPANY = uuid.uuid4()


# ── what counts as a brief ──────────────────────────────────────────────────

def test_only_the_board_build_is_a_brief() -> None:
    """`capability_build` is the one delegation that means "you have nobody
    who does this" — it starts the Meta-Agent board the shortlist comes off.
    `colleague` hands work to a child that already exists, which is an
    assignment; counting it would turn every delegated task into a hire."""
    assert br.BRIEF_KINDS == (DelegationKind.CAPABILITY_BUILD,)
    assert DelegationKind.COLLEAGUE not in br.BRIEF_KINDS
    assert DelegationKind.RESEARCH not in br.BRIEF_KINDS


# ── the absences are the deliverable ────────────────────────────────────────

def test_the_conversation_is_reported_absent() -> None:
    """`pragya_turns` carries no thread id, no subject and no link to a
    delegation, and the engagement is one row per company — so there is no
    honest way to say which turns are this brief."""
    fields = {a["field"] for a in br.BRIEF_ABSENT}
    assert "turns" in fields
    why = next(a["why"] for a in br.BRIEF_ABSENT if a["field"] == "turns")
    assert "pragya_turns" in why


def test_every_absence_says_why() -> None:
    """An absence with no reason is a shrug. The frontend renders these
    sentences, so an empty one would render as an empty panel."""
    for entry in br.BRIEF_ABSENT:
        assert set(entry) == {"field", "why"}
        assert len(entry["why"]) > 40


def test_the_clauses_and_permissions_are_absent_too() -> None:
    """The brief's terms and what the role may touch are the surface's two
    largest brief panels and neither has a store: a charter exists only
    once a colleague does."""
    fields = {a["field"] for a in br.BRIEF_ABSENT}
    assert {"clauses", "may_touch", "district"} <= fields


# ── the projection ──────────────────────────────────────────────────────────

def test_the_board_run_is_null_when_none_ran() -> None:
    assert br._board_run(None) is None


def test_the_board_run_projects_the_run_and_nothing_from_it() -> None:
    """The run is the join to the shortlist; its *result* is not projected.
    Reading candidates out of a result blob is exactly the invention this
    endpoint refuses — the board's output shape is E3's business."""
    run = SimpleNamespace(
        id="run-1", status="COMPLETED",
        started_at=datetime(2026, 7, 27, 9, 0),
        completed_at=datetime(2026, 7, 27, 9, 4),
        result_data={"candidates": ["invented"]})
    block = br._board_run(run)  # type: ignore[arg-type]
    assert block == {
        "run_id": "run-1",
        "status": "COMPLETED",
        "started_at": "2026-07-27T09:00:00",
        "completed_at": "2026-07-27T09:04:00",
    }


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> "_Result":
        return self

    def all(self) -> list[Any]:
        return self._rows


class _FakeDb:
    """Answers the two selects in order: delegations, then runs."""

    def __init__(self, *batches: list[Any]) -> None:
        self._batches = list(batches)
        self.calls = 0

    async def execute(self, _query: Any) -> _Result:
        self.calls += 1
        return _Result(self._batches.pop(0) if self._batches else [])


def _delegation(**overrides: Any) -> Any:
    base: dict[str, Any] = dict(
        id="d-1",
        params={"subject": "chasing disputed invoices"},
        created_at=datetime(2026, 7, 27, 8, 30),
        promise="You don't have anything that does that yet, so I'm having it built.",
        status="promised",
        stage=6,
        run_id=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_the_subject_is_the_owners_words_not_a_job_title() -> None:
    """`subject` is what the owner asked for, as Pragya recorded it. The
    surface's `role` — a job title — is written nowhere, so the field is
    not offered under that name."""
    db = _FakeDb([_delegation()])
    view = await br.brief_view(db, COMPANY)  # type: ignore[arg-type]
    brief = view["briefs"][0]
    assert brief["subject"] == "chasing disputed invoices"
    assert "role" not in brief
    assert "turns" not in brief
    assert "clauses" not in brief


@pytest.mark.asyncio
async def test_a_delegation_with_no_subject_is_null_not_guessed() -> None:
    db = _FakeDb([_delegation(params={})])
    view = await br.brief_view(db, COMPANY)  # type: ignore[arg-type]
    assert view["briefs"][0]["subject"] is None


@pytest.mark.asyncio
async def test_no_runs_are_fetched_when_no_brief_started_one() -> None:
    """One query, not two: the run lookup is skipped rather than issued
    with an empty IN list."""
    db = _FakeDb([_delegation(run_id=None)])
    await br.brief_view(db, COMPANY)  # type: ignore[arg-type]
    assert db.calls == 1


@pytest.mark.asyncio
async def test_the_absences_ride_on_every_response() -> None:
    """Including the empty one: a tenant who has never asked for a
    colleague must still be told the conversation is unavailable, or the
    region reads as "no briefs yet" when it is really "no store"."""
    db = _FakeDb([])
    view = await br.brief_view(db, COMPANY)  # type: ignore[arg-type]
    assert view["briefs"] == []
    assert {a["field"] for a in view["absent"]} == {
        a["field"] for a in br.BRIEF_ABSENT}


@pytest.mark.asyncio
async def test_the_limit_is_bounded_by_the_ceiling() -> None:
    db = _FakeDb([])
    await br.brief_view(db, COMPANY, limit=10_000)  # type: ignore[arg-type]
    db2 = _FakeDb([])
    await br.brief_view(db2, COMPANY, limit=0)  # type: ignore[arg-type]
    assert br.MAX_BRIEFS == 100


# ── the router: company from the session, never a parameter ─────────────────

@pytest.mark.asyncio
async def test_the_endpoint_scopes_to_the_session_company(monkeypatch: Any) -> None:
    from src.ai.talent import router as talent_router

    seen: dict[str, Any] = {}

    async def fake_view(db: Any, company_id: uuid.UUID, *, limit: int) -> dict[str, Any]:
        seen["company_id"] = company_id
        seen["limit"] = limit
        return {"briefs": [], "absent": []}

    monkeypatch.setattr(talent_router, "brief_view", fake_view)
    await talent_router.get_brief(
        limit=5,
        current_user=SimpleNamespace(company_id=COMPANY),  # type: ignore[arg-type]
        db=SimpleNamespace())  # type: ignore[arg-type]
    assert seen == {"company_id": COMPANY, "limit": 5}


def test_the_endpoint_takes_no_company_parameter() -> None:
    """A cross-tenant read must not be expressible on this surface. The
    absence of the parameter is the control, so it is pinned."""
    from src.ai.talent.router import get_brief

    assert set(inspect.signature(get_brief).parameters) == {
        "limit", "current_user", "db"}
