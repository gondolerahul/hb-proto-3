import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * DESIGN_CONTRACT §1.5, enforced over **every** stylesheet in the app.
 *
 * > Animate only `transform`/`opacity` (and `translate`/`scale`/`rotate` as
 * > their modern longhands). Never animate width, height, top, left, or
 * > box-shadow.
 *
 * A gate existed for this before and reached one directory —
 * `tests/certified.test.tsx` walked `src/components/certified/` only, and its
 * regex read just the first property of a comma-separated list, so
 * `transition: background …, box-shadow …` passed on the strength of its first
 * clause. Both blind spots hid real violations, so the scan is rewritten here:
 * every `.css` under `src/`, every property in every list, plus the bodies of
 * every `@keyframes`.
 *
 * ## Why there is a debt list rather than a clean sheet
 *
 * Running this for the first time found the rule broken in **22 files**,
 * including the shared design system the other twenty-one inherit from. That is
 * not something a wiring round should fix by editing every surface's look — a
 * `box-shadow` transition is visible, and removing it from `material.css`
 * changes all eighteen surfaces at once. So the existing violations are frozen
 * below, by file and by property, and the gate's real job is that **the list
 * cannot grow**. Burning it down belongs to R-5.
 *
 * The list is deliberately per-property, not per-file: a file already forgiven
 * for `color` still fails on a new `box-shadow`.
 *
 * `width` in `standup.css` is the one worth fixing first. Every other entry is
 * paint-only and cheap; `width` triggers layout on every frame of the
 * animation, and §1.5 names it explicitly.
 */

const SRC = path.resolve(__dirname, "..", "src");

/** The contract's allow-list, plus `none` (an explicit opt-out, not an
 *  animation) and CSS-wide keywords. */
const ALLOWED = new Set([
  "transform",
  "opacity",
  "translate",
  "scale",
  "rotate",
  "none",
  "inherit",
  "initial",
  "unset",
  "revert",
]);

/**
 * Pre-existing violations, frozen 2026-07-30. **Do not add to this.** If your
 * change needs a new entry, it needs a different implementation — the two the
 * R-4 foundations round introduced (`shell.css` and `palette.css` transitioning
 * `box-shadow`) were both rewritten to fade an overlay's opacity instead, which
 * is the shape every one of these can take.
 */
const KNOWN_DEBT: Record<string, string[]> = {
  "app/presession.css": ["color"],
  "background/background.css": ["backdrop-filter"],
  "components/certified/ceremony.css": ["color"],
  "design/base.css": ["text-decoration-color"],
  "design/material.css": ["background", "box-shadow", "color"],
  // `background-position` is the `vh-skeleton` sweep. Paint-only, and the
  // contract prefers a sweep to a pulse for good reason — but it is still
  // outside the allow-list.
  "design/motion.css": ["box-shadow", "background-position"],
  "shell/shell.css": ["background", "color"],
  "surfaces/bridges.css": ["background", "box-shadow"],
  /* `box-shadow` delisted 2026-07-31 by R-4 part W: it lived on
     `.di-traffic-item:hover`, and the traffic strip stopped being a control
     when wiring found it echoing an act it did not perform. The debt was paid
     by deleting the affordance, not by rewriting the animation. */
  "surfaces/district.css": ["background", "color"],
  "surfaces/dossier.css": ["background", "box-shadow"],
  "surfaces/gallery.css": ["background", "box-shadow"],
  "surfaces/glasshouse.css": ["box-shadow"],
  "surfaces/hall.css": ["background", "color"],
  "surfaces/library.css": ["background", "box-shadow", "color"],
  "surfaces/standup.css": ["background", "width"],
  "surfaces/still.css": ["background", "color"],
  "surfaces/study.css": ["background", "box-shadow", "color"],
  "surfaces/talent.css": ["color"],
  "surfaces/tray.css": ["box-shadow"],
  "surfaces/undercroft.css": ["background", "color"],
  "world/room.css": ["stroke"],
  // `offset-distance` moves a mark along a motion path. Compositor-friendly
  // in practice, and arguably within §1.5's intent rather than its letter —
  // which is a wording question for R-5, not a licence to add more.
  "world/territory.css": ["stroke", "offset-distance"],
};

