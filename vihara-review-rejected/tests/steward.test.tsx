/**
 * STEWARD S5–S8 — the channel client, the reducer, the dock, the voice
 * utilities, and the shared-stream consolidation, all against fakes.
 *
 * What these pin: a channel event becomes exactly one visible thing; the
 * ceremony over the channel is the SAME StepUpCeremony every certified
 * surface uses, retried whole exactly once; the viewport rides every
 * depth change (rule 2); barge-in stops playback locally first; and one
 * SSE wire serves every subscriber.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  connectChannel,
  parseChannelEvent,
  type SocketLike,
  type StewardEvent,
} from "../src/steward/channel";
import {
  INITIAL_STEWARD_STATE,
  LINE_LIMIT,
  reduceSteward,
  setConnected,
} from "../src/steward/state";
import { StewardDock, type Navigation } from "../src/steward/StewardDock";
import {
  floatTo16BitPCM,
  pcm16ToFloat32,
  rmsLevel,
} from "../src/steward/voice";
import { resetSharedStream, subscribeEstateStream } from "../src/estate/sharedStream";
import type { StreamEvent } from "../src/estate/live";

afterEach(() => {
  cleanup();
  resetSharedStream();
});

// ── the wire (S5) ────────────────────────────────────────────────────────────

class FakeSocket implements SocketLike {
  sent: unknown[] = [];
  listeners = new Map<string, ((event: unknown) => void)[]>();
  binaryType?: string;

  send(data: string | ArrayBuffer): void {
    this.sent.push(data);
  }

  close(): void {
    this.fire("close", {});
  }

  addEventListener(type: string, listener: (event: unknown) => void): void {
    const existing = this.listeners.get(type) ?? [];
    this.listeners.set(type, [...existing, listener]);
  }

  fire(type: string, event: unknown): void {
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }

  emit(payload: unknown): void {
    this.fire("message", { data: JSON.stringify(payload) });
  }
}

describe("the channel client", () => {
  it("parses known events and refuses garbage", () => {
    expect(
      parseChannelEvent({ type: "presence", state: "working" }),
    ).toEqual({ type: "presence", state: "working" });
    expect(
      parseChannelEvent({ type: "narrate", text: "hi" }),
    ).toEqual({ type: "narrate", text: "hi", anchors: [] });
    expect(parseChannelEvent({ type: "teleport" })).toBeNull();
    expect(parseChannelEvent("not an object")).toBeNull();
    expect(parseChannelEvent({ type: "narrate" })).toBeNull();
  });

  it("dispatches events, hands binary to the audio handler, and sends typed frames", () => {
    const socket = new FakeSocket();
    const events: StewardEvent[] = [];
    const audio: ArrayBuffer[] = [];
    const handle = connectChannel(
      { onEvent: (event) => events.push(event), onAudio: (frame) => audio.push(frame) },
      () => socket,
    );

    socket.emit({ type: "presence", state: "listening" });
    const frame = new ArrayBuffer(4);
    socket.fire("message", { data: frame });
    expect(events).toEqual([{ type: "presence", state: "listening" }]);
    expect(audio).toEqual([frame]);

    handle.say("approve it");
    handle.reportDepth(2);
    handle.reportViewport({ kind: "district", id: "P03" });
    handle.micOpen();
    expect(socket.sent.map((raw) => JSON.parse(String(raw)))).toEqual([
      { type: "utterance", text: "approve it" },
      { type: "depth_change", level: 2 },
      { type: "viewport", context_ref: { kind: "district", id: "P03" } },
      { type: "mic", state: "open" },
    ]);
    handle.close();
  });

  it("reconnects after a drop and stops when closed by the user", () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const make = (): FakeSocket => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    };
    const handle = connectChannel({ onEvent: () => undefined }, make);
    expect(sockets).toHaveLength(1);

    sockets[0]?.fire("close", {});
    vi.advanceTimersByTime(2500);
    expect(sockets).toHaveLength(2);

    handle.close();
    vi.advanceTimersByTime(5000);
    expect(sockets).toHaveLength(2);
    vi.useRealTimers();
  });
});

// ── the reducer (S6) ─────────────────────────────────────────────────────────

describe("the steward state", () => {
  it("keeps narrations bounded and clears the transcript on a reply", () => {
    let state = INITIAL_STEWARD_STATE;
    state = reduceSteward(state, {
      type: "transcript", text: "approve th", final: false });
    expect(state.transcript).toEqual({ text: "approve th", final: false });
    for (let i = 0; i < LINE_LIMIT + 5; i += 1) {
      state = reduceSteward(state, {
        type: "narrate", text: `line ${i}`, anchors: [] });
    }
    expect(state.lines).toHaveLength(LINE_LIMIT);
    expect(state.transcript).toBeNull();
  });

  it("stores a step-up ask and drops it on the next plain narration", () => {
    let state = reduceSteward(INITIAL_STEWARD_STATE, {
      type: "narrate",
      text: "That needs a passkey.",
      anchors: [],
      step_up: { tier: "T2", command_ref: "cmd:1", oob: false },
    });
    expect(state.stepUpAsk?.command_ref).toBe("cmd:1");
    state = reduceSteward(state, { type: "narrate", text: "Done.", anchors: [] });
    expect(state.stepUpAsk).toBeNull();
  });

  it("shows presence honestly and goes off when the wire drops", () => {
    let state = reduceSteward(INITIAL_STEWARD_STATE, {
      type: "presence", state: "away" });
    expect(state.presence).toBe("away");
    state = setConnected(state, false);
    expect(state.presence).toBe("off");
  });
});

// ── the dock (S6/S7/S8) ──────────────────────────────────────────────────────

function dockHarness(overrides: { depthLevel?: number } = {}) {
  const socket = new FakeSocket();
  const navigations: Navigation[] = [];
  let trays = 0;
  const playerStops: number[] = [];
  const micFrames: ArrayBuffer[] = [];
  let micHandlers: { onFrame: (f: ArrayBuffer) => void; onSpeech?: () => void } | null =
    null;

  const deps = {
    connect: (handlers: Parameters<typeof connectChannel>[0]) =>
      connectChannel(handlers, () => socket),
    mic: async (handlers: { onFrame: (f: ArrayBuffer) => void; onSpeech?: () => void }) => {
      micHandlers = handlers;
      return { stop: () => undefined };
    },
    player: () => ({
      enqueue: (frame: ArrayBuffer) => micFrames.push(frame),
      stop: () => playerStops.push(1),
      close: () => undefined,
    }),
    ceremony: {
      passkey: async () => ({ ok: true }),
      totp: async () => ({ ok: true }),
      oobIssue: async () => ({
        ok: true, challenge_id: "ch1", sent_to_channel: "whatsapp" }),
      oobConfirm: async () => ({ ok: true }),
    },
  };

  const view = render(
    <StewardDock
      onNavigate={(navigation) => navigations.push(navigation)}
      onTrayDelivered={() => {
        trays += 1;
      }}
      depthLevel={overrides.depthLevel ?? 0}
      contextRef={{ kind: "estate", id: null }}
      deps={deps}
    />,
  );
  return {
    socket,
    navigations,
    view,
    playerStops,
    getMicHandlers: () => micHandlers,
    trayCount: () => trays,
  };
}

describe("the dock", () => {
  it("shows presence, narrates with anchors, and an anchor walks the map", async () => {
    const { socket, navigations } = dockHarness();
    socket.fire("open", {});
    socket.emit({ type: "presence", state: "working" });
    await waitFor(() => {
      expect(screen.getByLabelText("Pragya is working")).toBeTruthy();
    });
    socket.emit({
      type: "narrate",
      text: "Acquisition is quiet.",
      anchors: [{ kind: "district", label: "P03", ref: "P03" }],
    });
    const anchor = await screen.findByRole("button", { name: "P03" });
    fireEvent.click(anchor);
    expect(navigations).toEqual([{ type: "focus", district: "P03" }]);
  });

  it("she walks the map when she says so", async () => {
    const { socket, navigations } = dockHarness();
    socket.emit({ type: "materialize", surface_id: "district.P06" });
    await waitFor(() => {
      expect(navigations).toEqual([
        { type: "materialize", surfaceId: "district.P06" },
      ]);
    });
  });

  it("saying something sends the utterance over the wire", async () => {
    const { socket } = dockHarness();
    socket.fire("open", {});
    const input = await screen.findByLabelText("ask Pragya");
    fireEvent.change(input, { target: { value: "pause care" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);
    const sent = socket.sent.map((raw) => JSON.parse(String(raw)));
    expect(sent.some(
      (m) => m.type === "utterance" && m.text === "pause care")).toBe(true);
  });

  it("a step_up narration opens the ceremony and the utterance retries whole, once", async () => {
    const { socket } = dockHarness();
    socket.fire("open", {});
    const input = await screen.findByLabelText("ask Pragya");
    fireEvent.change(input, { target: { value: "raise Meera to A3" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    socket.emit({
      type: "narrate",
      text: "That needs a passkey.",
      anchors: [],
      step_up: { tier: "T2", command_ref: "cmd:1", oob: false },
    });
    const ceremony = await screen.findByText("verify");
    const code = screen.getByLabelText(/one-time code/);
    fireEvent.change(code, { target: { value: "123456" } });
    fireEvent.submit(ceremony.closest("form") as HTMLFormElement);

    await waitFor(() => {
      const sent = socket.sent.map((raw) => JSON.parse(String(raw)));
      const utterances = sent.filter((m) => m.type === "utterance");
      expect(utterances).toEqual([
        { type: "utterance", text: "raise Meera to A3" },
        { type: "utterance", text: "raise Meera to A3" },
      ]);
      expect(sent.some(
        (m) => m.type === "step_up_result" && m.ok === true)).toBe(true);
    });
  });

  it("the T3 leg issues to a second channel and confirms the typed nonce", async () => {
    const { socket } = dockHarness();
    socket.fire("open", {});
    socket.emit({
      type: "narrate",
      text: "That needs the second channel.",
      anchors: [],
      step_up: { tier: "T3", command_ref: "cmd:9", oob: true },
    });
    const send = await screen.findByText("send the confirmation");
    fireEvent.click(send);
    const nonce = await screen.findByLabelText(/the code from whatsapp/);
    fireEvent.change(nonce, { target: { value: "424242" } });
    fireEvent.submit(nonce.closest("form") as HTMLFormElement);
    await waitFor(() => {
      const sent = socket.sent.map((raw) => JSON.parse(String(raw)));
      expect(sent.some(
        (m) => m.type === "step_up_result" && m.tier === "T3")).toBe(true);
    });
  });

  it("the mic opens the leg, streams frames, and barge-in stops playback first", async () => {
    const { socket, playerStops, getMicHandlers } = dockHarness();
    socket.fire("open", {});
    fireEvent.click(await screen.findByRole("button", { name: "mic" }));
    await waitFor(() => {
      expect(getMicHandlers()).not.toBeNull();
    });
    const sent = () => socket.sent.map((raw) => JSON.parse(String(raw)));
    expect(sent().some((m) => m.type === "mic" && m.state === "open")).toBe(true);

    // She starts speaking; the human talks over her.
    socket.emit({ type: "presence", state: "speaking" });
    await waitFor(() => {
      expect(screen.getByLabelText("Pragya is speaking")).toBeTruthy();
    });
    getMicHandlers()?.onSpeech?.();
    expect(playerStops.length).toBeGreaterThan(0);
    const micOpens = sent().filter((m) => m.type === "mic" && m.state === "open");
    expect(micOpens.length).toBe(2); // the toggle, then the interrupt
  });

  it("a delivered tray reaches the shell", async () => {
    const { socket, trayCount } = dockHarness();
    socket.emit({ type: "deliver_tray", tray: { tray_id: "t1" } });
    await waitFor(() => {
      expect(trayCount()).toBe(1);
    });
  });

  it("the viewport rides every depth change (rule 2)", async () => {
    const harness = dockHarness({ depthLevel: 0 });
    harness.socket.fire("open", {});
    harness.view.rerender(
      <StewardDock
        onNavigate={() => undefined}
        depthLevel={2}
        contextRef={{ kind: "district", id: "P03" }}
        deps={{
          connect: (handlers: Parameters<typeof connectChannel>[0]) =>
            connectChannel(handlers, () => harness.socket),
          mic: async () => null,
          player: () => null,
        }}
      />,
    );
    await waitFor(() => {
      const sent = harness.socket.sent.map((raw) => JSON.parse(String(raw)));
      expect(sent.some((m) => m.type === "depth_change" && m.level === 2)).toBe(
        true,
      );
      expect(
        sent.some(
          (m) =>
            m.type === "viewport" && m.context_ref?.kind === "district",
        ),
      ).toBe(true);
    });
  });
});

// ── voice utilities (S8) ─────────────────────────────────────────────────────

describe("the voice utilities", () => {
  it("round-trips PCM16 and clamps out-of-range samples", () => {
    const samples = new Float32Array([0, 0.5, -0.5, 1, -1, 1.5, -1.5]);
    const bytes = floatTo16BitPCM(samples);
    const back = pcm16ToFloat32(bytes);
    expect(back[0]).toBeCloseTo(0, 4);
    expect(back[1]).toBeCloseTo(0.5, 2);
    expect(back[2]).toBeCloseTo(-0.5, 2);
    expect(back[3]).toBeCloseTo(1, 4);
    expect(back[4]).toBeCloseTo(-1, 4);
    expect(back[5]).toBeCloseTo(1, 4); // clamped
    expect(back[6]).toBeCloseTo(-1, 4); // clamped
  });

  it("rms is zero for silence and rises with speech", () => {
    expect(rmsLevel(new Float32Array(100))).toBe(0);
    const loud = new Float32Array(100).fill(0.4);
    expect(rmsLevel(loud)).toBeCloseTo(0.4, 4);
  });
});

// ── the shared stream (S5's consolidation) ───────────────────────────────────

describe("the shared estate stream", () => {
  class FakeEventSource {
    static instances: FakeEventSource[] = [];
    closed = false;
    listeners = new Map<string, ((event: MessageEvent<string>) => void)[]>();

    constructor() {
      FakeEventSource.instances.push(this);
    }

    addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void {
      this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
    }

    close(): void {
      this.closed = true;
    }

    emit(type: string, payload: unknown): void {
      for (const listener of this.listeners.get(type) ?? []) {
        listener({ data: JSON.stringify(payload) } as MessageEvent<string>);
      }
    }
  }

  it("one wire serves every subscriber and closes with the last", () => {
    FakeEventSource.instances = [];
    const seenA: StreamEvent[] = [];
    const seenB: StreamEvent[] = [];
    const make = () => new FakeEventSource() as unknown as EventSource;

    const offA = subscribeEstateStream((event) => seenA.push(event), make);
    const offB = subscribeEstateStream((event) => seenB.push(event), make);
    expect(FakeEventSource.instances).toHaveLength(1);

    FakeEventSource.instances[0]?.emit("pulse", { healthy: true });
    expect(seenA).toHaveLength(1);
    expect(seenB).toHaveLength(1);

    offA();
    expect(FakeEventSource.instances[0]?.closed).toBe(false);
    offB();
    expect(FakeEventSource.instances[0]?.closed).toBe(true);
  });
});
