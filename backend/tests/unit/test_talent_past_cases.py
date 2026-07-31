"""Inc-7 D8 E4 — the exam, and what `replayable` may claim.

`replayable` is the one computed judgement on this surface, and the one
place a plausible-looking guess would be worst: a candidate graded against
a case that could never have run is a measurement of nothing. So the
verdict is TWIN's own two constraints, evaluated at their most generous
setting, and it has **three** states — a check that cannot see something
reports `null`, never `False`. The tests below are mostly about that
distinction.
"""
from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from src.ai.talent import past_cases as pc

COMPANY = uuid.uuid4()
NOW = datetime(2026, 7, 31, 12, 0, 0)
WINDOW = 30


def _verdict(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        signal_at=NOW - timedelta(days=3),
        records=[],
        unresolved=0,
        now=NOW,
        backend="schema",
        max_window_days=WINDOW,
    )
    base.update(overrides)
    return pc.replay_verdict(**base)


def _record(days_ago: int, label: str = "Invoice 4468abcd") -> dict[str, Any]:
    return {
        "record_id": str(uuid.uuid4()),
        "def": "Invoice",
        "label": label,
        "updated_at": NOW - timedelta(days=days_ago),
        "deleted": False,
    }


# ── the two constraints that make a "no" a fact ─────────────────────────────

def test_a_case_inside_the_window_is_replayable() -> None:
    v = _verdict(records=[_record(2)])
    assert v == {"replayable": True, "blocked_because": None, "unknown_because": None}


def test_a_case_older_than_the_cap_cannot_be_selected_by_any_scope() -> None:
    """`Scope.validate` refuses a window longer than TWIN_MAX_WINDOW_DAYS and
    `select_signals` filters on it, so this is a refusal of the engine's,
    not an opinion about the case."""
    v = _verdict(signal_at=NOW - timedelta(days=WINDOW + 1))
    assert v["replayable"] is False
    assert str(WINDOW) in v["blocked_because"]
    assert "31 days ago" in v["blocked_because"]
    assert v["unknown_because"] is None


def test_the_cap_is_inclusive_at_its_edge() -> None:
    """Exactly at the cap is still a legal window — the refusal is
    `> max`, matching `Scope.validate`. An off-by-one here would silently
    delete a day's worth of the tenant's history from the exam."""
    assert _verdict(signal_at=NOW - timedelta(days=WINDOW))["replayable"] is True


def test_a_record_untouched_since_before_the_cap_blocks_the_case() -> None:
    """Materialisation copies records by `updated_at`, so a stale record
    means the thing the case turned on would not be in the glass room —
    a signal in the window is necessary and not sufficient."""
    v = _verdict(records=[_record(2), _record(WINDOW + 5, label="Invoice deadbeef")])
    assert v["replayable"] is False
    assert "Invoice deadbeef" in v["blocked_because"]
    assert "would not be in the glass room" in v["blocked_because"]


def test_the_container_backend_blocks_every_case() -> None:
    """`materialise` raises ScopeRefused there. Reporting per-case
    replayability as True on a deployment where nothing can materialise
    would be the endpoint lying about the platform, not about the data."""
    v = _verdict(backend="container", records=[_record(1)])
    assert v["replayable"] is False
    assert "container backend" in v["blocked_because"]


def test_a_definite_no_outranks_an_unknown() -> None:
    """A stale record is a fact; an unresolved ref is a blind spot. Order
    matters: reporting `null` here would hide a refusal we can prove."""
    v = _verdict(records=[_record(WINDOW + 2)], unresolved=3)
    assert v["replayable"] is False
    assert v["unknown_because"] is None


# ── the third state: unknown is not false ───────────────────────────────────

def test_an_unresolvable_record_makes_replayability_unknown() -> None:
    """The ref names something this company's records do not have. Whether
    the twin would hold it is a question we cannot answer — and answering
    "no" would make our blind spot look like a property of their history."""
    v = _verdict(unresolved=1)
    assert v["replayable"] is None
    assert v["blocked_because"] is None
    assert "cannot be determined" in v["unknown_because"]


