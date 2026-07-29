/**
 * SUB T5 — the render pipeline. What these pin: a manifest renders through
 * regions; a missing binding is an empty state WITH A REASON; an
 * unimplemented component is a NAMED placeholder; a rejected manifest is a
 * refused surface pointing at its sheet. The theme is one rule — nothing
 * ever fails silent (D4 §7).
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { assessManifest } from "../src/manifest/refusals";
import type { WireScaffold } from "../src/manifest/schema";
import { BindingContext } from "../src/renderers/bindings";
import { RenderManifest } from "../src/renderers/RenderManifest";

afterEach(cleanup);

function still(overrides: Partial<WireScaffold> = {}): WireScaffold {
  return {
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
    ...overrides,
  };
}

function renderWith(
  manifest: WireScaffold,
  data: Record<string, unknown> = {},
) {
  const assessment = assessManifest(manifest);
  return render(
    <BindingContext.Provider value={(binding) => data[binding.source]}>
      <RenderManifest manifest={manifest} assessment={assessment} />
    </BindingContext.Provider>,
  );
}

describe("the still surface renders", () => {
  it("fills the template's slots from bindings, never from props", () => {
    renderWith(still(), {
      "estate.beacon": [{ approval_id: "a1" }, { approval_id: "a2" }],
      "estate.pulse": { beat_at: "t", healthy: true },
    });
    expect(
      screen.getByText("All is well. 2 hands raised."),
    ).toBeTruthy();
    expect(screen.getByText("Steady")).toBeTruthy();
  });

  it("an unresolved slot is an em-dash, never an invented figure", () => {
    renderWith(still(), { "estate.pulse": { healthy: true } });
    expect(screen.getByText("All is well. — hands raised.")).toBeTruthy();
  });

  it("a missing binding renders the empty state with its reason", () => {
    renderWith(still(), { "estate.beacon": [] });
    expect(
      screen.getByText("The pulse has not been read yet."),
    ).toBeTruthy();
  });
});

describe("failing visible", () => {
  it("a registered-but-unimplemented component is a named placeholder", () => {
    const manifest = still({
      components: [
        {
          id: "k1",
          type: "primitive.kanban@1",
          region: "line",
          props: { title: "Board", entity_def: "Lead", lane_field: "stage" },
          bindings: [{ source: "records.query" }],
        },
      ],
    });
    renderWith(manifest);
    const placeholder = screen.getByRole("note");
    expect(placeholder.textContent).toContain("primitive.kanban@1");
  });

  it("a rejected manifest is a refused surface that names its sheet", () => {
    const manifest = still({
      renderer: "W",
      sheet_equivalent: undefined,
      components: [],
    });
    renderWith(manifest);
    expect(screen.getByRole("alert").textContent).toContain(
      "cannot be shown safely",
    );
  });

  it("the W renderer is a stub that hands off to the sheet (L9)", () => {
    const manifest = still({
      renderer: "W",
      sheet_equivalent: "terrace.sheet",
      components: [],
    });
    renderWith(manifest);
    expect(screen.getByText("terrace.sheet")).toBeTruthy();
  });
});

describe("density and identity reach the DOM", () => {
  it("the surface carries renderer, density and surface id as data attributes", () => {
    const { container } = renderWith(still({ density: "operator" }), {
      "estate.beacon": [],
      "estate.pulse": { healthy: true },
    });
    const surface = container.querySelector('[data-part="surface"]');
    expect(surface?.getAttribute("data-density")).toBe("operator");
    expect(surface?.getAttribute("data-surface")).toBe("still");
  });
});