function stylesheets(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) stylesheets(full, found);
    else if (entry.name.endsWith(".css")) found.push(full);
  }
  return found;
}

/** Comments carry prose that names forbidden properties on purpose — usually to
 *  explain why one is *not* being animated. A scan that cannot tell an
 *  explanation from a declaration punishes writing the reason down. */
const strip = (css: string): string => css.replace(/\/\*[\s\S]*?\*\//g, "");

/** Every property named by a `transition` or `transition-property`, including
 *  each clause of a comma-separated list. */
function transitioned(css: string): string[] {
  const out: string[] = [];
  for (const match of css.matchAll(/transition(?:-property)?\s*:\s*([^;}]+)/g)) {
    for (const clause of match[1]!.split(",")) {
      const property = clause.trim().split(/\s+/)[0];
      if (property !== undefined && property !== "") out.push(property);
    }
  }
  return out;
}

/** Every property assigned inside a `@keyframes` body. Brace-counted rather
 *  than regexed, because keyframe bodies nest one level. */
function keyframed(css: string): string[] {
  const out: string[] = [];
  for (const at of css.matchAll(/@keyframes\s+[\w-]+\s*\{/g)) {
    let depth = 1;
    let i = at.index! + at[0].length;
    const start = i;
    while (i < css.length && depth > 0) {
      if (css[i] === "{") depth += 1;
      else if (css[i] === "}") depth -= 1;
      i += 1;
    }
    for (const decl of css.slice(start, i - 1).matchAll(/([\w-]+)\s*:/g)) {
      const property = decl[1]!;
      // The stop offsets (`from`, `to`, `50%`) are selectors, not properties.
      if (!/^\d/.test(property)) out.push(property);
    }
  }
  return out;
}

describe("DESIGN_CONTRACT §1.5 — only transform and opacity are animated", () => {
  const files = stylesheets(SRC);

  it("finds stylesheets at all — an empty scan proves nothing", () => {
    expect(files.length).toBeGreaterThan(15);
  });

  it("transitions no property outside the allow-list, beyond the frozen debt", () => {
    const offenders: string[] = [];

    for (const file of files) {
      const rel = path.relative(SRC, file).split(path.sep).join("/");
      const forgiven = new Set(KNOWN_DEBT[rel] ?? []);

      for (const property of transitioned(strip(readFileSync(file, "utf8")))) {
        if (ALLOWED.has(property) || forgiven.has(property)) continue;
        offenders.push(`${rel} transitions "${property}"`);
      }
    }

    expect(
      offenders,
      `§1.5 permits transform and opacity only. Fade an overlay's opacity instead — ` +
        `that is how shell.css and palette.css were fixed:\n  ${offenders.join("\n  ")}`,
    ).toEqual([]);
  });

  it("animates no forbidden property in a @keyframes body", () => {
    const offenders: string[] = [];

    for (const file of files) {
      const rel = path.relative(SRC, file).split(path.sep).join("/");
      const forgiven = new Set(KNOWN_DEBT[rel] ?? []);

      for (const property of keyframed(strip(readFileSync(file, "utf8")))) {
        if (ALLOWED.has(property) || forgiven.has(property)) continue;
        offenders.push(`${rel} @keyframes animates "${property}"`);
      }
    }

    expect(offenders, offenders.join("\n  ")).toEqual([]);
  });

  it("keeps the debt list honest — a forgiven property that is gone must be delisted", () => {
    /* Otherwise the list only ever grows as dead weight, and a future violation
       lands on an entry someone already fixed. */
    const stale: string[] = [];

    for (const [rel, properties] of Object.entries(KNOWN_DEBT)) {
      const file = path.join(SRC, rel);
      const css = strip(readFileSync(file, "utf8"));
      const live = new Set([...transitioned(css), ...keyframed(css)]);
      for (const property of properties) {
        if (!live.has(property)) stale.push(`${rel}: "${property}" is fixed — remove it from KNOWN_DEBT`);
      }
    }

    expect(stale, stale.join("\n  ")).toEqual([]);
  });
});
