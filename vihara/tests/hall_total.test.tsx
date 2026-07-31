import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EntityDef, TenantRecordOut } from "../src/api/tenant";
import { HallSurface } from "../src/surfaces/HallSurface";

/**
 * Registry Hall's §7.1 rule, held the way `tests/tray_cost.test.tsx` holds the
 * Tray's — and for the same reason it exists at all.
 *
 * The Hall shipped this:
 *
 * ```tsx
 * const total = rows.reduce((n, r) => n + Number(r.amount.replace(/[₹,]/g, "")), 0);
 * <dd>₹{total.toLocaleString("en-IN")}</dd>
 * ```
 *
 * so an empty register — or a filter matching nothing — printed **₹0**. That is
 * the exact defect the tray's cost test exists to prevent, one surface over,
 * and on a register of money it is the worse of the two: a total is a claim
 * about the estate, and ₹0 is a claim that everything is settled.
 *
 * Four things are wrong in those two lines and this file pins all four:
 *
 * 1. **A sum over nothing is nothing, not zero.** No rows → no VALUE pair.
 * 2. **The currency was hard-coded.** On the wire a `money` field is
 *    `{amount, currency}` and the currency is frequently `null`; nothing may
 *    supply one, and the absence is said rather than assumed (§7.4).
 * 3. **A partial sum is a wrong sum.** Rows that state no amount, or two
 *    currencies in one register, produce no figure and a named reason —
 *    adding rupees to dollars silently is how a register lies with arithmetic
 *    nobody can see.
 * 4. **The two empties are two different facts.** "Nothing has ever been filed
 *    here" and "nothing matches what you are looking at" ask for different
 *    things from the reader, and rendering one sentence for both is how a
 *    filtered-to-nothing table gets read as an empty business.
 */

const wire = vi.hoisted(() => ({
  defs: [] as unknown[],
  records: [] as unknown[],
  failDefs: false,
}));

vi.mock("../src/api/tenant", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchDefs: () =>
    wire.failDefs
      ? Promise.reject(new Error("504 from /ai/tenant/defs"))
      : Promise.resolve(wire.defs),
  fetchRecords: () => Promise.resolve(wire.records),
}));

afterEach(() => {
  cleanup();
  wire.defs = [];
  wire.records = [];
  wire.failDefs = false;
});

const INVOICE: EntityDef = {
  name: "Invoice",
  module: "finance",
  domain_tag: null,
  owner_process_code: "P06",
  version: 3,
  fields: [
    { name: "party", type: "string", required: true },
    { name: "amount", type: "money", required: true },
    { name: "state", type: "enum", values: ["open", "overdue", "disputed", "paid"] },
    { name: "note", type: "text" },
    { name: "attachments", type: "json" },
  ],
};

/** Deliberately awkward content (§7.5): a party name with real length, a
 *  disputed row, and money the platform never stamped a currency on. */
function record(
  id: string,
  data: Record<string, unknown>,
  overrides: Partial<TenantRecordOut> = {},
): TenantRecordOut {
  return {
    id,
    entity_def_id: "def-1",
    data,
    version: 2,
    def_version: 3,
    deleted_at: null,
    created_at: "2026-07-29T11:04:07.812345",
    sor: null,
    synced: false,
    ...overrides,
  };
}

const ROWS = [
  record("aaaaaaaa-1111-4000-8000-000000000001", {
    party: "Bhagwati Mills & Weaving Co.",
    amount: { amount: 241750, currency: null },
    state: "disputed",
  }),
  record("bbbbbbbb-2222-4000-8000-000000000002", {
    party: "Coromandel Garments & Furnishing Co-operative",
    amount: { amount: 308900, currency: null },
    state: "overdue",
  }),
];

async function mount() {
  wire.defs = [INVOICE];
  const view = render(<HallSurface onEcho={vi.fn()} />);
  await waitFor(() => expect(view.container.querySelector(".hl-title")).not.toBeNull());
  return view;
}

