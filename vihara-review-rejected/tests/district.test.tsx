/**
 * DRIVER D4 — the district sheet and the dossier (D6 §5–6). What these pin:
 *
 * - The sheet renders the estate's own district payload: colleagues with
 *   the raised hand ◈, the treasury with the reserve as its one gold
 *   element, the weather as its sentence, live runs filtered to the
 *   district's own people.
 * - The dossier TELLS recent work as sentences, keeps the trace one flip
 *   away (fetched lazily, echoed), renders honest absences (no invented
 *   SLO dials), and feedback echoes with the honest note about SEGA's
 *   proposal path.
 */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EchoInput } from "../src/api/genui";
import type { EntityOut, RunSummary } from "../src/api/entities";
import { artKeyFor } from "../src/api/entities";
import { DistrictSheet, type DistrictLoaders } from "../src/app/DistrictSheet";
import { DossierSurface, type DossierLoaders } from "../src/app/DossierSurface";

afterEach(cleanup);

const MEERA_ID = "aaaaaaaa-0000-0000-0000-00000000000a";
const RAVI_ID = "bbbbbbbb-0000-0000-0000-00000000000b";

const ESTATE = {
  estate: { pulse: { healthy: true } },
  beacons: [],
  districts: [
    {
      process_code: "P08",
      name: "Collections",
      quarter: "money",
      colleagues: [
        {
          entity_id: MEERA_ID,
          name: "Meera",
          autonomy: "A2",
          hand_raised: true,
          state: "running",
        },
        {
          entity_id: RAVI_ID,
          name: "Ravi",
          autonomy: "A1",
          hand_raised: false,
          state: "idle",
        },
      ],
      kpi: { plinth: [{ key: "dso", label: "DSO", value: "38d" }] },
      treasury: { spent: 18000, cap: 30000, reserve_protected: true },
      weather: { state: "fog", sentence: "Below target for 9 days." },
    },
  ],
};

const RUNS: RunSummary[] = [
  {
    id: "run-1",
    entity_id: MEERA_ID,
    status: "RUNNING",
    total_cost_usd: 0.2,
    execution_time_ms: 31000,
    error_message: null,
    started_at: "2026-07-29T09:00:00",
    completed_at: null,
    created_at: "2026-07-29T09:00:00",
  },
  {
    id: "run-2",
    entity_id: "cccccccc-0000-0000-0000-00000000000c", // another district
    status: "RUNNING",
    total_cost_usd: 0.1,
    execution_time_ms: null,
    error_message: null,
    started_at: null,
    completed_at: null,
    created_at: "2026-07-29T08:00:00",
  },
];

function districtLoaders(): DistrictLoaders {
  return {
    estate: async () => ESTATE as never,
    executions: async () => RUNS,
    stream: () => () => undefined,
  };
}

describe("the district sheet", () => {
  it("renders colleagues, the raised hand, the reserve and the weather", async () => {
    render(
      <DistrictSheet
        code="P08"
        onOpenDossier={() => undefined}
        loaders={districtLoaders()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText("Meera")).toBeDefined();
    });
    expect(document.querySelector("[data-part='hand-raised']")).not.toBeNull();
    expect(document.querySelector("[data-part='reserve']")).not.toBeNull();
    expect(screen.getByText("Below target for 9 days.")).toBeDefined();
    expect(screen.getByText("DSO")).toBeDefined();
  });

  it("live runs are the district's own people only", async () => {
    render(
      <DistrictSheet
        code="P08"
        onOpenDossier={() => undefined}
        loaders={districtLoaders()}
      />,
    );
    await waitFor(() => {
      expect(document.querySelector("[data-part='live-runs']")).not.toBeNull();
    });
    const runs = document.querySelector("[data-part='live-runs']");
    expect(runs?.textContent).toContain("Meera");
    expect(runs?.querySelectorAll("li")).toHaveLength(1);
  });

  it("a colleague's name opens the dossier", async () => {
    const opened = vi.fn();
    render(
      <DistrictSheet
        code="P08"
        onOpenDossier={opened}
        loaders={districtLoaders()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText("Ravi")).toBeDefined();
    });
    fireEvent.click(screen.getByText("Ravi"));
    expect(opened).toHaveBeenCalledWith({ id: RAVI_ID, name: "Ravi" });
  });
});

const MEERA: EntityOut = {
  id: MEERA_ID,
  name: "agt-046-payment-chaser",
  display_name: "Meera",
  type: "AGENT",
  description: "I chase overdue invoices and escalate past 60 days.",
  governance: { autonomy_level: "A2" },
  parent_id: null,
};

function dossierLoaders(): { loaders: DossierLoaders; echoes: EchoInput[] } {
  const echoes: EchoInput[] = [];
  return {
    echoes,
    loaders: {
      entity: async () => MEERA,
      executions: async () => [
        {
          ...RUNS[0]!,
          status: "COMPLETED",
          completed_at: "2026-07-28T10:00:00",
        },
      ],
      trace: async () => ({ steps: ["gate", "act"] }),
      echo: async (echo) => {
        echoes.push(echo);
      },
    },
  };
}

describe("the dossier", () => {
  it("derives the art key from the entity name", () => {
    expect(artKeyFor("agt-046-payment-chaser")).toBe("agt-046");
    expect(artKeyFor("custom-colleague")).toBe("custom-colleague");
  });

  it("tells work as sentences and keeps honest absences absent", async () => {
    const h = dossierLoaders();
    render(<DossierSurface entityId={MEERA_ID} loaders={h.loaders} />);
    await waitFor(() => {
      expect(screen.getByText("Meera")).toBeDefined();
    });
    expect(screen.getByText(/Finished a piece of work on 2026-07-28/)).toBeDefined();
    expect(document.querySelector("[data-part='slo-absent']")).not.toBeNull();
    expect(document.querySelector("[data-part='bust']")).not.toBeNull();
  });

  it("the trace is one flip away, fetched lazily, echoed", async () => {
    const h = dossierLoaders();
    render(<DossierSurface entityId={MEERA_ID} loaders={h.loaders} />);
    await waitFor(() => {
      expect(document.querySelector("[data-part='trace-flip']")).not.toBeNull();
    });
    const flip = document.querySelector("[data-part='trace-flip']") as HTMLDetailsElement;
    flip.open = true;
    fireEvent(flip, new Event("toggle"));
    await waitFor(() => {
      expect(flip.textContent).toContain('"gate"');
    });
    expect(h.echoes.some((echo) => echo.sentence.includes("trace"))).toBe(true);
  });

  it("feedback echoes and says honestly where it goes", async () => {
    const h = dossierLoaders();
    render(<DossierSurface entityId={MEERA_ID} loaders={h.loaders} />);
    await waitFor(() => {
      expect(screen.getByText(/Tell Meera something/)).toBeDefined();
    });
    fireEvent.change(document.querySelector("textarea") as Element, {
      target: { value: "hold the legal language a cycle" },
    });
    fireEvent.click(screen.getByText("tell"));
    await waitFor(() => {
      expect(
        h.echoes.some((echo) =>
          echo.sentence.includes("told Meera: hold the legal language a cycle"),
        ),
      ).toBe(true);
    });
    expect(document.querySelector("[data-part='tell-honesty']")).not.toBeNull();
  });
});
