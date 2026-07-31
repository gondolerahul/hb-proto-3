import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Dossier } from "../src/api/dossier";
import type { EstateSnapshot } from "../src/api/estate";
import type { KpiHistory } from "../src/api/gallery";
import type { LiveEstate } from "../src/estate/useLiveEstate";

/**
 * R-4 part W · task W4 — the District room, the Dossier and the Gallery, on the
 * network.
 *
 * Written as assertions about **what must not appear**, because that is what
 * this task's diff is mostly about. Three instruments in the district and three
 * dials on the dossier were drawn against numbers the platform does not have,
 * and the risk in wiring them is not that a fetch fails — it is that a
 * plausible default quietly takes the place of an absent binding. So the
 * sharpest tests here look for a `0`, a `—`, a target tick and a gauge, and
 * fail when they are found.
 */

const liveState = vi.hoisted(() => ({ current: null as unknown as LiveEstate }));
const wire = vi.hoisted(() => ({
  dossier: null as unknown as Dossier,
  entities: [] as Record<string, unknown>[],
  resolutions: [] as Record<string, unknown>[],
  history: null as unknown as KpiHistory,
  alumni: [] as unknown[],
  due: [] as Record<string, unknown>[],
  realized: null as unknown,
}));

vi.mock("../src/estate/useLiveEstate", () => ({
  useLiveEstate: () => liveState.current,
}));
vi.mock("../src/api/entities", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchExecutions: () => Promise.resolve([]),
}));
vi.mock("../src/api/dossier", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchDossier: () => Promise.resolve(wire.dossier),
}));
vi.mock("../src/api/talent", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchEntities: () => Promise.resolve(wire.entities),
}));
vi.mock("../src/api/gallery", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchSeasonMaterial: () =>
    Promise.resolve({ resolutions: wire.resolutions, history: wire.history }),
  fetchAlumni: () => Promise.resolve(wire.alumni),
  fetchReviewsDue: () => Promise.resolve(wire.due),
  fetchRealized: () => Promise.resolve(wire.realized),
}));

import { DistrictSurface } from "../src/surfaces/DistrictSurface";
import { DossierSurface } from "../src/surfaces/DossierSurface";
import { GallerySurface } from "../src/surfaces/GallerySurface";

afterEach(cleanup);

/* ------------------------------------------------------------------ fixtures */

