/**
 * SUB T2 — the two-copies gate for the brand tokens: the mirror in
 * src/tokens/ must be byte-identical to the design-system source of truth.
 * Drift means Vihara renders a brand nobody ratified — run
 * `node scripts/sync_tokens.mjs` and commit both.
 */
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const appRoot = path.resolve(
  path.dirname(new URL(import.meta.url).pathname), "..");
const repoRoot = path.resolve(appRoot, "..");
const dsProject = path.join(
  repoRoot, "docs", "product-road-map", "increment-7",
  "buddha-cognitive-lab-design-system", "project");
const tokensDir = path.join(appRoot, "src", "tokens");

describe("brand tokens", () => {
  it("mirrors the design-system token source byte for byte", () => {
    expect(readFileSync(path.join(tokensDir, "colors_and_type.css")))
      .toEqual(readFileSync(path.join(dsProject, "colors_and_type.css")));
  });

  it("mirrors the design-system material layer byte for byte (POLISH P1)", () => {
    expect(readFileSync(path.join(tokensDir, "styles.css")))
      .toEqual(readFileSync(path.join(dsProject, "styles.css")));
  });

  it("the mirror is imported, never edited — vihara additions live in tokens.css", () => {
    const entry = readFileSync(path.join(tokensDir, "tokens.css"), "utf-8");
    // styles.css imports colors_and_type.css itself; one import brings both.
    expect(entry).toContain('@import "./styles.css"');
    // The gold budget is enforced by usage: no new gold-* variable may be
    // minted outside the brand file (art bible §2.1).
    const minted = entry.match(/--gold-\d+\s*:/g) ?? [];
    expect(minted).toEqual([]);
  });

  it("no orphan --vh-* variables — the STEWARD/LINE/GLASS drift stays dead (POLISH P1)", () => {
    // These were referenced with hardcoded fallbacks and defined nowhere,
    // so the fallbacks (one of them an off-brand gold) were what rendered.
    const offenders: string[] = [];
    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/\.(css|tsx?)$/.test(entry.name)) {
          if (/var\(--vh-(line|surface|gold)/.test(readFileSync(full, "utf-8"))) {
            offenders.push(path.relative(appRoot, full));
          }
        }
      }
    };
    walk(path.join(appRoot, "src"));
    expect(offenders).toEqual([]);
  });
});
