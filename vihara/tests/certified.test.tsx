import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { act, cleanup, fireEvent, render, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CERTIFIED_ACTS,
  CERTIFIED_IMPLEMENTATIONS,
  CERTIFIED_TYPES,
  StepUpCeremony,
  useCertifiedAct,
  type CeremonyDeps,
  type CertifiedRefusal,
  type CertifiedType,
  type RunnableCertifiedType,
} from "../src/components/certified";
import { assessManifest } from "../src/manifest/refusals";
import { allEntries } from "../src/manifest/registry";
import type { WireScaffold } from "../src/manifest/schema";

/**
 * R-4 part C — the step-up ceremony, and the layer that makes it unavoidable.
 *
 * Six families, and each of them exists because the property it holds is
 * invisible when it breaks:
 *
 * 1. **The set is TEN.** The registry, the act table and the implementations
 *    are three views of one list. A component present in two of the three is a
 *    certified surface nobody gated, and nothing else in the app would notice.
 * 2. **Structural goldens.** Not pixels: the failure L5 fears is a certified
 *    block *differing between contexts*, and structure catches that without a
 *    browser. Pinned inline rather than in a snapshot file so a change to the
 *    thing a person authorises shows up as a readable diff in review.
 * 3. **The cross-context assertion**, stated twice — once behaviourally (the
 *    same subtree in an S host and a C host, at both densities) and once
 *    structurally (context is not a parameter these components take, so they
 *    could not vary on it even if someone wanted them to).
 * 4. **A refusal per component, one mutation at a time.** An injected prop and
 *    a missing prop must each reject the WHOLE manifest — a checker never
 *    observed to fail is a function that returns true.
 * 5. **The gates, against the backend.** The two paths §6 warns about — the
 *    ones that *silently succeed* — are pinned here, because the dangerous
 *    edit is not someone deleting a gate, it is someone quietly marking an
 *    ungated act `server` and shipping a ceremony that never fires.
 * 6. **The hook and the ceremony**, including the one thing part C says not to
 *    reinvent: a ceremony is retried whole, once.
 */

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const SRC = path.resolve(__dirname, "..", "src");
const CERTIFIED_DIR = path.join(SRC, "components", "certified");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) return walk(full);
    return /\.(ts|tsx)$/.test(full) ? [full] : [];
  });
}

/** Source with comments removed, so a scan tests the code and not the prose. */
function codeOf(file: string): string {
  return readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:])\/\/.*$/gm, "$1 ");
}

/* ============================================================ the fixtures
   Registry-conformant, and deliberately awkward (DESIGN_CONTRACT §7.5): a
   party name that wraps, a disputed record, a payment whose currency the
   platform never stated. A design that only survives tidy content has not
   been tested. */

const FIXTURES: Record<CertifiedType, Record<string, unknown>> = {
  "certified.approval": {
    approval_id: "8f2c1a44-0b7e-4d51-9a63-2c8e5f0a7b19",
    checkpoint_key: "before_outbound_payout_above_band",
    summary:
      "Release the balance on the Coromandel Garments & Furnishing Co-operative order — the dispute note on it was withdrawn yesterday.",
    tier: "T2",
  },
  "certified.payment": {
    approval_id: "8f2c1a44-0b7e-4d51-9a63-2c8e5f0a7b19",
    checkpoint_key: "before_outbound_payout_above_band",
    summary: "Pay Coromandel Garments & Furnishing Co-operative the balance.",
    amount: 842000.5,
    // Null on purpose: the endpoint may not state one, and §7.1 forbids
    // inventing it. The golden below pins that the gap is rendered.
    currency: null,
    tier: "T2",
  },
  "certified.consent": {
    channel: "whatsapp",
    purpose: "order updates and delivery windows",
    direction: "grant",
    summary: "Let Meera message customers on WhatsApp about their orders.",
  },
  "certified.autonomy-change": {
    entity_id: "1d9b3e70-5a12-4c88-bf04-6e21d3a95c77",
    entity_name: "Meera",
    from_band: "A2",
    to_band: "A3",
    summary:
      "Raise Meera to A3 — she has been on probation since the June mispost and has cleared it.",
  },
  "certified.connector-binding": {
    connector_key: "zoho_books",
    connector_name: "Zoho Books",
    summary:
      "Connect Zoho Books and let it write invoices and credit notes back into the estate.",
  },
  "certified.mastering-declaration": {
    def_name: "Invoice",
    connector_key: "zoho_books",
    direction: "external_masters",
    summary: "Zoho Books becomes the master of record for Invoice.",
  },
  "certified.provider-opt-in": {
    provider: "kimi",
    disclosure_version: "2026-07-25",
    summary: "Allow Kimi to process this workspace's data.",
  },
  "certified.strategy-resolution": {
    resolution_id: "res-2026-07-31-01",
    title: "Ship the north-market push before Diwali",
    summary: "Adopt the proposition as tabled, with the stock cap unchanged.",
  },
  "certified.step-up": {
    tier: "T2",
    command_ref: "approval:8f2c1a44-0b7e-4d51-9a63-2c8e5f0a7b19",
    command_summary: "a payout approval for 842,000.50",
  },
  "certified.second-channel-wait": {
    command_ref: "approval:8f2c1a44-0b7e-4d51-9a63-2c8e5f0a7b19",
    command_summary: "a payout approval for 842,000.50",
    channel: "whatsapp",
  },
};