def test_exactly_one_reason_is_ever_set() -> None:
    for v in (
        _verdict(),
        _verdict(unresolved=2),
        _verdict(backend="container"),
        _verdict(signal_at=NOW - timedelta(days=90)),
        _verdict(records=[_record(90)]),
    ):
        reasons = [v["blocked_because"], v["unknown_because"]]
        assert sum(r is not None for r in reasons) <= 1
        if v["replayable"] is False:
            assert v["blocked_because"] is not None
        if v["replayable"] is None:
            assert v["unknown_because"] is not None


def test_a_case_naming_no_records_is_judged_on_the_window_alone() -> None:
    """An empty scope is legitimate — `Scope(objects=())` means schema
    only — so a signal that names nothing is replayable if it is in time."""
    assert _verdict(records=[], unresolved=0)["replayable"] is True


def test_what_replayable_means_does_not_promise_a_result() -> None:
    """The claim is stated as a constant for the reason
    `twin.grading.GRADE_DESCRIPTIONS` is: a claim that lives only in a
    design document is one the surface eventually overstates."""
    assert "does not promise" in pc.REPLAYABLE_MEANS
    assert "has answered" in pc.REPLAYABLE_MEANS or "candidate" in pc.REPLAYABLE_MEANS


# ── refs, read for what they name and no more ───────────────────────────────

def test_a_bare_uuid_is_read_as_a_tenant_record() -> None:
    rid = str(uuid.uuid4())
    assert pc.parse_object_ref(rid) == {"ref": rid, "kind": None, "record_id": rid}


def test_a_prefixed_ref_names_something_outside_the_record_plane() -> None:
    """`entity:…` is not a tenant record, so it must not be counted against
    materialisation — treating it as an unresolvable record would make
    every learning signal permanently unknown."""
    eid = str(uuid.uuid4())
    parsed = pc.parse_object_ref(f"entity:{eid}")
    assert parsed == {"ref": f"entity:{eid}", "kind": "entity", "record_id": None}


def test_an_unreadable_ref_is_reported_rather_than_dropped() -> None:
    parsed = pc.parse_object_ref("whatever-this-is")
    assert parsed == {
        "ref": "whatever-this-is", "kind": None, "record_id": None}


# ── the absences ────────────────────────────────────────────────────────────

def test_the_prose_fields_are_absent_not_composed() -> None:
    """`what` and `actually` are the surface's comparison. Nothing writes
    them; generating them here would put a model's summary where the
    surface promises a record."""
    fields = {a["field"] for a in pc.PAST_CASE_ABSENT}
    assert {"what", "actually", "party"} <= fields


def test_the_interview_itself_is_absent() -> None:
    """Answers, verdicts and traces need a twin session per candidate per
    case. `twin_runs` are scenario runs and nothing joins a candidate to a
    case, so the exam ships with no attempts on it."""
    fields = {a["field"] for a in pc.PAST_CASE_ABSENT}
    assert "answers" in fields


def test_the_cases_are_not_claimed_to_belong_to_a_brief() -> None:
    """A brief names no signal types, records or district, so these are the
    tenant's recent handled work — not a set selected for the role. Saying
    otherwise would be the most believable lie on the surface."""
    why = next(
        a["why"] for a in pc.PAST_CASE_ABSENT if a["field"] == "brief_relevance")
    assert "rather than a set selected for a role" in why


def test_every_absence_says_why() -> None:
    for entry in pc.PAST_CASE_ABSENT:
        assert set(entry) == {"field", "why"}
        assert len(entry["why"]) > 40


# ── the composition ─────────────────────────────────────────────────────────

class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> "_Result":
        return self

    def all(self) -> list[Any]:
        return self._rows


class _FakeDb:
    def __init__(self, *batches: list[Any]) -> None:
        self._batches = list(batches)
        self.calls = 0

    async def execute(self, _query: Any) -> _Result:
        self.calls += 1
        return _Result(self._batches.pop(0) if self._batches else [])


