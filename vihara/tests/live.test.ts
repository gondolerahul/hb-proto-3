import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EstateSnapshot } from "../src/api/estate";
import { STREAM_EVENT_TYPES, applyStreamEvent, isStreamEventType } from "../src/estate/live";
import {
  BACKOFF_SECONDS,
  resetSharedStream,
  subscribeEstateStream,
  type WireState,
} from "../src/estate/sharedStream";
import { createSseDecoder, type Wire, type WireHandlers } from "../src/estate/sse";
import { useLiveEstate } from "../src/estate/useLiveEstate";

/**
 * R-4 part S — the live estate.
 *
 * Everything here runs with **no network**. The reducer is pure and the wire is
 * an injected function, which is the property the port was worth doing for: the
 * protocol is a data structure, so the interesting cases (a truncated frame, a
 * dropped connection, a replayed beacon) are typed rather than staged.
 *
 * The assertions cluster around one theme, because one theme is what part S is
 * for: **an estate that failed to load and an estate with nothing happening
 * must not render identically.** Every "does not invent" test below is that
 * sentence at field level, and every wire-state test is it at connection level.
 */

/* ─────────────────────────────────────────────────────────────── fixtures */

function snapshot(): EstateSnapshot {
  return {
    estate: {
      loop_id: "loop-1",
      pulse: { beat_at: "2026-07-31T09:40:00", healthy: true },
      local_time: "2026-07-31T09:41:00+05:30",
      phase: "day",
      standing: "active",
    },
    quarters: [{ code: "finance", name: "Finance", districts: ["P08"] }],
    districts: [
      {
        process_code: "P08",
        name: "Collections",
        quarter: "finance",
        colleagues: [
          {
            entity_id: "AGT-046",
            name: "Meera",
            autonomy: "A2",
            hand_raised: false,
            state: "idle",
          },
        ],
        kpi: { plinth: [] },
        treasury: {
          envelope_id: "env-1",
          spent: 180,
          cap: 300,
          reserve_protected: true,
        },
        weather: { state: "clear", icon: null, sentence: null },
        traffic: { in_1h: 42, out_1h: 37, parked: 3 },
      },
    ],
    gatehouses: [],
    bridges: [
      {
        binding_id: "bind-1",
        connector: "tally",
        state: "healthy",
        credentials_expire_at: null,
        conflicts_open: 0,
      },
    ],
    halls: [],
    monuments: [],
    beacons: [],
    glasshouse: { open_scenarios: 0, last_run_at: null },
    gallery: { versions: 0, terminated: 0 },
    as_of: "2026-07-31T09:41:00",
  };
}

const P08 = (estate: EstateSnapshot) => estate.districts[0]!;

/* ───────────────────────────────────────────────────────── the SSE decoder */

describe("the fetch-based reader's frame decoder (S1)", () => {
  it("reads one frame", () => {
    const feed = createSseDecoder();
    const frames = feed('event: pulse\nid: pulse:3\ndata: {"healthy": true}\n\n');
    expect(frames).toEqual([
      { type: "pulse", data: '{"healthy": true}', id: "pulse:3" },
    ]);
  });

  it("emits nothing for the server's keepalive comment", () => {
    // Quiet ticks send `: keepalive`. If that decoded to a frame, every silent
    // three seconds would look like an event and the reducer would churn.
    expect(createSseDecoder()(": keepalive\n\n")).toEqual([]);
  });

  it("holds a frame that arrives split across two chunks", () => {
    const feed = createSseDecoder();
    expect(feed("event: traffic\ndata: {\"in_1h\"")).toEqual([]);
    const frames = feed(": 51}\n\n");
    expect(frames).toHaveLength(1);
    expect(frames[0]!.data).toBe('{"in_1h": 51}');
  });

  it("joins a multi-line data field and tolerates CRLF", () => {
    const frames = createSseDecoder()("event: x\r\ndata: one\r\ndata: two\r\n\r\n");
    expect(frames[0]!.data).toBe("one\ntwo");
  });

  it("knows which frame types the estate reducer handles", () => {
    expect(STREAM_EVENT_TYPES).toHaveLength(9);
    expect(isStreamEventType("beacon.raised")).toBe(true);
    expect(isStreamEventType("token")).toBe(false);
  });
});

