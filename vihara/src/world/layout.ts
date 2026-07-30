import type { Box, Vec3 } from "./iso";

/**
 * The territory's layout — deterministic, and computed rather than authored.
 *
 * Art bible §13's territory construction language is the one R1 ruling the
 * redesign reopened (charter §4), because it is what produced finding RD-2. What
 * replaces it:
 *
 *   **A district is a plinth with built form on it.** A raised slab lifted off
 *   the ground, carrying two or three solid volumes of different heights. Not a
 *   wireframe cage, not a floating box — a platform with buildings, lit by one
 *   high warm key, in the register of the inspiration set's technical dioramas.
 *
 * The ground is deliberately *not drawn*: the hex-field background shows through
 * beneath the plinths, so the estate sits on the atmosphere rather than on a
 * second floor of its own. That is why the plinths carry contact shadows — they
 * are what make the estate land on a surface it does not own.
 *
 * Layout is a ring around the Sheel with gatehouses at the near edge. Ring
 * rather than grid because the Sheel is the one Loop everything hangs off, and a
 * grid says "these are peers" about a hierarchy that is not flat.
 */

export interface Plot {
  key: string;
  /** The raised slab. */
  slab: Box;
  /** Built form standing on the slab. */
  volumes: Box[];
  /** Where a road from the Sheel meets this plot. */
  gate: Vec3;
  /** Whether a gold beacon rises from it — hands raised. */
  beacon: boolean;
  /** Signal traffic on its road, per hour. Drives dot density. */
  traffic: number;
  /** The twin plane. Rendered desaturated, at the estate's edge (art bible §5). */
  twin?: boolean;
  /**
   * Direction away from the estate centre, in world x/z. Labels are pushed along
   * it so a ring of plots becomes a ring of labels instead of a pile — the
   * cheapest collision avoidance available, and it is deterministic.
   */
  outward: readonly [number, number];
}

const SLAB_H = 0.34;

/**
 * Volume massing per plot, chosen from the plot's own index so the estate is
 * stable across renders and across sessions. A territory that rearranges itself
 * between visits cannot be learned, and being learnable is the whole point of
 * putting the business in a place.
 */
const MASSING: readonly (readonly Vec3[])[] = [
  // [x offset, height, z offset] triples, sized below
  [
    [0.7, 2.6, 0.7],
    [3.1, 1.5, 1.0],
    [1.4, 0.9, 3.0],
  ],
  [
    [0.6, 1.8, 1.2],
    [2.8, 2.9, 0.6],
  ],
  [
    [1.0, 1.2, 0.8],
    [3.0, 2.0, 2.2],
    [0.8, 1.7, 2.6],
  ],
  [
    [0.8, 3.2, 1.0],
    [3.2, 1.1, 1.4],
  ],
];

const FOOTPRINT: readonly Vec3[] = [
  [1.9, 0, 1.7],
  [1.5, 0, 1.5],
  [2.2, 0, 1.4],
  [1.6, 0, 1.9],
];

export interface PlotSeed {
  key: string;
  beacon: boolean;
  traffic: number;
  twin?: boolean;
}

/**
 * Place `seeds` on a ring of radius `r`, starting at `startDeg` and sweeping
 * `sweepDeg`. Angles rather than a loop over a grid, so adding a district
 * re-spaces the ring instead of appending a lonely row.
 *
 * The default arc runs 150° → 30° (through the far side) and deliberately never
 * enters the 30°–150° near sector — that row belongs to the gatehouses, and a
 * district placed there collides with them and with their labels.
 */
export function ringPlots(
  seeds: PlotSeed[],
  { r = 13.5, startDeg = 150, sweepDeg = 240 }: { r?: number; startDeg?: number; sweepDeg?: number } = {},
): Plot[] {
  const n = Math.max(seeds.length, 1);
  return seeds.map((seed, i) => {
    const t = n === 1 ? 0.5 : i / (n - 1);
    const a = ((startDeg + t * sweepDeg) * Math.PI) / 180;
    // Snapped to a half-unit grid: an isometric drawing whose objects sit on a
    // grid reads as surveyed; off-grid reads as scattered.
    const cx = Math.round(Math.cos(a) * r * 2) / 2;
    const cz = Math.round(Math.sin(a) * r * 2) / 2;

    const w = 5.4;
    const d = 4.4;
    const slab: Box = { at: [cx - w / 2, 0, cz - d / 2], size: [w, SLAB_H, d] };

    const massing = MASSING[i % MASSING.length]!;
    const foot = FOOTPRINT[i % FOOTPRINT.length]!;
    const volumes: Box[] = massing.map(([ox, h, oz]) => ({
      at: [slab.at[0] + ox, SLAB_H, slab.at[2] + oz],
      size: [foot[0], h, foot[2]],
    }));

    return {
      key: seed.key,
      slab,
      volumes,
      // The road meets the slab's near corner, not its centre — a road that
      // vanishes under a building looks like a mistake.
      gate: [cx, 0, cz - d / 2],
      beacon: seed.beacon,
      traffic: seed.traffic,
      outward: [Math.cos(a), Math.sin(a)],
      ...(seed.twin ? { twin: true } : {}),
    };
  });
}

