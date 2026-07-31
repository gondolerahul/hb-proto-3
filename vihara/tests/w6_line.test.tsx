import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EstateSnapshot, PlinthKpi } from "../src/api/estate";
import type { KpiHistory } from "../src/api/gallery";
import type { MorningStory } from "../src/api/line";
import type { PragyaHistoryTurn } from "../src/api/pragya";
import type { Tray } from "../src/api/trays";
import type { LiveEstate } from "../src/estate/useLiveEstate";

/**
 * R-4 part W · task W6 — the Private Line on live data.
 *
 * `tests/line.test.tsx` holds the C4 invariant (the Thread's certified section
 * **is** `src/surfaces/TraySurface`, mounted) and the §7.1 absence rules that
 * survived the wiring. This file holds what only became reachable once the three
 * surfaces came off `src/fixtures/`: a pending state, an empty one, a failed
 * one, and the handful of derivations that could not have been wrong while the
 * data was a constant somebody had typed.
 *
 * Four things it is built to catch, and each of them has shipped somewhere in
 * this app before:
 *
 *  1. **A spinner, or a skeleton nobody can see.** D7 §3.1 gives the Glasshouse
 *     the only visible loading state in the product; the other seventeen paint
 *     their own structure. `vh-skeleton`'s ground is a ~6/255 delta on the raw
 *     canvas, so a bar drawn *outside* a plate is a scaffold that renders as a
 *     blank screen — which is the same bug as having no scaffold at all, and
 *     invisible to any test that only counts bars.
 *  2. **A fabricated count.** `1 of 0` was on the Morning Story's rail, and
 *     `Math.max()` of nothing is `-Infinity` and has shipped in this app once.
 *     Every reduce on the Desk's band is over a collection that can be empty.
 *  3. **A null read as a falsy.** The counted zero and the absent reading are in
 *     `line.test.tsx`; what is here is the other half — that the *reasons* are
 *     the platform's own and that a failed write is not announced as a success.
 *  4. **A renderer inferred rather than passed.** C5 says the echo bus must be
 *     able to tell a phone tap from an operator click. The Line has one job in
 *     that: pass `renderer="C"` to the component it mounts.
 */

/* ------------------------------------------------------------- the six wires */

const wire = vi.hoisted(() => ({
  morning: (() => Promise.reject(new Error("unset"))) as () => Promise<unknown>,
  history: (() => Promise.reject(new Error("unset"))) as () => Promise<unknown>,
  trays: (() => Promise.resolve([])) as () => Promise<unknown>,
  live: { phase: "loading" } as unknown,
  preferences: (() => Promise.resolve({})) as () => Promise<unknown>,
  kpi: (() => Promise.resolve({ from: "", to: "", series: [] })) as () => Promise<unknown>,
  company: (() => Promise.resolve(null)) as () => Promise<string | null>,
  writes: [] as unknown[],
  writeFails: false,
  echoes: [] as { params?: Record<string, unknown> }[],
}));

vi.mock("../src/api/line", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchMorningStory: () => wire.morning(),
}));
vi.mock("../src/api/pragya", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchThreadHistory: () => wire.history(),
}));
vi.mock("../src/api/trays", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchTrayList: () => wire.trays(),
  respondToApproval: () => Promise.resolve(),
}));
vi.mock("../src/estate/useLiveEstate", () => ({
  useLiveEstate: () => wire.live,
}));
vi.mock("../src/api/identity", () => ({
  fetchCompanyName: () => wire.company(),
}));
vi.mock("../src/api/study", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchPreferences: () => wire.preferences(),
  writePreference: (key: string, value: unknown) => {
    if (wire.writeFails) return Promise.reject(new Error("the store refused"));
    wire.writes.push({ key, value });
    return Promise.resolve();
  },
}));
vi.mock("../src/api/gallery", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchKpiHistory: () => wire.kpi(),
}));
/** The echo bus, captured. This is how C5 is checked rather than assumed. */
vi.mock("../src/api/genui", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  emitEcho: (echo: { action_ref?: { params?: Record<string, unknown> } }) => {
    wire.echoes.push({ params: echo.action_ref?.params });
    return Promise.resolve();
  },
}));

import { LineApp } from "../src/line/LineApp";
import { MorningStorySurface, UNVOICED } from "../src/line/MorningStorySurface";
import { PocketDesk } from "../src/line/PocketDesk";
import { ThreadSurface } from "../src/line/ThreadSurface";
import { TraySurface } from "../src/surfaces/TraySurface";

