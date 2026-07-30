/**
 * SUB T3 — the client manifest layer: resolution, the streaming merge, and
 * the refusal ladder. These mirror the backend's own manifest tests on
 * purpose: the two ends of the D4 contract must refuse the same things,
 * and each ladder row is exercised by exactly one broken manifest.
 */
import { describe, expect, it } from "vitest";

import { assessManifest } from "../src/manifest/refusals";
import { allEntries, declaredSources, resolve } from "../src/manifest/registry";
import {
  FillSchema,
  ScaffoldSchema,
  mergeFill,
  type WireComponent,
  type WireScaffold,
} from "../src/manifest/schema";

function scaffold(overrides: Partial<WireScaffold> = {}): WireScaffold {
  return {
    part: "scaffold",
    manifest_version: 1,
    surface_id: "still",
    renderer: "S",
    plane: "live",
    depth: 0,
    density: "novice",
    layout: { kind: "stack", regions: ["r"] },
    components: [],
    issued_at: "2026-07-29T00:00:00Z",
    ttl_seconds: 120,
    ...overrides,
  };
}

function pulse(overrides: Partial<WireComponent> = {}): WireComponent {
  return {
    id: "c1",
    type: "primitive.pulse@1",
    region: "r",
    props: { label: "The pulse" },
    bindings: [{ source: "estate.pulse", params: {} }],
    ...overrides,
  };
}

function certifiedApproval(
  overrides: Partial<WireComponent> = {},
): WireComponent {
  return {
    id: "x1",
    type: "certified.approval@1",
    region: "r",
    props: {
      approval_id: "a",
      checkpoint_key: "k",
      summary: "s",
      tier: "T2",
    },
    bindings: [],
    ...overrides,
  };
}

// ── the registry ─────────────────────────────────────────────────────────────

describe("registry resolution", () => {
  it("loads the 48-entry inventory the backend serves", () => {
    expect(allEntries().length).toBe(48);
  });

  it("resolves type@version and refuses futures and strangers", () => {
    expect(resolve("primitive.pulse@1").kind).toBe("ok");
    expect(resolve("primitive.pulse").kind).toBe("ok");
    expect(resolve("primitive.imaginary@1").kind).toBe("unknown");
    expect(resolve("primitive.pulse@9").kind).toBe("unknown");
  });

  it("a version below min_supported is unsupported, not unknown", () => {
    expect(resolve("primitive.pulse@0").kind).toBe("unsupported");
  });

  it("reads the declared binding sources off an entry", () => {
    const resolution = resolve("primitive.pulse@1");
    if (resolution.kind !== "ok") throw new Error("pulse must resolve");
    expect(declaredSources(resolution.entry)).toEqual(new Set(["estate.pulse"]));
  });
});

// ── the streaming merge (D4 §6) ──────────────────────────────────────────────

describe("mergeFill", () => {
  it("fills only what the scaffold declared", () => {
    const bare = scaffold({
      components: [pulse({ props: undefined, bindings: undefined })],
    });
    const merged = mergeFill(bare, {
      part: "fill",
      components: {
        c1: { props: { label: "p" }, bindings: [{ source: "estate.pulse" }] },
      },
    });
    expect(merged.kind).toBe("ok");
    if (merged.kind === "ok") {
      expect(merged.manifest.components[0]?.props).toEqual({ label: "p" });
    }
  });

  it("a fill may not invent a component", () => {
    const merged = mergeFill(scaffold(), {
      part: "fill",
      components: { ghost: { props: {} } },
    });
    expect(merged.kind).toBe("rejected");
  });

  it("a certified component may not stream", () => {
    const merged = mergeFill(
      scaffold({ components: [certifiedApproval()] }),
      { part: "fill", components: { x1: { props: {} } } },
    );
    expect(merged.kind).toBe("rejected");
    if (merged.kind === "rejected") expect(merged.reason).toContain("L5");
  });
});

// ── the refusal ladder (D4 §7) ───────────────────────────────────────────────

