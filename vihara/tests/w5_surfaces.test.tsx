import { readFileSync } from "node:fs";
import path from "node:path";

import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ConnectorBinding, CatalogConnector, SyncConflict } from "../src/api/bridges";
import type { EstateSnapshot } from "../src/api/estate";
import type { ConsentView } from "../src/api/undercroft";

/**
 * R-4 part W · task W5 — Bridges & Gates, the Undercroft and the Study, on the
 * network.
 *
 * Written as assertions about **what must not appear**, because that is what
 * this task's diff is mostly about. Three of these surfaces drew a figure, a
 * tick or a control against a binding the platform does not have, and one of
 * those — a blank credential expiry rendered as calm — is the single place in
 * this app where getting it wrong is a security defect rather than a cosmetic
 * one. So the sharpest tests here look for a green lamp, a rupee sign, a zero
 * and a Connect button, and fail when they are found.
 *
 * The Undercroft's tests are different in kind: that surface asserts in prose
 * that each named endpoint answers today, so its test reads the source file and
 * checks the four strings that were wrong.
 */

const wire = vi.hoisted(() => ({
  catalog: [] as CatalogConnector[],
  bindings: [] as ConnectorBinding[],
  estate: null as unknown as EstateSnapshot,
  conflicts: [] as SyncConflict[],
  consent: null as unknown as ConsentView,
  social: [] as Record<string, unknown>[],
  bindingsThrow: null as string | null,
  consentThrow: null as string | null,
  /* the Study */
  passkeys: [] as Record<string, unknown>[],
  preferences: {} as Record<string, { value: unknown; learned?: boolean }>,
  balance: {} as Record<string, unknown>,
  subscription: {} as Record<string, unknown>,
  registered: 0,
  written: [] as { key: string; value: unknown }[],
  /* the Undercroft */
  routing: [] as Record<string, unknown>[],
  signals: [] as Record<string, unknown>[],
  runs: [] as Record<string, unknown>[],
}));

vi.mock("../src/api/bridges", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchCatalog: () => Promise.resolve(wire.catalog),
  fetchBindings: () =>
    wire.bindingsThrow === null
      ? Promise.resolve(wire.bindings)
      : Promise.reject(new Error(wire.bindingsThrow)),
  fetchSyncConflicts: () => Promise.resolve(wire.conflicts),
  fetchSocialConnections: () => Promise.resolve(wire.social),
}));

vi.mock("../src/api/estate", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchEstate: () => Promise.resolve(wire.estate),
}));

vi.mock("../src/api/undercroft", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchConsent: () =>
    wire.consentThrow === null
      ? Promise.resolve(wire.consent)
      : Promise.reject(new Error(wire.consentThrow)),
  fetchSignals: () => Promise.resolve(wire.signals),
  fetchTriggers: () => Promise.resolve([]),
  fetchEnvelopes: () => Promise.resolve([]),
  fetchRoutingDecisions: () => Promise.resolve(wire.routing),
  fetchFeatureFlags: () => Promise.resolve({ defaults: {}, numeric_defaults: {}, overrides: {} }),
}));

vi.mock("../src/api/entities", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchExecutions: () => Promise.resolve(wire.runs),
}));

vi.mock("../src/api/tenant", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchDefs: () => Promise.resolve([]),
}));

vi.mock("../src/api/study", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchMe: () =>
    Promise.resolve({
      id: "u1",
      email: "rahul@northwind.co",
      full_name: "Rahul",
      company_id: "c1",
      role: "Owner",
    }),
  fetchPreferences: () => Promise.resolve(wire.preferences),
  writePreference: (key: string, value: unknown) => {
    wire.written.push({ key, value });
    return Promise.resolve();
  },
  observeDensity: () => Promise.resolve(),
  fetchBalance: () => Promise.resolve(wire.balance),
  fetchSubscription: () => Promise.resolve(wire.subscription),
}));

