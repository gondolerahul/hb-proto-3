/**
 * POLISH P9 — VG-22's harness half: the D7 §3.1 floors as a p75
 * REGRESSION CANARY over the render cost of the three surfaces the
 * table bolds (the Still Surface, the Terrace sheet, the Tray).
 *
 * Said plainly so nobody mistakes this for the proof: jsdom on this VM
 * is not tier B. What this harness pins is the JavaScript cost of
 * scaffold → on-screen at p75 over 25 runs, against the same numbers —
 * so a change that makes a surface materially slower fails here first.
 * The real p75-on-tier-B measurement (4× CPU throttle, mid-range
 * phone, network included) is a named row in the P11 device-matrix run
 * sheet, owner-side like every other live leg this increment.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Tray } from "../src/api/trays";
import { StillSurface, type StillLoaders } from "../src/app/StillSurface";
import { TraySurface, type TrayLoaders } from "../src/app/TraySurface";
import { assessManifest } from "../src/manifest/refusals";
import type { WireScaffold } from "../src/manifest/schema";
import { BindingContext, estateResolver } from "../src/renderers/bindings";
import { RenderManifest } from "../src/renderers/RenderManifest";

afterEach(cleanup);

const RUNS = 25;

function p75(samples: number[]): number {
  const sorted = [...samples].sort((a, b) => a - b);
  return sorted[Math.ceil(0.75 * sorted.length) - 1] ?? 0;
}

async function measure(run: () => Promise<void>): Promise<number> {
  const samples: number[] = [];
  for (let i = 0; i < RUNS; i++) {
    const start = performance.now();
    await run();
    samples.push(performance.now() - start);
    cleanup();
  }
  return p75(samples);
}

/* ── fixtures ──────────────────────────────────────────────────────── */

const fixturesDir = path.join(
  path.dirname(new URL(import.meta.url).pathname), "fixtures",
);

function scaffoldFromFixture(name: string): WireScaffold {
  const lines = readFileSync(path.join(fixturesDir, name), "utf-8")
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as { part?: string });
  const scaffold = lines.find((line) => line.part === "scaffold");
  if (scaffold === undefined) throw new Error(`${name} has no scaffold`);
  return scaffold as WireScaffold;
}

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
    beacons: [],
  }),
  echo: async () => undefined,
};

const PAYMENT_TRAY: Tray = {
  tray_id: "t-1",
  approval_id: "00000000-0000-0000-0000-000000000001",
  checkpoint_key: "before_outbound_payout_above_band",
  what_happened: { sentence: "A payout crossed its band.", object: null },
  recommendation: null,
  paths: [
    {
      key: "approve",
      label: "Approve",
      consequence: "the payout proceeds.",
      cost: { amount: 84200, currency: null, basis: "the amount itself" },
    },
    { key: "decline", label: "Decline", consequence: "it does not.", cost: null },
  ],
  certified: {
    component: "certified.payment@1",
    tier: "T2",
    props: {
      approval_id: "00000000-0000-0000-0000-000000000001",
      checkpoint_key: "before_outbound_payout_above_band",
      summary: "a payout of consequence",
      amount: 84200,
      currency: null,
      tier: "T2",
    },
    manifest_hash: "sha256:fixture",
  },
  sla: { seconds_left: 12400, on_timeout: "auto_deny" },
  prepared_by: { entity_id: "e-1", name: "Meera" },
};

const trayLoaders: TrayLoaders = {
  trays: async () => [PAYMENT_TRAY],
  respond: async () => undefined,
  echo: async () => undefined,
  stream: () => () => undefined,
  ceremony: {
    passkey: async () => ({ ok: true }),
    totp: async () => ({ ok: true }),
  },
};

/* ── the canary ────────────────────────────────────────────────────── */

describe("the D7 §3.1 floors as a p75 render-cost canary (VG-22 harness half)", () => {
  it("the Still Surface reaches its scaffold inside the 120ms budget", async () => {
    const ms = await measure(async () => {
      const view = render(<StillSurface loaders={stillLoaders} />);
      await view.findByText(/All is well/);
    });
    console.log(`p75 still scaffold: ${ms.toFixed(1)}ms (budget 120)`);
    expect(ms).toBeLessThan(120);
  });

  it("the Terrace sheet reaches its scaffold inside the 200ms budget", async () => {
    const scaffold = scaffoldFromFixture("terrace_sheet.ndjson");
    const assessment = assessManifest(scaffold);
    const resolver = estateResolver(null);
    const ms = await measure(async () => {
      render(
        <BindingContext.Provider value={resolver}>
          <RenderManifest manifest={scaffold} assessment={assessment} />
        </BindingContext.Provider>,
      );
      await waitFor(() => {
        expect(document.querySelector(".vh-sheet-surface")).not.toBeNull();
      });
    });
    console.log(`p75 terrace sheet scaffold: ${ms.toFixed(1)}ms (budget 200)`);
    expect(ms).toBeLessThan(200);
  });

  it("the Tray arrives whole inside the 250ms budget", async () => {
    const ms = await measure(async () => {
      render(<TraySurface loaders={trayLoaders} />);
      await waitFor(() => {
        expect(document.querySelector("[data-part='tray']")).not.toBeNull();
      });
    });
    console.log(`p75 tray whole: ${ms.toFixed(1)}ms (budget 250)`);
    expect(ms).toBeLessThan(250);
  });
});