describe("the Registry Hall's total", () => {
  it("prints no total at all on an empty register", async () => {
    wire.records = [];
    const { container } = await mount();
    await waitFor(() =>
      expect(container.textContent).toContain("Nothing has been filed as Invoice yet."),
    );

    expect(container.querySelector(".hl-summary")).toBeNull();
    for (const forbidden of ["₹0", "₹", "0.00", "NaN", "0 of 0"]) {
      expect(container.textContent).not.toContain(forbidden);
    }
    /* An em dash is punctuation in the empty copy, so the dash this rule is
       about is checked as a standalone value rather than as a substring. */
    for (const node of container.querySelectorAll("*")) {
      expect(node.textContent?.trim()).not.toBe("—");
    }
  });

  it("prints no total when a filter matches nothing", async () => {
    wire.records = ROWS;
    const { container } = await mount();
    await waitFor(() => expect(container.querySelector(".hl-table")).not.toBeNull());

    // A state no row is in. The register is not empty; the view of it is.
    const paid = [...container.querySelectorAll("button.m-chip")].find(
      (chip) => chip.textContent === "paid",
    );
    fireEvent.click(paid as HTMLElement);

    expect(container.textContent).toContain("Nothing here matches what you are looking for.");
    expect(container.querySelector(".hl-summary-val")?.textContent).toBe("0 of 2");
    // The count is a measurement and stays. The sum is not, and goes.
    expect(container.querySelectorAll(".hl-summary > div")).toHaveLength(1);
    expect(container.textContent).not.toContain("₹");
  });

  it("says the two empties differently, because they are different facts", async () => {
    wire.records = [];
    const first = await mount();
    await waitFor(() =>
      expect(first.container.textContent).toContain("Nothing has been filed as Invoice yet."),
    );
    const nothingFiled = first.container.textContent ?? "";
    cleanup();

    wire.records = ROWS;
    const { container } = await mount();
    await waitFor(() => expect(container.querySelector(".hl-table")).not.toBeNull());
    fireEvent.click(
      [...container.querySelectorAll("button.m-chip")].find(
        (chip) => chip.textContent === "paid",
      ) as HTMLElement,
    );

    expect(nothingFiled).not.toContain("Nothing here matches");
    expect(container.textContent).not.toContain("Nothing has been filed");
    // And the filtered one offers the way out; the never-filed one has none to
    // offer, so it draws no button rather than a dead control (§7.4).
    expect(container.textContent).toContain("Show everything");
    expect(nothingFiled).not.toContain("Show everything");
  });

  it("totals what it can, with the currency the records state and no other", async () => {
    wire.records = ROWS;
    const { container } = await mount();
    await waitFor(() => expect(container.querySelector(".hl-table")).not.toBeNull());

    const values = [...container.querySelectorAll(".hl-summary-val")].map(
      (node) => node.textContent,
    );
    expect(values).toContain("2 of 2");
    // 241750 + 308900, grouped by hand rather than by the machine's locale,
    // and with no symbol because no record stated one.
    expect(values).toContain("550,650");
    expect(container.textContent).not.toMatch(/[₹$€£]/);
    expect(container.textContent).toContain("carries no currency");
  });

  it("refuses to total two currencies, and says which refusal it is", async () => {
    wire.records = [
      record("aaaaaaaa-1111-4000-8000-000000000001", {
        party: "Bhagwati Mills & Weaving Co.",
        amount: { amount: 241750, currency: "INR" },
        state: "disputed",
      }),
      record("bbbbbbbb-2222-4000-8000-000000000002", {
        party: "Nilgiri Fabrics",
        amount: { amount: 4100, currency: "USD" },
        state: "open",
      }),
    ];
    const { container } = await mount();
    await waitFor(() => expect(container.querySelector(".hl-table")).not.toBeNull());

    expect(container.querySelectorAll(".hl-summary > div")).toHaveLength(1);
    expect(container.textContent).toContain(
      "No total is shown: these records are in more than one currency.",
    );
    // Never a sum of the two, in any grouping.
    expect(container.textContent).not.toContain("245,850");
  });

  it("refuses to total a register where some rows state no amount", async () => {
    wire.records = [
      ROWS[0]!,
      record("cccccccc-3333-4000-8000-000000000003", {
        party: "Ashoka Retail",
        state: "open",
      }),
    ];
    const { container } = await mount();
    await waitFor(() => expect(container.querySelector(".hl-table")).not.toBeNull());

    expect(container.textContent).toContain("not every Invoice here states amount");
    // The visible figure of the one row that does state an amount must not be
    // promoted into a total for the register.
    expect(container.querySelectorAll(".hl-summary > div")).toHaveLength(1);
  });
});