vi.mock("../src/api/identity", () => ({
  fetchCompanyName: () => Promise.resolve("Northwind Textiles"),
}));

vi.mock("../src/api/authn", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  isPasskeySupported: () => true,
  listPasskeys: () => Promise.resolve(wire.passkeys),
  registerPasskey: () => {
    wire.registered += 1;
    return Promise.resolve();
  },
  deletePasskey: () => Promise.resolve(),
}));

import { BridgesSurface } from "../src/surfaces/BridgesSurface";
import { StudySurface } from "../src/surfaces/StudySurface";
import { UndercroftSurface } from "../src/surfaces/UndercroftSurface";

afterEach(() => {
  cleanup();
  wire.bindingsThrow = null;
  wire.consentThrow = null;
  wire.registered = 0;
  wire.written = [];
});

/* ------------------------------------------------------------------ fixtures */

function connector(over: Partial<CatalogConnector> = {}): CatalogConnector {
  return {
    connector_id: "zoho_books",
    domain: "finance",
    display_name: "Zoho Books (Accounting)",
    backend: "own_adapter",
    auth: "oauth2",
    masters: ["Invoice", "Contact"],
    bindable: true,
    ...over,
  };
}

function binding(over: Record<string, unknown> = {}): ConnectorBinding {
  return {
    connector_id: "zoho_books",
    status: "active",
    cost_sku: "mcp-zoho-books",
    tool_allow: ["list_invoices"],
    write_allow: [],
    has_credential: true,
    last_error: null,
    ...over,
  };
}

function estate(bridges: EstateSnapshot["bridges"]): EstateSnapshot {
  return {
    estate: {
      loop_id: null,
      pulse: { beat_at: null, healthy: true },
      local_time: "2026-07-31T21:41:00+05:30",
      phase: "night",
      standing: "current",
    },
    quarters: [],
    districts: [],
    gatehouses: [],
    bridges,
    halls: [],
    monuments: [],
    beacons: [],
    glasshouse: { open_scenarios: 0, last_run_at: null },
    gallery: { versions: 0, terminated: 0 },
    as_of: "2026-07-31T16:11:00",
  };
}

function consentView(over: Partial<ConsentView> = {}): ConsentView {
  return {
    as_of: "2026-07-31T16:11:00",
    totals: { dnc: 3, unsubscribed: 1, granted: 12, denied: 2 },
    channels: [
      {
        channel: "whatsapp",
        posture: "restricted",
        reason: "the company posture row denies marketing on whatsapp",
        purposes: { marketing: false, transactional: true },
        dnc: 3,
        unsubscribed: 1,
        granted: 12,
        denied: 2,
      },
    ],
    entries: [],
    limit: 200,
    ...over,
  };
}

/** The estate's bridge block with the field the connectors door does not
 *  project. `null` on every real row — that is the gap under test. */
function projected(expiresAt: string | null): EstateSnapshot["bridges"] {
  return [
    {
      binding_id: "b1",
      connector: "zoho_books",
      state: "active",
      credentials_expire_at: expiresAt,
      conflicts_open: 0,
    },
  ];
}

function loadedBridges(): void {
  wire.catalog = [connector()];
  wire.bindings = [binding()];
  wire.estate = estate(projected(null));
  wire.conflicts = [];
  wire.consent = consentView();
  wire.social = [];
}

/* ========================================================================== */
/*  BRIDGES & GATES                                                           */
/* ========================================================================== */