function snapshot(over: Partial<EstateSnapshot> = {}): EstateSnapshot {
  return {
    estate: {
      loop_id: "loop-1",
      pulse: { beat_at: "2026-07-31T09:40:00", healthy: true },
      local_time: "2026-07-31T21:41:00+05:30",
      phase: "night",
      standing: "active",
    },
    quarters: [{ code: "money", name: "Money", districts: ["P08"] }],
    districts: [
      {
        process_code: "P08",
        name: "Collections",
        quarter: "money",
        colleagues: [
          {
            entity_id: "3f2a0c11-0000-0000-0000-000000000001",
            name: "Meera",
            autonomy: "A2",
            hand_raised: true,
            state: "running",
          },
        ],
        kpi: {
          plinth: [
            {
              kpi_key: "dso",
              display_name: "Days sales outstanding",
              value: 38,
              measurable: true,
              unit: "days",
            },
            {
              kpi_key: "gm",
              display_name: "Gross margin",
              value: null,
              measurable: false,
              unit: "percent",
            },
          ],
        },
        treasury: null,
        weather: { state: "storm", icon: "cloud-lightning", sentence: "Below target." },
        traffic: { in_1h: 42, out_1h: 37, parked: 3 },
      },
    ],
    gatehouses: [],
    bridges: [],
    halls: [],
    monuments: [],
    beacons: [],
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

/** The E3 read model's own `absent` list, verbatim in shape: every field named
 *  with a reason. The surface must render all seven. */
const ABSENT = [
  { field: "slos", why: "No SLO target is defined anywhere on the platform." },
  { field: "probation", why: "No probationary period ships." },
  { field: "standing", why: "Associate / probationer / senior is not modelled." },
  { field: "own_words", why: "No first-person charter statement is stored." },
  { field: "doing", why: "No run records a human-readable statement of what it is doing." },
  { field: "charter_proposals", why: "Nothing stores a pending charter-change proposal." },
  { field: "decisions", why: "GET /ai/executions takes no parameters at all." },
];

function dossier(over: Partial<Dossier> = {}): Dossier {
  return {
    as_of: "2026-07-31T16:11:00",
    entity_id: "3f2a0c11-0000-0000-0000-000000000001",
    name: "agt-046-collections",
    display_name: "Meera",
    role: "Collections",
    type: "AGENT",
    status: "ACTIVE",
    version: 3,
    charter_updated_at: "2026-07-04T10:00:00",
    retired_at: null,
    district: { process_code: "P08", name: "Collections", quarter: "money" },
    autonomy: { band: "A2" },
    charter: {
      clauses: [
        { label: "Goal", value: "Chase overdue invoices.", source: "entity.goal" },
      ],
      governance: { autonomy_level: "A2" },
      authority: [
        {
          category: "payout",
          tools: ["payment_release"],
          checkpoint_key: "before_outbound_payout_above_band",
          decision: "PASS",
          reason: "A2 may act within the payout band.",
          band: 500,
          unit: "usd",
          hard_block: 10000,
          always_hitl: false,
          conditional_on_amount: true,
        },
      ],
    },
    competencies: [
      {
        name: "send_email",
        kind: "tool",
        registered: false,
        category: null,
        checkpoint_key: null,
      },
      {
        name: "payment_release",
        kind: "tool",
        registered: true,
        category: "payout",
        checkpoint_key: "before_outbound_payout_above_band",
        note: "Releases an approved payment.",
      },
    ],
    reliability: {
      window_days: 14,
      runs_total: 0,
      runs_failed: 0,
      failure_rate: null,
      p95_latency_ms: null,
      demotion_bar: {
        min_runs: 20,
        failure_rate: 0.2,
        latency_multiple: 3,
        latency_floor_ms: null,
      },
    },
    running_runs: 0,
    open_approvals: 0,
    absent: ABSENT,
    ...over,
  };
}

const EMPTY_HISTORY: KpiHistory = { from: "2026-05-02", to: "2026-07-31", series: [] };

function resolution(id: string, title: string, adopted: string) {
  return {
    id,
    entity_def_id: "def-1",
    data: { title, adopted_on: adopted, status: "active", concerns_module: "Collections" },
    version: 1,
    def_version: 1,
    deleted_at: null,
    created_at: `${adopted}T09:00:00`,
    sor: null,
    synced: false,
  };
}

/* ========================================================================== */

describe("W4 — the District room", () => {
  it("scaffolds on plates and never a spinner", () => {
    liveState.current = { phase: "loading" };
    const { container } = render(
      <DistrictSurface code="P08" onOpenHall={vi.fn()} onEcho={vi.fn()} />,
    );
    expect(container.querySelector("[data-lifecycle='scaffold']")).not.toBeNull();
    expect(container.querySelector(".lc-bar.vh-skeleton")).not.toBeNull();
    /* The bars must sit inside a drawn plate: `vh-skeleton`'s ground is a
       ~6/255 delta on the raw canvas, so a scaffold on the page background is
       invisible and proves nothing. */
    expect(container.querySelector(".m-plate .lc-bar")).not.toBeNull();
  });

  it("takes the wire's own traffic keys, not the fixture's", () => {
    liveState.current = ready(snapshot());
    const { container } = render(
      <DistrictSurface code="P08" onOpenHall={vi.fn()} onEcho={vi.fn()} />,
    );
    const traffic = container.querySelector(".di-traffic")?.textContent ?? "";
    expect(traffic).toContain("42");
    expect(traffic).toContain("37");
    expect(traffic).toContain("3");
  });

  it("says so when the URL names a district the estate does not have", () => {
    liveState.current = ready(snapshot());
    const { container } = render(
      <DistrictSurface code="P99" onOpenHall={vi.fn()} onEcho={vi.fn()} />,
    );
    expect(container.textContent).toContain("no district called P99");
    // and names what it does have, rather than leaving the reader guessing
    expect(container.textContent).toContain("P08");
  });

  it("distinguishes an empty estate from a bad link", () => {
    liveState.current = ready(snapshot({ districts: [] }));
    const { container } = render(
      <DistrictSurface code="P08" onOpenHall={vi.fn()} onEcho={vi.fn()} />,
    );
    expect(container.textContent).toContain("No district has been stood up yet");
  });

  it("draws no target meter, because no KPI declares a target", () => {
    liveState.current = ready(snapshot());
    const { container } = render(
      <DistrictSurface code="P08" onOpenHall={vi.fn()} onEcho={vi.fn()} />,
    );
    expect(container.querySelector(".di-meter")).toBeNull();
    expect(container.querySelector(".di-meter-tick")).toBeNull();
  });

  it("prints no figure for a KPI that was never measured, and no zero", () => {
    liveState.current = ready(snapshot());
    const { container } = render(
      <DistrictSurface code="P08" onOpenHall={vi.fn()} onEcho={vi.fn()} />,
    );
    /* Open the readings fixture the way a person does. */
    const kpi = [...container.querySelectorAll("g,button,[role='button']")];
    void kpi;
    // The plinth's unmeasured KPI must never acquire a figure anywhere on the
    // surface — not in the room label, not in the panel.
    const text = container.textContent ?? "";
    expect(text).not.toContain("Gross margin · 0");
    expect(text).not.toContain("Gross margin · —");
  });
});

describe("W4 — the Dossier", () => {
  it("renders every declared absence, with the endpoint's own reason", async () => {
    wire.entities = [
      { id: "3f2a0c11-0000-0000-0000-000000000001", name: "agt-046-collections", display_name: "Meera", type: "AGENT", description: null, governance: null, parent_id: null },
    ];
    wire.dossier = dossier();
    const { container } = render(<DossierSurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.querySelector(".do-charter")).not.toBeNull(),
    );
    const text = container.textContent ?? "";
    /* All seven. A dossier that drops one has silently answered a question the
       platform declined to answer. */
    for (const item of ABSENT) {
      expect(text, `missing the reason for "${item.field}"`).toContain(item.why);
    }
  });

  it("draws no dial for reliability — there is no target to draw one to", async () => {
    wire.dossier = dossier();
    const { container } = render(<DossierSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".do-readings")).not.toBeNull());
    expect(container.querySelector(".do-slo")).toBeNull();
    expect(container.querySelector(".do-slo-fill")).toBeNull();
    expect(container.querySelector(".do-slo-tick")).toBeNull();
    /* And the block did render — otherwise the three nulls above would pass on
       an empty screen, which is the vacuous-test shape this increment has now
       been bitten by twice. */
    expect(container.textContent).toContain("THE DEMOTION BAR");
  });

  it("prints no failure rate where there are no runs, and never 0%", async () => {
    wire.dossier = dossier();
    const { container } = render(<DossierSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".do-readings")).not.toBeNull());
    /* Scoped to the reading itself. An unscoped "no 0%" would also match the
       demotion bar's own `20%`, which is a real threshold and must stay. */
    const rate = [...container.querySelectorAll(".do-reading")].find((row) =>
      row.textContent?.includes("FAILURE RATE"),
    );
    expect(rate).toBeDefined();
    expect(rate!.textContent).toContain("no runs in this window, so there is no rate");
    expect(rate!.querySelector(".do-reading-val")).toBeNull();
    expect(rate!.textContent).not.toContain("%");
  });

  it("says a granted tool is not registered, and prints no note for it", async () => {
    wire.dossier = dossier();
    const { container } = render(<DossierSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".do-comps")).not.toBeNull());
    const rows = [...container.querySelectorAll(".do-comp")];
    const unregistered = rows.find((row) => row.textContent?.includes("send_email"));
    expect(unregistered).toBeDefined();
    expect(unregistered!.getAttribute("data-unregistered")).toBe("true");
    expect(unregistered!.textContent).toContain("not registered");
    expect(unregistered!.querySelector(".do-comp-note")?.textContent).toBe("");
  });

  it("carries the gate's own reason and says when it is conditional", async () => {
    wire.dossier = dossier();
    const { container } = render(<DossierSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".do-verdict")).not.toBeNull());
    const text = container.textContent ?? "";
    expect(text).toContain("A2 may act within the payout band.");
    expect(text).toContain("USD 500");
    expect(text).toContain("depends on the amount");
  });

  it("names the column every clause came from", async () => {
    wire.dossier = dossier();
    const { container } = render(<DossierSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".do-charter")).not.toBeNull());
    expect(container.querySelector(".do-source")?.textContent).toBe("entity.goal");
  });
});