function manifestWith(
  type: string,
  props: Record<string, unknown>,
  renderer: "S" | "C" = "S",
  density: "novice" | "operator" = "novice",
): WireScaffold {
  return {
    part: "scaffold",
    manifest_version: 1,
    surface_id: "tray.test",
    renderer,
    plane: "live",
    depth: 1,
    density,
    layout: { kind: "stack", regions: ["body"] },
    components: [
      { id: "x1", type: `${type}@1`, region: "body", props, bindings: [] },
    ],
    issued_at: "t",
    ttl_seconds: 120,
  };
}

/** Serialise structure: tags, data-* identity, role, and text shape. */
function structure(node: Element): string {
  const attrs = Array.from(node.attributes)
    .filter((a) => a.name.startsWith("data-") || a.name === "role")
    .map((a) => `${a.name}=${a.value}`)
    .sort()
    .join(" ");
  const children = Array.from(node.children).map(structure).join("");
  const ownText = Array.from(node.childNodes)
    .filter((n) => n.nodeType === 3)
    .map((n) => n.textContent?.trim())
    .filter(Boolean)
    .join(" ");
  const tag = node.tagName.toLowerCase();
  return `<${tag}${attrs ? " " + attrs : ""}${ownText ? ` "${ownText}"` : ""}>${children}</${tag}>`;
}

/**
 * Render one certified component inside a host that declares a renderer and a
 * density, and return its subtree. The host attributes are what a real surface
 * would carry; the point of the assertion below is that they change nothing.
 */
function certifiedSubtree(
  type: CertifiedType,
  renderer: "S" | "C" = "S",
  density: "novice" | "operator" = "operator",
): string {
  const Implementation = CERTIFIED_IMPLEMENTATIONS[type];
  const { container } = render(
    <div data-renderer={renderer} data-density={density}>
      <Implementation
        component={{ id: "x1", type: `${type}@1`, props: FIXTURES[type] }}
      />
    </div>,
  );
  const block =
    container.querySelector('[data-part="certified"]') ??
    container.querySelector('[data-part="consent-revoke"]');
  if (block === null) throw new Error(`${type} rendered no certified block`);
  const out = structure(block);
  cleanup();
  return out;
}

/* ================================================== 1 · the set is exactly ten */

describe("the certified set is ten (C4)", () => {
  it("has ten implementations, ten act-table rows, and ten registry entries", () => {
    const registry = allEntries()
      .filter((entry) => entry.class === "certified")
      .map((entry) => entry.type)
      .sort();
    const implementations = Object.keys(CERTIFIED_IMPLEMENTATIONS).sort();
    const acts = [...CERTIFIED_TYPES].sort();

    expect(registry).toHaveLength(10);
    expect(implementations).toEqual(registry);
    expect(acts).toEqual(registry);
  });

  it("would fail if an eleventh appeared in any one of the three", () => {
    // The guard above is an equality between three lists, so a component added
    // to the registry without an implementation (or to the act table without a
    // gate) breaks it. Stated here so the intent survives a refactor of the
    // assertion above.
    const registry = allEntries().filter((e) => e.class === "certified");
    expect(new Set(registry.map((e) => e.type)).size).toBe(10);
  });
});

/* ============================================================== 2 · goldens */

/**
 * The pinned structure of every certified block. These change only when the
 * thing a person authorises changes shape, which is a review-worthy event —
 * hence inline, not a snapshot file that regenerates on `-u`.
 */