describe("W5 — Bridges & Gates: the credential gap is the security case", () => {
  it("scaffolds on plates and never a spinner", () => {
    loadedBridges();
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    expect(container.querySelector("[data-lifecycle='scaffold']")).not.toBeNull();
    /* Bars must sit inside a drawn plate: `vh-skeleton`'s ground is a ~6/255
       delta on the raw canvas, so a scaffold on the page background is
       invisible and proves nothing. */
    expect(container.querySelector(".m-plate .lc-bar.vh-skeleton")).not.toBeNull();
  });

  it("draws no clean bill of health where no expiry was ever written", async () => {
    loadedBridges();
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    const block = await waitFor(() => {
      const found = container.querySelector(".bg-cred[data-expiry='unknown']");
      expect(found).not.toBeNull();
      return found!;
    });

    /* The whole finding in one assertion: no positive lamp anywhere in the
       credential block. A green tick against an expiry nobody has ever written
       would tell a tenant their keys have been checked. */
    expect(block.querySelector(".m-lamp[data-positive]")).toBeNull();
    expect(block.textContent).toContain("not a clean bill of health");
  });

  it("keeps the gap block whether or not a bridge is under repair", async () => {
    loadedBridges();
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".bg-gap")).not.toBeNull();
    });
    const gap = container.querySelector(".bg-gap")!.textContent ?? "";
    expect(gap).toContain("nothing has ever written one");
    /* And it names the second layer wiring found: the endpoint a reader would
       check does not even return the column. */
    expect(gap).toContain("does not even return the column");
  });

  it("renders the expiry the day one is written, rather than the gap", async () => {
    loadedBridges();
    wire.estate = estate(projected("2026-09-01T00:00:00"));
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".bg-cred[data-expiry='known']")).not.toBeNull();
    });
    expect(container.querySelector(".bg-cred[data-expiry='known']")!.textContent).toContain(
      "2026-09-01",
    );
  });

  it("invents no answer to which system masters an object", async () => {
    loadedBridges();
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".bg-master-table")).not.toBeNull();
    });
    const body = container.querySelector(".bg-master-table tbody")!;
    /* The catalogue's objects are real and are shown. The declaration is not a
       read this platform serves, so the cell says so — and in particular it
       does not say "Zoho Books", which is the guess a reader would make. */
    expect(body.textContent).toContain("Invoice");
    expect(body.textContent).toContain("not a read this estate serves");
    expect(body.textContent).not.toContain("Zoho Books");
  });

  it("gives a settled conflict no gold and no decision to make", async () => {
    loadedBridges();
    wire.conflicts = [
      {
        signal_id: "sig-1",
        def_name: "Invoice",
        record_id: "INV-4468",
        losing_delta: { amount: "241750", terms: "Net 30" },
        connector: "zoho_books",
        created_at: "2026-07-30T13:41:00",
      },
    ];
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".bg-dispute")).not.toBeNull();
    });
    const dispute = container.querySelector(".bg-dispute")!;

    /* Master-wins was applied before the signal was raised, so nothing here is
       waiting on anybody — and §2.1 gives gold to nothing else. */
    expect(dispute.querySelector(".m-lamp[data-lit]")).toBeNull();
    expect(dispute.querySelector(".bg-dispute-waiting")).toBeNull();
    expect(dispute.textContent).toContain("The master already won");
    expect(dispute.textContent).toContain("Nothing is waiting on you");
    /* One side, because one side is what the signal carries. */
    expect(dispute.textContent).toContain("INV-4468");
    expect(dispute.querySelectorAll(".bg-dispute button").length).toBe(0);
  });

  it("draws no Connect control for a connector it cannot credential", async () => {
    loadedBridges();
    wire.catalog = [connector(), connector({ connector_id: "stripe_payouts", display_name: "Stripe", auth: "api_key" })];
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".bg-avail")).not.toBeNull();
    });
    const catalogue = container.querySelector(".bg-avail")!;
    expect(catalogue.textContent).toContain("Stripe");
    expect(
      [...catalogue.querySelectorAll("button")].map((b) => b.textContent ?? ""),
      "a bind posted with no credentials succeeds and leaves a binding that cannot authenticate",
    ).toEqual([]);
    /* The gate is named from the certified table so the claim is checkable. */
    expect(container.textContent).toContain("POST /ai/connectors/{connector_id}/bind");
  });

  it("says a failed load is not an empty edge", async () => {
    loadedBridges();
    wire.bindingsThrow = "502 from the connectors service";
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector("[data-state='failed']")).not.toBeNull();
    });
    const failed = container.querySelector("[data-state='failed']")!;
    expect(failed.textContent).toContain("This is not an empty");
    expect(failed.textContent).toContain("502 from the connectors service");
    /* The gates column is a different read and is unharmed by it. */
    expect(container.querySelector(".bg-gate")).not.toBeNull();
  });

  it("says an estate with no bindings is young rather than broken", async () => {
    loadedBridges();
    wire.bindings = [];
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector("[data-state='empty']")).not.toBeNull();
    });
    const empty = container.querySelector("[data-state='empty']")!;
    expect(empty.querySelector(".m-lamp[data-negative]")).toBeNull();
    expect(empty.textContent).toContain("Nothing is connected");
  });
});