describe("the Registry Hall's cells", () => {
  it("renders nothing where a record does not carry the field", async () => {
    wire.records = [record("aaaaaaaa-1111-4000-8000-000000000001", { party: "Ashoka Retail" })];
    const { container } = await mount();
    await waitFor(() => expect(container.querySelector(".hl-table")).not.toBeNull());

    const cells = [...container.querySelectorAll("tbody td")].map((cell) =>
      cell.textContent?.trim(),
    );
    expect(cells).toContain("Ashoka Retail");
    // Absent amount and absent state are empty cells, never a dash or a zero.
    for (const cell of cells) {
      expect(cell).not.toBe("—");
      expect(cell).not.toBe("0");
      expect(cell).not.toBe("unknown");
    }
  });

  it("lights no lamp on a tenant's own enum, because a def declares no polarity", async () => {
    wire.records = ROWS;
    const { container } = await mount();
    await waitFor(() => expect(container.querySelector(".hl-table")).not.toBeNull());

    // "overdue" and "disputed" look bad to a reader of invoices and mean
    // nothing to the platform: `tenant_schema` declares enum *values* and no
    // polarity. Deciding which of a tenant's states is a fault is not this
    // client's to make up (§7.1).
    for (const lamp of container.querySelectorAll("tbody .hl-state .m-lamp")) {
      expect(lamp.hasAttribute("data-negative")).toBe(false);
      expect(lamp.hasAttribute("data-positive")).toBe(false);
      expect(lamp.hasAttribute("data-lit")).toBe(false);
    }
    // The word is always there, so the row never depends on colour (§4).
    expect(container.textContent).toContain("disputed");
  });

  it("marks a withdrawn record rather than hiding it", async () => {
    wire.records = [
      record(
        "dddddddd-4444-4000-8000-000000000004",
        { party: "Kanwal Trading", amount: { amount: 96500, currency: null }, state: "open" },
        { deleted_at: "2026-07-30T08:15:00.000000" },
      ),
    ];
    const { container } = await mount();
    await waitFor(() => expect(container.querySelector(".hl-table")).not.toBeNull());

    const row = container.querySelector("tbody tr");
    expect(row?.getAttribute("data-withdrawn")).toBe("true");
    expect(row?.querySelector(".m-lamp[data-negative]")).not.toBeNull();
  });
});

describe("the Registry Hall's lifecycle", () => {
  it("scaffolds rather than spins, and counts nothing before it has counted", async () => {
    wire.defs = [INVOICE];
    wire.records = ROWS;
    const { container } = render(<HallSurface onEcho={vi.fn()} />);

    // D7 §3.1: the pending state is the room's own structure.
    expect(container.querySelector(".lc-bar")).not.toBeNull();
    expect(container.querySelector('[role="progressbar"]')).toBeNull();
    // "0 of 0" while the read is in flight is a measurement nobody made.
    expect(container.textContent).not.toContain("0 of 0");

    await waitFor(() => expect(container.querySelector(".hl-table")).not.toBeNull());
  });

  it("says a failed load is not an empty register", async () => {
    wire.failDefs = true;
    const { container } = render(<HallSurface onEcho={vi.fn()} />);

    await waitFor(() =>
      expect(container.textContent).toContain("could not load the Registry Hall"),
    );
    expect(container.textContent).toContain("not an empty the Registry Hall");
    expect(container.querySelector(".lc-reason")?.textContent).toBe(
      "504 from /ai/tenant/defs",
    );
    expect(container.querySelector('[data-state="failed"]')).not.toBeNull();
    expect(container.querySelector('[data-state="empty"]')).toBeNull();
  });

  it("says so when the estate keeps no registers at all", async () => {
    wire.defs = [];
    const { container } = render(<HallSurface onEcho={vi.fn()} />);

    await waitFor(() =>
      expect(container.textContent).toContain("This estate keeps no registers yet."),
    );
    expect(container.querySelector("table")).toBeNull();
    expect(container.querySelector(".hl-summary")).toBeNull();
  });
});
