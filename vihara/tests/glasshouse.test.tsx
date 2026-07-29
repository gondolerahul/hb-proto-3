/**
 * GLASS X5 — the room, against fakes.
 *
 * The four rules the surface must not break: the surface desaturates
 * (never the components), the ribbon is the only saturated thing in the
 * twin pane, four grades with `untested` distinct from `unknown`, and a
 * lever prices itself before it is pulled.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/api/genui", () => ({
  emitEcho: vi.fn(async () => undefined),
  fetchEstate: vi.fn(async () => ({
    as_of: "t",
    estate: { pulse: { beat_at: "t", healthy: true } },
    beacons: [],
    districts: [
      {
        process_code: "P03",
        weather: { state: "clear", icon: null, sentence: null },
        traffic: { in_1h: 4, out_1h: 2, parked: 0 },
        treasury: { spent: 0, cap: 0 },
        colleagues: [],
      },
    ],
  })),
}));

import {
  divergences,
  GRADE_LABELS,
  GRADE_SHORT,
  GlasshouseSurface,
  UNTESTED,
  type GlasshouseLoaders,
} from "../src/app/GlasshouseSurface";
import { resetSharedStream } from "../src/estate/sharedStream";

afterEach(() => {
  cleanup();
  resetSharedStream();
  vi.clearAllMocks();
});

const SCENARIO = {
  id: "s1",
  name: "chase at 4 days",
  kind: "policy",
  scope: { objects: [], window_days: 7 },
  status: "ready",
  acknowledged_estimate_usd: 0.42,
};

const RUN = {
  id: "r1",
  grade: "replay",
  grade_means: "Replayed real events that actually happened.",
  method: "replayed 63 signal(s)",
  metrics: { signals_replayed: 63, by_category: { email_dispatch: 5 } },
  cost_usd: 0.41,
  is_baseline: false,
  refusal_reason: null as string | null,
  started_at: "t",
  finished_at: "t",
};

function loaders(overrides: Partial<GlasshouseLoaders> = {}): {
  deps: GlasshouseLoaders;
  ran: string[];
} {
  const ran: string[] = [];
  return {
    ran,
    deps: {
      scenarios: async () => [SCENARIO],
      runs: async () => [RUN],
      estimate: async () => ({
        estimate: { rows: 10, signals: 63, usd: 0.42, method: "a declared rate" },
        budget: {
          admitted: true, parked: false, reason: "within budget",
          spent_today_usd: 0, daily_cap_usd: 5,
        },
      }),
      run: async (id: string) => {
        ran.push(id);
      },
      echo: async () => undefined,
      ...overrides,
    } as GlasshouseLoaders,
  };
}

// ── rule 1 + 2: the plane boundary ──────────────────────────────────────────

describe("the panes", () => {
  it("the SURFACE desaturates the twin pane, not the components", async () => {
    const { deps } = loaders();
    render(<GlasshouseSurface loaders={deps} />);
    await screen.findByLabelText("Twin");
    const twin = document.querySelector("[data-part='pane-twin']");
    const real = document.querySelector("[data-part='pane-real']");
    expect(twin?.classList.contains("vh-desaturated")).toBe(true);
    expect(real?.classList.contains("vh-desaturated")).toBe(false);
    // No component inside carries the class — that is what makes the
    // boundary unforgeable.
    expect(twin?.querySelector(".vh-desaturated")).toBeNull();
  });

  it("the divergence ribbon lives in the twin pane and nowhere else", async () => {
    const { deps } = loaders();
    render(<GlasshouseSurface loaders={deps} />);
    await waitFor(() => {
      expect(document.querySelector("[data-part='divergence']")).toBeTruthy();
    });
    const twin = document.querySelector("[data-part='pane-twin']");
    const real = document.querySelector("[data-part='pane-real']");
    expect(twin?.querySelector("[data-part='divergence']")).toBeTruthy();
    expect(real?.querySelector("[data-part='divergence']")).toBeNull();
  });

  it("no run means no ribbon — nothing has diverged from anything", async () => {
    const { deps } = loaders({ runs: async () => [] });
    render(<GlasshouseSurface loaders={deps} />);
    await screen.findByText(/nothing rehearsed yet/);
    expect(document.querySelector("[data-part='divergence']")).toBeNull();
  });
});

describe("divergences", () => {
  it("is empty without a run and without touched categories", () => {
    const districts = [
      { process_code: "P03", traffic: { in_1h: 1, out_1h: 1 } },
    ];
    expect(divergences(districts, null)).toEqual([]);
    expect(divergences(districts, { by_category: {} })).toEqual([]);
  });
});

// ── rule 3: four grades, and untested ≠ unknown ─────────────────────────────

describe("the honesty grades", () => {
  it("renders four, and untested does not read like unknown", () => {
    expect(Object.keys(GRADE_LABELS).sort()).toEqual(
      ["forecast", "replay", "unknown", "untested"],
    );
    expect(GRADE_SHORT[UNTESTED]).not.toEqual(GRADE_SHORT["unknown"]);
    expect(GRADE_SHORT[UNTESTED]).toMatch(/never/);
    expect(GRADE_SHORT["unknown"]).toMatch(/Tried/);
  });

  it("an empty shelf says never tried, not ungradable", async () => {
    const { deps } = loaders({ runs: async () => [] });
    render(<GlasshouseSurface loaders={deps} />);
    await screen.findByLabelText("Twin");
    await waitFor(() => {
      const empty = document.querySelector("[data-part='shelf-empty']");
      expect(empty?.textContent ?? "").toMatch(/never tried/);
    });
  });

  it("the caveat travels with the number", async () => {
    const { deps } = loaders();
    render(<GlasshouseSurface loaders={deps} />);
    await screen.findByText(/Replayed real events that actually happened/);
  });

  it("a refused run shows why instead of a gap", async () => {
    const { deps } = loaders({
      runs: async () => [
        {
          ...RUN,
          grade: "unknown",
          refusal_reason: "this would take today's spend past the daily budget",
        },
      ],
    });
    render(<GlasshouseSurface loaders={deps} />);
    await screen.findByText(/past the daily budget/);
  });
});

// ── rule 4: the price comes before the pull ─────────────────────────────────

describe("the levers", () => {
  it("prices before running, and the price is shown with its method", async () => {
    const { deps, ran } = loaders();
    render(<GlasshouseSurface loaders={deps} />);
    fireEvent.click(await screen.findByText("what would this cost?"));
    await waitFor(() => {
      const shown = document.querySelector("[data-part='estimate']");
      expect(shown?.textContent ?? "").toMatch(/about \$0\.42/);
      expect(shown?.textContent ?? "").toMatch(/a declared rate/);
    });
    expect(ran).toEqual([]);

    fireEvent.click(screen.getByText("rehearse"));
    await waitFor(() => {
      expect(ran).toEqual(["s1"]);
    });
  });

  it("an unpriced scenario cannot be rehearsed", async () => {
    const { deps } = loaders({
      scenarios: async () => [
        { ...SCENARIO, acknowledged_estimate_usd: null, status: "draft" },
      ],
    });
    render(<GlasshouseSurface loaders={deps} />);
    const button = await screen.findByText("rehearse");
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("a parked budget blocks the rehearsal and says it resumes tomorrow", async () => {
    const { deps, ran } = loaders({
      estimate: async () => ({
        estimate: { rows: 10, signals: 63, usd: 9.0, method: "declared" },
        budget: {
          admitted: false, parked: true,
          reason: "past the $5.00 daily budget. The scenario is kept and resumes tomorrow",
          spent_today_usd: 4.9, daily_cap_usd: 5,
        },
      }),
    });
    render(<GlasshouseSurface loaders={deps} />);
    fireEvent.click(await screen.findByText("what would this cost?"));
    await waitFor(() => {
      const shown = document.querySelector("[data-part='estimate']");
      expect(shown?.textContent ?? "").toMatch(/resumes tomorrow/);
    });
    const button = screen.getByText("rehearse") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(ran).toEqual([]);
  });
});