describe("W5 — Bridges & Gates: consent has an endpoint now", () => {
  it("prints the registry's own reason rather than a second copy of the rules", async () => {
    loadedBridges();
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".bg-gate")).not.toBeNull();
    });
    const gate = container.querySelector(".bg-gate")!;
    expect(gate.textContent).toContain(
      "the company posture row denies marketing on whatsapp",
    );
    /* A restricted gate is not lit green. */
    expect(gate.querySelector(".m-lamp[data-positive]")).toBeNull();
  });

  it("shows no send volume, because nothing counts one", async () => {
    loadedBridges();
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".bg-gate")).not.toBeNull();
    });
    const gate = container.querySelector(".bg-gate")!.textContent ?? "";
    expect(gate).not.toContain("last seven days");
    expect(gate).toContain("is not counted anywhere");
  });

  it("refuses a consent grant and says why, rather than reporting one kept", async () => {
    loadedBridges();
    const onEcho = vi.fn();
    const { container, findByText } = render(<BridgesSurface onEcho={onEcho} />);
    const button = await waitFor(() => {
      const found = [...container.querySelectorAll("button")].find((b) =>
        (b.textContent ?? "").includes("Open this gate"),
      );
      expect(found).not.toBeUndefined();
      return found!;
    });

    fireEvent.click(button);

    /* `certified.consent` is gate kind `absent`: the hook performs nothing,
       echoes nothing, and returns the platform's own sentence. */
    await findByText(/This estate cannot record consent yet/);
    expect(onEcho).not.toHaveBeenCalled();
  });

  it("says an empty registry is young rather than permissive", async () => {
    loadedBridges();
    wire.consent = consentView({ channels: [], totals: { dnc: 0, unsubscribed: 0, granted: 0, denied: 0 } });
    const { container } = render(<BridgesSurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.textContent).toContain("Nobody has asked this estate to stop");
    });
    expect(container.textContent).toContain("young estate rather than a permissive one");
  });
});

/* ========================================================================== */
/*  THE UNDERCROFT                                                            */
/* ========================================================================== */

const UNDERCROFT_SOURCE = readFileSync(
  path.resolve(__dirname, "..", "src", "surfaces", "UndercroftSurface.tsx"),
  "utf8",
);

/** Every endpoint the shipped schema declares, without the `/api/v1` mount. */
const OPENAPI_PATHS: Set<string> = new Set(
  Object.keys(
    (
      JSON.parse(
        readFileSync(path.resolve(__dirname, "..", "src", "api", "openapi.json"), "utf8"),
      ) as { paths: Record<string, unknown> }
    ).paths,
  ).map((route) => route.replace(/^\/api\/v1/, "")),
);