/* -------------------------------------------------------------- the payloads */

/** A read that never answers — the pending state, held open. */
const NEVER = (): Promise<never> => new Promise(() => undefined);

function morning(over: Partial<MorningStory> = {}): MorningStory {
  return {
    story_date: "2026-07-30",
    generated_at: "2026-07-30T02:25:00",
    degraded_reason: null,
    cards: [
      {
        entity_id: "AGT-046",
        name: "Meera",
        district: "P08",
        sentences: ["Finished 33 pieces of work since yesterday.", "Is waiting on you."],
        waiting: true,
        audio: { mime: "audio/wav", data_b64: "UklGRiQAAABXQVZF" },
      },
    ],
    ...over,
  };
}

function turn(over: Partial<PragyaHistoryTurn> = {}): PragyaHistoryTurn {
  return {
    role: "pragya",
    content: "Farhan caught a duplicate against Bhagwati Mills before it reached the ledger.",
    at: "2026-07-30T09:20:00",
    ...over,
  };
}

function tray(over: Partial<Tray> = {}): Tray {
  return {
    tray_id: "TR-1",
    approval_id: "1f0e6a52-33c4-4c0a-9b71-8e0a5d6c1122",
    checkpoint_key: "before_outbound_payout_above_band",
    what_happened: { sentence: "The band was reached.", object: null },
    recommendation: null,
    paths: [
      { key: "approve", label: "Release it", consequence: "It goes out.", cost: null },
      { key: "decline", label: "Hold it", consequence: "Nothing moves.", cost: null },
    ],
    certified: {
      component: "certified.payment@1",
      tier: "T2",
      props: {
        approval_id: "1f0e6a52-33c4-4c0a-9b71-8e0a5d6c1122",
        summary: "Release the payment to Sundar Textiles",
        amount: 184000,
        currency: null,
        tier: "T2",
      },
      manifest_hash: "sha256:8f2c1a440b7e4d519a632c8e5f0a7b1988f0c1de2b4a7690",
    },
    sla: { seconds_left: 2040, on_timeout: "AUTO_DENY" },
    prepared_by: { entity_id: "AGT-046", name: "Meera" },
    ...over,
  };
}

const DSO: PlinthKpi = {
  kpi_key: "kpi.dso",
  display_name: "Days sales outstanding",
  value: 38,
  measurable: true,
  unit: "days",
};

function estate(over: Partial<EstateSnapshot> = {}): EstateSnapshot {
  return {
    estate: {
      loop_id: "loop-1",
      pulse: { beat_at: "2026-07-30T21:00:00", healthy: true },
      local_time: "2026-07-30T21:00:00+05:30",
      phase: "night",
      standing: "active",
    },
    quarters: [{ code: "finance", name: "Finance", districts: ["P08"] }],
    districts: [
      {
        process_code: "P08",
        name: "Collections",
        quarter: "finance",
        colleagues: [],
        kpi: { plinth: [DSO] },
        treasury: null,
        weather: { state: "clear", icon: null, sentence: null },
        traffic: { in_1h: 0, out_1h: 0, parked: 0 },
      },
    ],
    gatehouses: [],
    bridges: [],
    halls: [],
    monuments: [],
    beacons: [],
    glasshouse: { open_scenarios: 0, last_run_at: null },
    gallery: { versions: 0, terminated: 0 },
    as_of: "2026-07-30T21:00:00",
    ...over,
  };
}

function ready(over: Partial<EstateSnapshot> = {}): LiveEstate {
  return { phase: "ready", estate: estate(over), wire: { status: "live" } };
}

function series(points: { on: string; value: number | null }[]): KpiHistory {
  return {
    from: "2026-07-25",
    to: "2026-07-30",
    series: [
      {
        key: DSO.kpi_key,
        display_name: DSO.display_name,
        unit: "days",
        first_measurable_on: points[0]?.on ?? null,
        measurable_days: points.filter((p) => p.value !== null).length,
        points: points.map((p) => ({
          captured_on: p.on,
          value: p.value,
          measurable: p.value !== null,
          missing: [],
          baseline_value: null,
          sample_size: null,
        })),
      },
    ],
  };
}

/* ---------------------------------------------------------------- the checks */

