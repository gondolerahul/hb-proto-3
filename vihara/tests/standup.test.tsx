/**
 * DRIVER D5 — the Standup (D6 §10). What these pin:
 *
 * - The pure composition: one line per colleague, waiting-first ordering,
 *   yesterday's window, the quiet-day sentence (never an empty card).
 * - The card is PREPARED BY the colleague and relayed by Pragya (L2) —
 *   the eyebrow carries both names, and nothing renders a colleague
 *   speaking in the first person voice channel.
 * - Sequencing by arrows; every opened card echoes; the drill goes to
 *   the dossier with the district in hand.
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
import type { RunSummary } from "../src/api/entities";
import type { Tray } from "../src/api/trays";
import {
  composeStandup,
  StandupSurface,
  type StandupLoaders,
} from "../src/app/StandupSurface";
import type { EstateSnapshot } from "../src/renderers/world/layout";

afterEach(cleanup);

const NOW = new Date("2026-07-29T09:00:00Z");
const MEERA = "aaaaaaaa-0000-0000-0000-00000000000a";
const RAVI = "bbbbbbbb-0000-0000-0000-00000000000b";

const ESTATE = {
  estate: { phase: "day", pulse: { healthy: true } },
  beacons: [],
  districts: [
    {
      process_code: "P08",
      name: "Collections",
      quarter: "money",
      colleagues: [
        { entity_id: MEERA, name: "Meera", autonomy: "A2", hand_raised: false, state: "idle" },
        { entity_id: RAVI, name: "Ravi", autonomy: "A1", hand_raised: false, state: "idle" },
      ],
      weather: { state: "clear", icon: null, sentence: null },
      traffic: { in_1h: 0, out_1h: 0, parked: 0 },
      treasury: null,
    },
  ],
} as unknown as EstateSnapshot;

function run(entity: string, status: string, createdAt: string): RunSummary {
  return {
    id: `run-${entity.slice(0, 4)}-${createdAt}`,
    entity_id: entity,
    status,
    total_cost_usd: 0,
    execution_time_ms: null,
    error_message: null,
    started_at: null,
    completed_at: null,
    created_at: createdAt,
  };
}

describe("composeStandup — the pure heart", () => {
  it("counts yesterday only, tells a quiet day, and puts the waiting first", () => {
    const lines = composeStandup(
      ESTATE,
      [
        run(MEERA, "COMPLETED", "2026-07-29T02:00:00Z"),
        run(MEERA, "COMPLETED", "2026-07-20T02:00:00Z"), // out of window
        run(MEERA, "FAILED", "2026-07-29T03:00:00Z"),
      ],
      new Set([RAVI]),
      NOW,
    );
    expect(lines).toHaveLength(2);
    // Ravi is waiting, so he comes first even with no runs.
    expect(lines[0]?.name).toBe("Ravi");
    expect(lines[0]?.sentences).toContain("Is waiting on you.");
    expect(lines[1]?.sentences).toContain(
      "Finished one piece of work since yesterday.",
    );
    expect(lines[1]?.sentences).toContain(
      "One thing went wrong — it is in the trace.",
    );
  });

  it("a colleague with nothing at all still gets a sentence", () => {
    const lines = composeStandup(ESTATE, [], new Set(), NOW);
    expect(
      lines.every((line) =>
        line.sentences.includes("A quiet day — nothing to report."),
      ),
    ).toBe(true);
  });
});

function harness(): { loaders: StandupLoaders; echoes: EchoInput[] } {
  const echoes: EchoInput[] = [];
  return {
    echoes,
    loaders: {
      estate: async () => ESTATE as never,
      executions: async () => [run(MEERA, "COMPLETED", "2026-07-29T02:00:00Z")],
      trays: async () =>
        [
          {
            tray_id: "t1",
            approval_id: "t1",
            checkpoint_key: null,
            what_happened: { sentence: "x", object: null },
            recommendation: null,
            paths: [],
            certified: { component: "certified.approval@1", tier: "T2", props: {}, manifest_hash: "h" },
            sla: { seconds_left: null, on_timeout: null },
            prepared_by: { entity_id: RAVI, name: "Ravi" },
          },
        ] as Tray[],
      echo: async (echo) => {
        echoes.push(echo);
      },
    },
  };
}

describe("the surface", () => {
  it("relays, sequences, echoes each opened card, and drills with district", async () => {
    const h = harness();
    const opened = vi.fn();
    render(
      <StandupSurface
        onOpenDossier={opened}
        loaders={h.loaders}
        now={() => NOW}
      />,
    );
    await waitFor(() => {
      expect(document.querySelector("[data-part='standup-card']")).not.toBeNull();
    });
    // Ravi first (waiting), eyebrow carries both names (L2).
    expect(screen.getByText(/prepared by Ravi · relayed by Pragya/)).toBeDefined();
    expect(document.querySelector("[data-part='standup-waiting']")).not.toBeNull();

    fireEvent.click(screen.getByLabelText("next colleague"));
    await waitFor(() => {
      expect(screen.getByText(/prepared by Meera/)).toBeDefined();
    });
    expect(
      h.echoes.filter((echo) => echo.sentence.includes("standup line")),
    ).toHaveLength(2);

    fireEvent.click(screen.getByText("open the dossier"));
    expect(opened).toHaveBeenCalledWith({
      id: MEERA,
      name: "Meera",
      district: "P08",
    });
  });
});
