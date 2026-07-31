/**
 * DRIVER D7 — the Talent Office (D6 §9, VG-18). What these pin:
 *
 * - **Hire lands at A1 no matter what the template says** — the band is
 *   the client-side floor; raising it later is the certified act.
 * - The interview affordance is drawn and honestly disabled until G5.
 * - Termination success tells the tenure and files the memo (echoed);
 *   a live-run refusal shows the platform's own sentence and the
 *   colleague stays — never a silent strand.
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
import type { EntityOut } from "../src/api/entities";
import { hireFromTemplate } from "../src/api/talent";
import { TalentSurface, type TalentLoaders } from "../src/app/TalentSurface";

afterEach(cleanup);

function entity(
  id: string,
  name: string,
  type: string,
  extra: Partial<EntityOut> = {},
): EntityOut {
  return {
    id,
    name,
    display_name: name,
    type,
    description: null,
    governance: null,
    parent_id: null,
    status: "ACTIVE",
    ...extra,
  } as EntityOut;
}

const TEMPLATE = entity("tpl-1", "agt-046-payment-chaser", "AGENT", {
  display_name: "Payment Chaser",
  description: "Chases overdue invoices.",
  governance: { autonomy_level: "A3" },
  is_template: true,
} as Partial<EntityOut>);

const PROCESS = entity("proc-1", "p08-collections", "PROCESS", {
  display_name: "Collections",
});
const MEERA = entity("agt-1", "agt-046-meera", "AGENT", {
  display_name: "Meera",
});

interface Harness {
  loaders: TalentLoaders;
  echoes: EchoInput[];
  hired: { templateId: string; processId: string; name: string }[];
}

function harness(overrides: Partial<TalentLoaders> = {}): Harness {
  const echoes: EchoInput[] = [];
  const hired: { templateId: string; processId: string; name: string }[] = [];
  const loaders: TalentLoaders = {
    templates: async () => [TEMPLATE],
    entities: async () => [PROCESS, MEERA],
    hire: async (template, processId, name) => {
      hired.push({ templateId: template.id, processId, name });
      return entity("agt-new", name, "AGENT");
    },
    terminate: async () => ({
      status: "terminated",
      memo_artifact_id: "memo-1",
      summary: {
        name: "Meera",
        runs_total: 40,
        runs_completed: 36,
        pending_approvals: 1,
      },
    }),
    echo: async (echo) => {
      echoes.push(echo);
    },
    ...overrides,
  };
  return { loaders, echoes, hired };
}

async function renderOffice(h: Harness): Promise<void> {
  render(<TalentSurface loaders={h.loaders} />);
  await waitFor(() => {
    expect(document.querySelector("[data-part='talent-office']")).not.toBeNull();
  });
}

describe("hiring", () => {
  it("hire lands at A1 even when the template says A3 — the API contract", async () => {
    // The client function itself forces the band; pin it directly.
    const posted: Record<string, unknown>[] = [];
    const { api } = await import("../src/api/client");
    const original = api.post;
    (api as { post: unknown }).post = async (
      _url: string,
      body: Record<string, unknown>,
    ) => {
      posted.push(body);
      return { data: entity("agt-new", "x", "AGENT") };
    };
    try {
      await hireFromTemplate(TEMPLATE, "proc-1", "Meera II");
    } finally {
      (api as { post: unknown }).post = original;
    }
    const governance = posted[0]?.["governance"] as Record<string, unknown>;
    expect(governance["autonomy_level"]).toBe("A1");
    expect(posted[0]?.["template_source_id"]).toBe("tpl-1");
    expect(posted[0]?.["is_template"]).toBe(false);
  });

  it("the office hires into a chosen process and echoes", async () => {
    const h = harness();
    await renderOffice(h);
    fireEvent.click(screen.getByText("hire…"));
    fireEvent.click(screen.getByText("hire at A1"));
    await waitFor(() => {
      expect(h.hired).toHaveLength(1);
    });
    expect(h.hired[0]?.processId).toBe("proc-1");
    expect(h.echoes.some((echo) => echo.sentence.includes("at A1"))).toBe(true);
  });

  it("the interview is drawn and honestly disabled", async () => {
    const h = harness();
    await renderOffice(h);
    const interview = document.querySelector(
      "[data-part='interview']",
    ) as HTMLButtonElement;
    expect(interview.disabled).toBe(true);
    expect(interview.title).toContain("G5");
  });
});

describe("termination", () => {
  it("success tells the tenure and echoes the memo", async () => {
    const h = harness();
    await renderOffice(h);
    fireEvent.click(screen.getByText("exit interview & terminate"));
    await waitFor(() => {
      expect(document.querySelector("[data-part='terminated-note']")).not.toBeNull();
    });
    expect(screen.getByText(/36 pieces of work stand/)).toBeDefined();
    expect(screen.getByText(/1 approval\(s\) remain yours/)).toBeDefined();
    expect(
      h.echoes.some((echo) => echo.sentence.includes("handover memo")),
    ).toBe(true);
  });

  it("a live-run refusal shows the platform's sentence; nobody leaves", async () => {
    const h = harness({
      terminate: async () => {
        throw {
          response: {
            status: 409,
            data: {
              detail: {
                error: "termination_refused",
                reason: "Meera is mid-work on 2 run(s). Wait for them or pause them.",
                running_run_ids: ["r1", "r2"],
              },
            },
          },
        };
      },
    });
    await renderOffice(h);
    fireEvent.click(screen.getByText("exit interview & terminate"));
    await waitFor(() => {
      expect(
        document.querySelector("[data-part='termination-refused']"),
      ).not.toBeNull();
    });
    expect(screen.getByText(/mid-work on 2 run\(s\)/)).toBeDefined();
    // The colleague is still on the roster.
    expect(screen.getByText("exit interview & terminate")).toBeDefined();
  });
});
