/**
 * LINE L5–L9 — the pocket, against fakes.
 *
 * What these pin: the Morning Story tells a degraded morning honestly and
 * swiping echoes; the Pocket Desk keeps vitals on top and writes pins to
 * the surface.* namespace; the Thread reuses the steward channel (one
 * session across devices) and the certified path is TraySurface itself,
 * never a pocket copy; and the push client computes the honest iOS
 * answer before the user hunts for a missing prompt.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/api/genui", () => ({
  emitEcho: vi.fn(async () => undefined),
  fetchEstate: vi.fn(async () => ({
    as_of: "t",
    estate: { pulse: { beat_at: "t", healthy: true } },
    beacons: [{ approval_id: "a1", district: "P03", sla_seconds_left: 60 }],
    districts: [
      {
        process_code: "P03",
        weather: { state: "clear", icon: null, sentence: "Clear and busy." },
        traffic: { in_1h: 4, out_1h: 2, parked: 1 },
        treasury: { spent: 0, cap: 0 },
        colleagues: [],
      },
      {
        process_code: "P06",
        weather: { state: "clear", icon: null, sentence: null },
        traffic: { in_1h: 0, out_1h: 0, parked: 0 },
        treasury: { spent: 0, cap: 0 },
        colleagues: [],
      },
    ],
  })),
}));

vi.mock("../src/api/trays", () => ({
  fetchTrayList: vi.fn(async () => []),
  respondToApproval: vi.fn(async () => undefined),
}));

import { emitEcho } from "../src/api/genui";
import { MorningStorySurface } from "../src/line/MorningStorySurface";
import { PocketDesk } from "../src/line/PocketDesk";
import { ThreadSurface } from "../src/line/ThreadSurface";
import { vapidKeyBytes } from "../src/line/push";
import { connectChannel, type SocketLike } from "../src/steward/channel";
import { resetSharedStream } from "../src/estate/sharedStream";

afterEach(() => {
  cleanup();
  resetSharedStream();
  vi.clearAllMocks();
});

const STORY = {
  story_date: "2026-07-29",
  generated_at: "2026-07-29T02:25:00",
  degraded_reason: null as string | null,
  cards: [
    {
      entity_id: "e1", name: "Meera", district: "P03",
      sentences: ["Is waiting on you."], waiting: true,
      audio: { mime: "audio/wav", data_b64: "UklGRg==" },
    },
    {
      entity_id: "e2", name: "Ravi", district: "P06",
      sentences: ["A quiet day — nothing to report."], waiting: false,
      audio: null,
    },
  ],
};

describe("the Morning Story", () => {
  it("tells the first card with her voice and swipes with an echo", async () => {
    const echoes: unknown[] = [];
    render(
      <MorningStorySurface
        loaders={{
          story: async () => STORY,
          echo: async (echo) => {
            echoes.push(echo);
          },
        }}
      />,
    );
    await screen.findByText("Meera");
    expect(screen.getByText("Is waiting on you.")).toBeTruthy();
    expect(document.querySelector("[data-part='card-audio']")).toBeTruthy();

    fireEvent.click(screen.getByText("next →"));
    await screen.findByText("Ravi");
    // Ravi's card is text-only — no player, no placeholder.
    expect(document.querySelector("[data-part='card-audio']")).toBeNull();
    expect(echoes).toHaveLength(1);
  });

  it("a degraded morning says why, it does not just go quiet", async () => {
    render(
      <MorningStorySurface
        loaders={{
          story: async () => ({ ...STORY, degraded_reason: "wallet" }),
          echo: async () => undefined,
        }}
      />,
    );
    await screen.findByText(/wallet could not cover her voice/);
  });
});

describe("the Pocket Desk", () => {
  const loaders = (pins: string[] = []) => {
    const writes: unknown[] = [];
    return {
      writes,
      deps: {
        preferences: async () => ({
          "surface.line_pins": { value: pins, learned: false },
        }),
        write: async (key: string, value: unknown) => {
          writes.push([key, value]);
          return undefined as never;
        },
        echo: emitEcho,
      },
    };
  };

  it("vitals stay on top and a pin writes to surface.line_pins", async () => {
    const { writes, deps } = loaders();
    render(<PocketDesk loaders={deps} />);
    await screen.findByText("1 decision waiting");
    expect(screen.getByText("all well")).toBeTruthy();

    const pinButtons = await screen.findAllByText("pin");
    fireEvent.click(pinButtons[0] as HTMLElement);
    await waitFor(() => {
      expect(writes).toEqual([["surface.line_pins", ["P03"]]]);
    });
  });

  it("with pins set, only pinned districts show — vitals regardless", async () => {
    const { deps } = loaders(["P06"]);
    render(<PocketDesk loaders={deps} />);
    await screen.findByText("P06");
    expect(screen.queryByText("Clear and busy.")).toBeNull();
    expect(screen.getByText("1 decision waiting")).toBeTruthy();
  });
});

class FakeSocket implements SocketLike {
  sent: unknown[] = [];
  listeners = new Map<string, ((event: unknown) => void)[]>();
  send(data: string | ArrayBuffer): void {
    this.sent.push(data);
  }
  close(): void {
    this.fire("close", {});
  }
  addEventListener(type: string, listener: (event: unknown) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  fire(type: string, event: unknown): void {
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
  emit(payload: unknown): void {
    this.fire("message", { data: JSON.stringify(payload) });
  }
}

describe("the Thread", () => {
  it("history, live narration and the certified section share one surface", async () => {
    const socket = new FakeSocket();
    render(
      <ThreadSurface
        deps={{
          history: async () => [
            { role: "owner", content: "pause care", at: "t1" },
            { role: "pragya", content: "Paused.", at: "t2" },
          ],
          connect: (handlers) => connectChannel(handlers, () => socket),
        }}
      />,
    );
    await screen.findByText("pause care");
    expect(screen.getByText("Paused.")).toBeTruthy();

    socket.fire("open", {});
    socket.emit({ type: "narrate", text: "Ravi finished the quote.", anchors: [] });
    await screen.findByText("Ravi finished the quote.");

    // The certified section is TraySurface itself (empty list here).
    expect(document.querySelector("[data-part='thread-trays']")).toBeTruthy();

    const input = screen.getByLabelText("tell Pragya");
    fireEvent.change(input, { target: { value: "thanks" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);
    const utterances = socket.sent
      .map((raw) => JSON.parse(String(raw)))
      .filter((message) => message.type === "utterance");
    expect(utterances).toEqual([{ type: "utterance", text: "thanks" }]);
  });
});

describe("the push client", () => {
  it("decodes a base64url VAPID key to bytes", () => {
    const bytes = vapidKeyBytes("AQAB");
    expect([...bytes]).toEqual([1, 0, 1]);
  });
});
