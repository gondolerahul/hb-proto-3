import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EstateSnapshot } from "../src/api/estate";
import type { MorningStory } from "../src/api/line";
import type { LiveEstate } from "../src/estate/useLiveEstate";

const liveState = vi.hoisted(() => ({ current: null as unknown as LiveEstate }));
const morning = vi.hoisted(() => ({
  current: null as unknown as Promise<MorningStory>,
}));

vi.mock("../src/estate/useLiveEstate", () => ({
  useLiveEstate: () => liveState.current,
}));
vi.mock("../src/api/identity", () => ({
  fetchCompanyName: () => Promise.resolve("Northwind Textiles"),
}));
vi.mock("../src/api/line", () => ({
  fetchMorningStory: () => morning.current,
}));

import { StandupSurface } from "../src/surfaces/StandupSurface";
import { StillSurface } from "../src/surfaces/StillSurface";
import { TerraceSurface } from "../src/surfaces/TerraceSurface";

afterEach(cleanup);

function snapshot(over: Partial<EstateSnapshot> = {}): EstateSnapshot {
  return {
    estate: {
      loop_id: "loop-1",
      pulse: { beat_at: "2026-07-31T09:40:00", healthy: true },
      local_time: "2026-07-31T21:41:00+05:30",
      phase: "night",
      standing: "active",
    },
    quarters: [{ code: "finance", name: "Finance", districts: ["P08"] }],
    districts: [
      {
        process_code: "P08",
        name: "Collections",
        quarter: "finance",
        colleagues: [
          { entity_id: "a", name: "Meera", autonomy: "A2", hand_raised: true, state: "running" },
        ],
        kpi: {
          plinth: [
            { kpi_key: "dso", display_name: "Days sales outstanding", value: 38, measurable: true, unit: "days" },
            { kpi_key: "gm", display_name: "Gross margin", value: null, measurable: false, unit: "percent" },
          ],
        },
        treasury: null,
        weather: { state: "storm", icon: "cloud-lightning", sentence: "Collections is stopped." },
        traffic: { in_1h: 42, out_1h: 37, parked: 3 },
      },
    ],
    gatehouses: [
      { gateway_code: "kar-01", channel: "whatsapp", health: "ok", inbound_today: 4, parked: 0, consent: null },
    ],
    bridges: [],
    halls: [],
    monuments: [],
    beacons: [{ approval_id: "ap-1", district: "P08", sla_seconds_left: 600 }],
    glasshouse: { open_scenarios: 0, last_run_at: null },
    gallery: { versions: 0, terminated: 0 },
    as_of: "2026-07-31T16:11:00",
    ...over,
  };
}

const ready = (estate: EstateSnapshot): LiveEstate => ({
  phase: "ready",
  estate,
  wire: { status: "live" },
});

describe("W1 — Still", () => {
  it("scaffolds on a plate and never a spinner", () => {
    liveState.current = { phase: "loading" };
    const { container } = render(<StillSurface onDescend={vi.fn()} />);
    const plate = container.querySelector(".st-scaffold");
    expect(plate?.className).toContain("m-plate");
    expect(container.querySelectorAll(".lc-bar.vh-skeleton").length).toBeGreaterThan(2);
    expect(container.textContent).not.toMatch(/loading/i);
  });

  it("offers a way onward when it fails, because there is no shell", () => {
    liveState.current = { phase: "failed", reason: "504", retry: vi.fn() };
    const { container } = render(<StillSurface onDescend={vi.fn()} />);
    expect(container.textContent).toContain("could not load the estate");
    expect(container.querySelector(".st-descend")).not.toBeNull();
  });

  it("says an empty estate is empty, not broken", () => {
    liveState.current = ready(snapshot({ districts: [], beacons: [] }));
    const { container } = render(<StillSurface onDescend={vi.fn()} />);
    expect(container.textContent).toContain("has not been built yet");
    expect(container.querySelector('[data-state="empty"]')).not.toBeNull();
    expect(container.textContent).not.toContain("0 signals");
  });

  it("prints the estate's own sentence, its own hour, and a real figure", async () => {
    liveState.current = ready(snapshot());
    const { container } = render(<StillSurface onDescend={vi.fn()} />);
    await waitFor(() => expect(container.textContent).toContain("NORTHWIND TEXTILES"));
    expect(container.querySelector("h1")?.textContent).toBe("Collections is stopped.");
    expect(container.textContent).toContain("21:00");
    expect(container.textContent).toContain("NIGHT");
    expect(container.textContent).toContain("Days sales outstanding stands at");
    expect(container.querySelector(".st-figure")?.textContent).toBe("38d");
    expect(container.textContent).toContain("One colleague is waiting for you.");
    expect(container.textContent).toContain("42 signals an hour");
    expect(container.textContent).toContain("1 district");
  });

  it("prints nothing where nothing is measurable, and no zero", () => {
    const estate = snapshot();
    estate.districts[0]!.kpi.plinth = [
      { kpi_key: "gm", display_name: "Gross margin", value: null, measurable: false, unit: "percent" },
    ];
    estate.districts[0]!.traffic.in_1h = 0;
    liveState.current = ready(estate);
    const { container } = render(<StillSurface onDescend={vi.fn()} />);
    expect(container.querySelector(".st-figure")).toBeNull();
    expect(container.textContent).not.toContain("stands at");
    expect(container.textContent).toContain("nothing has come in this hour");
    expect(container.textContent).not.toContain("0 signals");
  });

  it("keeps zero gold at rest, and marks a dropped stream", () => {
    const calm = snapshot({ beacons: [] });
    calm.districts[0]!.colleagues[0]!.hand_raised = false;
    liveState.current = ready(calm);
    const { container } = render(<StillSurface onDescend={vi.fn()} />);
    expect(container.querySelector(".st-line-gold")).toBeNull();
    expect(container.textContent).toContain("Nothing needs you.");
    expect(container.querySelector(".st-stale-text")).toBeNull();

    cleanup();
    liveState.current = {
      phase: "ready",
      estate: calm,
      wire: { status: "stale", reason: "closed", retryInSeconds: 4 },
    };
    const stale = render(<StillSurface onDescend={vi.fn()} />).container;
    expect(stale.textContent).toContain("stopped sending updates");
    expect(stale.textContent).toContain("4s");
  });
});