describe("W5 — the Undercroft names endpoints that answer", () => {
  it("every bay's source is a path the schema declares", () => {
    const declared = [...UNDERCROFT_SOURCE.matchAll(/source: "(GET [^"]+)"/g)].map(
      (match) => match[1]!.slice(4),
    );
    /* Eight of the nine name a door; the manifest inspector names memory. */
    expect(declared.length).toBe(8);
    const missing = declared.filter((route) => !OPENAPI_PATHS.has(route));
    expect(
      missing,
      "this is the one surface that asserts in prose that each named endpoint answers today",
    ).toEqual([]);
  });

  it("carries none of the four strings that were wrong", () => {
    /* `/ai/intelligence/routing` is a prefix of the real path, so the check is
       on the closing quote rather than on the substring. */
    for (const wrong of [
      '"GET /ai/tenant-schema/defs"',
      '"GET /ai/intelligence/routing"',
      '"GET /ai/flags"',
    ]) {
      expect(UNDERCROFT_SOURCE, `${wrong} does not answer`).not.toContain(wrong);
    }
  });

  it("does not claim an endpoint behind the manifest inspector", () => {
    /* The log is in memory, this session only. `GET /ai/genui/manifest` serves
       a manifest and has never served a history of them. */
    expect(UNDERCROFT_SOURCE).toContain('source: "in memory');
  });

  it("puts no count in the rail against a bay it has not loaded", async () => {
    /* One bay loads at a time, so a figure beside the other eight would be
       eight numbers nobody measured.

       This asserted `.uc-bay-count` was absent — a class NO code path rendered
       and which survived only as a dead rule in `undercroft.css`. It could not
       fail. The rule is deleted and the assertion now reads the rail that
       actually exists: no rail entry may contain a digit. That breaks the
       moment someone adds a count, which is the whole point. */
    const { container } = render(<UndercroftSurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".uc-bays")).not.toBeNull();
    });

    const entries = [...container.querySelectorAll(".uc-bays li")];
    expect(entries.length, "the rail scan matched nothing").toBeGreaterThan(5);
    for (const entry of entries) {
      expect(
        entry.textContent ?? "",
        `a rail entry carries a figure: "${entry.textContent}"`,
      ).not.toMatch(/\d/);
    }
  });

  it("prints no cost in the routing bay, and says where cost lives", async () => {
    wire.routing = [
      {
        id: "r1",
        run_id: "3f2a0c11",
        task_type: "compose chase",
        model_registry_id: "sonnet-5",
        reason: "complexity 0.62 · default band",
        fallback_used: false,
        signals: null,
        created_at: "2026-07-31T09:41:00",
      },
    ];
    const { container, findByText } = render(<UndercroftSurface onEcho={vi.fn()} />);
    fireEvent.click(await findByText("Routing"));

    await waitFor(() => {
      expect(container.querySelector(".uc-table")).not.toBeNull();
    });
    const pane = container.querySelector(".uc-body")!.textContent ?? "";
    const head = container.querySelector(".uc-table thead")!.textContent ?? "";
    const body = container.querySelector(".uc-table tbody")!.textContent ?? "";

    expect(pane).toContain("sonnet-5");
    expect(pane).toContain("complexity 0.62");
    /* `RoutingDecision` stores no cost at all. Not a rupee, not a dollar, not
       a zero — and the reason is stated in prose rather than the column being
       silently dropped. */
    expect(head).not.toMatch(/cost/i);
    expect(body).not.toContain("₹");
    expect(body).not.toMatch(/USD/);
    expect(pane).toContain("There is no cost column, and there cannot be one");
    expect(pane).toContain("attributed against the");
  });

  it("prints the cost the run actually carries in the traces bay", async () => {
    wire.runs = [
      {
        id: "9c11aaaa",
        entity_id: "3f2a0c11",
        status: "completed",
        total_cost_usd: 0.0412,
        execution_time_ms: 1840,
        error_message: null,
        started_at: "2026-07-31T09:40:00",
        completed_at: "2026-07-31T09:40:02",
        created_at: "2026-07-31T09:40:00",
      },
    ];
    const { container, findByText } = render(<UndercroftSurface onEcho={vi.fn()} />);
    fireEvent.click(await findByText("Run traces"));
    await waitFor(() => {
      expect(container.querySelector(".uc-table")).not.toBeNull();
    });
    expect(container.querySelector(".uc-body")!.textContent).toContain("USD 0.0412");
  });

  it("renders nothing, not a zero, for a signal nobody has consumed", async () => {
    wire.signals = [
      {
        id: "sig-9f1caaaa",
        source: "connector",
        type: "whatsapp.inbound",
        urgency: null,
        confidence: null,
        trust: null,
        status: "pending",
        object_refs: null,
        payload: null,
        dedupe_key: null,
        owner_process_id: null,
        consumed_by_run_id: null,
        park_review_at: null,
        attempts: 1,
        replayed_from: null,
        last_error: null,
        created_at: "2026-07-31T09:36:12",
        consumed_at: null,
      },
    ];
    const { container, findByText } = render(<UndercroftSurface onEcho={vi.fn()} />);
    fireEvent.click(await findByText("Signals"));
    await waitFor(() => {
      expect(container.querySelector(".uc-table tbody tr")).not.toBeNull();
    });
    const cells = [...container.querySelectorAll(".uc-table tbody tr td")];
    const consumed = cells[cells.length - 1]!;
    expect(consumed.textContent).toBe("");
  });

  it("says an empty bay is empty, in prose, rather than heading no rows", async () => {
    wire.routing = [];
    const { container, findByText } = render(<UndercroftSurface onEcho={vi.fn()} />);
    fireEvent.click(await findByText("Routing"));
    await waitFor(() => {
      expect(container.querySelector("[data-state='empty']")).not.toBeNull();
    });
    expect(container.querySelector("[data-state='empty']")!.textContent).toContain(
      "No model has been chosen yet",
    );
  });
});

