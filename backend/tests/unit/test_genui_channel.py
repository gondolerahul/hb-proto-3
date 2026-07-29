"""SEAM T8 — the Pragya channel's protocol, driven without a wire.

The rules under test are the contract's four (D5 §5): one session across
devices, viewport kept, **the channel never elevates**, and one delivery
door — sockets first, push only when nobody is listening, never both.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.ai.genui import channel as ch

COMPANY = uuid.uuid4()
USER = uuid.uuid4()
SESSION = uuid.uuid4()


class FakeSocket:
    def __init__(self, broken: bool = False):
        self.sent: list[dict] = []
        self.broken = broken

    async def send_json(self, data):
        if self.broken:
            raise RuntimeError("gone")
        self.sent.append(data)


@pytest.fixture()
def hub(monkeypatch):
    fresh = ch.ChannelHub()
    monkeypatch.setattr(ch, "_hub", fresh)
    return fresh


# ── membership (rule 1) ──────────────────────────────────────────────────────

def test_a_second_device_joins_the_same_session(hub):
    first, second = FakeSocket(), FakeSocket()
    state1 = hub.join(SESSION, COMPANY, USER, first)
    state2 = hub.join(SESSION, COMPANY, USER, second)
    assert state1 is state2
    assert state1.sockets == {first, second}


def test_context_survives_a_disconnect(hub):
    socket = FakeSocket()
    state = hub.join(SESSION, COMPANY, USER, socket)
    state.viewport = {"kind": "process", "id": "P06"}
    hub.leave(SESSION, socket)
    assert hub.state_for_user(COMPANY, USER).viewport == {
        "kind": "process", "id": "P06"}


# ── dispatch ─────────────────────────────────────────────────────────────────

async def _dispatch(hub, message, db=None):
    state = hub.join(SESSION, COMPANY, USER, FakeSocket())
    return state, await ch.dispatch_message(db, state, COMPANY, USER, message)


@pytest.mark.asyncio
async def test_viewport_and_depth_are_kept_silently(hub):
    state, reply = await _dispatch(
        hub, {"type": "viewport", "context_ref": {"kind": "record", "id": "r1"}})
    assert reply is None
    assert state.viewport == {"kind": "record", "id": "r1"}
    _, reply = await _dispatch(hub, {"type": "depth_change", "level": 3})
    assert reply is None


@pytest.mark.asyncio
async def test_step_up_result_is_a_hint_and_nothing_more(hub):
    """Rule 3, pinned twice: the dispatch stores an in-memory hint, and the
    module's source never touches the session row's elevation fields."""
    state, reply = await _dispatch(
        hub, {"type": "step_up_result", "tier": "T2", "ok": True})
    assert reply is None
    assert state.step_up_hint == {"tier": "T2", "ok": True}

    import ast
    import inspect

    tree = ast.parse(inspect.getsource(ch))
    touched = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not {"auth_level", "elevated_until", "elevated_by"} & touched
    assert "elevate" not in called


@pytest.mark.asyncio
async def test_an_unknown_type_fails_visible(hub):
    _, reply = await _dispatch(hub, {"type": "teleport"})
    assert reply["type"] == "error" and "teleport" in reply["reason"]


@pytest.mark.asyncio
async def test_a_malformed_echo_is_refused_not_recorded(hub):
    _, reply = await _dispatch(
        hub, {"type": "action_echo", "sentence": "", "action_ref": {}})
    assert reply["type"] == "error"


@pytest.mark.asyncio
async def test_an_empty_utterance_is_an_error(hub):
    _, reply = await _dispatch(hub, {"type": "utterance", "text": "  "})
    assert reply["type"] == "error"


@pytest.mark.asyncio
async def test_an_utterance_narrates_and_reports_a_needed_ceremony(hub, monkeypatch):
    async def fake_run_turn(db, request):
        return SimpleNamespace(
            reply="That needs a passkey.", needs_step_up=True, needs_oob=False,
            tier="T2", command_ref="cmd:1")

    class FakeDB:
        async def commit(self):
            return None

    import src.ai.pragya.runtime as runtime

    monkeypatch.setattr(runtime, "run_turn", fake_run_turn)
    _, reply = await _dispatch(
        hub, {"type": "utterance", "text": "raise Meera to A3"}, db=FakeDB())
    assert reply["type"] == "narrate"
    assert reply["text"] == "That needs a passkey."
    assert reply["step_up"] == {"tier": "T2", "command_ref": "cmd:1", "oob": False}


# ── the delivery door (rule 4 / L8) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_tray_goes_to_the_socket_when_one_listens(hub, monkeypatch):
    called = []

    async def fake_push(*a, **k):
        called.append(k)
        return 1

    monkeypatch.setattr(ch, "send_tray_push", fake_push)
    socket = FakeSocket()
    hub.join(SESSION, COMPANY, USER, socket)

    outcome = await ch.deliver_tray(None, COMPANY, USER, {
        "tray_id": "t1", "what_happened": {"sentence": "A payout needs you."}})
    assert outcome == "socket"
    assert socket.sent[-1]["type"] == "deliver_tray"
    assert called == []  # never both — no double notification


@pytest.mark.asyncio
async def test_a_tray_falls_back_to_push_when_nobody_listens(hub, monkeypatch):
    pushed = {}

    async def fake_push(db, company_id, user_id, *, tray_id, one_sentence, transport=None):
        pushed.update(tray_id=tray_id, one_sentence=one_sentence)
        return 1

    monkeypatch.setattr(ch, "send_tray_push", fake_push)
    outcome = await ch.deliver_tray(None, COMPANY, USER, {
        "tray_id": "t1", "what_happened": {"sentence": "A payout needs you."}})
    assert outcome == "push"
    assert pushed == {"tray_id": "t1", "one_sentence": "A payout needs you."}


@pytest.mark.asyncio
async def test_a_dead_socket_falls_through_to_push(hub, monkeypatch):
    async def fake_push(*a, **k):
        return 1

    monkeypatch.setattr(ch, "send_tray_push", fake_push)
    hub.join(SESSION, COMPANY, USER, FakeSocket(broken=True))
    outcome = await ch.deliver_tray(None, COMPANY, USER, {"tray_id": "t1"})
    assert outcome == "push"


# ── echo fan-out ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_echoes_land_in_context_never_back_on_the_wire(hub):
    from datetime import datetime

    socket = FakeSocket()
    state = hub.join(SESSION, COMPANY, USER, socket)
    echo = SimpleNamespace(
        company_id=COMPANY, user_id=USER, sentence="filtered Invoices",
        action_ref={"kind": "register.filter"}, occurred_at=datetime(2026, 7, 29))
    await ch.echo_fanout(echo)
    assert state.echoes[-1]["sentence"] == "filtered Invoices"
    assert socket.sent == []