/**
 * Every skeleton bar stands on a material, and there is no spinner anywhere.
 *
 * The material check is the point. A `.lc-bar` is `vh-skeleton`, whose ground is
 * a ~6/255 delta on the raw canvas — on the page background it draws nothing,
 * so a scaffold made of bars that are not on plates is a blank screen with a
 * passing test in front of it.
 */
function scaffoldIsHonest(container: HTMLElement, within = ""): void {
  /* `within` scopes the material check to the surface's *own* scaffold. On the
     Thread the mounted Tray draws one too, and that one belongs to
     `src/surfaces/` — holding this file's rule over somebody else's file would
     make a task that does not own it responsible for fixing it. */
  const root = within === "" ? container : container.querySelector(within);
  expect(root, `nothing matched "${within}"`).not.toBeNull();

  expect(
    root!.querySelector('[data-lifecycle="scaffold"]'),
    "no scaffold at all — D7 §3.1 puts the layout on screen before the data",
  ).not.toBeNull();

  const bars = [...root!.querySelectorAll(".lc-bar")];
  expect(bars.length, "a scaffold with nothing in it").toBeGreaterThan(0);
  for (const bar of bars) {
    expect(
      bar.closest(".m-plate, .m-well, .m-glass"),
      "a skeleton bar drawn on the raw canvas is a skeleton nobody can see",
    ).not.toBeNull();
  }

  // The one live sentence that speaks for all of them (§6, and Scaffold's own
  // rule): a screen reader hearing "blank" nineteen times has been told less
  // than nothing.
  expect(root!.querySelector('[role="status"]')?.textContent).toMatch(/arriving/);

  // And no spinner, by any of the names one arrives under.
  expect(container.querySelector(".spinner, .loader, [data-spinner]")).toBeNull();
  expect(container.textContent ?? "").not.toMatch(/loading|please wait/i);
}

/**
 * Wait for the surface to hydrate, and *then* read it.
 *
 * Settled on the scaffold being GONE rather than on a content class appearing —
 * the lesson `tests/line.test.tsx` had to learn one file over. A scaffold draws
 * the surface's own structure, so it uses the surface's own classes: the Desk's
 * ghost cards are `.pd-card` on `.m-plate`, and a `waitFor` on `.pd-card` is
 * satisfied by the very state it means to skip — then hands back a node React
 * is about to throw away, whose `textContent` never changes again.
 */
async function settled(container: HTMLElement): Promise<void> {
  await waitFor(() =>
    expect(container.querySelector('[data-lifecycle="scaffold"]')).toBeNull(),
  );
}

/** jsdom has no `matchMedia`, and `Background` probes it on mount to decide
 *  whether this device runs the world at all. Absent, the probe throws inside an
 *  effect and takes the frame down — which is a fact about the test environment
 *  and not about the Line. Answering "no" is the tier-C branch the phone takes
 *  anyway. */
beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
  /* And the WebGL probe. jsdom logs a "not implemented" through its virtual
     console for every `getContext` call, which buries a real failure in three
     screens of stack; returning null is the honest tier-C answer this
     environment would give anyway. */
  Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
    writable: true,
    configurable: true,
    value: () => null,
  });

  wire.morning = () => Promise.resolve(morning());
  wire.history = () => Promise.resolve([turn()]);
  wire.trays = () => Promise.resolve([]);
  wire.live = ready();
  wire.preferences = () => Promise.resolve({});
  wire.kpi = () => Promise.resolve({ from: "", to: "", series: [] });
  wire.company = () => Promise.resolve(null);
  wire.writes = [];
  wire.writeFails = false;
  wire.echoes = [];
});

afterEach(cleanup);

/* ═══════════════════════════════════════════════════ the Morning Story ═════ */

