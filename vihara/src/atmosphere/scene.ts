/**
 * The atmosphere's shared scene description (POLISH P2, 15_polish.md §4).
 *
 * One description, two renderers: the Canvas-2D floor (every tier, the
 * reduced-motion static frame, the paint under the GL chunk's load) and
 * the GL port (P3, tier A/B). Everything a renderer needs to agree on
 * lives here — the tile grid, the seeded light-blob field, the day–night
 * luminance and the per-depth dimming — so the two cannot drift apart.
 *
 * The palette rule is decision 1 (owner, 2026-07-29): every glow is warm
 * LIGHT (`246,241,233`), never gold and never the legacy blue. The floor
 * spends no gold — §2.1's budget is what makes a raised hand visible.
 */

export const FLOOR = {
  /** Internal paint-buffer size — fixed, cheap, blurred by perspective. */
  width: 1280,
  height: 720,
  hexRadius: 26,
  gap: 2.4,
  /** Matte tile over the glow — the legacy system's construction. */
  tile: "#0b0a09",
  tileDay: "#12100e",
  backdrop: "#060505",
  /** Light, not signal (art bible §13: the energy floor is light, never gold). */
  light: "246,241,233",
  blobCount: 7,
} as const;

export interface LightBlob {
  x: number;
  y: number;
  r: number;
  dx: number;
  dy: number;
  phase: number;
  /** One blob runs brighter — the wireframes' focal point. */
  bright: boolean;
}

/**
 * Deterministic blob field — the wireframes' own LCG, kept so the floor
 * looks the same on every visit (an estate does not rearrange its light).
 */
export function seededBlobs(
  seed = 11,
  count: number = FLOOR.blobCount,
): LightBlob[] {
  let state = seed;
  const rnd = (): number => {
    state = (state * 16807) % 2147483647;
    return state / 2147483647;
  };
  const blobs: LightBlob[] = [];
  for (let i = 0; i < count; i++) {
    blobs.push({
      x: rnd() * FLOOR.width,
      y: rnd() * FLOOR.height,
      r: 130 + rnd() * 180,
      dx: 0.3 + rnd() * 0.7,
      dy: 0.25 + rnd() * 0.6,
      phase: rnd() * 6.28,
      bright: i === count - 1,
    });
  }
  return blobs;
}

export interface Luminance {
  phase: "day" | "night" | "dawn" | "dusk";
  /** Built-form / tile lift multiplier (estate-visual's --daymul). */
  face: number;
  /** Glow strength multiplier (estate-visual's --glowmul). */
  glow: number;
}

const NIGHT = { face: 1, glow: 1 } as const;
const DAY = { face: 2.3, glow: 0.5 } as const;
const SUNRISE_MIN = 6 * 60 + 30;
const SUNSET_MIN = 18 * 60 + 30;
/** Art bible §4: 20 minutes of real time either side, interpolated. */
const WINDOW_MIN = 20;

function mix(a: number, b: number, k: number): number {
  return a + (b - a) * k;
}

/**
 * Day–night as luminance on the local clock (art bible §4, charter
 * decision 3). Pure over the Date so both renderers — and the tests —
 * agree about the hour. Beacons and certified gold are exempt by rule;
 * they are not painted here.
 */
export function luminanceAt(date: Date): Luminance {
  const minutes = date.getHours() * 60 + date.getMinutes();
  const dawn = (minutes - (SUNRISE_MIN - WINDOW_MIN)) / (2 * WINDOW_MIN);
  const dusk = (minutes - (SUNSET_MIN - WINDOW_MIN)) / (2 * WINDOW_MIN);
  if (dawn >= 0 && dawn <= 1) {
    return {
      phase: "dawn",
      face: mix(NIGHT.face, DAY.face, dawn),
      glow: mix(NIGHT.glow, DAY.glow, dawn),
    };
  }
  if (dusk >= 0 && dusk <= 1) {
    return {
      phase: "dusk",
      face: mix(DAY.face, NIGHT.face, dusk),
      glow: mix(DAY.glow, NIGHT.glow, dusk),
    };
  }
  if (minutes > SUNRISE_MIN && minutes < SUNSET_MIN) {
    return { phase: "day", ...DAY };
  }
  return { phase: "night", ...NIGHT };
}

/**
 * How much floor shows through at each depth — the wireframes' own
 * opacities (still .5, estate .4), falling as surfaces grow dense. The
 * Undercroft keeps a trace: depth 3 is the engine room, not a void.
 */
export const DEPTH_DIM: Record<"0" | "1" | "2" | "3" | "presession" | "line", number> = {
  "0": 0.5,
  "1": 0.4,
  "2": 0.22,
  "3": 0.12,
  presession: 0.5,
  line: 0.3,
};
