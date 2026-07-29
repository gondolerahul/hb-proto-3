/**
 * SUB T2 — the two-copies gate for the brand tokens: the mirror in
 * src/tokens/ must be byte-identical to the design-system source of truth.
 * Drift means Vihara renders a brand nobody ratified — run
 * `node scripts/sync_tokens.mjs` and commit both.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const appRoot = path.resolve(
  path.dirname(new URL(import.meta.url).pathname), "..");
const repoRoot = path.resolve(appRoot, "..");
const source = path.join(
  repoRoot, "docs", "product-road-map", "increment-7",
  "buddha-cognitive-lab-design-system", "project", "colors_and_type.css");
const mirror = path.join(appRoot, "src", "tokens", "colors_and_type.css");

describe("brand tokens", () => {
  it("mirrors the design-system source byte for byte", () => {
    expect(readFileSync(mirror)).toEqual(readFileSync(source));
  });

  it("the mirror is imported, never edited — vihara additions live in tokens.css", () => {
    const entry = readFileSync(
      path.join(appRoot, "src", "tokens", "tokens.css"), "utf-8");
    expect(entry).toContain('@import "./colors_and_type.css"');
    // The gold budget is enforced by usage: no new gold-* variable may be
    // minted outside the brand file (art bible §2.1).
    const minted = entry.match(/--gold-\d+\s*:/g) ?? [];
    expect(minted).toEqual([]);
  });
});