def _signal(**overrides: Any) -> Any:
    base: dict[str, Any] = dict(
        id=uuid.uuid4(),
        type="email.inbound",
        created_at=NOW - timedelta(days=2),
        source="karuna_gateway",
        trust="counterparty",
        urgency="normal",
        object_refs=None,
        consumed_by_run_id=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_a_case_carries_the_facts_and_none_of_the_prose(
    monkeypatch: Any,
) -> None:
    async def no_records(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(pc, "_resolve_records", no_records)
    db = _FakeDb([_signal()])
    view = await pc.past_cases_view(db, COMPANY, now=NOW)  # type: ignore[arg-type]
    case = view["cases"][0]
    assert case["signal_type"] == "email.inbound"
    assert case["when"] == (NOW - timedelta(days=2)).isoformat()
    assert case["outcome"] is None  # no run row came back
    for invented in ("what", "actually", "party", "verdict", "trace"):
        assert invented not in case


@pytest.mark.asyncio
async def test_the_absences_and_the_cap_ride_on_every_response(
    monkeypatch: Any,
) -> None:
    async def no_records(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(pc, "_resolve_records", no_records)
    db = _FakeDb([])
    view = await pc.past_cases_view(db, COMPANY, now=NOW)  # type: ignore[arg-type]
    assert view["cases"] == []
    assert view["replayable_means"] == pc.REPLAYABLE_MEANS
    assert view["max_window_days"] > 0
    assert {a["field"] for a in view["absent"]} == {
        a["field"] for a in pc.PAST_CASE_ABSENT}


@pytest.mark.asyncio
async def test_only_handled_work_is_an_exam_case(monkeypatch: Any) -> None:
    """A signal nobody picked up has no ending to compare a candidate
    against, so the query asks for `consumed_by_run_id IS NOT NULL`. Pinned
    against the compiled SQL because the filter is the definition."""
    captured: list[str] = []

    class _Capturing(_FakeDb):
        async def execute(self, query: Any) -> _Result:
            captured.append(str(query))
            return await super().execute(query)

    async def no_records(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(pc, "_resolve_records", no_records)
    await pc.past_cases_view(_Capturing([]), COMPANY, now=NOW)  # type: ignore[arg-type]
    assert "consumed_by_run_id IS NOT NULL" in captured[0]
    assert "company_id" in captured[0]


@pytest.mark.asyncio
async def test_an_unresolved_ref_leaves_the_case_unknown(monkeypatch: Any) -> None:
    missing = str(uuid.uuid4())

    async def no_records(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(pc, "_resolve_records", no_records)
    db = _FakeDb([_signal(object_refs=[missing])])
    view = await pc.past_cases_view(db, COMPANY, now=NOW)  # type: ignore[arg-type]
    case = view["cases"][0]
    assert case["replayable"] is None
    assert case["unresolved_refs"] == [missing]
    assert case["records"] == []


@pytest.mark.asyncio
async def test_a_resolved_record_is_labelled_by_def_and_id_head(
    monkeypatch: Any,
) -> None:
    """The tray's rule: a def plus the head of the id, which is what an
    operator matches a row on. Never a field guessed out of the document —
    record fields are per-tenant and no field is known to name a party."""
    rid = str(uuid.uuid4())

    async def one_record(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            rid: {
                "record_id": rid,
                "def": "Invoice",
                "label": f"Invoice {rid[:8]}",
                "updated_at": NOW - timedelta(days=1),
                "deleted": False,
            }
        }

    monkeypatch.setattr(pc, "_resolve_records", one_record)
    db = _FakeDb([_signal(object_refs=[rid, "entity:not-a-record"])])
    view = await pc.past_cases_view(db, COMPANY, now=NOW)  # type: ignore[arg-type]
    case = view["cases"][0]
    assert case["records"][0]["label"] == f"Invoice {rid[:8]}"
    assert case["other_refs"] == [
        {"ref": "entity:not-a-record", "kind": "entity"}]
    assert case["replayable"] is True


# ── the router ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_endpoint_scopes_to_the_session_company(monkeypatch: Any) -> None:
    from src.ai.talent import router as talent_router

    seen: dict[str, Any] = {}

    async def fake_view(db: Any, company_id: uuid.UUID, *, limit: int) -> dict[str, Any]:
        seen["company_id"] = company_id
        seen["limit"] = limit
        return {"cases": []}

    monkeypatch.setattr(talent_router, "past_cases_view", fake_view)
    await talent_router.get_past_cases(
        limit=7,
        current_user=SimpleNamespace(company_id=COMPANY),  # type: ignore[arg-type]
        db=SimpleNamespace())  # type: ignore[arg-type]
    assert seen == {"company_id": COMPANY, "limit": 7}


def test_the_endpoint_takes_no_company_parameter() -> None:
    from src.ai.talent.router import get_past_cases

    assert set(inspect.signature(get_past_cases).parameters) == {
        "limit", "current_user", "db"}