describe("W1 — Terrace", () => {
  it("draws the estate's own districts, gatehouses and beacons", () => {
    liveState.current = ready(snapshot());
    const { container } = render(
      <TerraceSurface onOpenDistrict={vi.fn()} onEcho={vi.fn()} />,
    );
    expect(container.textContent).toContain("THE ESTATE · STORM · NIGHT");
    expect(container.textContent).toContain("Collections is stopped.");
    expect(container.textContent).toContain("1 waiting on you");
    expect(container.textContent).toContain("P08 · 38d");
    expect(container.textContent).toContain("WhatsApp");
    expect(container.textContent).toContain("needs you");
    // The four weather words the backend can emit, and no others.
    expect(container.textContent).not.toMatch(/\bFOG\b|\bBUSY\b|\bFROST\b/);
  });

  it("says an empty estate is empty", () => {
    liveState.current = ready(snapshot({ districts: [], beacons: [] }));
    const { container } = render(
      <TerraceSurface onOpenDistrict={vi.fn()} onEcho={vi.fn()} />,
    );
    expect(container.textContent).toContain("no estate to draw yet");
    expect(container.querySelector("svg.tv-svg")).toBeNull();
  });

  it("echoes the district it actually opened", () => {
    liveState.current = ready(snapshot());
    const onOpenDistrict = vi.fn();
    const onEcho = vi.fn();
    render(<TerraceSurface onOpenDistrict={onOpenDistrict} onEcho={onEcho} />);
    screen.getByRole("button", { name: "Collections" }).click();
    expect(onOpenDistrict).toHaveBeenCalledWith("P08");
    expect(onEcho).toHaveBeenCalledWith("opened Collections");
  });
});

const story = (over: Partial<MorningStory> = {}): MorningStory => ({
  story_date: "2026-07-31",
  generated_at: null,
  degraded_reason: "not_generated",
  cards: [
    {
      entity_id: "a1",
      name: "Meera",
      district: "P08",
      sentences: ["Finished 34 pieces of work since yesterday.", "Is waiting on you."],
      waiting: true,
      audio: null,
    },
    {
      entity_id: "a2",
      name: "Devika",
      district: "P03",
      sentences: ["A quiet day — nothing to report."],
      waiting: false,
      audio: null,
    },
  ],
  ...over,
});

describe("W1 — Standup", () => {
  it("scaffolds on plates", () => {
    morning.current = new Promise(() => undefined);
    const { container } = render(<StandupSurface onEcho={vi.fn()} />);
    expect(container.querySelector(".su-scaffold-head")?.className).toContain("m-plate");
    expect(container.textContent).not.toMatch(/loading/i);
  });

  it("tells the Line's story, joined, with the ask left where it is", async () => {
    morning.current = Promise.resolve(story());
    const { container } = render(<StandupSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.textContent).toContain("Meera"));
    expect(container.querySelector(".su-line")?.textContent).toBe(
      "Finished 34 pieces of work since yesterday. Is waiting on you.",
    );
    expect(container.textContent).toContain("P08 · a1");
    expect(container.textContent).toContain("WAITING ON YOU");
    expect(container.textContent).toContain("The ask is in the tray");
    expect(container.textContent).toContain("1 waiting on you");
    expect(container.textContent).toContain("2 colleagues");
    expect(container.textContent).toContain("composed just now");
    expect(container.textContent).toContain("1 of 2");
  });

  it("says which morning it is when the job did run", async () => {
    morning.current = Promise.resolve(
      story({ generated_at: "2026-07-31T02:25:00", degraded_reason: null }),
    );
    const { container } = render(<StandupSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.textContent).toContain("told at"));
    expect(container.textContent).toContain("the morning’s telling");
  });

  it("says a story with nobody in it is empty, not broken", async () => {
    morning.current = Promise.resolve(story({ cards: [] }));
    const { container } = render(<StandupSurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.textContent).toContain("Nobody has a line this morning."),
    );
    expect(container.querySelector('[data-state="empty"]')).not.toBeNull();
    expect(container.textContent).toContain("This morning’s standup");
    expect(container.textContent).not.toContain("0 colleagues");
  });

  it("fails legibly, and offers a retry", async () => {
    morning.current = Promise.reject(new Error("502"));
    const { container } = render(<StandupSurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.textContent).toContain("could not load this morning’s standup"),
    );
    expect(container.querySelector('[data-state="failed"]')).not.toBeNull();
  });
});