/* ────────────────────────────────────────────────────────────── the reducer */

describe("the reducer applies what it is told (S2)", () => {
  it("raises a beacon and clears it", () => {
    const raised = applyStreamEvent(snapshot(), {
      type: "beacon.raised",
      payload: {
        approval_id: "HITL-8841",
        district: "P08",
        checkpoint_key: "payment.release",
        sla_seconds_left: 900,
      },
    });
    expect(raised.beacons).toEqual([
      {
        approval_id: "HITL-8841",
        district: "P08",
        checkpoint_key: "payment.release",
        sla_seconds_left: 900,
      },
    ]);
    const cleared = applyStreamEvent(raised, {
      type: "beacon.cleared",
      payload: { approval_id: "HITL-8841" },
    });
    expect(cleared.beacons).toEqual([]);
  });

  it("re-applies a replayed beacon in place, not as a second row", () => {
    // Replay is snapshot-on-connect, not `Last-Event-ID`: every (re)connect
    // resends `beacon.raised` for every pending approval. At-least-once, keyed
    // by approval id — so the upsert has to be idempotent, and it has to keep
    // the beacon's position or the list reshuffles itself on every reconnect.
    let estate = snapshot();
    for (const id of ["A", "B", "C"]) {
      estate = applyStreamEvent(estate, {
        type: "beacon.raised",
        payload: { approval_id: id, district: "P08", sla_seconds_left: 600 },
      });
    }
    const replayed = applyStreamEvent(estate, {
      type: "beacon.raised",
      payload: { approval_id: "B", district: "P08", sla_seconds_left: 120 },
    });
    expect(replayed.beacons.map((b) => b.approval_id)).toEqual(["A", "B", "C"]);
    expect(replayed.beacons[1]!.sla_seconds_left).toBe(120);
  });

  it("updates traffic, weather, treasury, a colleague and a bridge", () => {
    let estate = snapshot();
    estate = applyStreamEvent(estate, {
      type: "traffic",
      payload: { district: "P08", in_1h: 51, out_1h: 44, parked: 1 },
    });
    estate = applyStreamEvent(estate, {
      type: "weather.changed",
      payload: {
        district: "P08",
        state: "heat-shimmer",
        icon: "flame",
        sentence: "Collections has used 84% of its envelope.",
      },
    });
    estate = applyStreamEvent(estate, {
      type: "envelope.burn",
      payload: {
        district: "P08",
        envelope_id: "env-1",
        spent: 260,
        cap: 300,
        reserve_protected: true,
      },
    });
    estate = applyStreamEvent(estate, {
      type: "run.state",
      payload: {
        district: "P08",
        entity_id: "AGT-046",
        state: "running",
        hand_raised: true,
      },
    });
    estate = applyStreamEvent(estate, {
      type: "bridge.state",
      payload: { binding_id: "bind-1", state: "credentials_expiring" },
    });

    expect(P08(estate).traffic).toEqual({ in_1h: 51, out_1h: 44, parked: 1 });
    expect(P08(estate).weather.state).toBe("heat-shimmer");
    expect(P08(estate).treasury?.spent).toBe(260);
    expect(P08(estate).colleagues[0]).toMatchObject({
      state: "running",
      hand_raised: true,
    });
    expect(estate.bridges[0]!.state).toBe("credentials_expiring");
  });

  it("advances as_of, which is when something last changed", () => {
    const estate = applyStreamEvent(snapshot(), {
      type: "traffic",
      payload: { district: "P08", in_1h: 51, as_of: "2026-07-31T09:44:03" },
    });
    expect(estate.as_of).toBe("2026-07-31T09:44:03");
  });

  it("ignores an event for a district this client never loaded", () => {
    const before = snapshot();
    const after = applyStreamEvent(before, {
      type: "traffic",
      payload: { district: "P99", in_1h: 9 },
    });
    // Same identity, so a surface does not re-render for a phantom.
    expect(after).toBe(before);
  });
});

/**
 * DESIGN_CONTRACT §7.1 at field level. Each of these was a real line in the
 * rejected build's reducer — `Number(x ?? 0)`, `String(x ?? "clear")`,
 * `x === true` — and each turns a truncated frame into a confident lie.
 */
