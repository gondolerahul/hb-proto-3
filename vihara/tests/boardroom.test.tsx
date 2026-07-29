/**
 * DRIVER D6 — the Boardroom (D6 §8). What these pin:
 *
 * - The producer: raising a proposition CREATES a Planning record (the
 *   first this platform has ever had a producer for), and it is born
 *   `untested`, never gradeless.
 * - UNTESTED renders as its own words, distinct from UNKNOWN (D4 §3.1).
 * - Adoption is the certified act: draft cannot adopt (it tables first),
 *   a tabled one meets the ceremony on refusal and retries whole.
 * - Take-to-Glasshouse is honestly disabled until GLASS.
 * - The agenda says "not measurable yet" rather than inventing a figure.
 */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { EchoInput } from "../src/api/genui";
import type { TenantRecordOut, WriteResult } from "../src/api/tenant";
import {
  BoardroomSurface,
  type BoardroomLoaders,
} from "../src/app/BoardroomSurface";

afterEach(cleanup);

function record(
  id: string,
  data: Record<string, unknown>,
): TenantRecordOut {
  return {
    id,
    entity_def_id: "def-prop",
    data,
    version: 1,
    def_version: 1,
    deleted_at: null,
    created_at: "2026-07-29T00:00:00",
    sor: null,
    synced: false,
  };
}

const TABLED = record("prop-1", {
  title: "Raise chase cadence to every 4 days",
  rationale: "DSO is up 9 days since June",
  status: "tabled",
  honesty_grade: "untested",
});

const DRAFT = record("prop-2", {
  title: "Trim the ad budget",
  status: "draft",
  honesty_grade: "unknown",
});

const APPLIED: WriteResult = {
  status: "applied",
  record: TABLED,
  signal_id: null,
  reason: null,
};

const REFUSAL_ERROR = {
  response: {
    status: 403,
    data: {
      detail: {
        error: "step_up_required",
        tier: "T2",
        why: "resolutions need a ceremony",
        reason: "step up to T2 first",
        needs_step_up: true,
        needs_oob: false,
        locked: false,
        command_ref: "strategy.adopt:prop-1",
        command_summary: "Adopt the proposition",
      },
    },
  },
};

interface Harness {
  loaders: BoardroomLoaders;
  echoes: EchoInput[];
  created: { def: string; data: Record<string, unknown> }[];
  adopted: string[];
}

function harness(overrides: Partial<BoardroomLoaders> = {}): Harness {
  const echoes: EchoInput[] = [];
  const created: { def: string; data: Record<string, unknown> }[] = [];
  const adopted: string[] = [];
  const loaders: BoardroomLoaders = {
    records: async (defName) =>
      defName === "Proposition" ? [TABLED, DRAFT] : [],
    create: async (defName, data) => {
      created.push({ def: defName, data });
      return APPLIED;
    },
    update: async () => APPLIED,
    adopt: async (body) => {
      adopted.push(body.proposition_id);
      return {
        resolution_id: "res-1",
        proposition_id: body.proposition_id,
        status: "applied",
      };
    },
    kpis: async () => [
      { key: "dso", label: "DSO", value: "38d" },
      { key: "csat", label: "CSAT", value: null },
    ],
    echo: async (echo) => {
      echoes.push(echo);
    },
    ceremony: {
      passkey: async () => ({ ok: true }),
      totp: async () => ({ ok: true }),
    },
    ...overrides,
  };
  return { loaders, echoes, created, adopted };
}

async function renderBoard(h: Harness): Promise<void> {
  render(
    <BoardroomSurface onOpenPlanningHall={() => undefined} loaders={h.loaders} />,
  );
  await waitFor(() => {
    expect(document.querySelector("[data-part='boardroom']")).not.toBeNull();
  });
}

describe("grades are words, and untested is its own word", () => {
  it("renders UNTESTED and UNKNOWN differently", async () => {
    const h = harness();
    await renderBoard(h);
    await waitFor(() => {
      expect(screen.getByText(/UNTESTED — never tried/)).toBeDefined();
    });
    expect(screen.getByText(/UNKNOWN — tried, could not be graded/)).toBeDefined();
  });

  it("the glasshouse button is drawn and honestly disabled", async () => {
    const h = harness();
    await renderBoard(h);
    await waitFor(() => {
      expect(
        document.querySelectorAll("[data-part='to-glasshouse']").length,
      ).toBeGreaterThan(0);
    });
    for (const button of document.querySelectorAll("[data-part='to-glasshouse']")) {
      expect((button as HTMLButtonElement).disabled).toBe(true);
    }
  });
});

describe("the agenda", () => {
  it("says not-measurable rather than inventing a figure", async () => {
    const h = harness();
    await renderBoard(h);
    await waitFor(() => {
      expect(screen.getByText("38d")).toBeDefined();
    });
    expect(screen.getByText("not measurable yet")).toBeDefined();
  });
});

describe("the producer", () => {
  it("raising a proposition creates the Planning record, born untested", async () => {
    const h = harness();
    await renderBoard(h);
    fireEvent.change(screen.getByLabelText("proposition title"), {
      target: { value: "Open a second collections lane" },
    });
    fireEvent.click(screen.getByText("raise"));
    await waitFor(() => {
      expect(h.created).toHaveLength(1);
    });
    expect(h.created[0]?.def).toBe("Proposition");
    expect(h.created[0]?.data["honesty_grade"]).toBe("untested");
    expect(h.created[0]?.data["status"]).toBe("draft");
    expect(
      h.echoes.some((echo) => echo.sentence.startsWith("raised a proposition")),
    ).toBe(true);
  });

  it("opening minutes creates a Minutes record", async () => {
    const h = harness();
    await renderBoard(h);
    fireEvent.click(screen.getByText("open minutes"));
    await waitFor(() => {
      expect(h.created.some((c) => c.def === "Minutes")).toBe(true);
    });
  });
});

describe("adoption is the certified act", () => {
  it("a draft offers table-it, never adopt", async () => {
    const h = harness();
    await renderBoard(h);
    await waitFor(() => {
      expect(screen.getByText(/Trim the ad budget/)).toBeDefined();
    });
    const draftCard = document.querySelector("[data-status='draft']");
    expect(draftCard?.querySelector("[data-part='table']")).not.toBeNull();
    expect(draftCard?.querySelector("[data-part='adopt']")).toBeNull();
  });

  it("refusal → ceremony → retry whole → adopted and echoed", async () => {
    let refused = false;
    const h = harness({
      adopt: async (body) => {
        if (!refused) {
          refused = true;
          throw REFUSAL_ERROR;
        }
        return {
          resolution_id: "res-1",
          proposition_id: body.proposition_id,
          status: "applied",
        };
      },
    });
    await renderBoard(h);
    await waitFor(() => {
      expect(screen.getByText(/Adopt as Resolution/)).toBeDefined();
    });
    fireEvent.click(screen.getByText(/Adopt as Resolution/));
    await waitFor(() => {
      expect(document.querySelector("[data-part='ceremony']")).not.toBeNull();
    });
    fireEvent.change(screen.getByLabelText(/one-time code/), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByText("verify"));
    await waitFor(() => {
      expect(
        h.echoes.some((echo) => echo.sentence.includes("as a resolution")),
      ).toBe(true);
    });
  });
});