describe("the refusal ladder", () => {
  it("a clean manifest renders whole", () => {
    const assessment = assessManifest(scaffold({ components: [pulse()] }));
    expect(assessment.verdict).toBe("render");
    if (assessment.verdict === "render") {
      expect(assessment.dispositions[0]?.kind).toBe("render");
    }
  });

  it("an unknown type becomes a NAMED placeholder and the rest renders", () => {
    const assessment = assessManifest(scaffold({
      components: [
        pulse(),
        pulse({ id: "c2", type: "primitive.imaginary@1" }),
      ],
    }));
    expect(assessment.verdict).toBe("render");
    if (assessment.verdict === "render") {
      const [first, second] = assessment.dispositions;
      expect(first?.kind).toBe("render");
      expect(second?.kind).toBe("placeholder");
      if (second?.kind === "placeholder") {
        expect(second.reason).toContain("primitive.imaginary");
        expect(second.reason).toContain("still");
      }
    }
  });

  it("a version below min_supported refuses the whole manifest", () => {
    const assessment = assessManifest(scaffold({
      components: [pulse({ type: "primitive.pulse@0" })],
    }));
    expect(assessment.verdict).toBe("reject");
  });

  it("a W manifest without its sheet is refused (L9)", () => {
    expect(assessManifest(scaffold({ renderer: "W" })).verdict).toBe("reject");
  });

  it("an undeclared certified prop rejects the WHOLE manifest (L5)", () => {
    const assessment = assessManifest(scaffold({
      components: [
        pulse(),
        certifiedApproval({ props: { approval_id: "a", checkpoint_key: "k", summary: "s", tier: "T2", injected: "!" } }),
      ],
    }));
    expect(assessment.verdict).toBe("reject");
    if (assessment.verdict === "reject") {
      expect(assessment.reason).toContain("undeclared prop injected");
    }
  });

  it("a missing certified prop rejects the whole manifest", () => {
    const assessment = assessManifest(scaffold({
      components: [certifiedApproval({ props: { approval_id: "a" } })],
    }));
    expect(assessment.verdict).toBe("reject");
  });

  it("a certified component carrying a grade rejects the manifest (L5)", () => {
    const assessment = assessManifest(scaffold({
      components: [
        certifiedApproval({ honesty_grade: "replay", twin_run_id: "r1" }),
      ],
    }));
    expect(assessment.verdict).toBe("reject");
  });

  it("certified never sits on the twin plane (L5)", () => {
    const assessment = assessManifest(scaffold({
      plane: "twin",
      components: [certifiedApproval({ honesty_grade: undefined })],
    }));
    expect(assessment.verdict).toBe("reject");
  });

  it("a gradeless twin component fails visible, not silent (L6)", () => {
    const assessment = assessManifest(scaffold({
      plane: "twin",
      components: [pulse()],
    }));
    expect(assessment.verdict).toBe("render");
    if (assessment.verdict === "render") {
      expect(assessment.dispositions[0]?.kind).toBe("placeholder");
    }
  });

  it("a simulation grade without a run id is a placeholder; untested needs none (L6)", () => {
    for (const grade of ["replay", "forecast", "unknown"] as const) {
      const assessment = assessManifest(scaffold({
        plane: "twin",
        components: [pulse({ honesty_grade: grade })],
      }));
      if (assessment.verdict !== "render") throw new Error("must render");
      expect(assessment.dispositions[0]?.kind).toBe("placeholder");
    }
    const untested = assessManifest(scaffold({
      plane: "twin",
      components: [pulse({ honesty_grade: "untested" })],
    }));
    if (untested.verdict !== "render") throw new Error("must render");
    expect(untested.dispositions[0]?.kind).toBe("render");
  });

  it("an undeclared binding source is a visible placeholder", () => {
    const assessment = assessManifest(scaffold({
      components: [pulse({ bindings: [{ source: "billing.wallet" }] })],
    }));
    if (assessment.verdict !== "render") throw new Error("must render");
    expect(assessment.dispositions[0]?.kind).toBe("placeholder");
  });

  it("a world component outside W is a placeholder", () => {
    const assessment = assessManifest(scaffold({
      components: [pulse({ type: "world.district@1", props: { process_code: "P03", name: "x" } })],
    }));
    if (assessment.verdict !== "render") throw new Error("must render");
    expect(assessment.dispositions[0]?.kind).toBe("placeholder");
  });

  it("a narrative template with a digit is refused visibly (R7)", () => {
    const assessment = assessManifest(scaffold({
      components: [pulse({
        type: "narrative.still-line@1",
        props: { template: "Revenue was 42 this week." },
        bindings: [{ source: "estate.pulse" }],
      })],
    }));
    if (assessment.verdict !== "render") throw new Error("must render");
    expect(assessment.dispositions[0]?.kind).toBe("placeholder");
  });
});

// ── the wire schemas ─────────────────────────────────────────────────────────

describe("wire schemas", () => {
  it("a scaffold parses and a mislabelled part does not", () => {
    expect(ScaffoldSchema.safeParse(scaffold()).success).toBe(true);
    expect(
      ScaffoldSchema.safeParse({ ...scaffold(), part: "fill" }).success,
    ).toBe(false);
    expect(
      FillSchema.safeParse({ part: "fill", components: {} }).success,
    ).toBe(true);
  });
});