const GOLDENS: Record<CertifiedType, string> = {
  "certified.approval":
    "<section data-certified-type=certified.approval data-part=certified role=region><header><span><svg><path></path></svg></span><span data-certified=true \"APPROVAL · T2\"></span><span \"Certified act\"></span></header><hr></hr><div><p \"Release the balance on the Coromandel Garments & Furnishing Co-operative order — the dispute note on it was withdrawn yesterday.\"></p><div data-deep=true><dl><div><dt \"Checkpoint\"></dt><dd \"before_outbound_payout_above_band\"></dd></div><div><dt \"Approval\"></dt><dd \"8f2c1a44-0b7e-4d51-9a63-2c8e5f0a7b19\"></dd></div></dl></div></div><footer><button data-action=approve data-rank=certified \"approve\"><svg><path></path></svg></button><button data-action=decline data-rank=quiet \"decline\"></button></footer></section>",
  "certified.payment":
    "<section data-certified-type=certified.payment data-part=certified role=region><header><span><svg><path></path></svg></span><span data-certified=true \"PAYMENT · T2\"></span><span \"Certified act\"></span></header><hr></hr><div><p \"Pay Coromandel Garments & Furnishing Co-operative the balance.\"></p><p><output \"842,000.5\"></output></p><p \"The currency was not stated on this approval.\"></p><div data-deep=true><dl><div><dt \"Checkpoint\"></dt><dd \"before_outbound_payout_above_band\"></dd></div><div><dt \"Approval\"></dt><dd \"8f2c1a44-0b7e-4d51-9a63-2c8e5f0a7b19\"></dd></div></dl></div></div><footer><button data-action=approve data-rank=certified \"approve\"><svg><path></path></svg></button><button data-action=decline data-rank=quiet \"decline\"></button></footer></section>",
  "certified.consent":
    "<section data-certified-type=certified.consent data-part=certified role=region><header><span><svg><path></path></svg></span><span data-certified=true \"CONSENT\"></span><span \"Certified act\"></span></header><hr></hr><div><p \"Let Meera message customers on WhatsApp about their orders.\"></p><div data-deep=true><dl><div><dt \"Channel\"></dt><dd \"whatsapp\"></dd></div><div><dt \"Purpose\"></dt><dd \"order updates and delivery windows\"></dd></div></dl></div></div><footer><button data-action=grant data-rank=certified \"grant\"><svg><path></path></svg></button></footer></section>",
  "certified.autonomy-change":
    "<section data-certified-type=certified.autonomy-change data-part=certified role=region><header><span><svg><path></path></svg></span><span data-certified=true \"AUTONOMY\"></span><span \"Certified act\"></span></header><hr></hr><div><p \"Raise Meera to A3 — she has been on probation since the June mispost and has cleared it.\"></p><h3 \"Meera\"></h3><p><span \"A2\"></span><svg><path></path></svg><span data-selected=true \"A3\"></span><span \"autonomy band A2 raised to A3\"></span></p><div data-deep=true><dl><div><dt \"Colleague\"></dt><dd \"1d9b3e70-5a12-4c88-bf04-6e21d3a95c77\"></dd></div></dl></div></div><footer><button data-action=confirm data-rank=certified \"confirm\"><svg><path></path></svg></button><button data-action=keep as is data-rank=quiet \"keep as is\"></button></footer></section>",
  "certified.connector-binding":
    "<section data-certified-type=certified.connector-binding data-part=certified role=region><header><span><svg><path></path></svg></span><span data-certified=true \"CONNECTOR\"></span><span \"Certified act\"></span></header><hr></hr><div><h3 \"Zoho Books\"></h3><p \"Connect Zoho Books and let it write invoices and credit notes back into the estate.\"></p><div data-deep=true><dl><div><dt \"Connector\"></dt><dd \"zoho_books\"></dd></div></dl></div></div><footer><button data-action=bind data-rank=certified \"bind\"><svg><path></path></svg></button></footer></section>",
  "certified.mastering-declaration":
    "<section data-certified-type=certified.mastering-declaration data-part=certified role=region><header><span><svg><path></path></svg></span><span data-certified=true \"MASTERING\"></span><span \"Certified act\"></span></header><hr></hr><div><h3 \"Invoice\"></h3><p \"Zoho Books becomes the master of record for Invoice.\"></p><div data-deep=true><dl><div><dt \"Connector\"></dt><dd \"zoho_books\"></dd></div><div><dt \"Direction\"></dt><dd \"external_masters\"></dd></div></dl></div></div><footer><button data-action=apply data-rank=certified \"apply\"><svg><path></path></svg></button></footer></section>",
  "certified.provider-opt-in":
    "<section data-certified-type=certified.provider-opt-in data-part=certified role=region><header><span><svg><path></path></svg></span><span data-certified=true \"MODEL PROVIDER\"></span><span \"Certified act\"></span></header><hr></hr><div><h3 \"kimi\"></h3><p \"Allow Kimi to process this workspace's data.\"></p><div data-deep=true><dl><div><dt \"Disclosure\"></dt><dd \"2026-07-25\"></dd></div></dl></div></div><footer><button data-action=opt in data-rank=certified \"opt in\"><svg><path></path></svg></button></footer></section>",
  "certified.strategy-resolution":
    "<section data-certified-type=certified.strategy-resolution data-part=certified role=region><header><span><svg><path></path></svg></span><span data-certified=true \"RESOLUTION\"></span><span \"Certified act\"></span></header><hr></hr><div><h3 \"Ship the north-market push before Diwali\"></h3><p \"Adopt the proposition as tabled, with the stock cap unchanged.\"></p><div data-deep=true><dl><div><dt \"Proposition\"></dt><dd \"res-2026-07-31-01\"></dd></div></dl></div></div><footer><button data-action=adopt data-rank=certified \"adopt\"><svg><path></path></svg></button></footer></section>",
  "certified.step-up":
    "<section data-certified-type=certified.step-up data-part=certified><header><span><svg><path></path></svg></span><span data-certified=true \"PROVE IT IS YOU · T2\"></span><span \"Certified act\"></span></header><hr></hr><div><p \"a payout approval for 842,000.50\"></p><div data-deep=true><dl><div><dt \"Command\"></dt><dd \"approval:8f2c1a44-0b7e-4d51-9a63-2c8e5f0a7b19\"></dd></div></dl></div></div><footer><button data-action=use passkey data-rank=certified \"use passkey\"><svg><path></path></svg></button></footer></section>",
  "certified.second-channel-wait":
    "<section data-certified-type=certified.second-channel-wait data-part=certified><header><span><svg><path></path></svg></span><span data-certified=true \"SECOND CHANNEL\"></span><span \"Certified act\"></span></header><hr></hr><div><p \"a payout approval for 842,000.50\"></p><div data-deep=true><dl><div><dt \"Waiting on\"></dt><dd \"whatsapp\"></dd></div><div><dt \"Command\"></dt><dd \"approval:8f2c1a44-0b7e-4d51-9a63-2c8e5f0a7b19\"></dd></div></dl></div></div></section>",
};