describe("the Morning Story on the wire", () => {
  it("paints its own card as a skeleton, on a plate, and never a spinner", () => {
    wire.morning = NEVER;
    const { container } = render(<MorningStorySurface onEcho={vi.fn()} />);
    scaffoldIsHonest(container);
  });

  it("counts nothing when there is nothing — no rail, and no “1 of 0”", async () => {
    wire.morning = () => Promise.resolve(morning({ cards: [] }));
    const { container } = render(<MorningStorySurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.querySelector('[data-state="empty"]')).not.toBeNull(),
    );

    /* The bug this closes: the rail read `{at + 1} of {cards.length}` with `at`
       pinned at 0, so an empty morning printed a count of a deck that was not
       there — beneath two controls that could not move. */
    expect(container.querySelector(".mo-count")).toBeNull();
    expect(container.querySelector(".mo-rail")).toBeNull();
    expect(container.textContent ?? "").not.toMatch(/\bof 0\b/);
    expect(container.textContent ?? "").not.toMatch(/\b0 colleagues\b/);

    // And the empty state is prose that says why (§7.3), not a blank column.
    expect(container.querySelector(".lc-body")?.textContent).toMatch(/one card per colleague/);
  });

  it("tells a failed morning apart from an empty one, in material and in words", async () => {
    wire.morning = () => Promise.reject(new Error("504 from the estate"));
    const { container } = render(<MorningStorySurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.querySelector('[data-state="failed"]')).not.toBeNull(),
    );

    expect(container.querySelector('[data-state="empty"]')).toBeNull();
    // The machine's own words, kept as evidence rather than as the message.
    expect(container.querySelector(".lc-reason")?.textContent).toBe("504 from the estate");
    // The sentence that stops a failed read being read as a quiet morning.
    expect(container.textContent ?? "").toMatch(/not an empty/i);
  });

  it("handles the morning most tenants get: composed on read, and all text", async () => {
    /* `morning.py` composes fresh when the 02:25 job has not written a row, and
       that path sets every card's `audio` to `None` with the reason named. It
       is the *common* case, not an edge, so the surface is checked against it. */
    wire.morning = () =>
      Promise.resolve(
        morning({
          generated_at: null,
          degraded_reason: "not_generated",
          cards: [
            { ...morning().cards[0]!, audio: null },
            { ...morning().cards[0]!, entity_id: "AGT-041", name: "Anjali", audio: null },
          ],
        }),
      );

    const { container } = render(<MorningStorySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelectorAll(".mo-unvoiced")).toHaveLength(2));

    for (const node of container.querySelectorAll(".mo-unvoiced")) {
      expect(node.textContent).toBe(UNVOICED.not_generated);
    }
    // No player at all, and certainly not a disabled one.
    expect(container.querySelectorAll(".mo-listen")).toHaveLength(0);
    expect(container.querySelector(".mo-degraded")?.textContent).toContain(
      "None of the 2 cards are voiced.",
    );
    // A telling that was composed on read does not claim an hour it was told at.
    expect(container.querySelector(".mo-title")?.textContent).toBe(
      "2 colleagues, composed just now",
    );
  });

  it("prints a reason it has no sentence for as itself, never as the nearest of the four", async () => {
    wire.morning = () =>
      Promise.resolve(
        morning({
          degraded_reason: "speaker_quota_exhausted",
          cards: [{ ...morning().cards[0]!, audio: null }],
        }),
      );

    const { container } = render(<MorningStorySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".mo-unvoiced")).not.toBeNull());
    const stated = container.querySelector(".mo-unvoiced")?.textContent ?? "";

    /* Mapping an unknown code onto a neighbour would put a *specific* and wrong
       explanation on the screen, which is worse than the vague true one — and
       the code is the only part of this a reader could check against the row
       that produced it. */
    expect(stated).toContain("speaker_quota_exhausted");
    for (const known of Object.values(UNVOICED)) expect(stated).not.toBe(known);
  });

  it("plays the clip the wire sent, from the wire's own bytes", async () => {
    const { container } = render(<MorningStorySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".mo-listen")).not.toBeNull());

    expect(container.querySelector(".mo-unvoiced")).toBeNull();
    expect(container.querySelector("audio")?.getAttribute("src")).toBe(
      "data:audio/wav;base64,UklGRiQAAABXQVZF",
    );
  });
});

/* ═════════════════════════════════════════════════════ the Pocket Desk ═════ */