/* ========================================================================== */
/*  THE STUDY                                                                 */
/* ========================================================================== */

function loadedStudy(): void {
  wire.passkeys = [
    { id: "pk-1", label: "MacBook Touch ID", created_at: "2026-03-12T10:00:00", last_used_at: null },
    { id: "pk-2", label: null, created_at: "2026-06-02T10:00:00", last_used_at: "2026-07-30T08:00:00" },
  ];
  wire.preferences = {};
  wire.balance = { account_model: "pay_as_you_go", total_available: 4200, daily_credits: 200 };
  wire.subscription = { subscription: null, account_model: "pay_as_you_go" };
}

describe("W5 — the Study: passkeys have to actually work", () => {
  it("runs the real registration ceremony rather than echoing one", async () => {
    loadedStudy();
    const onEcho = vi.fn();
    const { container, findByText } = render(<StudySurface onEcho={onEcho} />);
    fireEvent.click(await findByText("Add a passkey"));

    await waitFor(() => {
      expect(wire.registered).toBe(1);
    });
    await waitFor(() => {
      expect(onEcho).toHaveBeenCalledWith("added a passkey");
    });
    expect(container.querySelector(".sy-keys")).not.toBeNull();
  });

  it("names an unlabelled credential by its id rather than inventing a device", async () => {
    loadedStudy();
    const { container } = render(<StudySurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelectorAll(".sy-key").length).toBe(2);
    });
    const labels = [...container.querySelectorAll(".sy-key-label")].map(
      (node) => node.textContent ?? "",
    );
    expect(labels).toEqual(["MacBook Touch ID", "pk-2"]);
    /* And no "this device" chip: nothing on the wire says which credential
       belongs to the machine you are sitting at. */
    expect(container.querySelector(".sy-key-here")).toBeNull();
  });

  it("says what no passkey costs you, rather than showing an empty list", async () => {
    loadedStudy();
    wire.passkeys = [];
    const { container } = render(<StudySurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector("[data-state='empty']")).not.toBeNull();
    });
    expect(container.querySelector("[data-state='empty']")!.textContent).toContain(
      "no certified act can be completed",
    );
  });
});

