/**
 * PORTRAITS — the one portrait door. The properties that matter: the
 * promoted ten render busts, everything else renders a seal (nothing is
 * ever portrait-less), and the shipped SVGs are what the manifest says
 * they are — gold dot geometry on the near-black ground, no raster
 * embeds, no foreign colour.
 */
import { cleanup, render } from "@testing-library/react";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import manifest from "../src/components/portraits/manifest.json";
import { Portrait, hasBust } from "../src/components/portraits/Portrait";

afterEach(cleanup);

const appRoot = path.resolve(
  path.dirname(new URL(import.meta.url).pathname), "..");
const publicDir = path.join(appRoot, "public", "portraits");

describe("the manifest and the files agree", () => {
  it("every manifest key has its SVG, and every SVG its key", () => {
    const files = readdirSync(publicDir)
      .filter((name) => name.endsWith(".svg"))
      .map((name) => name.replace(/\.svg$/, ""))
      .sort();
    expect(files).toEqual(Object.keys(manifest.portraits).sort());
  });

  it("the promoted set is the ratified roster: Pragya + the nine", () => {
    expect(Object.keys(manifest.portraits)).toHaveLength(10);
    expect(manifest.portraits).toHaveProperty("pragya", "Pragya");
    expect(manifest.treatment).toBe("T4");
  });
});

describe("the shipped SVGs keep the medium", () => {
  it("gold dot geometry on the near-black ground — nothing else", () => {
    for (const key of Object.keys(manifest.portraits)) {
      const svg = readFileSync(path.join(publicDir, `${key}.svg`), "utf-8");
      expect(svg).toContain('fill="#0a0908"');
      expect(svg).not.toContain("<image"); // geometry, never an embed
      const fills = new Set(
        [...svg.matchAll(/fill="(#[0-9a-f]{6})"/g)].map((m) => m[1]));
      fills.delete("#0a0908");
      // The gold ramp and only the gold ramp.
      expect([...fills].sort()).toEqual(["#a8722a", "#edab48", "#fdc871"]);
      expect((svg.match(/<circle/g) ?? []).length).toBeGreaterThan(500);
    }
  });
});

describe("the one portrait door", () => {
  it("a promoted colleague renders the bust", () => {
    const { container } = render(
      <Portrait entityKey="agt-046" name="Bookkeeping & Reconciliation" />);
    const bust = container.querySelector('[data-part="bust"]');
    expect(bust?.getAttribute("src")).toBe("/portraits/agt-046.svg");
    expect(bust?.getAttribute("alt")).toContain("Bookkeeping");
  });

  it("keys are case-insensitive — AGT-046 is agt-046", () => {
    expect(hasBust("AGT-046")).toBe(true);
  });

  it("everything else renders the seal — nothing is ever portrait-less", () => {
    const { container } = render(
      <Portrait entityKey="agt-999" entityId="entity-1" name="New Hire" />);
    expect(container.querySelector('[data-part="bust"]')).toBeNull();
    expect(container.querySelector('[data-part="seal"]')).not.toBeNull();
  });

  it("the bust carries no glow chrome of its own — gold at rest is the beacon's, not the face's", () => {
    const { container } = render(<Portrait entityKey="pragya" name="Pragya" />);
    const bust = container.querySelector('[data-part="bust"]');
    expect(bust?.getAttribute("style")).toBeNull();
    expect(bust?.className ?? "").toBe("");
  });
});