describe("the Pocket Desk on the wire", () => {
  it("paints the band and two cards as a skeleton, and never a spinner", () => {
    wire.live = { phase: "loading" };
    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    scaffoldIsHonest(container);
  });

  it("says a failed estate is a failed estate", async () => {
    wire.live = { phase: "failed", reason: "The estate could not be reached.", retry: vi.fn() };
    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.querySelector('[data-state="failed"]')).not.toBeNull(),
    );
    expect(container.querySelector(".pd-still")).toBeNull();
  });

  it("keeps the band when it is the pins that could not be read", async () => {
    /* Two different failures, and collapsing them would be a claim about the
       owner's own settings: "nothing pinned" is a choice, and "we could not
       read what you pinned" is a fault. The estate is fine, so the band stands. */
    wire.preferences = () => Promise.reject(new Error("preferences timed out"));
    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.querySelector('[data-state="failed"]')).not.toBeNull(),
    );

    expect(container.querySelector(".pd-still")?.textContent).toBe("All is well.");
    expect(container.querySelector(".pd-empty")).toBeNull();
    expect(container.querySelector(".lc-reason")?.textContent).toBe("preferences timed out");
  });

  it("never composes a figure out of an empty collection", async () => {
    /* `Math.min()` of nothing is `Infinity` and `Math.max()` of nothing is
       `-Infinity`; one of those has already shipped in this app as a rendered
       figure. With no beacons there is no deadline, so there is no cell. */
    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".pd-strip")).not.toBeNull());

    const labels = [...container.querySelectorAll(".pd-cell dt")].map((d) => d.textContent);
    expect(labels).not.toContain("Soonest decision");
    const strip = container.querySelector(".pd-strip")?.textContent ?? "";
    expect(strip).not.toMatch(/Infinity|NaN/);

    // A counted zero in the band still prints: a quiet hour is a reading.
    expect(labels).toContain("Signals an hour");
    const figures = [...container.querySelectorAll(".pd-cell-figure")].map((f) => f.textContent);
    expect(figures).toContain("0");
  });

  it("draws the deadline cell once the estate has a beacon that carries one", async () => {
    wire.live = ready({
      beacons: [
        { approval_id: "a", district: "P08", sla_seconds_left: null },
        { approval_id: "b", district: "P08", sla_seconds_left: 2040 },
      ],
    });
    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".pd-strip")).not.toBeNull());

    const cells = [...container.querySelectorAll(".pd-cell")];
    const soonest = cells.find((c) => c.querySelector("dt")?.textContent === "Soonest decision");
    // Floored, as the Tray floors it: "1h" with fifty-nine minutes gone is worse
    // than "0h". A null `sla_seconds_left` is skipped, never read as zero.
    expect(soonest?.querySelector(".pd-cell-figure")?.textContent).toBe("34m");
    expect(container.querySelector(".pd-hands-word")?.textContent).toBe("2 waiting on you");
  });

  it("marks a dropped wire rather than going quietly calm", async () => {
    wire.live = {
      phase: "ready",
      estate: estate(),
      wire: { status: "stale", reason: "the stream closed", retryInSeconds: 4 },
    };
    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".pd-stale")).not.toBeNull());
    expect(container.querySelector(".pd-stale")?.textContent).toContain("Trying again in 4s");
  });

  it("stays quiet about the wire while it is merely live", async () => {
    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".pd-strip")).not.toBeNull());
    expect(container.querySelector(".pd-stale")).toBeNull();
  });

  it("says so, in prose, when the estate carries no reading to pin at all", async () => {
    wire.live = ready({
      districts: [
        {
          process_code: "P08",
          name: "Collections",
          quarter: "finance",
          colleagues: [],
          kpi: { plinth: [] },
          treasury: null,
          weather: { state: "clear", icon: null, sentence: null },
          traffic: { in_1h: 3, out_1h: 0, parked: 0 },
        },
      ],
    });
    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.querySelector('[data-state="empty"]')).not.toBeNull(),
    );

    // Distinct from "nothing pinned", which is a choice rather than an absence.
    expect(container.querySelector(".pd-empty")).toBeNull();
    expect(container.querySelector(".pd-shelf")).toBeNull();
    expect(container.querySelector(".pd-still")).not.toBeNull();
  });

  it("writes a pin to the preference store, and echoes only once the store took it", async () => {
    const onEcho = vi.fn();
    const { container } = render(<PocketDesk onEcho={onEcho} />);
    await waitFor(() => expect(container.querySelector(".pd-shelf-row")).not.toBeNull());

    fireEvent.click(container.querySelector(".pd-shelf-row .m-btn") as HTMLElement);
    await waitFor(() => expect(wire.writes).toHaveLength(1));

    expect(wire.writes[0]).toEqual({
      key: "surface.line_pins",
      value: ["kpi.dso"],
    });
    expect(onEcho).toHaveBeenCalledWith(
      "pinned Days sales outstanding to the pocket desk",
    );
    await waitFor(() => expect(container.querySelector(".pd-card")).not.toBeNull());
  });

  it("puts the reading back, and says nothing happened, when the store refuses", async () => {
    /* The fraud part C names: a control that looks kept and is forgotten. A pin
       that echoed and did not persist would be gone the next time this phone was
       opened, with nothing having said so. */
    wire.writeFails = true;
    const onEcho = vi.fn();
    const { container } = render(<PocketDesk onEcho={onEcho} />);
    await waitFor(() => expect(container.querySelector(".pd-shelf-row")).not.toBeNull());

    fireEvent.click(container.querySelector(".pd-shelf-row .m-btn") as HTMLElement);
    await waitFor(() => expect(container.querySelector(".pd-refused")).not.toBeNull());

    expect(onEcho).not.toHaveBeenCalled();
    expect(container.querySelector(".pd-card")).toBeNull();
    expect(container.querySelector(".pd-shelf-row")).not.toBeNull();
    expect(container.querySelector(".pd-refused")?.textContent).toContain(
      "nothing has changed",
    );
  });

  it("reports the move as up or down, never as better or worse", async () => {
    /* `KpiDefinition` carries a formula, a baseline and a unit — and no target
       and no direction. So which way is good is a fact the platform does not
       hold, and a sage lamp beside "six days better" would be this file
       deciding. The move is still reported: it is a measurement. */
    wire.preferences = () =>
      Promise.resolve({ "surface.line_pins": { value: [DSO.kpi_key] } });
    wire.kpi = () =>
      Promise.resolve(
        series([
          { on: "2026-07-25", value: 44 },
          { on: "2026-07-30", value: 38 },
        ]),
      );

    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    await settled(container);
    const card = await waitFor(() => {
      const found = container.querySelector(".pd-card");
      expect(found?.textContent).toContain("6d lower than 2026-07-25");
      return found!;
    });

    expect(card.textContent).not.toMatch(/better|worse|ahead|behind|target/i);
    // No meter, and no lamp on this surface graded good or bad.
    expect(card.querySelector(".pd-meter")).toBeNull();
    for (const lamp of card.querySelectorAll(".m-lamp")) {
      expect(lamp.hasAttribute("data-positive")).toBe(false);
      expect(lamp.hasAttribute("data-negative")).toBe(false);
    }
  });

  it("says the record has no earlier day rather than drawing a move it cannot compute", async () => {
    wire.preferences = () =>
      Promise.resolve({ "surface.line_pins": { value: [DSO.kpi_key] } });
    wire.kpi = () => Promise.resolve(series([{ on: "2026-07-30", value: 38 }]));

    const { container } = render(<PocketDesk onEcho={vi.fn()} />);
    await settled(container);
    await waitFor(() =>
      expect(container.querySelector(".pd-card")?.textContent).toContain(
        "no earlier reading · the series starts 2026-07-30",
      ),
    );
  });
});