describe("W5 — the Study: one preference is read, and two are not", () => {
  it("draws one switch, and the unread keys as absences", async () => {
    loadedStudy();
    const { container } = render(<StudySurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".sy-toggles")).not.toBeNull();
    });
    /* `notify.whatsapp_mirror` is the only preference anything on the platform
       consults. A switch for the other two would write a row nothing reads and
       report it as kept. */
    expect(container.querySelectorAll("[role='switch']").length).toBe(1);
    expect(container.querySelectorAll(".sy-toggle[data-absent]").length).toBe(2);
    expect(container.textContent).toContain("notify.whatsapp_mirror");
  });

  it("reads an absent mirror preference as ON, because the platform does", async () => {
    loadedStudy();
    const { container } = render(<StudySurface onEcho={vi.fn()} />);
    const toggle = await waitFor(() => {
      const found = container.querySelector("[role='switch']");
      expect(found).not.toBeNull();
      return found!;
    });
    /* The mirror reads `value not in ("off", False)`. An unchecked box for a
       preference nobody stated would tell a tenant they had turned off
       something that is running. */
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    expect(container.textContent).toContain("never stated, and on by default");
  });

  it("turns the mirror off by writing the store's own word", async () => {
    loadedStudy();
    const { container } = render(<StudySurface onEcho={vi.fn()} />);
    const toggle = await waitFor(() => {
      const found = container.querySelector("[role='switch']");
      expect(found).not.toBeNull();
      return found!;
    });
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(wire.written).toEqual([{ key: "notify.whatsapp_mirror", value: "off" }]);
    });
    await waitFor(() => {
      expect(container.querySelector("[role='switch']")!.getAttribute("aria-checked")).toBe(
        "false",
      );
    });
  });

  it("invents no learned density and no observation count", async () => {
    loadedStudy();
    const { container } = render(<StudySurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".sy-density")).not.toBeNull();
    });
    const panel = container.textContent ?? "";
    /* `learn_preference` is never called with a density key anywhere in the
       backend and no job turns observations into a preference, so "learned:
       novice · 4 observations" was two figures nobody measured. */
    expect(panel).not.toMatch(/learned:/);
    expect(panel).not.toMatch(/\d+ observations/);
    expect(panel).toContain("No room in the estate reads this yet");
  });
});

describe("W5 — the Study: the wallet is credits, and nobody stamped a currency", () => {
  it("prints no rupee sign and no runway", async () => {
    loadedStudy();
    const { container } = render(<StudySurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".sy-balance")).not.toBeNull();
    });
    const wallet = container.querySelector(".sy-wallet")!.textContent ?? "";
    expect(wallet).toContain("4,200");
    expect(wallet).toContain("credits");
    expect(wallet, "the body carries buckets of credits and stamps no currency").not.toContain(
      "₹",
    );
    expect(wallet, "nothing reports a burn rate, so the denominator was invented").not.toMatch(
      /About \d+ days/,
    );
  });

  it("renders nothing for a bucket the endpoint did not send", async () => {
    loadedStudy();
    const { container } = render(<StudySurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".sy-balance")).not.toBeNull();
    });
    const labels = [...container.querySelectorAll(".sy-wallet .sy-fact dt")].map(
      (node) => node.textContent ?? "",
    );
    /* Only `daily_credits` came down the wire. A topped-up or subscription
       bucket rendered as 0 would be a balance nobody reported. */
    expect(labels).toEqual(["Daily"]);
  });

  it("marks no rung on the dunning ladder it cannot read", async () => {
    loadedStudy();
    const { container } = render(<StudySurface onEcho={vi.fn()} />);
    await waitFor(() => {
      expect(container.querySelector(".sy-rungs")).not.toBeNull();
    });
    /* The ladder is always visible — that is the panel's whole point — and no
       rung is claimed as yours, because this desk reads no standing. */
    expect(container.querySelectorAll(".sy-rung").length).toBe(4);
    expect(container.querySelectorAll(".sy-rung[data-here]").length).toBe(0);
    expect(container.textContent).toContain("None of these is marked as yours");
  });
});