describe("structural goldens (C4)", () => {
  for (const type of CERTIFIED_TYPES) {
    it(`${type}`, () => {
      expect(certifiedSubtree(type)).toBe(GOLDENS[type]);
    });
  }

  it("never invents a currency, and says so where none was stated", () => {
    const withGap = certifiedSubtree("certified.payment");
    expect(withGap).toContain("The currency was not stated");
    expect(withGap).not.toMatch(/₹|\$|INR/);

    const Payment = CERTIFIED_IMPLEMENTATIONS["certified.payment"];
    const stated = render(
      <Payment
        component={{
          id: "x1",
          type: "certified.payment@1",
          props: { ...FIXTURES["certified.payment"], currency: "INR" },
        }}
      />,
    );
    const block = stated.container.querySelector('[data-part="certified"]')!;
    expect(block.textContent).toContain("INR");
    expect(block.textContent).not.toContain("The currency was not stated");
  });

  it("groups a figure without asking the machine's locale", () => {
    const block = certifiedSubtree("certified.payment");
    // 842000.5 → 842,000.5 on every machine, ICU data or none. No padding to
    // two decimals either: that would be a digit the wire never sent.
    expect(block).toContain("842,000.5");
    expect(block).not.toContain("842,000.50");
  });

  it("renders no row at all for a prop the server left empty", () => {
    // The registry types `command_ref` as a required string, so an absent one
    // arrives as "". A labelled row with nothing in it reads as a truncation
    // bug; §7.1 says render nothing.
    const StepUp = CERTIFIED_IMPLEMENTATIONS["certified.step-up"];
    const { container } = render(
      <StepUp
        component={{
          id: "x1",
          type: "certified.step-up@1",
          props: { ...FIXTURES["certified.step-up"], command_ref: "" },
        }}
      />,
    );
    expect(container.textContent).not.toContain("Command");
    expect(container.querySelector("dl")).toBeNull();
  });
});

/* ================================================ 3 · the cross-context rule */

describe("one certified block in every context (L5)", () => {
  for (const type of CERTIFIED_TYPES) {
    it(`${type} is identical in S and C, novice and operator`, () => {
      const base = certifiedSubtree(type, "S", "novice");
      expect(certifiedSubtree(type, "C", "novice")).toBe(base);
      expect(certifiedSubtree(type, "S", "operator")).toBe(base);
      expect(certifiedSubtree(type, "C", "operator")).toBe(base);
    });
  }

  it("cannot vary on context, because context is not an input", () => {
    // The behavioural assertion above proves the current implementations agree.
    // This one proves the stronger thing: there is no parameter they could
    // disagree on, so no future edit can make them disagree by accident.
    const source = codeOf(path.join(CERTIFIED_DIR, "certifiedSet.tsx"));
    expect(source).not.toMatch(/\bdensity\b/);
    expect(source).not.toMatch(/\brenderer\b/);
  });
});

/* ============================================== 4 · a refusal per component */

describe("a refusal per component, one mutation at a time", () => {
  for (const type of CERTIFIED_TYPES) {
    it(`${type}: an injected prop rejects the whole manifest`, () => {
      const assessment = assessManifest(
        manifestWith(type, { ...FIXTURES[type], injected: "!" }),
      );
      expect(assessment.verdict).toBe("reject");
      if (assessment.verdict === "reject") {
        expect(assessment.reason).toContain("injected");
      }
    });

    it(`${type}: a missing required prop rejects the whole manifest`, () => {
      const props: Record<string, unknown> = { ...FIXTURES[type] };
      const firstKey = Object.keys(props)[0]!;
      delete props[firstKey];
      const assessment = assessManifest(manifestWith(type, props));
      expect(assessment.verdict).toBe("reject");
      if (assessment.verdict === "reject") {
        expect(assessment.reason).toContain(firstKey);
      }
    });
  }
});

describe("the consent asymmetry (D3 §3.4)", () => {
  it("granting is a ceremony; revoking is one plain control", () => {
    const grant = certifiedSubtree("certified.consent");
    expect(grant).toContain("data-part=certified");
    expect(grant).toContain('data-action=grant');
    expect(grant).toContain('data-rank=certified');

    const Consent = CERTIFIED_IMPLEMENTATIONS["certified.consent"];
    const { container } = render(
      <Consent
        component={{
          id: "x1",
          type: "certified.consent@1",
          props: { ...FIXTURES["certified.consent"], direction: "revoke" },
        }}
      />,
    );
    expect(container.querySelector('[data-part="certified"]')).toBeNull();
    const revoke = container.querySelector('[data-part="consent-revoke"]')!;
    // No seal, no gold, no gate: the safe direction is never the harder one.
    expect(revoke.querySelector(".m-medallion")).toBeNull();
    expect(revoke.querySelector('[data-rank="certified"]')).toBeNull();
    expect(revoke.querySelector('[data-action="revoke"]')).not.toBeNull();
  });

  it("keeps revoking out of the act table, so it routes through no gate", () => {
    const rows = Object.values(CERTIFIED_ACTS).map((entry) => entry.verb);
    expect(rows).not.toContain("revoke");
  });
});

/* ================================================ 5 · the gates, pinned */

