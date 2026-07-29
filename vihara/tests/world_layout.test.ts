/**
 * WORLD W3 — the territory layout's guarantees, and W2's tier classifier.
 * The layout property that carries L4 ("one geography") is determinism:
 * the same estate lays out identically every visit, whatever order the
 * payload arrived in.
 */
import { describe, expect, it } from "vitest";

import { classifyTier, type ProbedCapabilities } from "../src/app/tier";
import {
  placeTerritory,
  type EstateSnapshot,
} from "../src/renderers/world/layout";

function estate(overrides: Partial<EstateSnapshot> = {}): EstateSnapshot {
  return {
    estate: { phase: "day", pulse: { healthy: true } },
    districts: [
      district("P03", "acquisition"),
      district("P06", "care"),
      district("P08", "finance"),
      district("P10", "finance"),
    ],
    gatehouses: [
      { gateway_code: "KAR-02", channel: "email", inbound_today: 12, parked: 0 },
      { gateway_code: "KAR-03", channel: "whatsapp", inbound_today: 40, parked: 2 },
    ],
    beacons: [],
    ...overrides,
  };
}

function district(code: string, quarter: string) {
  return {
    process_code: code,
    name: code,
    quarter,
    colleagues: [],
    weather: { state: "clear", icon: null, sentence: null },
    traffic: { in_1h: 4, out_1h: 2, parked: 0 },
    treasury: null,
  };
}

describe("the territory layout", () => {
  it("is deterministic whatever order the payload arrived in", () => {
    const forward = placeTerritory(estate());
    const shuffled = estate();
    shuffled.districts.reverse();
    shuffled.gatehouses.reverse();
    expect(placeTerritory(shuffled)).toEqual(forward);
  });

  it("gives every district a home and no two share one", () => {
    const layout = placeTerritory(estate());
    const positions = layout.districts.map((d) => d.position.join(","));
    expect(new Set(positions).size).toBe(4);
  });

  it("keeps a quarter's districts inside its own sector", () => {
    const layout = placeTerritory(estate());
    const finance = layout.districts.filter((d) => d.quarter === "finance");
    expect(finance).toHaveLength(2);
    // Same quarter → neighbours on the ring: closer to each other than to
    // any district of another quarter.
    const [p08, p10] = finance;
    const gap = distance(p08!.position, p10!.position);
    for (const other of layout.districts.filter((d) => d.quarter !== "finance")) {
      expect(gap).toBeLessThan(distance(p08!.position, other.position));
    }
  });

  it("roads connect gatehouses to the hub and the hub to every district", () => {
    const layout = placeTerritory(estate());
    expect(layout.roads).toHaveLength(2 + 4);
    for (const road of layout.roads.slice(2)) {
      expect(road.from).toEqual([0, 0]);
    }
    const intensities = layout.roads.map((r) => r.intensity);
    expect(Math.max(...intensities)).toBeLessThanOrEqual(1);
  });

  it("a beacon stands at its district; an unhomed beacon at the hub", () => {
    const layout = placeTerritory(estate({
      beacons: [
        { approval_id: "a1", district: "P06", sla_seconds_left: 100 },
        { approval_id: "a2", district: null, sla_seconds_left: null },
      ],
    }));
    const p06 = layout.districts.find((d) => d.process_code === "P06");
    expect(layout.beacons[0]?.position).toEqual(p06?.position);
    expect(layout.beacons[1]?.position).toEqual([0, 0]);
  });

  it("day–night is luminance, not palette (charter decision 3)", () => {
    const day = placeTerritory(estate()).lighting;
    const night = placeTerritory(
      estate({ estate: { phase: "night", pulse: { healthy: true } } }),
    ).lighting;
    expect(day.keyColor).toBe(night.keyColor); // one colour, two intensities
    expect(night.keyIntensity).toBeLessThan(day.keyIntensity);
    expect(night.lampIntensity).toBeGreaterThan(day.lampIntensity);
  });

  it("an empty estate still lays out (lighting present, nothing placed)", () => {
    const layout = placeTerritory(
      estate({ districts: [], gatehouses: [], beacons: [] }),
    );
    expect(layout.districts).toEqual([]);
    expect(layout.lighting.phase).toBe("day");
  });
});

function distance(a: readonly [number, number], b: readonly [number, number]) {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

// ── the tier classifier (W2) ─────────────────────────────────────────────────

function caps(overrides: Partial<ProbedCapabilities> = {}): ProbedCapabilities {
  return {
    webgl2: true,
    deviceMemoryGb: 16,
    cores: 12,
    saveData: false,
    reducedMotion: false,
    reducedTransparency: false,
    ...overrides,
  };
}

describe("the tier classifier (probed, never sniffed)", () => {
  it("a capable laptop is tier A", () => {
    expect(classifyTier(caps())).toBe("A");
  });

  it("a mid-range phone is tier B", () => {
    expect(classifyTier(caps({ deviceMemoryGb: 4, cores: 8 }))).toBe("B");
  });

  it("no WebGL2, low memory or saveData is tier C", () => {
    expect(classifyTier(caps({ webgl2: false }))).toBe("C");
    expect(classifyTier(caps({ deviceMemoryGb: 2 }))).toBe("C");
    expect(classifyTier(caps({ saveData: true }))).toBe("C");
  });

  it("reduced motion or transparency is tier D — a designed path, not a penalty", () => {
    expect(classifyTier(caps({ reducedMotion: true }))).toBe("D");
    expect(classifyTier(caps({ reducedTransparency: true }))).toBe("D");
  });

  it("an unknown deviceMemory falls back to cores rather than punishing", () => {
    expect(classifyTier(caps({ deviceMemoryGb: null, cores: 10 }))).toBe("A");
    expect(classifyTier(caps({ deviceMemoryGb: null, cores: 4 }))).toBe("B");
  });
});
