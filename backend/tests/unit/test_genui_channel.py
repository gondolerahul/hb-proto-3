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
async def test_the_mic_branch_routes_to_the_voice_leg(hub, monkeypatch):
    """The dispatch branch is thin routing; the leg itself is S4-tested.
    What this pins: open and closed reach the right functions, and an
    unknown mic state fails visible like any unknown type."""
    from src.ai.genui import voice_channel as vc

    calls = []

    async def fake_open(db, state, company_id, user_id):
        calls.append("open")
        return None

    async def fake_close(state, *, abort=False):
        calls.append(f"close(abort={abort})")

    monkeypatch.setattr(vc, "open_mic", fake_open)
    monkeypatch.setattr(vc, "close_mic", fake_close)
    _, reply = await _dispatch(hub, {"type": "mic", "state": "open"})
    assert reply is None
    _, reply = await _dispatch(hub, {"type": "mic", "state": "closed"})
    assert reply is None
    _, reply = await _dispatch(hub, {"type": "mic", "state": "sideways"})
    assert reply["type"] == "error" and "sideways" in reply["reason"]
    assert calls == ["open", "close(abort=False)"]


@pytest.mark.asyncio
async def test_a_malformed_echo_is_refused_not_recorded(hub):
    _, reply = await _dispatch(
        hub, {"type": "action_echo", "sentence": "", "action_ref": {}})
    assert reply["type"] == "error"


@pytest.mark.asyncio
async def test_an_empty_utterance_is_an_error(hub):
    _, reply = await _dispatch(hub, {"type": "utterance", "text": "  "})
    assert reply["type"] == "error"


class FakeDB:
    async def commit(self):
        return None


def _fake_outcome(**overrides):
    base = dict(
        reply="Done.", needs_step_up=False, needs_oob=False,
        tier=None, command_ref=None, command=None, raised_approval=False)
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_an_utterance_narrates_to_the_session_and_reports_a_ceremony(
        hub, monkeypatch):
    """STEWARD S3: the answer goes to the session (every device), not to the
    asking socket alone — one session across devices is rule 1's promise."""
    async def fake_run_turn(db, request):
        return _fake_outcome(
            reply="That needs a passkey.", needs_step_up=True,
            tier="T2", command_ref="cmd:1")

    import src.ai.pragya.runtime as runtime

    monkeypatch.setattr(runtime, "run_turn", fake_run_turn)
    asking, second = FakeSocket(), FakeSocket()
    state = hub.join(SESSION, COMPANY, USER, asking)
    hub.join(SESSION, COMPANY, USER, second)
    reply = await ch.dispatch_message(
        FakeDB(), state, COMPANY, USER,
        {"type": "utterance", "text": "raise Meera to A3"})
    assert reply is None
    for socket in (asking, second):
        narrate = [m for m in socket.sent if m["type"] == "narrate"]
        assert len(narrate) == 1
        assert narrate[0]["text"] == "That needs a passkey."
        assert narrate[0]["step_up"] == {
            "tier": "T2", "command_ref": "cmd:1", "oob": False}


@pytest.mark.asyncio
async def test_presence_cycles_working_then_listening_around_a_turn(
        hub, monkeypatch):
    async def fake_run_turn(db, request):
        return _fake_outcome()

    import src.ai.pragya.runtime as runtime

    monkeypatch.setattr(runtime, "run_turn", fake_run_turn)
    socket = FakeSocket()
    state = hub.join(SESSION, COMPANY, USER, socket)
    await ch.dispatch_message(
        FakeDB(), state, COMPANY, USER, {"type": "utterance", "text": "hi"})
    presence = [m["state"] for m in socket.sent if m["type"] == "presence"]
    assert presence == ["working", "listening"]


@pytest.mark.asyncio
async def test_a_failed_turn_means_away_not_a_dead_channel(hub, monkeypatch):
    """§7's honest mapping: she is *not able to be present* — pretending to
    listen would be a lie, and the socket must survive to say so."""
    async def broken_run_turn(db, request):
        raise RuntimeError("runtime down")

    import src.ai.pragya.runtime as runtime

    monkeypatch.setattr(runtime, "run_turn", broken_run_turn)
    socket = FakeSocket()
    state = hub.join(SESSION, COMPANY, USER, socket)
    reply = await ch.dispatch_message(
        FakeDB(), state, COMPANY, USER, {"type": "utterance", "text": "hi"})
    assert reply["type"] == "error"
    presence = [m["state"] for m in socket.sent if m["type"] == "presence"]
    assert presence == ["working", "away"]
    assert [m for m in socket.sent if m["type"] == "narrate"] == []


@pytest.mark.asyncio
async def test_she_walks_the_map_before_she_speaks(hub, monkeypatch):
    """A read of a district materializes its surface — emitted before the
    narration, so the place arrives, then the words about it."""
    async def fake_run_turn(db, request):
        return _fake_outcome(
            reply="Acquisition is quiet today.",
            command=SimpleNamespace(
                kind="tenant_read", target="p03", summary="show acquisition"))

    import src.ai.pragya.runtime as runtime

    monkeypatch.setattr(runtime, "run_turn", fake_run_turn)
    socket = FakeSocket()
    state = hub.join(SESSION, COMPANY, USER, socket)
    await ch.dispatch_message(
        FakeDB(), state, COMPANY, USER,
        {"type": "utterance", "text": "show me acquisition"})
    kinds = [m["type"] for m in socket.sent]
    assert kinds.index("materialize") < kinds.index("narrate")
    materialize = next(m for m in socket.sent if m["type"] == "materialize")
    assert materialize["surface_id"] == "district.P03"
    narrate = next(m for m in socket.sent if m["type"] == "narrate")
    assert {"kind": "district", "label": "P03", "ref": "P03"} in narrate["anchors"]


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
