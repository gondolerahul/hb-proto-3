"""genui/stream.py — the company-scoped live stream (VG-03, D5 §3).

One SSE connection per session, multiplexing every estate event type. Three
properties, from the contract:

* **Scoping is a security boundary, not a filter.** The company is fixed at
  connect from the session; the emitter only ever reads that company's
  estate. There is no client-supplied selector to get wrong.
* **Aggregation happens server-side.** The wire carries deltas of the
  *estate read model* — rates and states — never signal rows. A busy
  tenant's signal log stays in the database.
* **Backpressure is dropping, not queueing.** ``traffic``, ``pulse`` and
  ``envelope.burn`` are sampled states: each tick emits the current value
  when it changed, and a missed tick is simply superseded by the next.
  ``beacon.raised``/``beacon.cleared`` and ``tray.delivered`` are **not**
  droppable — and the replay story is deliberately *snapshot-on-connect*
  rather than a ``Last-Event-ID`` cursor: every (re)connect first receives
  ``beacon.raised`` for every currently-pending approval, so a client
  rebuilds exact state with no cursor to lose. At-least-once, keyed by
  approval id, idempotent to re-apply. (A cursor would have needed a
  durable per-event ordering the platform does not keep; the snapshot is
  the stronger guarantee and is recorded as a build delta against D5 §3.)

The engine is a poll-diff loop over the estate read model — the platform
has no push fabric for these states, and a bounded-interval diff against
one projection is honest and cheap (the projection is one read, VG-02's).
``diff_estate`` is pure; the loop around it is plumbing.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Awaitable, Callable

from src.ai.genui.estate import estate_view

STREAM_INTERVAL_SECONDS = 3.0

#: Sampled event types — a newer value supersedes a missed one.
SAMPLED = ("traffic", "pulse", "envelope.burn")


# ── pure: what changed between two estate reads ──────────────────────────────

def diff_estate(
    prev: dict[str, Any] | None, cur: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """(event_type, payload) pairs. ``prev=None`` is the connect snapshot:
    every pending beacon (and its tray mirror) plus the current pulse."""
    events: list[tuple[str, dict[str, Any]]] = []
    as_of = cur.get("as_of")

    prev_beacons = {
        b["approval_id"]: b for b in (prev or {}).get("beacons", [])}
    cur_beacons = {b["approval_id"]: b for b in cur.get("beacons", [])}

    for approval_id, beacon in cur_beacons.items():
        if approval_id not in prev_beacons:
            events.append(("beacon.raised", {**beacon, "as_of": as_of}))
            events.append(("tray.delivered", {
                "tray_id": approval_id, "district": beacon.get("district"),
                "as_of": as_of}))
    for approval_id, beacon in prev_beacons.items():
        if approval_id not in cur_beacons:
            events.append(("beacon.cleared", {
                "approval_id": approval_id,
                "district": beacon.get("district"), "as_of": as_of}))

    if prev is None:
        events.append(("pulse", {**cur["estate"]["pulse"], "as_of": as_of}))
        return events

    if prev["estate"]["pulse"] != cur["estate"]["pulse"]:
        events.append(("pulse", {**cur["estate"]["pulse"], "as_of": as_of}))

    prev_districts = {d["process_code"]: d for d in prev.get("districts", [])}
    for district in cur.get("districts", []):
        code = district["process_code"]
        before = prev_districts.get(code)
        if before is None:
            continue
        if before["weather"] != district["weather"]:
            events.append(("weather.changed", {
                "district": code, **district["weather"], "as_of": as_of}))
        if before["traffic"] != district["traffic"]:
            events.append(("traffic", {
                "district": code, **district["traffic"], "as_of": as_of}))
        if before["treasury"] != district["treasury"] and district["treasury"]:
            events.append(("envelope.burn", {
                "district": code, **district["treasury"], "as_of": as_of}))
        before_states = {
            c["entity_id"]: (c["state"], c["hand_raised"])
            for c in before["colleagues"]}
        for colleague in district["colleagues"]:
            state = (colleague["state"], colleague["hand_raised"])
            if before_states.get(colleague["entity_id"], state) != state:
                events.append(("run.state", {
                    "district": code, "entity_id": colleague["entity_id"],
                    "state": colleague["state"],
                    "hand_raised": colleague["hand_raised"], "as_of": as_of}))

    prev_bridges = {b["binding_id"]: b for b in prev.get("bridges", [])}
    for bridge in cur.get("bridges", []):
        before_bridge = prev_bridges.get(bridge["binding_id"])
        if before_bridge is not None and before_bridge["state"] != bridge["state"]:
            events.append(("bridge.state", {**bridge, "as_of": as_of}))

    return events


def sse_format(event_type: str, payload: dict[str, Any], event_id: str) -> str:
    """One SSE frame. The id is advisory (the replay story is the snapshot);
    it exists so a client can de-duplicate an at-least-once beacon."""
    return (
        f"event: {event_type}\n"
        f"id: {event_id}\n"
        f"data: {json.dumps(payload)}\n\n"
    )


# ── the loop ─────────────────────────────────────────────────────────────────

async def stream_events(
    company_id: uuid.UUID,
    *,
    interval: float = STREAM_INTERVAL_SECONDS,
    max_ticks: int | None = None,
    read_estate: Callable[[uuid.UUID], Awaitable[dict[str, Any]]] | None = None,
) -> AsyncIterator[str]:
    """The SSE body: snapshot, then diffs, with a heartbeat comment on quiet
    ticks so proxies keep the pipe open. ``read_estate`` is injectable for
    tests; the default opens a short-lived session per tick — a stream must
    never hold one request-scoped session across its whole life."""
    reader = read_estate or _read_estate_fresh
    prev: dict[str, Any] | None = None
    tick = 0
    while True:
        cur = await reader(company_id)
        events = diff_estate(prev, cur)
        if events:
            for event_type, payload in events:
                event_id = f"{event_type}:{payload.get('approval_id') or payload.get('tray_id') or tick}"
                yield sse_format(event_type, payload, event_id)
        else:
            yield ": keepalive\n\n"
        prev = cur
        tick += 1
        if max_ticks is not None and tick >= max_ticks:
            return
        await asyncio.sleep(interval)


async def _read_estate_fresh(company_id: uuid.UUID) -> dict[str, Any]:
    from src.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        return await estate_view(db, company_id, now=datetime.utcnow())