describe("the reducer never invents what it was not told", () => {
  it("does not zero traffic the frame omitted", () => {
    const estate = applyStreamEvent(snapshot(), {
      type: "traffic",
      payload: { district: "P08", in_1h: 51 },
    });
    expect(P08(estate).traffic).toEqual({ in_1h: 51, out_1h: 37, parked: 3 });
  });

  it("does not report calm for a weather word it does not know", () => {
    // `fog` is the live case: the fixture had it, the backend deliberately does
    // not emit it. If it ever arrived, reporting `clear` would be inventing
    // good news.
    let estate = applyStreamEvent(snapshot(), {
      type: "weather.changed",
      payload: { district: "P08", state: "storm", icon: "cloud-lightning" },
    });
    estate = applyStreamEvent(estate, {
      type: "weather.changed",
      payload: { district: "P08", state: "fog" },
    });
    expect(P08(estate).weather.state).toBe("storm");
  });

  it("does not mark the estate unhealthy on a pulse with no verdict", () => {
    const estate = applyStreamEvent(snapshot(), {
      type: "pulse",
      payload: { beat_at: "2026-07-31T09:44:00" },
    });
    expect(estate.estate.pulse.healthy).toBe(true);
  });

  it("does not build a treasury out of a partial burn", () => {
    const bare = snapshot();
    bare.districts[0]!.treasury = null;
    const estate = applyStreamEvent(bare, {
      type: "envelope.burn",
      payload: { district: "P08", spent: 260 },
    });
    // A gauge drawn from one of four fields is a gauge with a made-up axis.
    expect(P08(estate).treasury).toBeNull();
  });

  it("does not lower a raised hand a run.state frame said nothing about", () => {
    let estate = applyStreamEvent(snapshot(), {
      type: "run.state",
      payload: { district: "P08", entity_id: "AGT-046", hand_raised: true },
    });
    estate = applyStreamEvent(estate, {
      type: "run.state",
      payload: { district: "P08", entity_id: "AGT-046", state: "running" },
    });
    expect(P08(estate).colleagues[0]!.hand_raised).toBe(true);
  });

  it("does not insert a bridge it has never seen the whole of", () => {
    const estate = applyStreamEvent(snapshot(), {
      type: "bridge.state",
      payload: { binding_id: "bind-unknown", state: "broken" },
    });
    expect(estate.bridges).toHaveLength(1);
  });
});

/* ──────────────────────────────────────────────────── the shared connection */

interface FakeWire {
  wire: Wire;
  handlers: WireHandlers[];
  disposals: number;
  latest: () => WireHandlers;
}

function fakeWire(): FakeWire {
  const state: FakeWire = {
    handlers: [],
    disposals: 0,
    latest: () => state.handlers[state.handlers.length - 1]!,
    wire: (handlers) => {
      state.handlers.push(handlers);
      return () => {
        state.disposals += 1;
      };
    },
  };
  return state;
}

