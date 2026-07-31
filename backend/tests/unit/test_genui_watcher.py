"""STEWARD S1 — the approval watcher, driven without a database.

What the unit layer can prove: who counts as listening, that the loop
outlives a raising sweep (the tripwire — a silent dead watcher is the
failure mode this codebase keeps finding), and the recommendation rule:
written once, only before anyone has been reached, never blocking a tray.
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from src.ai.genui import channel as ch
from src.ai.genui import watcher as w
from src.ai.genui.models import TrayRecommendation

COMPANY = uuid.uuid4()
OTHER_COMPANY = uuid.uuid4()
USER = uuid.uuid4()
SECOND_USER = uuid.uuid4()


class FakeSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, data):
        self.sent.append(data)


@pytest.fixture()
def hub(monkeypatch):
    fresh = ch.ChannelHub()
    monkeypatch.setattr(ch, "_hub", fresh)
    return fresh


@pytest.fixture(autouse=True)
def _no_installed_recommender():
    w.install_recommender(None)
    yield
    w.install_recommender(None)


# ── who is listening ─────────────────────────────────────────────────────────

def test_a_user_with_a_live_socket_is_listening(hub):
    hub.join(uuid.uuid4(), COMPANY, USER, FakeSocket())
    assert hub.users_with_open_sockets(COMPANY) == {USER}


def test_a_disconnected_user_is_not_listening_even_though_context_survives(hub):
    session, socket = uuid.uuid4(), FakeSocket()
    hub.join(session, COMPANY, USER, socket)
    hub.leave(session, socket)
    # The session state survives (rule 1) — presence must not read it as a
    # live device, or every tray would be "delivered" to an empty room.
    assert hub.state_for_user(COMPANY, USER) is not None
    assert hub.users_with_open_sockets(COMPANY) == set()


def test_listening_is_company_scoped(hub):
    hub.join(uuid.uuid4(), COMPANY, USER, FakeSocket())
    hub.join(uuid.uuid4(), OTHER_COMPANY, SECOND_USER, FakeSocket())
    assert hub.users_with_open_sockets(COMPANY) == {USER}
    assert hub.users_with_open_sockets(OTHER_COMPANY) == {SECOND_USER}


# ── the loop must outlive its sweeps (the tripwire) ──────────────────────────

@pytest.mark.asyncio
async def test_the_loop_survives_a_raising_sweep():
    calls = 0
    stop = asyncio.Event()

    async def broken_sweep():
        nonlocal calls
        calls += 1
        if calls >= 3:
            stop.set()
        raise RuntimeError("sweep died")

    await asyncio.wait_for(
        w.watcher_loop(interval=0.01, stop=stop, sweep=broken_sweep), timeout=5)
    assert calls >= 3


@pytest.mark.asyncio
async def test_the_loop_stops_promptly_when_asked():
    stop = asyncio.Event()

    async def idle_sweep():
        return None

    task = asyncio.create_task(
        w.watcher_loop(interval=60.0, stop=stop, sweep=idle_sweep))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1)


# ── the recommendation rule (§5) ─────────────────────────────────────────────

def _fake_db(existing: TrayRecommendation | None = None):
    added: list = []

    async def get(model, key):
        assert model is TrayRecommendation
        return existing

    return SimpleNamespace(get=get, add=added.append), added


@pytest.mark.asyncio
async def test_an_existing_sentence_is_read_and_the_writer_is_not_consulted():
    async def writer(db, company_id, tray):  # pragma: no cover — must not run
        raise AssertionError("the writer must not be consulted twice")

    w.install_recommender(writer)
    db, added = _fake_db(existing=TrayRecommendation(
        approval_id=uuid.uuid4(), company_id=COMPANY, sentence="stored"))
    sentence = await w._recommendation_for(
        db, COMPANY, uuid.uuid4(), {}, first_delivery=True)
    assert sentence == "stored"
    assert added == []


@pytest.mark.asyncio
async def test_after_first_delivery_no_sentence_is_ever_written():
    """Once a tray has gone out without a recommendation it stays without
    one — advice appearing under a card the owner already read looks like
    the platform changing its mind after the fact."""
    async def writer(db, company_id, tray):
        return w.RecommendationDraft(sentence="late advice")

    w.install_recommender(writer)
    db, added = _fake_db()
    sentence = await w._recommendation_for(
        db, COMPANY, uuid.uuid4(), {}, first_delivery=False)
    assert sentence is None
    assert added == []


@pytest.mark.asyncio
async def test_the_first_delivery_writes_once_and_stores():
    async def writer(db, company_id, tray):
        return w.RecommendationDraft(
            sentence="within band — I'd approve", model_used="m1")

    w.install_recommender(writer)
    db, added = _fake_db()
    approval_id = uuid.uuid4()
    sentence = await w._recommendation_for(
        db, COMPANY, approval_id, {}, first_delivery=True)
    assert sentence == "within band — I'd approve"
    assert len(added) == 1
    assert added[0].approval_id == approval_id
    assert added[0].sentence == sentence


@pytest.mark.asyncio
async def test_a_broken_writer_loses_advice_never_the_tray():
    async def writer(db, company_id, tray):
        raise RuntimeError("model down")

    w.install_recommender(writer)
    db, added = _fake_db()
    sentence = await w._recommendation_for(
        db, COMPANY, uuid.uuid4(), {}, first_delivery=True)
    assert sentence is None
    assert added == []


@pytest.mark.asyncio
async def test_no_installed_writer_means_no_sentence():
    db, added = _fake_db()
    sentence = await w._recommendation_for(
        db, COMPANY, uuid.uuid4(), {}, first_delivery=True)
    assert sentence is None
    assert added == []


# ── the shape that goes out on the socket (D8 E5) ────────────────────────────

def test_the_socket_copy_carries_the_composer_s_object_not_a_bare_string():
    """The bug this closes: the watcher assigned the sentence itself, so a
    client reading ``recommendation.sentence`` found an object on a reload
    and a string on a live delivery."""
    tray = {"tray_id": "t", "recommendation": None}
    w.apply_recommendation(tray, "within band — I'd approve")
    assert tray["recommendation"] == {
        "sentence": "within band — I'd approve", "why": None}


def test_a_missing_sentence_never_blanks_what_the_composer_joined():
    """Set, never clear: ``tray_detail`` reads the persisted row back, and
    the watcher must not write ``None`` over a card that already has one."""
    composed = {"sentence": "stored", "why": None}
    tray = {"tray_id": "t", "recommendation": composed}
    w.apply_recommendation(tray, None)
    assert tray["recommendation"] == composed


def test_a_tray_with_no_recommendation_at_all_still_goes_out():
    tray = {"tray_id": "t", "recommendation": None, "certified": {"tier": "T2"}}
    w.apply_recommendation(tray, None)
    assert tray["recommendation"] is None
    assert tray["certified"] == {"tier": "T2"}  # advice lost, never work
