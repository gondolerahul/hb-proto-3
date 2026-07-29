/**
 * DRIVER D3 — the Registry Halls (D6 §7). What these pin:
 *
 * - Columns derive from the def — a field the def gains appears with no
 *   code change (schema evolution needs no deploy).
 * - The tracked-change mark ◧ renders others-propose, and the master's
 *   seal ⊛ renders SoR mastering — marks, never re-implementations.
 * - A CAS conflict is said plainly, never silently retried.
 * - Bulk is T2: the button meets the step-up ceremony (the certified bulk
 *   endpoint refuses a plain session), the act retries whole and echoes.
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
import type {
  EntityDef,
  RecordProposal,
  TenantRecordOut,
  WriteResult,
} from "../src/api/tenant";
import { HallsSurface, type HallLoaders } from "../src/app/HallsSurface";

afterEach(cleanup);

const INVOICE_DEF: EntityDef = {
  name: "Invoice",
  module: "Accounting",
  domain_tag: "financial",
  owner_process_code: "P08",
  version: 3,
  fields: [
    { name: "invoice_number", type: "string" },
    {
      name: "status",
      type: "enum",
      values: ["draft", "sent", "paid", "overdue"],
    },
    { name: "total", type: "money" },
    { name: "due_date", type: "date" },
  ],
};

const LEAD_DEF: EntityDef = {
  name: "Lead",
  module: "CRM",
  domain_tag: "crm",
  owner_process_code: "P03",
  version: 1,
  fields: [{ name: "display_name", type: "string", required: true }],
};

function record(
  id: string,
  data: Record<string, unknown>,
  extra: Partial<TenantRecordOut> = {},
): TenantRecordOut {
  return {
    id,
    entity_def_id: "def-1",
    data,
    version: 1,
    def_version: 3,
    deleted_at: null,
    created_at: "2026-07-29T00:00:00",
    sor: null,
    synced: false,
    ...extra,
  };
}

const KT: TenantRecordOut = record(
  "aaaaaaaa-0000-0000-0000-000000000001",
  { invoice_number: "KT-2291", status: "overdue", total: 84200 },
  { sor: "zoho_books", synced: true },
);
const ST: TenantRecordOut = record("bbbbbbbb-0000-0000-0000-000000000002", {
  invoice_number: "ST-1180",
  status: "sent",
  total: 12400,
});

const PROPOSAL: RecordProposal = {
  signal_id: "sig-1",
  record_id: ST.id,
  def_name: "Invoice",
  op: "update",
  delta: { status: "paid" },
  actor: "P10",
  created_at: "2026-07-29T00:00:00",
};

const REFUSAL_ERROR = {
  response: {
    status: 403,
    data: {
      detail: {
        error: "step_up_required",
        tier: "T2",
        why: "bulk needs a ceremony",
        reason: "step up to T2 first",
        needs_step_up: true,
        needs_oob: false,
        locked: false,
        command_ref: "bulk:Invoice:update:2",
        command_summary: "update 2 Invoice records",
      },
    },
  },
};

const APPLIED: WriteResult = {
  status: "applied",
  record: KT,
  signal_id: null,
  reason: null,
};

interface Harness {
  loaders: HallLoaders;
  echoes: EchoInput[];
  bulkCalls: { op: string; ids: string[] }[];
  updates: { id: string; data: Record<string, unknown>; version: number }[];
}

function harness(overrides: Partial<HallLoaders> = {}): Harness {
  const echoes: EchoInput[] = [];
  const bulkCalls: { op: string; ids: string[] }[] = [];
  const updates: {
    id: string;
    data: Record<string, unknown>;
    version: number;
  }[] = [];
  const loaders: HallLoaders = {
    defs: async () => [INVOICE_DEF, LEAD_DEF],
    records: async () => [KT, ST],
    create: async () => APPLIED,
    update: async (id, data, version) => {
      updates.push({ id, data, version });
      return APPLIED;
    },
    remove: async () => undefined,
    bulk: async (_def, op, ids) => {
      bulkCalls.push({ op, ids });
      return { op, def_name: "Invoice", applied: ids.length, results: [] };
    },
    proposals: async () => [PROPOSAL],
    echo: async (echo) => {
      echoes.push(echo);
    },
    ceremony: {
      passkey: async () => ({ ok: true }),
      totp: async () => ({ ok: true }),
    },
    ...overrides,
  };
  return { loaders, echoes, bulkCalls, updates };
}

async function renderHall(h: Harness): Promise<void> {
  render(<HallsSurface loaders={h.loaders} />);
  await waitFor(() => {
    expect(document.querySelector("[data-record-id]")).not.toBeNull();
  });
}

describe("the register derives from the def", () => {
  it("columns are the def's fields and rows are the records", async () => {
    const h = harness();
    await renderHall(h);
    expect(screen.getByText("invoice_number")).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText("KT-2291")).toBeDefined();
    });
    expect(screen.getByText("ST-1180")).toBeDefined();
  });

  it("the halls are the modules; switching hall switches defs", async () => {
    const h = harness();
    await renderHall(h);
    fireEvent.click(screen.getByText("CRM"));
    await waitFor(() => {
      expect(screen.getByText("display_name")).toBeDefined();
    });
  });
});

describe("marks render what the platform already guarantees", () => {
  it("the master's seal on the SoR-mastered row, the tracked mark on the proposed row", async () => {
    const h = harness();
    await renderHall(h);
    const ktRow = document.querySelector(`[data-record-id='${KT.id}']`);
    const stRow = document.querySelector(`[data-record-id='${ST.id}']`);
    expect(ktRow?.querySelector("[data-part='master-seal']")).not.toBeNull();
    expect(stRow?.querySelector("[data-part='tracked-change']")).not.toBeNull();
    expect(ktRow?.querySelector("[data-part='tracked-change']")).toBeNull();
  });

  it("the sheet shows the proposal and taking it merges the delta into the draft", async () => {
    const h = harness();
    await renderHall(h);
    fireEvent.click(screen.getByText("ST-1180"));
    await waitFor(() => {
      expect(document.querySelector("[data-part='proposals']")).not.toBeNull();
    });
    fireEvent.click(screen.getByText("take into the draft"));
    fireEvent.click(screen.getByText("save"));
    await waitFor(() => {
      expect(h.updates).toHaveLength(1);
    });
    expect(h.updates[0]?.data["status"]).toBe("paid");
    expect(
      h.echoes.some((echo) => echo.sentence.startsWith("accepted P10's")),
    ).toBe(true);
  });
});

describe("a CAS conflict is said plainly", () => {
  it("conflict → the honest sentence, no silent retry", async () => {
    const h = harness({
      update: async () => ({
        status: "conflict",
        record: null,
        signal_id: null,
        reason: "version moved",
      }),
    });
    await renderHall(h);
    fireEvent.click(screen.getByText("KT-2291"));
    await waitFor(() => {
      expect(document.querySelector("[data-part='record-sheet']")).not.toBeNull();
    });
    fireEvent.click(screen.getByText("save"));
    await waitFor(() => {
      expect(
        screen.getByText(/Someone changed this record while you edited/),
      ).toBeDefined();
    });
  });
});

describe("bulk is T2 — the ceremony, never a confirm dialog", () => {
  it("refusal → step-up → retry whole → applied + echoed", async () => {
    let refused = false;
    const h = harness();
    const bulkOnceRefusing = h.loaders.bulk;
    h.loaders.bulk = async (defName, op, ids, data) => {
      if (!refused) {
        refused = true;
        throw REFUSAL_ERROR;
      }
      return bulkOnceRefusing(defName, op, ids, data);
    };
    await renderHall(h);

    fireEvent.click(screen.getByLabelText(`select ${KT.id.slice(0, 8)}`));
    fireEvent.click(screen.getByLabelText(`select ${ST.id.slice(0, 8)}`));
    fireEvent.click(screen.getByText(/Bulk delete/));

    await waitFor(() => {
      expect(document.querySelector("[data-part='ceremony']")).not.toBeNull();
    });
    fireEvent.change(screen.getByLabelText(/one-time code/), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByText("verify"));

    await waitFor(() => {
      expect(h.bulkCalls).toHaveLength(1);
    });
    expect(h.bulkCalls[0]?.ids).toHaveLength(2);
    expect(
      h.echoes.some((echo) =>
        echo.sentence.includes("bulk-deleted 2 Invoice records"),
      ),
    ).toBe(true);
    await waitFor(() => {
      expect(screen.getByText("2 of 2 applied")).toBeDefined();
    });
  });
});

describe("the analytics flip", () => {
  it("counts by an enum field and echoes the flip", async () => {
    const h = harness();
    await renderHall(h);
    fireEvent.click(screen.getByText(/⇄ analytics/));
    await waitFor(() => {
      expect(document.querySelector("[data-part='analytics']")).not.toBeNull();
    });
    expect(screen.getByText("overdue")).toBeDefined();
    expect(
      h.echoes.some((echo) => echo.sentence === "flipped Invoice to analytics"),
    ).toBe(true);
  });
});

describe("creation", () => {
  it("a new record posts the entered fields and echoes", async () => {
    const created: Record<string, unknown>[] = [];
    const h = harness({
      create: async (_def, data) => {
        created.push(data);
        return APPLIED;
      },
    });
    await renderHall(h);
    fireEvent.click(screen.getByText("new Invoice"));
    await waitFor(() => {
      expect(document.querySelector("[data-part='record-sheet']")).not.toBeNull();
    });
    fireEvent.change(document.querySelector("#field-invoice_number") as Element, {
      target: { value: "NW-0042" },
    });
    fireEvent.click(screen.getByText("create"));
    await waitFor(() => {
      expect(created).toHaveLength(1);
    });
    expect(created[0]?.["invoice_number"]).toBe("NW-0042");
    expect(h.echoes.some((echo) => echo.sentence === "created a Invoice")).toBe(
      true,
    );
  });
});