describe("W4 — the Gallery", () => {
  it("makes the thin state the designed state, not a broken one", async () => {
    wire.resolutions = [];
    wire.history = EMPTY_HISTORY;
    wire.alumni = [];
    wire.due = [];
    const { container } = render(<GallerySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".ga-frame")).not.toBeNull());
    const text = container.textContent ?? "";
    expect(text).toContain("The record has not started.");
    expect(text).toContain("Nothing has been decided here yet.");
    /* Nothing invented and nothing zeroed: the day strip is absent rather than
       drawn empty, and no first-trend date is projected from a start that has
       not happened. */
    expect(container.querySelector(".ga-days")).toBeNull();
    expect(text).not.toContain("0 of 90");
  });

  /** Two measured days out of a three-month window — the shape §11 promises
   *  for the first quarter after deploy. */
  const MEASURED_HISTORY: KpiHistory = {
    from: "2026-05-02",
    to: "2026-07-31",
    series: [
      {
        key: "dso",
        display_name: "Days sales outstanding",
        unit: "days",
        first_measurable_on: "2026-07-25",
        measurable_days: 2,
        points: [
          { captured_on: "2026-07-25", value: 44, measurable: true, missing: [], baseline_value: null, sample_size: null },
          { captured_on: "2026-07-30", value: 41, measurable: true, missing: [], baseline_value: null, sample_size: null },
        ],
      },
    ],
  };

  it("hatches what was told and gates where the record begins", async () => {
    wire.resolutions = [
      resolution("r-1", "Chase at forty-five days", "2026-04-02"),
      resolution("r-2", "Voice first above the large accounts", "2026-07-28"),
    ];
    wire.history = MEASURED_HISTORY;
    const { container } = render(<GallerySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelectorAll(".ga-season").length).toBe(2));

    const cards = [...container.querySelectorAll(".ga-season")];
    expect(cards[0]!.getAttribute("data-told")).toBe("true");
    expect(cards[1]!.getAttribute("data-told")).toBeNull();
    /* Exactly one gate: it is the boundary between the measured and the merely
       lived, and two of them would say the record started twice. */
    expect(container.querySelectorAll(".ga-gate").length).toBe(1);
    expect(container.textContent).toContain("25 July 2026");
  });

  it("counts days of record from what came back, not from the window asked for", async () => {
    /* The window is 90 days wide and two days of it were measurable. A count
       taken off `history.from`/`to` would say 90. */
    wire.resolutions = [];
    wire.history = MEASURED_HISTORY;
    const { container } = render(<GallerySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".ga-days-count")).not.toBeNull());
    expect(container.querySelector(".ga-days-count")?.textContent).toBe("2 of 90");
    // …and the first trend is 90 days after the first measurable day.
    expect(container.textContent).toContain("23 October 2026");
  });

  it("renders no bar for a prediction nobody made", async () => {
    wire.due = [{ record_id: "m-1", title: "Seven days of grace", status: "issued" }];
    wire.realized = {
      mandate_id: "m-1",
      kpi_key: null,
      predicted_value: null,
      predicted_from: null,
      realized_value: 3,
      measurable: true,
      missing: [],
      verdict: null,
      direction: null,
      honesty_grade: "untested",
      twin_run_id: null,
      review_fields: {},
    };
    const { container } = render(<GallerySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".ga-ghost")).not.toBeNull());
    await waitFor(() =>
      expect(container.querySelector(".ga-ghost-absent")).not.toBeNull(),
    );
    expect(container.querySelector(".ga-bar")).toBeNull();
    const text = container.textContent ?? "";
    expect(text).toContain("No prediction was made.");
    /* §7.2: `untested` is "never tried", and it must not read like `unknown`.
       The structural tell is that there is no run behind it to name. */
    expect(text).toContain("untested · never tried");
    expect(text).not.toContain("The run behind it");
  });

  it("names the run behind a graded bet, so untested and unknown differ structurally", async () => {
    wire.due = [{ record_id: "m-2", title: "Chase at thirty days", status: "issued" }];
    wire.realized = {
      mandate_id: "m-2",
      kpi_key: "dso",
      predicted_value: 34,
      predicted_from: "forecast",
      realized_value: 41,
      measurable: true,
      missing: [],
      verdict: "missed",
      direction: "down",
      honesty_grade: "unknown",
      twin_run_id: "TWN-2203",
      review_fields: {},
    };
    const { container } = render(<GallerySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".ga-bar")).not.toBeNull());
    const text = container.textContent ?? "";
    expect(text).toContain("unknown · could not be graded");
    expect(text).toContain("The run behind it");
    expect(text).toContain("TWN-2203");
    // Both bars, scaled to the pair and not to another row.
    expect(container.querySelectorAll(".ga-bar").length).toBe(2);
  });

  it("spends no gold on a certified seal the record does not carry", async () => {
    wire.due = [];
    const { container } = render(<GallerySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".ga-frame")).not.toBeNull());
    expect(container.querySelector(".m-medallion")).toBeNull();
    expect(container.querySelector("[data-certified]")).toBeNull();
  });
});
