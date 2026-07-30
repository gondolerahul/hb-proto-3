import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The contrast floor, computed rather than asserted.
 *
 * `DESIGN_CONTRACT.md` §6 requires 4.5:1 for body text and 3:1 for large text and
 * UI boundaries, and it names `--fg-faint` as the **disabled** step that must
 * never carry information. Every surface author was told that. Nothing checked it.
 *
 * So this reads the real token values out of the brand stylesheet — not copies —
 * and computes WCAG 2.x ratios for the pairs the product actually uses. Reading
 * the source is the point: a test with the hex values pasted in would pass forever
 * after someone re-tuned the ramp.
 *
 * The one deliberate exception is documented inline: `--fg-faint` fails on
 * purpose, and the test asserts that it fails, so that a future "fix" that
 * brightens it to pass would break here and force the real conversation — which is
 * whether the ramp needs a sixth step, not whether disabled should look enabled.
 */

const TOKENS = readFileSync(
  path.resolve(__dirname, "..", "src", "design", "tokens.brand.css"),
  "utf8",
);

/** Pull a hex-valued custom property from the `:root` block. */
function token(name: string): string {
  const m = TOKENS.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{3,8})`));
  if (!m?.[1]) throw new Error(`no hex token ${name}`);
  return m[1];
}

function srgbToLinear(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h.slice(0, 6);
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

function ratio(fg: string, bg: string): number {
  const a = luminance(fg);
  const b = luminance(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

/** The three grounds text actually sits on. */
const GROUNDS = {
  canvas: "--ink-950",
  surface: "--surface",
  raised: "--surface-2",
} as const;

describe("text contrast against every ground it sits on", () => {
  const bodySteps = ["--fg", "--fg-muted"] as const;
  const largeSteps = ["--fg-subtle"] as const;

  for (const [groundName, groundToken] of Object.entries(GROUNDS)) {
    const bg = token(groundToken);

    it.each(bodySteps)(`%s clears 4.5:1 on ${groundName}`, (fgToken) => {
      const r = ratio(token(fgToken), bg);
      expect(r, `${fgToken} on ${groundToken} is ${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
    });

    it.each(largeSteps)(`%s clears 3:1 on ${groundName}`, (fgToken) => {
      const r = ratio(token(fgToken), bg);
      expect(r, `${fgToken} on ${groundToken} is ${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(3);
    });
  }

  it("gold-300 clears 4.5:1 on the canvas — beacons and callouts are text too", () => {
    const r = ratio(token("--gold-300"), token("--ink-950"));
    expect(r, `--gold-300 on --ink-950 is ${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
  });

  it("on-accent clears 4.5:1 on gold — the certified button's own label", () => {
    // The metallic gradient's darkest stop is what a label has to survive, so the
    // core amber is the honest ground to measure against rather than the lightest.
    const r = ratio(token("--on-accent"), token("--gold-500"));
    expect(r, `--on-accent on --gold-500 is ${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
  });

  /**
   * `--fg-faint` fails, deliberately, and is asserted to fail.
   *
   * It is the disabled step. If someone brightens it until this passes, they have
   * made disabled look enabled, and this test breaking is the prompt to have the
   * real conversation — whether the ramp needs a sixth step — instead of quietly
   * losing the distinction.
   */
  it("keeps --fg-faint below the body floor, because it is the disabled step", () => {
    const r = ratio(token("--fg-faint"), token("--surface"));
    expect(r, `--fg-faint on --surface is ${r.toFixed(2)}:1`).toBeLessThan(4.5);
  });
});
