/**
 * POLISH P4 — the glass placement map's two invariants, held statically
 * over app.css (jsdom applies no external stylesheets, so the material
 * rules are checked as text, the way the layout lint checks python):
 *
 * 1. Every selector that declares a backdrop-filter also appears in the
 *    prefers-reduced-transparency fallback — the brand's rule that glass
 *    goes solid, never invisible, for that preference.
 * 2. Glass never appears inside a sheet: the registry hall, the record
 *    sheet, the dossier, the boardroom, the library, the study and the
 *    undercroft stay flat (art bible §10 — "glass over a flat surface is
 *    milky and costs GPU for nothing").
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const appCss = readFileSync(
  path.join(
    path.dirname(new URL(import.meta.url).pathname),
    "..", "src", "app", "app.css",
  ),
  "utf-8",
).replace(/\/\*[\s\S]*?\*\//g, "");

function selectorsOf(block: string): string[] {
  return block
    .split(",")
    .map((selector) => selector.trim())
    .filter((selector) => selector.length > 0);
}

describe("the glass material (P4)", () => {
  const mediaMatch = appCss.match(
    /@media \(prefers-reduced-transparency: reduce\) \{([\s\S]*?)\n\}/,
  );

  it("ships the reduced-transparency fallback block", () => {
    expect(mediaMatch).not.toBeNull();
  });

  it("every glass selector has a solid fallback", () => {
    const fallbackSelectors = new Set(
      selectorsOf((mediaMatch?.[1] ?? "").split("{")[0] ?? ""),
    );
    const beforeMedia = appCss.slice(0, mediaMatch?.index ?? appCss.length);
    const missing: string[] = [];
    for (const rule of beforeMedia.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
      const body = rule[2] ?? "";
      if (!body.includes("backdrop-filter: var(")) continue;
      for (const selector of selectorsOf(rule[1] ?? "")) {
        const name = selector.split("\n").pop()?.trim() ?? selector;
        if (!fallbackSelectors.has(name)) missing.push(name);
      }
    }
    expect(missing).toEqual([]);
  });

  it("glass never appears inside a sheet (art bible §10)", () => {
    const flatRooms = [
      ".vh-hall",
      ".vh-record-sheet",
      ".vh-dossier",
      ".vh-board",
      ".vh-library",
      ".vh-study",
      ".vh-undercroft",
      ".vh-gallery",
      ".vh-glass-panes",
    ];
    for (const room of flatRooms) {
      for (const rule of appCss.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
        const selectors = rule[1] ?? "";
        const body = rule[2] ?? "";
        if (selectors.includes(room)) {
          expect(
            body.includes("backdrop-filter"),
            `${room} must stay flat`,
          ).toBe(false);
        }
      }
    }
  });
});