/* ══════════════════════════════════════════════════════════ the Thread ═════ */

describe("the Thread's day, and the renderer it passes", () => {
  it("scaffolds the day on plates while the Tray beside it does its own", () => {
    wire.history = NEVER;
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    scaffoldIsHonest(container, ".th-turns");
    // The section keeps its name through every state — a room that loses its
    // label while loading has moved under the reader between two frames.
    expect(container.querySelector("#th-earlier")?.textContent).toBe("EARLIER");
  });

  it("says the day failed without taking the certified block down with it", async () => {
    wire.history = () => Promise.reject(new Error("history is unavailable"));
    wire.trays = () => Promise.resolve([tray()]);

    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.querySelector('[data-state="failed"]')).not.toBeNull(),
    );

    expect(container.querySelector(".lc-reason")?.textContent).toBe("history is unavailable");
    // `alone={false}`: the Tray above is still working and still taking acts.
    expect(container.querySelector('[data-state="failed"]')?.hasAttribute("data-alone")).toBe(
      false,
    );
    await waitFor(() => expect(container.querySelector(".tr")).not.toBeNull());
    expect(container.querySelector(".th-step")).not.toBeNull();
  });

  it("has designed prose for a thread nothing has been said in", async () => {
    wire.history = () => Promise.resolve([]);
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.querySelector('.th-turns [data-state="empty"]')).not.toBeNull(),
    );

    // Scoped to the day: the mounted Tray draws its own empty state above, and
    // an unscoped read would be asserting somebody else's copy.
    expect(container.querySelector(".th-turns .lc-body")?.textContent).toMatch(
      /Your colleagues cannot write to you at all/,
    );
    // No day in the eyebrow: with no turns there is no day, and naming one
    // would be a date nothing happened on.
    expect(container.querySelector("#th-earlier")?.textContent).toBe("EARLIER");
  });

  it("names the day off the newest turn rather than off a constant", async () => {
    wire.history = () =>
      Promise.resolve([turn({ at: "2026-07-28T08:00:00" }), turn({ at: "2026-07-30T20:55:00" })]);
    const { container } = render(<ThreadSurface onEcho={vi.fn()} />);
    // Locale-agnostic: the runtime's `Intl` decides the order of the parts, and
    // pinning one order would be testing the ICU data rather than the surface.
    // 30 July 2026 is a Thursday; the 28th is a Tuesday, and it is not the day
    // this thread reaches.
    await waitFor(() =>
      expect(container.querySelector("#th-earlier")?.textContent).toMatch(/THURSDAY/),
    );
    const eyebrow = container.querySelector("#th-earlier")?.textContent ?? "";
    expect(eyebrow).toMatch(/\b30\b/);
    expect(eyebrow).not.toMatch(/TUESDAY|\b28\b/);
  });

  it("passes renderer C to the Tray, so a phone tap is not recorded as an operator click", async () => {
    /* C5, and the one thing the Line owes `useCertifiedAct`: the renderer is a
       parameter and is never inferred, because inferring it from the DOM or from
       a module global is exactly how the two front doors would eventually agree
       by accident. The desk's own render is the control. */
    wire.trays = () => Promise.resolve([tray()]);

    const line = render(<ThreadSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(line.container.querySelector("button.tr-path")).not.toBeNull());
    fireEvent.click(line.container.querySelector("button.tr-path") as HTMLElement);
    await waitFor(() => expect(wire.echoes).toHaveLength(1));
    expect(wire.echoes[0]?.params?.["renderer"]).toBe("C");
    cleanup();

    wire.echoes = [];
    const desk = render(<TraySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(desk.container.querySelector("button.tr-path")).not.toBeNull());
    fireEvent.click(desk.container.querySelector("button.tr-path") as HTMLElement);
    await waitFor(() => expect(wire.echoes).toHaveLength(1));
    expect(wire.echoes[0]?.params?.["renderer"]).toBe("S");
  });
});

