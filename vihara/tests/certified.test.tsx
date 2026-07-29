/**
 * SUB T6 — the certified set's goldens and refusals (D1 §4.1).
 *
 * Three families:
 * - **Structural goldens** — a DOM-structure snapshot per certified
 *   component × renderer × density, checked in. Not pixels: the failure
 *   L5 fears is a certified surface *differing between contexts*, and
 *   structure catches that without a browser.
 * - **The cross-context assertion** — the same certified manifest through
 *   the Sheet renderer and the Card renderer (which is also the Line)
 *   yields an identical certified subtree.
 * - **A refusal per component, one mutation at a time** — an injected
 *   prop and a missing prop must each reject the WHOLE manifest, because
 *   a checker never observed to fail is a function that returns true.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { assessManifest } from "../src/manifest/refusals";
import type { WireScaffold } from "../src/manifest/schema";
import { RenderManifest } from "../src/renderers/RenderManifest";

afterEach(cleanup);

/** Registry-conformant fixture props per certified type. */
const FIXTURES: Record<string, Record<string, unknown>> = {
  "certified.approval": {
    approval_id: "00000000-0000-0000-0000-000000000001",
    checkpoint_key: "before_outbound_payout_above_band",
    summary: "a payout approval",
    tier: "T2",
  },
  "certified.payment": {
    approval_id: "00000000-0000-0000-0000-000000000001",
    checkpoint_key: "before_outbound_payout_above_band",
    summary: "a payout of consequence",
    amount: 84200,
    currency: null,
    tier: "T2",
  },
  "certified.consent": {
    channel: "whatsapp",
    purpose: "order updates",
    direction: "grant",
    summary: "let Meera message customers about orders",
  },
  "certified.autonomy-change": {
    entity_id: "00000000-0000-0000-0000-000000000002",
    entity_name: "Meera",
    from_band: "A2",
    to_band: "A3",
    summary: "raise Meera to A3",
  },
  "certified.connector-binding": {
    connector_key: "zoho_books",
    connector_name: "Zoho Books",
    summary: "bind Zoho Books",
  },
  "certified.mastering-declaration": {
    def_name: "Invoice",
    connector_key: "zoho_books",
    direction: "external_masters",
    summary: "Zoho Books masters Invoice",
  },
  "certified.provider-opt-in": {
    provider: "kimi",
    disclosure_version: "2026-07-25",
    summary: "allow Kimi to serve this workspace",
  },
  "certified.strategy-resolution": {
    resolution_id: "r-1",
    title: "Ship the north-market push",
    summary: "adopt the resolution as tabled",
  },
  "certified.step-up": {
    tier: "T2",
    command_ref: "approval:1",
    command_summary: "approving a payout",
  },
  "certified.second-channel-wait": {
    command_ref: "approval:1",
    command_summary: "approving a payout",
    channel: "whatsapp",
  },
};

const CERTIFIED_TYPES = Object.keys(FIXTURES);

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

/** Serialize structure: tags, data-* identity, action names, text shape. */
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
  return `<${node.tagName.toLowerCase()}${attrs ? " " + attrs : ""}${
    ownText ? ` "${ownText}"` : ""
  }>${children}</${node.tagName.toLowerCase()}>`;
}

function certifiedSubtree(
  type: string,
  renderer: "S" | "C",
  density: "novice" | "operator",
): string {
  const manifest = manifestWith(type, FIXTURES[type]!, renderer, density);
  const assessment = assessManifest(manifest);
  if (assessment.verdict !== "render") {
    throw new Error(`fixture for ${type} must render: ${assessment.reason}`);
  }
  const { container } = render(
    <RenderManifest manifest={manifest} assessment={assessment} />,
  );
  const certified =
    container.querySelector('[data-part="certified"]') ??
    container.querySelector('[data-part="consent-revoke"]');
  if (certified === null) throw new Error(`${type} rendered no certified block`);
  const out = structure(certified);
  cleanup();
  return out;
}

describe("structural goldens", () => {
  for (const type of CERTIFIED_TYPES) {
    for (const renderer of ["S", "C"] as const) {
      for (const density of ["novice", "operator"] as const) {
        it(`${type} · ${renderer} · ${density}`, () => {
          expect(certifiedSubtree(type, renderer, density)).toMatchSnapshot();
        });
      }
    }
  }
});

describe("the cross-context assertion (L5)", () => {
  for (const type of CERTIFIED_TYPES) {
    it(`${type} renders one identical certified subtree in S, C and the Line`, () => {
      const sheet = certifiedSubtree(type, "S", "novice");
      const card = certifiedSubtree(type, "C", "novice"); // the Line IS the Card renderer
      expect(card).toBe(sheet);
    });
  }
});

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
      const props = { ...FIXTURES[type] };
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
  it("granting is a ceremony; revoking is deliberately plain", () => {
    const grant = certifiedSubtree("certified.consent", "S", "novice");
    expect(grant).toContain("data-part=certified");

    const manifest = manifestWith("certified.consent", {
      ...FIXTURES["certified.consent"],
      direction: "revoke",
    });
    const assessment = assessManifest(manifest);
    if (assessment.verdict !== "render") throw new Error("must render");
    const { container } = render(
      <RenderManifest manifest={manifest} assessment={assessment} />,
    );
    expect(container.querySelector('[data-part="certified"]')).toBeNull();
    expect(
      container.querySelector('[data-part="consent-revoke"]'),
    ).not.toBeNull();
  });
});