describe("one connection per app, and an honest one (S2, S3)", () => {
  beforeEach(() => {
    resetSharedStream();
  });

  afterEach(() => {
    resetSharedStream();
    vi.useRealTimers();
  });

  it("opens once for two subscribers and closes with the last", () => {
    const fake = fakeWire();
    const seen: WireState[] = [];
    const off1 = subscribeEstateStream(
      { onEvent: () => undefined, onWire: (s) => seen.push(s) },
      fake.wire,
    );
    const off2 = subscribeEstateStream({
      onEvent: () => undefined,
      onWire: () => undefined,
    });
    expect(fake.handlers).toHaveLength(1);

    off1();
    expect(fake.disposals).toBe(0);
    off2();
    expect(fake.disposals).toBe(1);
    expect(seen[0]).toEqual({ status: "connecting" });
  });

  it("tells a late subscriber where things stand", () => {
    // On a healthy quiet estate the next transition could be never, so a
    // subscriber that joined after the connection opened must not sit on
    // "connecting" forever.
    const fake = fakeWire();
    subscribeEstateStream(
      { onEvent: () => undefined, onWire: () => undefined },
      fake.wire,
    );
    fake.latest().onOpen();
    const seen: WireState[] = [];
    subscribeEstateStream({
      onEvent: () => undefined,
      onWire: (s) => seen.push(s),
    });
    expect(seen).toEqual([{ status: "live" }]);
  });

  it("fans one frame out to every subscriber, parsed", () => {
    const fake = fakeWire();
    const a: string[] = [];
    const b: string[] = [];
    subscribeEstateStream(
      { onEvent: (e) => a.push(e.type), onWire: () => undefined },
      fake.wire,
    );
    subscribeEstateStream({
      onEvent: (e) => b.push(e.type),
      onWire: () => undefined,
    });
    fake.latest().onOpen();
    fake.latest().onFrame({
      type: "beacon.raised",
      data: '{"approval_id": "X"}',
      id: null,
    });
    expect(a).toEqual(["beacon.raised"]);
    expect(b).toEqual(["beacon.raised"]);
  });

  it("drops a malformed frame without dropping the connection", () => {
    const fake = fakeWire();
    const seen: string[] = [];
    subscribeEstateStream(
      { onEvent: (e) => seen.push(e.type), onWire: () => undefined },
      fake.wire,
    );
    fake.latest().onOpen();
    fake.latest().onFrame({ type: "pulse", data: "{not json", id: null });
    fake.latest().onFrame({ type: "token", data: '{"text": "hi"}', id: null });
    fake.latest().onFrame({ type: "pulse", data: '{"healthy": true}', id: null });
    expect(seen).toEqual(["pulse"]);
    expect(fake.disposals).toBe(0);
  });

  it("reports a dropped stream as stale, with a reason and a real countdown", () => {
    // The whole point of S3: a dropped stream is never silently calm.
    vi.useFakeTimers();
    const fake = fakeWire();
    const seen: WireState[] = [];
    subscribeEstateStream(
      { onEvent: () => undefined, onWire: (s) => seen.push(s) },
      fake.wire,
    );
    fake.latest().onOpen();
    fake.latest().onClosed("the connection to the estate dropped");

    const stale = seen[seen.length - 1]!;
    expect(stale.status).toBe("stale");
    if (stale.status !== "stale") throw new Error("unreachable");
    expect(stale.reason).toBe("the connection to the estate dropped");
    expect(stale.retryInSeconds).toBeGreaterThan(0);
    expect(stale.retryInSeconds).toBeLessThanOrEqual(BACKOFF_SECONDS[0]! * 1.2);
  });

  it("reconnects on the ladder, and backs off further each time", () => {
    vi.useFakeTimers();
    const fake = fakeWire();
    subscribeEstateStream(
      { onEvent: () => undefined, onWire: () => undefined },
      fake.wire,
    );
    fake.latest().onOpen();

    fake.latest().onClosed("dropped");
    vi.advanceTimersByTime(BACKOFF_SECONDS[0]! * 1000 * 1.2 + 1);
    expect(fake.handlers).toHaveLength(2);

    // Still failing: the second rung must be longer than the first, or a dead
    // backend is hammered at one attempt a second forever.
    fake.latest().onClosed("dropped");
    vi.advanceTimersByTime(BACKOFF_SECONDS[0]! * 1000 * 1.2 + 1);
    expect(fake.handlers).toHaveLength(2);
    vi.advanceTimersByTime(BACKOFF_SECONDS[1]! * 1000 * 1.2 + 1);
    expect(fake.handlers).toHaveLength(3);
  });

  it("returns to the first rung once a connection succeeds", () => {
    vi.useFakeTimers();
    const fake = fakeWire();
    subscribeEstateStream(
      { onEvent: () => undefined, onWire: () => undefined },
      fake.wire,
    );
    fake.latest().onOpen();
    fake.latest().onClosed("dropped");
    vi.advanceTimersByTime(BACKOFF_SECONDS[0]! * 1000 * 1.2 + 1);
    fake.latest().onOpen();
    fake.latest().onClosed("dropped again");
    vi.advanceTimersByTime(BACKOFF_SECONDS[0]! * 1000 * 1.2 + 1);
    expect(fake.handlers).toHaveLength(3);
  });

  it("schedules no reconnect once the last subscriber has gone", () => {
    vi.useFakeTimers();
    const fake = fakeWire();
    const off = subscribeEstateStream(
      { onEvent: () => undefined, onWire: () => undefined },
      fake.wire,
    );
    fake.latest().onOpen();
    off();
    fake.latest().onClosed("dropped");
    vi.advanceTimersByTime(60_000);
    expect(fake.handlers).toHaveLength(1);
  });
});