/* ═══════════════════════════════════════════════════════ the Line frame ═════ */

describe("the Line's frame reads the estate the desk reads", () => {
  it("counts the beacons the estate counts, and nothing before it has answered", async () => {
    wire.live = { phase: "loading" };
    const first = render(<LineApp />);
    /* Absent rather than zero. An unlit tab means "nothing is waiting", and
       claiming that before anything has been counted is the calm-screen failure
       part L named. */
    expect(first.container.querySelector(".ln-tab-hands")).toBeNull();
    cleanup();

    wire.live = ready({
      beacons: [
        { approval_id: "a", district: "P08", sla_seconds_left: 600 },
        { approval_id: "b", district: null, sla_seconds_left: null },
      ],
    });
    const { container } = render(<LineApp />);
    await waitFor(() => expect(container.querySelector(".ln-tab-hands")).not.toBeNull());

    expect(container.querySelector(".ln-tab-count")?.textContent).toBe("2");
    // Never colour alone (§4): the numeral is visible, the sentence is read out.
    expect(container.querySelector(".ln-tab-hands .vh-sr-only")?.textContent).toBe(
      ", 2 waiting on you",
    );
    // One beacon, one tab. A count on a tab that cannot answer it would be a
    // route the product does not have.
    expect(container.querySelectorAll(".ln-tab-hands")).toHaveLength(1);
  });

  it("prints no company name at all rather than a placeholder", async () => {
    const { container } = render(<LineApp />);
    await waitFor(() => expect(container.querySelector(".ln-rail")).not.toBeNull());
    expect(container.querySelector(".ln-company")).toBeNull();

    cleanup();
    wire.company = () => Promise.resolve("Bhagwati Mills & Weaving Co.");
    const named = render(<LineApp />);
    await waitFor(() =>
      expect(named.container.querySelector(".ln-company")?.textContent).toBe(
        "Bhagwati Mills & Weaving Co.",
      ),
    );
  });
});
