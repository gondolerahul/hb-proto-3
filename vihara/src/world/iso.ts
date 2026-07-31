/**
 * Isometric projection, and the box grammar the territory is built from.
 *
 * ## Why this exists rather than only a three.js scene
 *
 * Finding **RD-1**: the first build painted every label onto the 3D ground
 * plane, so district names, colleague names and KPI figures were skewed with the
 * perspective and unreadable. Finding **RD-2**: the built form was hollow
 * wireframe cages that read as an unfinished CAD export.
 *
 * The architectural answer to both is to stop treating the territory as a scene
 * that happens to contain text:
 *
 *   - **Geometry is drawn.** Here, in SVG, with real faces, real lighting and
 *     real edges — solid volumes, not cages.
 *   - **Text is DOM**, positioned over the drawing in screen space by projecting
 *     each object's anchor through the same transform. Always upright, always
 *     selectable, always in the accessibility tree.
 *
 * That split is also what makes the surface honest about tiers: an SVG territory
 * is the tier-C path and the L9 sheet equivalent *simultaneously*, at full
 * quality rather than as a fallback (decision D1). The three.js territory in
 * `world/territory.ts` uses this same anchor projection for its labels, so the
 * two paths differ in how the ground is *rendered* and not in what it says.
 *
 * ## The projection
 *
 * A 2:1 dimetric — 30° from horizontal, the register the inspiration set uses.
 * Not true isometric (35.264°): 30° gives whole-number-friendly ratios and reads
 * as a technical drawing rather than as a game.
 */

/** World units → screen units. */
export const ISO = { ax: 0.866, ay: 0.5, ah: 0.94 } as const;

export type Vec3 = readonly [number, number, number];
export type Pt = readonly [number, number];

/** Project a world point to the SVG/screen plane. */
export function proj(x: number, y: number, z: number): Pt {
  return [(x - z) * ISO.ax, (x + z) * ISO.ay - y * ISO.ah];
}

export function projV(v: Vec3): Pt {
  return proj(v[0], v[1], v[2]);
}

const path = (pts: Pt[]) => pts.map((p) => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" ");

export interface Box {
  /** Near-left ground corner. */
  at: Vec3;
  /** Extent along x, y (up), z. */
  size: Vec3;
}

/**
 * The three visible faces of a box, as SVG polygon point strings.
 *
 * In this projection the camera sees the top, the +x face and the +z face. Face
 * order in the returned object is also paint order: +z, +x, top — so the top
 * always wins the overlap, which is what makes an edge read as an edge.
 */
export function boxFaces({ at, size }: Box): { front: string; side: string; top: string } {
  const [x, y, z] = at;
  const [w, h, d] = size;
  const yTop = y + h;

  return {
    // +z face — turned toward the viewer, catches the most fill light.
    front: path([
      proj(x, yTop, z + d),
      proj(x + w, yTop, z + d),
      proj(x + w, y, z + d),
      proj(x, y, z + d),
    ]),
    // +x face — turned away from the key, the darkest of the three.
    side: path([
      proj(x + w, yTop, z),
      proj(x + w, yTop, z + d),
      proj(x + w, y, z + d),
      proj(x + w, y, z),
    ]),
    // Top — faces the key light directly.
    top: path([
      proj(x, yTop, z),
      proj(x + w, yTop, z),
      proj(x + w, yTop, z + d),
      proj(x, yTop, z + d),
    ]),
  };
}

/** The ground quad a plinth or district occupies, for its contact shadow. */
export function groundQuad({ at, size }: Box): string {
  const [x, y, z] = at;
  const [w, , d] = size;
  return path([proj(x, y, z), proj(x + w, y, z), proj(x + w, y, z + d), proj(x, y, z + d)]);
}

/** Centre of a box's top face — where a beacon rises from and a label anchors. */
export function topCentre({ at, size }: Box): Pt {
  return proj(at[0] + size[0] / 2, at[1] + size[1], at[2] + size[2] / 2);
}

/** Centre of a box's ground footprint. */
export function baseCentre({ at, size }: Box): Pt {
  return proj(at[0] + size[0] / 2, at[1], at[2] + size[2] / 2);
}

/**
 * A road between two ground points, as a path with one right-angled bend.
 *
 * Straight diagonals between plinths look accidental; an orthogonal run with a
 * single mitred corner looks laid out. The bend is taken on the axis with more
 * distance to cover, so the corner lands away from either endpoint.
 */
export function road(from: Vec3, to: Vec3): string {
  const [x1, y1, z1] = from;
  const [x2, , z2] = to;
  const bendOnX = Math.abs(x2 - x1) >= Math.abs(z2 - z1);
  const mid: Vec3 = bendOnX ? [x2, y1, z1] : [x1, y1, z2];
  const a = projV(from);
  const m = projV(mid);
  const b = proj(x2, y1, z2);
  return `M ${a[0].toFixed(2)} ${a[1].toFixed(2)} L ${m[0].toFixed(2)} ${m[1].toFixed(2)} L ${b[0].toFixed(2)} ${b[1].toFixed(2)}`;
}

/**
 * Bounding box of projected points, for a computed viewBox.
 *
 * `pad` is in **world units, not pixels** — the estate spans roughly 60 units, so
 * a pad of 5 is a comfortable margin and a pad of 34 shrinks the estate to a
 * third of the frame. Getting this wrong is silent: the drawing is still correct,
 * it is just tiny.
 */
export function extentOf(points: Pt[], pad = 5): { x: number; y: number; w: number; h: number } {
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const minX = Math.min(...xs) - pad;
  const maxX = Math.max(...xs) + pad;
  const minY = Math.min(...ys) - pad;
  const maxY = Math.max(...ys) + pad;
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

/**
 * The transform that lays flat text on the ground plane.
 *
 * Owner review A2 (2026-07-30) reversed the screen-space label decision, and
 * correctly: finding **RD-1** was that labels were *skewed AND overlapping AND
 * illegible*, not that they were flat. The inspiration set labels flat on the
 * ground and reads beautifully. So labels lie on the floor again — but on
 * **clear ground beside** the structure rather than under it, at reading size,
 * and as real SVG `<text>` so they stay selectable and in the accessibility
 * tree. Skew was never the defect; collision and size were.
 *
 * The matrix maps local text space onto the floor: the text's own +x runs along
 * world **+x**, and its +y (downward, i.e. successive lines) runs along world
 * **+z**. That is the standard isometric floor-decal transform.
 */
export function groundTextTransform(x: number, z: number, scale = 1): string {
  const [tx, ty] = proj(x, 0, z);
  const a = ISO.ax * scale;
  const b = ISO.ay * scale;
  return `matrix(${a} ${b} ${-a} ${b} ${tx.toFixed(2)} ${ty.toFixed(2)})`;
}

/*
 * There is deliberately no mirrored variant.
 *
 * A second matrix that flips an axis produces text with a negative reading
 * direction — it renders backwards, which is exactly what the first attempt at
 * this did. Labels that need to grow the other way keep THIS transform and set
 * `text-anchor: end` instead: the glyphs still run left-to-right, the block just
 * extends from its anchor in the other direction. One transform, one reading
 * direction, no mirrored text possible.
 */
