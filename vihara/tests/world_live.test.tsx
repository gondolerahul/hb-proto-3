/**
 * WORLD W5 + W6 — the stream reducer (each event type alone, idempotent
 * beacons for the at-least-once wire) and the seal (deterministic forever,
 * quiet gold, never a photograph).
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Seal, sealSpec } from "../src/components/portraits/Seal";
import { applyStreamEvent, type StreamEvent } from "../src/estate/live";
import type { EstateSnapshot } from "../src/renderers/world/layout";

afterEach(cleanup);

function estate(): EstateSnapshot {
  return {
    estate: { phase: "day", pulse: { healthy: true } },
    districts: [
      {
        process_code: "P06",
        name: "Care",
        quarter: "care",
        colleagues: [
          {
            entity_id: "e1",
            name: "Meera",
            autonomy: "A2",
            hand_raised: false,
            state: "idle",
          },
        ],
        weather: { state: "clear", icon: null, sentence: null },
        traffic: { in_1h: 0, out_1h: 0, parked: 0 },
        treasury: { spent: 1, cap: 10 },
      },
    ],
    gatehouses: [],
    beacons: [],
  };
}

function event(type: StreamEvent["type"], payload: Record<string, unknown>) {
  return { type, payload };
}

describe("the stream reducer", () => {
  it("a raised beacon lands once, however many times the wire replays it", () => {
    let state = estate();
    const raised = event("beacon.raised", {
      approval_id: "a1",
      district: "P06",
      sla_seconds_left: 100,
    });
    state = applyStreamEvent(state, raised);
    state = applyStreamEvent(state, raised); // snapshot-on-connect replay
    expect(state.beacons).toHaveLength(1);
    state = applyStreamEvent(state, event("beacon.cleared", { approval_id: "a1" }));
    expect(state.beacons).toHaveLength(0);
  });

  it("traffic, weather and the envelope land on their district only", () => {
    let state = estate();
    state = applyStreamEvent(
      state,
      event("traffic", { district: "P06", in_1h: 9, out_1h: 3, parked: 1 }),
    );
    state = applyStreamEvent(
      state,
      event("weather.changed", {
        district: "P06",
        state: "moonlit",
        icon: "moon",
        sentence: "Care is hibernating; nothing is scheduled.",
      }),
    );
    state = applyStreamEvent(
      state,
      event("envelope.burn", { district: "P06", spent: 8, cap: 10 }),
    );
    const p06 = state.districts[0]!;
    expect(p06.traffic.in_1h).toBe(9);
    expect(p06.weather.state).toBe("moonlit");
    expect(p06.treasury?.spent).toBe(8);
  });

  it("a colleague's run state and hand travel together", () => {
    const state = applyStreamEvent(
      estate(),
      event("run.state", {
        district: "P06",
        entity_id: "e1",
        state: "running",
        hand_raised: true,
      }),
    );
    const colleague = state.districts[0]!.colleagues[0]!;
    expect(colleague.state).toBe("running");
    expect(colleague.hand_raised).toBe(true);
  });

  it("an event for an unknown district changes nothing — no invented sites", () => {
    const before = estate();
    const after = applyStreamEvent(
      before,
      event("traffic", { district: "P99", in_1h: 5, out_1h: 0, parked: 0 }),
    );
    expect(after).toEqual(before);
  });

  it("the pulse updates the estate's heart", () => {
    const state = applyStreamEvent(estate(), event("pulse", { healthy: false }));
    expect(state.estate.pulse.healthy).toBe(false);
  });
});

describe("the seal (portrait direction C)", () => {
  it("the same id yields the same seal, forever", () => {
    expect(sealSpec("entity-123")).toEqual(sealSpec("entity-123"));
  });

  it("different ids yield different seals", () => {
    expect(sealSpec("entity-123")).not.toEqual(sealSpec("entity-456"));
  });

  it("renders as an SVG dot field with an accessible name", () => {
    const { container } = render(<Seal id="entity-123" label="Meera's seal" />);
    const svg = container.querySelector('svg[data-part="seal"]');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("aria-label")).toBe("Meera's seal");
    expect(container.querySelectorAll("circle").length).toBeGreaterThan(10);
  });

  it("wears quiet gold-700 — never the gradient, never gold-glowing at rest", () => {
    const { container } = render(<Seal id="entity-123" />);
    for (const circle of container.querySelectorAll("circle")) {
      expect(circle.getAttribute("fill")).toContain("--gold-700");
    }
  });
});