/* ─────────────────────────────────────────────────────────────── the hook */

describe("useLiveEstate (S2, S3)", () => {
  beforeEach(() => {
    resetSharedStream();
  });

  afterEach(() => {
    resetSharedStream();
  });

  it("scaffolds, reads, then goes live", async () => {
    const fake = fakeWire();
    const { result } = renderHook(() =>
      useLiveEstate({ wire: fake.wire, read: async () => snapshot() }),
    );
    expect(result.current.phase).toBe("loading");
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    act(() => fake.latest().onOpen());
    if (result.current.phase !== "ready") throw new Error("unreachable");
    expect(result.current.wire).toEqual({ status: "live" });
  });

  it("keeps the estate and marks it stale when the wire drops", async () => {
    const fake = fakeWire();
    const { result } = renderHook(() =>
      useLiveEstate({ wire: fake.wire, read: async () => snapshot() }),
    );
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    act(() => fake.latest().onOpen());
    act(() => fake.latest().onClosed("the connection to the estate dropped"));

    if (result.current.phase !== "ready") throw new Error("unreachable");
    // The numbers stay — they were true when we last heard. What changes is
    // that the surface can now say so.
    expect(P08(result.current.estate).traffic.in_1h).toBe(42);
    expect(result.current.wire.status).toBe("stale");
  });

  it("re-reads the projection on a reconnect, not just the beacon replay", async () => {
    // `diff_estate` returns early when `prev is None`, so a reconnect replays
    // beacons and pulse and nothing else. Without the re-read a district would
    // hold whatever traffic it had when the wire dropped, forever, invisibly.
    let reads = 0;
    const fake = fakeWire();
    const { result } = renderHook(() =>
      useLiveEstate({
        wire: fake.wire,
        read: async () => {
          reads += 1;
          const estate = snapshot();
          estate.districts[0]!.traffic.in_1h = reads === 1 ? 42 : 88;
          return estate;
        },
      }),
    );
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    act(() => fake.latest().onOpen());
    act(() => fake.latest().onClosed("dropped"));
    act(() => fake.latest().onOpen());

    await waitFor(() => {
      if (result.current.phase !== "ready") throw new Error("not ready");
      expect(P08(result.current.estate).traffic.in_1h).toBe(88);
    });
    expect(reads).toBe(2);
  });

  it("reduces a frame into the estate the surface is holding", async () => {
    const fake = fakeWire();
    const { result } = renderHook(() =>
      useLiveEstate({ wire: fake.wire, read: async () => snapshot() }),
    );
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    act(() => fake.latest().onOpen());
    act(() =>
      fake.latest().onFrame({
        type: "beacon.raised",
        data: '{"approval_id": "HITL-8841", "district": "P08", "sla_seconds_left": 900}',
        id: "beacon.raised:HITL-8841",
      }),
    );
    if (result.current.phase !== "ready") throw new Error("unreachable");
    expect(result.current.estate.beacons[0]?.approval_id).toBe("HITL-8841");
  });

  it("fails honestly when the projection cannot be read, and offers a retry", async () => {
    let attempt = 0;
    const fake = fakeWire();
    const { result } = renderHook(() =>
      useLiveEstate({
        wire: fake.wire,
        read: async () => {
          attempt += 1;
          if (attempt === 1) throw new Error("no");
          return snapshot();
        },
      }),
    );
    await waitFor(() => expect(result.current.phase).toBe("failed"));
    if (result.current.phase !== "failed") throw new Error("unreachable");
    // No silent blank, and no estate drawn over an absence.
    expect(result.current.reason).toBe("The estate could not be reached.");
    act(() => {
      if (result.current.phase === "failed") result.current.retry();
    });
    await waitFor(() => expect(result.current.phase).toBe("ready"));
  });
});
