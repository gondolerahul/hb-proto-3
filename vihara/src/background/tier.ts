/**
 * The device tier probe (D7 §3.1–§3.3).
 *
 * D7 makes one rule a **hard build gate**: *a tier-C device never downloads
 * three.js.* Quarantining three into its own rollup chunk is necessary and not
 * sufficient — a static `import` puts that chunk in the initial module graph, and
 * Vite then emits a `<link rel="modulepreload">` for it, so every device fetches
 * it whether or not it will ever run a frame. That is precisely the gate failing
 * while looking like it passes.
 *
 * So the atmosphere is loaded through a **dynamic import behind this probe**, and
 * `tests/tier_gate.test.ts` asserts the built `index.html` does not preload the
 * world chunk. The chunk boundary is what makes the budget measurable; the probe
 * is what makes it honest.
 *
 * The probe is deliberately conservative: when it cannot tell, it answers "C".
 * Guessing high costs a slow device a 137 KB download and a stuttering frame;
 * guessing low costs a fast device a static gradient it will never notice, since
 * the reduced-motion path already looks deliberate.
 */

export type Tier = "A" | "B" | "C";

interface Nav {
  deviceMemory?: number;
  hardwareConcurrency?: number;
  connection?: { saveData?: boolean; effectiveType?: string };
}

export function probeTier(): Tier {
  if (typeof window === "undefined") return "C";

  // Someone who has asked for less motion has asked for less of this.
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return "C";

  const nav = navigator as Navigator & Nav;

  // Save-Data is an explicit request not to spend the user's bytes.
  if (nav.connection?.saveData) return "C";
  if (nav.connection?.effectiveType && /^(slow-)?2g$/.test(nav.connection.effectiveType)) {
    return "C";
  }

  // No WebGL2 means the scene cannot render at all, so the download is pure waste.
  try {
    const canvas = document.createElement("canvas");
    if (!canvas.getContext("webgl2")) return "C";
  } catch {
    return "C";
  }

  const mem = nav.deviceMemory ?? 0;
  const cores = nav.hardwareConcurrency ?? 0;

  // `deviceMemory` is Chromium-only and coarse (0.25…8). Absent on Safari and
  // Firefox, which is why cores carry the decision when it is missing rather than
  // the absence forcing tier C on every non-Chromium browser.
  if (mem >= 8 || cores >= 8) return "A";
  if (mem >= 4 || cores >= 4) return "B";
  return "C";
}

/** Tiers A and B run the scene; C never downloads it. */
export function tierRunsWorld(tier: Tier): boolean {
  return tier === "A" || tier === "B";
}