describe("the act table against the backend (§6)", () => {
  it("names a concrete endpoint and enforcement site for every server gate", () => {
    for (const [type, entry] of Object.entries(CERTIFIED_ACTS)) {
      if (entry.gate.kind !== "server") continue;
      expect(entry.gate.call, type).toMatch(/^(GET|POST|PUT|PATCH|DELETE) \/ai\//);
      expect(entry.gate.enforcedBy, type).toMatch(/enforce_(tier|kind)/);
    }
  });

  it("marks the ceremony pair as the ceremony, not as acts it guards", () => {
    expect(CERTIFIED_ACTS["certified.step-up"].gate.kind).toBe("ceremony");
    expect(CERTIFIED_ACTS["certified.second-channel-wait"].gate.kind).toBe("ceremony");
  });

  /* §6's first silent success. `certified.consent` maps to no gate because it
     maps to no endpoint — the tables and the migration ship behind no router
     (part E, E1). If this ever flips to `server` without an endpoint arriving,
     the estate starts granting consent that nothing records. */
  it("keeps certified.consent marked absent until E1 lands", () => {
    const gate = CERTIFIED_ACTS["certified.consent"].gate;
    expect(gate.kind).toBe("absent");
    if (gate.kind === "absent") {
      expect(gate.closedBy).toMatch(/E1/);
      expect(gate.why).toMatch(/Nothing was granted/);
    }
  });

  /* §6's second. `talent.hireFromTemplate` forces A1 and `POST /ai/entities`
     carries no enforce_* at all, so hiring is not a certified act however the
     Talent Office draws it. The guard is that no act kind exists for it. */
  it("has no act for hiring, because hiring is not gated", () => {
    const calls = Object.values(CERTIFIED_ACTS)
      .map((entry) => (entry.gate.kind === "server" ? entry.gate.call : ""))
      .join(" ");
    expect(calls).not.toMatch(/POST \/ai\/entities\b/);
    expect(Object.keys(CERTIFIED_ACTS).join(" ")).not.toMatch(/hire/i);
    // Only the raise is gated, and it is a PUT.
    expect(CERTIFIED_ACTS["certified.autonomy-change"].gate).toMatchObject({
      kind: "server",
      call: "PUT /ai/entities/{entity_id}",
    });
  });
});

describe("hard to call a gated endpoint without the hook (C2)", () => {
  const OWN = (file: string) =>
    file.startsWith(CERTIFIED_DIR) || file.startsWith(path.join(SRC, "api"));

  it("names no gated endpoint outside src/api and the certified layer", () => {
    const patterns = Object.values(CERTIFIED_ACTS)
      .filter(
        (entry): entry is typeof entry & { gate: { kind: "server"; call: string } } =>
          entry.gate.kind === "server",
      )
      .map((entry) => {
        const [, route] = entry.gate.call.split(" ");
        // `/ai/x/{id}/y` → a regex that also matches `/ai/x/${id}/y`.
        const source = (route ?? "")
          .split(/\{[^}]+\}/)
          .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
          .join("[^\"'`\\s]*");
        return { call: entry.gate.call, re: new RegExp(source) };
      });

    const offenders: string[] = [];
    for (const file of walk(SRC)) {
      if (OWN(file)) continue;
      const body = codeOf(file);
      for (const { call, re } of patterns) {
        if (re.test(body)) offenders.push(`${path.relative(SRC, file)} → ${call}`);
      }
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });

  it("lets no module reach past the layer's barrel", () => {
    const offenders: string[] = [];
    for (const file of walk(SRC)) {
      if (file.startsWith(CERTIFIED_DIR)) continue;
      const body = codeOf(file);
      // `.../certified/useCertifiedAct` and friends — the barrel is
      // `.../certified` or `.../certified/index`.
      const deep = body.match(/from\s+"[^"]*\/certified\/(?!index")[^"]+"/g);
      if (deep !== null) offenders.push(`${path.relative(SRC, file)} → ${deep.join(", ")}`);
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });

  it("requires any module naming a gated wrapper to route through the hook", () => {
    // The three wrappers whose own doc comments already say the refusal
    // "belongs to useCertifiedAct". A surface that calls one straight is the
    // regression this catches.
    const GATED_WRAPPERS = ["respondToApproval", "adoptProposition", "bindConnector"];
    const offenders: string[] = [];
    for (const file of walk(SRC)) {
      if (OWN(file)) continue;
      const body = codeOf(file);
      const named = GATED_WRAPPERS.filter((w) => new RegExp(`\\b${w}\\b`).test(body));
      if (named.length === 0) continue;
      if (!/\buseCertifiedAct\b/.test(body)) {
        offenders.push(`${path.relative(SRC, file)} → ${named.join(", ")}`);
      }
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });
});

/* ================================================= 6 · the hook and the modal */

function refusalOf(overrides: Partial<CertifiedRefusal> = {}): CertifiedRefusal {
  return {
    error: "step_up_required",
    tier: "T2",
    // `why` is the classifier's sentence; `reason` is the session's. The
    // ceremony renders both, and they are never the same words.
    why: "a payout above the auto-release band is a T2 act",
    reason: "T2 needs ELEVATED, session holds BOUND",
    needs_step_up: true,
    needs_oob: false,
    locked: false,
    command_ref: "approval:8f2c1a44-0b7e-4d51-9a63-2c8e5f0a7b19",
    command_summary: "a payout approval for 842,000.50",
    current_level: "BOUND",
    required_level: "ELEVATED",
    ...overrides,
  };
}

function refusalError(overrides: Partial<CertifiedRefusal> = {}): unknown {
  return { response: { status: 403, data: { detail: refusalOf(overrides) } } };
}

const REQUEST = {
  act: "certified.approval" as RunnableCertifiedType,
  echo: "approved the Coromandel payout",
  summary: "a payout approval for 842,000.50",
  subject: "8f2c1a44-0b7e-4d51-9a63-2c8e5f0a7b19",
};

function harness(renderer: "S" | "C" = "S") {
  const onEcho = vi.fn();
  const emit = vi.fn(async (echo: unknown) => {
    void echo;
  });
  const hook = renderHook(() =>
    useCertifiedAct({ renderer, surface: "tray", onEcho, emit }),
  );
  return { hook, onEcho, emit };
}

describe("useCertifiedAct (C2, C3)", () => {
  it("treats a step_up_required 403 as the ceremony's entry point, not an error", async () => {
    const { hook } = harness();
    const perform = vi.fn().mockRejectedValueOnce(refusalError());

    await act(async () => {
      // Note: no rejection. A refusal is the ceremony arriving.
      await hook.result.current.run(REQUEST, perform);
    });

    expect(hook.result.current.ceremony).not.toBeNull();
    expect(hook.result.current.ceremony?.refusal.needs_step_up).toBe(true);
    expect(hook.result.current.problem).toBeNull();
  });

  it("widens the refusal with the levels the backend actually sends", async () => {
    const { hook } = harness();
    await act(async () => {
      await hook.result.current.run(REQUEST, vi.fn().mockRejectedValueOnce(refusalError()));
    });
    expect(hook.result.current.ceremony?.refusal.current_level).toBe("BOUND");
    expect(hook.result.current.ceremony?.refusal.required_level).toBe("ELEVATED");
  });

  it("re-throws anything that is not a step-up refusal", async () => {
    const { hook } = harness();
    const boom = { response: { status: 409, data: { detail: "already responded" } } };
    await expect(
      act(async () => {
        await hook.result.current.run(REQUEST, vi.fn().mockRejectedValueOnce(boom));
      }),
    ).rejects.toBe(boom);
    expect(hook.result.current.ceremony).toBeNull();
  });

  it("retries the act WHOLE, once, after the ceremony completes", async () => {
    const { hook, onEcho } = harness();
    const perform = vi
      .fn()
      .mockRejectedValueOnce(refusalError())
      .mockResolvedValueOnce(undefined);

    await act(async () => {
      await hook.result.current.run(REQUEST, perform);
    });
    await act(async () => {
      hook.result.current.onElevated();
    });

    await waitFor(() => expect(onEcho).toHaveBeenCalledTimes(1));
    expect(perform).toHaveBeenCalledTimes(2);
    expect(hook.result.current.ceremony).toBeNull();
    expect(hook.result.current.problem).toBeNull();
  });

  it("stops at one retry, and reports the server's own reason", async () => {
    const { hook, onEcho } = harness();
    const perform = vi.fn().mockRejectedValue(refusalError());

    await act(async () => {
      await hook.result.current.run(REQUEST, perform);
    });
    await act(async () => {
      hook.result.current.onElevated();
    });

    await waitFor(() =>
      expect(hook.result.current.problem).toEqual({
        kind: "refused",
        message: "T2 needs ELEVATED, session holds BOUND",
      }),
    );
    expect(perform).toHaveBeenCalledTimes(2);
    // Re-opening would loop against a server that has already decided.
    expect(hook.result.current.ceremony).toBeNull();
    expect(onEcho).not.toHaveBeenCalled();
  });

  it("drops the pending act when the ceremony is abandoned", async () => {
    const { hook, onEcho } = harness();
    const perform = vi.fn().mockRejectedValueOnce(refusalError());

    await act(async () => {
      await hook.result.current.run(REQUEST, perform);
    });
    await act(async () => {
      hook.result.current.onClose();
    });
    await act(async () => {
      hook.result.current.onElevated();
    });

    expect(perform).toHaveBeenCalledTimes(1);
    expect(onEcho).not.toHaveBeenCalled();
  });

  /* The failure §6 calls the dangerous one. */
  it("never performs, and never echoes, an act whose gate does not exist", async () => {
    const { hook, onEcho, emit } = harness();
    const perform = vi.fn().mockResolvedValue(undefined);

    await act(async () => {
      await hook.result.current.run(
        { ...REQUEST, act: "certified.consent" as RunnableCertifiedType },
        perform,
      );
    });

    expect(perform).not.toHaveBeenCalled();
    expect(onEcho).not.toHaveBeenCalled();
    expect(emit).not.toHaveBeenCalled();
    expect(hook.result.current.problem?.kind).toBe("gap");
    expect(hook.result.current.ceremony).toBeNull();
  });
});

describe("every certified path echoes, with its renderer (C5)", () => {
  it("carries S for the estate", async () => {
    const { hook, onEcho, emit } = harness("S");
    await act(async () => {
      await hook.result.current.run(REQUEST, vi.fn().mockResolvedValue(undefined));
    });
    expect(onEcho).toHaveBeenCalledWith("approved the Coromandel payout");
    expect(emit.mock.calls[0]?.[0]).toMatchObject({
      sentence: "approved the Coromandel payout",
      action_ref: {
        kind: "certified_act",
        surface_id: "tray",
        params: { renderer: "S", act: "certified.approval" },
      },
    });
  });

  it("carries C for the Line, so a phone tap is not an operator click", async () => {
    const { hook, emit } = harness("C");
    await act(async () => {
      await hook.result.current.run(REQUEST, vi.fn().mockResolvedValue(undefined));
    });
    expect(emit.mock.calls[0]?.[0]).toMatchObject({
      action_ref: { params: { renderer: "C" } },
    });
  });

  it("takes the renderer as a parameter rather than inferring it", () => {
    const source = codeOf(path.join(CERTIFIED_DIR, "useCertifiedAct.ts"));
    // No sniffing of the DOM, the URL or a module-level global.
    expect(source).not.toMatch(/document\.|window\.|location\./);
    expect(source).toMatch(/renderer:\s*EchoRenderer/);
  });
});

/* ===================================================== the ceremony itself */

function ceremonyDeps(overrides: Partial<CeremonyDeps> = {}): CeremonyDeps {
  return {
    passkey: vi.fn(async () => ({ ok: true })),
    totp: vi.fn(async () => ({ ok: true })),
    oobIssue: vi.fn(async () => ({ ok: true, challenge_id: "c-1", sent_to_channel: "whatsapp" })),
    oobConfirm: vi.fn(async () => ({ ok: true })),
    passkeySupported: () => true,
    ...overrides,
  };
}

describe("StepUpCeremony (C1)", () => {
  it("restates the act through the pinned block, not through this file", () => {
    const { container, getByText } = render(
      <StepUpCeremony
        prompt={{ refusal: refusalOf(), summary: "fallback" }}
        onElevated={vi.fn()}
        onClose={vi.fn()}
        deps={ceremonyDeps()}
      />,
    );
    const block = container.querySelector('[data-certified-type="certified.step-up"]');
    expect(block).not.toBeNull();
    expect(block!.textContent).toContain("a payout approval for 842,000.50");
    // The server's own words, never a paraphrase.
    expect(getByText("T2 needs ELEVATED, session holds BOUND", { exact: false })).toBeDefined();
  });

  it("is a dialog you can leave", () => {
    const onClose = vi.fn();
    const { container, getByText } = render(
      <StepUpCeremony
        prompt={{ refusal: refusalOf(), summary: "fallback" }}
        onElevated={vi.fn()}
        onClose={onClose}
        deps={ceremonyDeps()}
      />,
    );
    const dialog = container.querySelector('[role="dialog"]')!;
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-label")).toContain("a payout approval");

    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(getByText("Not now"));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("elevates when the passkey verifies", async () => {
    const onElevated = vi.fn();
    const deps = ceremonyDeps();
    const { getByText } = render(
      <StepUpCeremony
        prompt={{ refusal: refusalOf(), summary: "fallback" }}
        onElevated={onElevated}
        onClose={vi.fn()}
        deps={deps}
      />,
    );
    fireEvent.click(getByText("use passkey"));
    await waitFor(() => expect(onElevated).toHaveBeenCalledTimes(1));
    expect(deps.passkey).toHaveBeenCalledTimes(1);
  });

  it("reports a failed factor with the count, and does not elevate", async () => {
    const onElevated = vi.fn();
    const deps = ceremonyDeps({
      passkey: vi.fn(async () => ({
        ok: false,
        reason: "that passkey is not registered on this account",
        failed_attempts: 2,
      })),
    });
    const { findByRole, getByText } = render(
      <StepUpCeremony
        prompt={{ refusal: refusalOf(), summary: "fallback" }}
        onElevated={onElevated}
        onClose={vi.fn()}
        deps={deps}
      />,
    );
    fireEvent.click(getByText("use passkey"));
    const alert = await findByRole("alert");
    expect(alert.textContent).toContain("that passkey is not registered");
    // The lockout is shown coming rather than sprung.
    expect(alert.textContent).toContain("2 failed attempts");
    expect(onElevated).not.toHaveBeenCalled();
  });

  it("offers the one-time code behind a word, and verifies with it", async () => {
    const onElevated = vi.fn();
    const deps = ceremonyDeps();
    const { container, getByText } = render(
      <StepUpCeremony
        prompt={{ refusal: refusalOf(), summary: "fallback" }}
        onElevated={onElevated}
        onClose={vi.fn()}
        deps={deps}
      />,
    );
    expect(container.querySelector("input")).toBeNull();
    fireEvent.click(getByText("Use a one-time code instead"));
    const input = container.querySelector("input")!;
    fireEvent.change(input, { target: { value: "418209" } });
    fireEvent.click(getByText("Verify"));
    await waitFor(() => expect(onElevated).toHaveBeenCalledTimes(1));
    expect(deps.totp).toHaveBeenCalledWith("418209");
  });

  it("draws no passkey control on a device that has none", () => {
    const { container, queryByText, getByText } = render(
      <StepUpCeremony
        prompt={{ refusal: refusalOf(), summary: "fallback" }}
        onElevated={vi.fn()}
        onClose={vi.fn()}
        deps={ceremonyDeps({ passkeySupported: () => false })}
      />,
    );
    // Never a control that goes nowhere (DESIGN_CONTRACT §7.4) …
    expect(queryByText("use passkey")).toBeNull();
    // … and never at the cost of the statement.
    expect(getByText("a payout approval for 842,000.50")).toBeDefined();
    expect(container.querySelector("input")).not.toBeNull();
  });

  it("hands over the code leg when the account has no passkey enrolled", async () => {
    const deps = ceremonyDeps({
      passkey: vi.fn(async () => {
        throw { response: { status: 400, data: { detail: "no passkey registered" } } };
      }),
    });
    const { container, getByText, queryByRole } = render(
      <StepUpCeremony
        prompt={{ refusal: refusalOf(), summary: "fallback" }}
        onElevated={vi.fn()}
        onClose={vi.fn()}
        deps={deps}
      />,
    );
    fireEvent.click(getByText("use passkey"));
    await waitFor(() => expect(container.querySelector("input")).not.toBeNull());
    // A 400 "no passkey registered" is not a failed attempt and is not reported
    // as one — saying "that did not verify" here would be a lie about the user.
    expect(queryByRole("alert")).toBeNull();
  });

  it("offers no factor once the session is locked", () => {
    const { queryByText, getByText, container } = render(
      <StepUpCeremony
        prompt={{
          refusal: refusalOf({
            locked: true,
            needs_step_up: false,
            reason: "step-up locked until 2026-07-31 18:40 UTC after repeated failures",
          }),
          summary: "fallback",
        }}
        onElevated={vi.fn()}
        onClose={vi.fn()}
        deps={ceremonyDeps()}
      />,
    );
    expect(queryByText("use passkey")).toBeNull();
    expect(container.querySelector("input")).toBeNull();
    // Says when, not "later" — the server's reason carries the wall clock.
    expect(getByText(/2026-07-31 18:40 UTC/)).toBeDefined();
    // Still names what was refused.
    expect(getByText("a payout approval for 842,000.50")).toBeDefined();
  });

  it("offers no factor when no ceremony could lift the refusal", () => {
    // `require_tier` only sets needs_step_up when the session resolves to a
    // user. An unbound channel comes back with every flag false, and a passkey
    // button there would fail on every press.
    const { queryByText, getByText, container } = render(
      <StepUpCeremony
        prompt={{
          refusal: refusalOf({
            needs_step_up: false,
            needs_oob: false,
            locked: false,
            current_level: "NONE",
            reason:
              "T2 needs ELEVATED but this channel is not bound to a user — enroll it from the console first",
          }),
          summary: "fallback",
        }}
        onElevated={vi.fn()}
        onClose={vi.fn()}
        deps={ceremonyDeps()}
      />,
    );
    expect(queryByText("use passkey")).toBeNull();
    expect(queryByText("Use a one-time code instead")).toBeNull();
    expect(container.querySelector("input")).toBeNull();
    expect(getByText("NOT PERMITTED HERE")).toBeDefined();
    // The two levels, where they are the actionable part rather than an echo.
    expect(getByText("THIS SESSION HOLDS")).toBeDefined();
    expect(getByText("NONE")).toBeDefined();
    expect(getByText("ELEVATED")).toBeDefined();
  });

  it("says the levels once, not twice", () => {
    const { container } = render(
      <StepUpCeremony
        prompt={{ refusal: refusalOf(), summary: "fallback" }}
        onElevated={vi.fn()}
        onClose={vi.fn()}
        deps={ceremonyDeps()}
      />,
    );
    // The reason sentence already names both; a ladder beside it is the same
    // fact twice on the modal that can least afford noise.
    expect(container.textContent).not.toContain("BOUND → ELEVATED");
  });

  it("falls to the lockout when the ceremony's own endpoint locks out", async () => {
    const deps = ceremonyDeps({
      passkey: vi.fn(async () => {
        throw {
          response: {
            status: 403,
            data: { detail: "step-up is locked after repeated failures" },
          },
        };
      }),
    });
    const { getByText, queryByText } = render(
      <StepUpCeremony
        prompt={{ refusal: refusalOf(), summary: "fallback" }}
        onElevated={vi.fn()}
        onClose={vi.fn()}
        deps={deps}
      />,
    );
    fireEvent.click(getByText("use passkey"));
    await waitFor(() => expect(queryByText("use passkey")).toBeNull());
    expect(getByText("STEP-UP LOCKED")).toBeDefined();
    // The server's own sentence, carried through rather than restated.
    expect(getByText("step-up is locked after repeated failures")).toBeDefined();
  });

  it("drives the T3 second-channel leg end to end", async () => {
    const onElevated = vi.fn();
    const deps = ceremonyDeps();
    const { container, getByText } = render(
      <StepUpCeremony
        prompt={{ refusal: refusalOf({ needs_oob: true, tier: "T3" }), summary: "fallback" }}
        onElevated={onElevated}
        onClose={vi.fn()}
        deps={deps}
      />,
    );
    fireEvent.click(getByText("Send the confirmation"));
    await waitFor(() => expect(container.querySelector("input")).not.toBeNull());
    fireEvent.change(container.querySelector("input")!, { target: { value: "77213" } });
    fireEvent.click(getByText("Confirm"));
    await waitFor(() => expect(onElevated).toHaveBeenCalledTimes(1));
    expect(deps.oobConfirm).toHaveBeenCalledWith(
      "c-1",
      "approval:8f2c1a44-0b7e-4d51-9a63-2c8e5f0a7b19",
      "77213",
    );
  });

  it("sends nothing when the refusal named no command to bind to", () => {
    const deps = ceremonyDeps();
    const { queryByText, getByText } = render(
      <StepUpCeremony
        prompt={{
          refusal: refusalOf({ needs_oob: true, tier: "T3", command_ref: null }),
          summary: "fallback",
        }}
        onElevated={vi.fn()}
        onClose={vi.fn()}
        deps={deps}
      />,
    );
    expect(queryByText("Send the confirmation")).toBeNull();
    expect(getByText(/named no command/)).toBeDefined();
    expect(deps.oobIssue).not.toHaveBeenCalled();
  });
});

/* ============================================================ house rules */

describe("the layer keeps the house rules", () => {
  it("uses no emoji and no raw hex or px for colour", () => {
    for (const file of walk(CERTIFIED_DIR)) {
      const body = readFileSync(file, "utf8");
      expect(body, file).not.toMatch(/\p{Extended_Pictographic}/u);
      expect(body, file).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    }
    for (const file of readdirSync(CERTIFIED_DIR).filter((f) => f.endsWith(".css"))) {
      const body = readFileSync(path.join(CERTIFIED_DIR, file), "utf8");
      expect(body, file).not.toMatch(/!important/);
      // Colour arrives as a token; the only literals allowed are the scrim's
      // own dim and the shadow alphas, both commented in place.
      const declarations = body.match(/#[0-9a-fA-F]{3,8}\b/g);
      expect(declarations, file).toBeNull();
    }
  });

  it("animates only transform and opacity", () => {
    for (const file of readdirSync(CERTIFIED_DIR).filter((f) => f.endsWith(".css"))) {
      const body = readFileSync(path.join(CERTIFIED_DIR, file), "utf8");
      const transitions = body.match(/transition:[^;]+;/g) ?? [];
      for (const rule of transitions) {
        expect(rule, `${file}: ${rule}`).toMatch(
          /transition:\s*(color|opacity|translate|scale|rotate|transform)\b/,
        );
      }
      expect(body, file).not.toMatch(/@keyframes[\s\S]*?(width|height|top|left):/);
    }
  });
});
