/**
 * POLISH P8 — the WCAG 2.2 AA audit's automatable half.
 *
 * Two instruments:
 * 1. The art bible §11 contrast table, COMPUTED from the shipped tokens
 *    rather than transcribed — the values are parsed out of the mirrored
 *    brand file, so a future brand edit that breaks a ratio breaks this
 *    test instead of a real user's reading.
 * 2. axe-core over the wire-free surfaces (pre-session, the still round
 *    trip) in jsdom — structure, names, roles, labels. Colour-contrast
 *    is disabled there because jsdom applies no stylesheets; instrument
 *    1 is the contrast check.
 *
 * The remaining AA legs are eyes-and-devices work and live in the P11
 * run sheet (screen reader sweep, keyboard walk on a real browser).
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import axe from "axe-core";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PreSession } from "../src/app/PreSession";
import { StillSurface, type StillLoaders } from "../src/app/StillSurface";
import { assessManifest } from "../src/manifest/refusals";
import type { WireScaffold } from "../src/manifest/schema";

afterEach(cleanup);

/* ── instrument 1: the §11 table, computed ─────────────────────────── */

const tokensCss = readFileSync(
  path.join(
    path.dirname(new URL(import.meta.url).pathname),
    "..", "src", "tokens", "colors_and_type.css",
  ),
  "utf-8",
);

function token(name: string): string {
  const match = tokensCss.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (match?.[1] === undefined) throw new Error(`token ${name} not found`);
  return match[1];
}

function luminance(hex: string): number {
  const channel = (value: number): number => {
    const scaled = value / 255;
    return scaled <= 0.03928
      ? scaled / 12.92
      : Math.pow((scaled + 0.055) / 1.055, 2.4);
  };
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(fg: string, bg: string): number {
  const [light, dark] = [luminance(fg), luminance(bg)].sort((a, b) => b - a);
  return ((light ?? 0) + 0.05) / ((dark ?? 0) + 0.05);
}

describe("the §11 contrast table, computed from the shipped tokens", () => {
  it("--fg on the canvas clears AA with room to spare", () => {
    expect(contrast(token("--fg"), token("--ink-950"))).toBeGreaterThan(7);
  });

  it("--fg-muted works as body copy on every surface step", () => {
    expect(contrast(token("--fg-muted"), token("--ink-950"))).toBeGreaterThan(4.5);
    expect(contrast(token("--fg-muted"), token("--surface"))).toBeGreaterThan(4.5);
    expect(contrast(token("--fg-muted"), token("--surface-2"))).toBeGreaterThan(4.5);
  });

  it("--fg-subtle clears AA for LARGE text only — which is why it is never body copy", () => {
    const ratio = contrast(token("--fg-subtle"), token("--ink-950"));
    expect(ratio).toBeGreaterThan(3);
    expect(ratio).toBeLessThan(4.5);
  });

  it("gold text clears the large-text floor on the canvas — certified prose stays --fg", () => {
    expect(contrast(token("--gold-500"), token("--ink-950"))).toBeGreaterThan(3);
    expect(contrast(token("--gold-300"), token("--ink-950"))).toBeGreaterThan(4.5);
  });
});

/* ── instrument 2: axe over the wire-free surfaces ─────────────────── */

const STILL: WireScaffold = {
  part: "scaffold",
  manifest_version: 1,
  surface_id: "still",
  renderer: "S",
  plane: "live",
  depth: 0,
  density: "novice",
  layout: { kind: "stack", regions: ["line", "pulse"] },
  components: [
    {
      id: "c1",
      type: "narrative.still-line@1",
      region: "line",
      props: { template: "All is well. {raised} hands raised." },
      bindings: [{ source: "estate.beacon", params: {} }],
    },
    {
      id: "c2",
      type: "primitive.pulse@1",
      region: "pulse",
      props: { label: "The pulse" },
      bindings: [{ source: "estate.pulse", params: {} }],
    },
  ],
  issued_at: "t",
  ttl_seconds: 120,
};

const stillLoaders: StillLoaders = {
  manifest: async () => ({ manifest: STILL, assessment: assessManifest(STILL) }),
  estate: async () => ({
    estate: { pulse: { beat_at: "t", healthy: true } },
    beacons: [{ approval_id: "a1" }],
  }),
  echo: async () => undefined,
};

async function expectNoViolations(container: Element): Promise<void> {
  const results = await axe.run(container, {
    rules: {
      // jsdom applies no stylesheets; instrument 1 carries contrast.
      "color-contrast": { enabled: false },
      // Surfaces render inside the shell's landmarks in production.
      region: { enabled: false },
    },
  });
  expect(
    results.violations.map((violation) => `${violation.id}: ${violation.help}`),
  ).toEqual([]);
}

describe("axe over the wire-free surfaces", () => {
  it("pre-session has no structural violations", async () => {
    const { container } = render(<PreSession onEntered={() => undefined} />);
    await expectNoViolations(container);
  });

  it("the still round trip has no structural violations", async () => {
    const { container, findByText } = render(
      <StillSurface loaders={stillLoaders} />,
    );
    await findByText(/All is well/);
    await expectNoViolations(container);
  });
});