/** The Sheel — the one root Loop, at the centre, small and distinct. */
export const SHEEL: Plot = {
  key: "sheel",
  slab: { at: [-2.2, 0, -2.2], size: [4.4, 0.22, 4.4] },
  volumes: [{ at: [-0.85, 0.22, -0.85], size: [1.7, 1.15, 1.7] }],
  gate: [0, 0, 0],
  beacon: false,
  traffic: 0,
  outward: [0, 1],
};

/** Gatehouses — the channels, at the near edge where work enters. */
export function gatehousePlots(keys: string[]): Plot[] {
  const spacing = 6.2;
  const z = 14.5;
  const x0 = (-(keys.length - 1) * spacing) / 2;
  return keys.map((key, i) => {
    const cx = x0 + i * spacing;
    const slab: Box = { at: [cx - 1.7, 0, z - 1.5], size: [3.4, 0.26, 3.0] };
    return {
      key,
      slab,
      volumes: [{ at: [cx - 0.8, 0.26, z - 0.75], size: [1.6, 0.95, 1.5] }],
      gate: [cx, 0, z - 1.5],
      beacon: false,
      traffic: 0,
      // Gatehouses sit at the near edge, so their free space is BELOW them.
      outward: [0, 1],
    };
  });
}

// ============================================================================
// THE MODEL
// ============================================================================

import { extentOf, proj, topCentre, type Pt } from "./iso";

export interface TerritoryAnchor {
  key: string;
  /** Screen-space point in viewBox units, for the DOM label layer. */
  at: Pt;
  beacon: boolean;
  twin: boolean;
  /** Which side of its plot the label should sit on. */
  side: "above" | "below";
}

export interface TerritoryModel {
  plots: Plot[];
  /** Painter's order: farther objects first. */
  ordered: Plot[];
  anchors: TerritoryAnchor[];
  view: { x: number; y: number; w: number; h: number };
}

/**
 * The single source of the estate's geometry.
 *
 * Both the drawing and the DOM label layer read this, so a label can never drift
 * from the plot it names — which is the failure mode of any design that projects
 * anchors twice.
 */
export function buildTerritory(
  districts: PlotSeed[],
  gatehouses: string[],
  glasshouse = true,
  sheel = true,
): TerritoryModel {
  const ring = ringPlots(districts);
  const gates = gatehousePlots(gatehouses);

  // The twin sits well off the ring, on the far side and further out. Art bible
  // §5 wants it *beside* the real and unmistakably not part of it; an angle
  // adjacent to a district would read as another quarter.
  const twin = glasshouse
    ? ringPlots([{ key: "glasshouse", beacon: false, traffic: 0, twin: true }], {
        r: 21,
        startDeg: -30, // screen right, clear of both the ring and the gate row
        sweepDeg: 0,
      }).map((p) => ({ ...p, twin: true as const }))
    : [];

  // `sheel: false` is the district room's diorama — one plot, no centre, no
  // roads. The room shows a place, not the estate.
  const plots = sheel ? [SHEEL, ...ring, ...gates, ...twin] : [...ring, ...gates, ...twin];

  const corners: Pt[] = plots.flatMap((p) => {
    const [x, y, z] = p.slab.at;
    const [w, , d] = p.slab.size;
    const tallest = Math.max(0, ...p.volumes.map((v) => v.size[1]));
    return [
      proj(x, y, z),
      proj(x + w, y, z),
      proj(x + w, y, z + d),
      proj(x, y, z + d),
      // Headroom for the beacon shaft, only where one actually rises.
      proj(x + w / 2, y + tallest + (p.beacon ? 5.4 : 1.2), z + d / 2),
    ];
  });

  /**
   * Labels are pushed along their plot's `outward` vector before projection, so a
   * ring of plots becomes a ring of labels rather than a pile in the middle. This
   * is deterministic and needs no measurement pass — the alternative, resolving
   * collisions from measured DOM boxes, would reflow on every font load.
   */
  const OUT = 3.4;
  const anchors: TerritoryAnchor[] = [...ring, ...gates, ...twin].map((p) => {
    const [ox, oz] = p.outward;
    const c = p.slab;
    const at = topCentre({
      at: [c.at[0] + ox * OUT, c.at[1], c.at[2] + oz * OUT],
      size: c.size,
    });
    // Only truly near-edge plots (the gatehouse row) label downward — a ring
    // plot at 30° labelled "below" runs into the near row and the shell footer.
    const side: "above" | "below" = oz > 0.6 ? "below" : "above";
    return { key: p.key, at, beacon: p.beacon, twin: Boolean(p.twin), side };
  });

  return {
    plots,
    ordered: [...plots].sort(
      (a, b) => a.slab.at[0] + a.slab.at[2] - (b.slab.at[0] + b.slab.at[2]),
    ),
    anchors,
    view: extentOf(corners, 5),
  };
}
