"""SEAM T4 — the live stream's pure diff.

Every event type reachable alone from one changed field, and the connect
snapshot pinned: a reconnecting client rebuilds beacon state from the
snapshot, so a dropped connection can lose a *sampled* value (superseded
next tick) but never a beacon — the non-droppable/droppable split of D5 §3.
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.genui.stream import diff_estate, sse_format, stream_events


def _estate(**overrides):
    base = {
        "estate": {"pulse": {"beat_at": "t0", "healthy": True}},
        "beacons": [],
        "districts": [{
            "process_code": "P06", "name": "Care",
            "colleagues": [
                {"entity_id": "e1", "state": "idle", "hand_raised": False}],
            "weather": {"state": "clear", "icon": None, "sentence": None},
            "traffic": {"in_1h": 0, "out_1h": 0, "parked": 0},
            "treasury": {"envelope_id": "env1", "spent": 1.0, "cap": 10.0,
                         "reserve_protected": True},
            "kpi": {"plinth": []},
        }],
        "bridges": [{"binding_id": "b1", "connector": "zoho_books",
                     "state": "active", "credentials_expire_at": None,
                     "conflicts_open": 0}],
        "as_of": "now",
    }
    base.update(overrides)
    return base


def _beacon(approval_id="a1"):
    return {"approval_id": approval_id, "district": "P06",
            "checkpoint_key": "k", "sla_seconds_left": 100}


def _types(events):
    return [event_type for event_type, _ in events]


# ── the connect snapshot ─────────────────────────────────────────────────────

def test_connect_replays_every_pending_beacon_and_the_pulse():
    cur = _estate(beacons=[_beacon("a1"), _beacon("a2")])
    events = diff_estate(None, cur)
    assert _types(events) == [
        "beacon.raised", "tray.delivered",
        "beacon.raised", "tray.delivered", "pulse"]


def test_a_quiet_estate_connects_with_only_the_pulse():
    assert _types(diff_estate(None, _estate())) == ["pulse"]


# ── each event type, alone ───────────────────────────────────────────────────

def test_a_new_beacon_raises_and_delivers_its_tray():
    events = diff_estate(_estate(), _estate(beacons=[_beacon()]))
    assert _types(events) == ["beacon.raised", "tray.delivered"]
    assert events[1][1]["tray_id"] == "a1"


def test_a_resolved_beacon_clears():
    events = diff_estate(_estate(beacons=[_beacon()]), _estate())
    assert _types(events) == ["beacon.cleared"]
    assert events[0][1]["approval_id"] == "a1"


def test_an_unchanged_beacon_is_silent():
    prev = _estate(beacons=[_beacon()])
    assert diff_estate(prev, _estate(beacons=[_beacon()])) == []


def test_weather_change_names_the_district():
    cur = _estate()
    cur["districts"][0]["weather"] = {
        "state": "moonlit", "icon": "moon", "sentence": "…"}
    events = diff_estate(_estate(), cur)
    assert _types(events) == ["weather.changed"]
    assert events[0][1]["district"] == "P06"
    assert events[0][1]["state"] == "moonlit"


def test_traffic_is_sampled_on_change():
    cur = _estate()
    cur["districts"][0]["traffic"] = {"in_1h": 4, "out_1h": 1, "parked": 0}
    assert _types(diff_estate(_estate(), cur)) == ["traffic"]


def test_envelope_burn_on_spend():
    cur = _estate()
    cur["districts"][0]["treasury"] = {
        "envelope_id": "env1", "spent": 5.0, "cap": 10.0,
        "reserve_protected": True}
    assert _types(diff_estate(_estate(), cur)) == ["envelope.burn"]


def test_a_colleague_starting_work_emits_run_state():
    cur = _estate()
    cur["districts"][0]["colleagues"][0] = {
        "entity_id": "e1", "state": "running", "hand_raised": False}
    events = diff_estate(_estate(), cur)
    assert _types(events) == ["run.state"]
    assert events[0][1]["entity_id"] == "e1"


def test_a_bridge_going_dark_emits_bridge_state():
    cur = _estate()
    cur["bridges"][0] = {**cur["bridges"][0], "state": "error"}
    assert _types(diff_estate(_estate(), cur)) == ["bridge.state"]


def test_pulse_change_emits_and_stillness_does_not():
    cur = _estate()
    cur["estate"]["pulse"] = {"beat_at": "t1", "healthy": True}
    assert _types(diff_estate(_estate(), cur)) == ["pulse"]
    assert diff_estate(_estate(), _estate()) == []


# ── framing and the loop ─────────────────────────────────────────────────────

def test_sse_frames_are_well_formed():
    frame = sse_format("beacon.raised", {"approval_id": "a1"}, "beacon.raised:a1")
    assert frame == (
        'event: beacon.raised\nid: beacon.raised:a1\n'
        'data: {"approval_id": "a1"}\n\n')


@pytest.mark.asyncio
async def test_the_loop_snapshots_then_diffs_then_keeps_alive():
    company = uuid.uuid4()
    sequence = [
        _estate(beacons=[_beacon("a1")]),          # connect: snapshot
        _estate(beacons=[_beacon("a1")]),          # nothing changed
        _estate(),                                  # a1 resolved
    ]
    reads = iter(sequence)

    async def reader(_cid):
        return next(reads)

    frames = [
        frame async for frame in stream_events(
            company, interval=0, max_ticks=3, read_estate=reader)]
    joined = "".join(frames)
    assert "event: beacon.raised" in frames[0]
    assert any(frame == ": keepalive\n\n" for frame in frames)
    assert "event: beacon.cleared" in joined
