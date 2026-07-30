import { useMemo } from "react";
import { boxFaces, extentOf, groundQuad, groundTextTransform, proj, type Box, type Pt } from "./iso";
import "./room.css";

/**
 * A room, drawn at room scale.
 *
 * Owner review B (2026-07-30): the district room should have the Terrace's
 * structure — a place you look at and click into — rather than a column of
 * panels beside a small picture of one. And colleagues should be **personified
 * as structures**, not an icon with a letter in it.
 *
 * So this is the estate's grammar one level down. `Territory` draws districts on
 * an estate; `Room` draws **workplaces and fixtures on one district's floor**.
 * They deliberately share `iso.ts` — the same projection, the same three-face box,
 * the same contact shadows, the same flat ground labels — because descending a
 * level should change the *scale* of what you are looking at and nothing else.
 * Two isometric grammars in one product would be two products.
 *
 * Everything here is geometry and flat SVG text. Detail panels are the caller's
 * job, and they open on selection — which is what "some details hidden and
 * revealed when the user clicks the appropriate structure" means in practice.
 */

export type RoomItemKind = "workplace" | "fixture";

export interface RoomItem {
  key: string;
  kind: RoomItemKind;
  /** Flat ground label. Kept short — a long flat label reframes the room. */
  heading: string;
  detail?: string;
  /** Gold, and only ever "this needs you" (§2.1). */
  callout?: string | null;
  /** A lit lamp on the structure — running, occupied, alive. */
  lit?: boolean;
  /** A gold beacon rising from it — hands raised. */
  beacon?: boolean;
  /**
   * Massing variant. For a workplace this is what personifies it: each
   * colleague's place of work is a different built form, stable across sessions
   * because it is derived from their position in the district's roster.
   */
  variant: number;
  /** Fixtures can carry a gold seam — the protected reserve, and nothing else. */
  seam?: { at: number; of: number } | null;
}

interface Placed {
  item: RoomItem;
  slab: Box;
  volumes: Box[];
  labelAt: { x: number; z: number };
  anchorEnd: boolean;
}

/** Workplace massing. Each is a small building, not a marker. */
const WORKPLACE_MASSING: readonly (readonly [number, number, number, number, number][])[] = [
  // [xOff, zOff, w, h, d]
  [
    [0.35, 0.4, 1.5, 2.1, 1.3],
    [2.1, 0.9, 1.0, 1.15, 0.9],
  ],
  [
    [0.4, 0.35, 1.15, 1.35, 1.15],
    [1.8, 0.5, 1.35, 2.5, 1.5],
  ],
  [
    [0.3, 0.5, 2.4, 1.5, 1.2],
    [1.15, 1.9, 1.0, 0.85, 0.8],
  ],
  [
    [0.55, 0.5, 1.25, 2.8, 1.25],
    [2.15, 1.5, 0.85, 1.0, 0.85],
  ],
  [
    [0.3, 0.3, 1.7, 1.15, 1.7],
    [1.35, 1.5, 1.35, 1.9, 1.15],
  ],
];

/** Fixture massing — the KPI obelisk, the treasury vault, the runs table. */
const FIXTURE_MASSING: readonly (readonly [number, number, number, number, number][])[] = [
  // 0 — an obelisk. Tall and thin: a reading, standing up.
  [[1.5, 1.3, 0.9, 4.4, 0.9]],
  // 1 — a vault. Low, wide, and heavy: money at rest.
  [[0.5, 0.6, 3.2, 1.15, 2.0]],
  // 2 — a table. Almost flat: work in progress, laid out.
  [[0.4, 0.5, 3.4, 0.5, 2.2]],
];

const SLAB_H = 0.3;

/**
 * Two rows on one floor: fixtures at the back, workplaces at the front.
 *
 * Back and front rather than a grid, because the two are different kinds of
 * thing — a fixture is a reading you consult, a workplace is a colleague you
 * visit. A grid would say they are the same kind of thing in different slots.
 */
function layoutRoom(items: RoomItem[]) {
  const workplaces = items.filter((i) => i.kind === "workplace");
  const fixtures = items.filter((i) => i.kind === "fixture");

  const place = (list: RoomItem[], z: number, spacing: number, massing: typeof WORKPLACE_MASSING): Placed[] => {
    const x0 = (-(list.length - 1) * spacing) / 2;
    return list.map((item, i) => {
      const cx = x0 + i * spacing;
      const w = spacing - 1.5;
      const d = 3.6;
      const slab: Box = { at: [cx - w / 2, 0, z - d / 2], size: [w, SLAB_H, d] };
      const mass = massing[item.variant % massing.length]!;
      const volumes: Box[] = mass.map(([ox, oz, vw, vh, vd]) => ({
        at: [slab.at[0] + ox, SLAB_H, slab.at[2] + oz],
        size: [vw, vh, vd],
      }));
      return {
        item,
        slab,
        volumes,
        // The label sits on clear floor in front of its structure.
        labelAt: { x: cx - w / 2, z: z + d / 2 + 1.1 },
        anchorEnd: false,
      };
    });
  };

  const placed = [
    ...place(fixtures, -3.4, 6.6, FIXTURE_MASSING),
    ...place(workplaces, 5.2, 6.2, WORKPLACE_MASSING),
  ];

  // The floor the whole room stands on.
  const xs = placed.flatMap((p) => [p.slab.at[0], p.slab.at[0] + p.slab.size[0]]);
  const zs = placed.flatMap((p) => [p.slab.at[2], p.slab.at[2] + p.slab.size[2]]);
  const pad = 2.2;
  const floor: Box = {
    at: [Math.min(...xs) - pad, -SLAB_H, Math.min(...zs) - pad],
    size: [
      Math.max(...xs) - Math.min(...xs) + pad * 2,
      SLAB_H,
      Math.max(...zs) - Math.min(...zs) + pad * 2,
    ],
  };

  const corners: Pt[] = [
    ...placed.flatMap((p) => {
      const tallest = Math.max(0, ...p.volumes.map((v) => v.size[1]));
      const [x, , z] = p.slab.at;
      const [w, , d] = p.slab.size;
      return [
        proj(x, 0, z),
        proj(x + w, 0, z + d),
        proj(x + w / 2, tallest + (p.item.beacon ? 4.6 : 1), z + d / 2),
        /* Labels are part of the frame, so both ends of the run count. Omitting
           the origin corner left the leftmost label's start outside the box. */
        proj(p.labelAt.x, 0, p.labelAt.z),
        proj(p.labelAt.x + 8, 0, p.labelAt.z + 2.6),
      ];
    }),
    proj(floor.at[0], 0, floor.at[2]),
    proj(floor.at[0] + floor.size[0], 0, floor.at[2] + floor.size[2]),
  ];

  return { placed, floor, view: extentOf(corners, 2.2) };
}

export function Room({
  items,
  selectedKey,
  hoveredKey,
  onHover,
  onSelect,
}: {
  items: RoomItem[];
  selectedKey?: string | null;
  hoveredKey?: string | null;
  onHover?: (key: string | null) => void;
  onSelect?: (key: string) => void;
}) {
  const { placed, floor, view } = useMemo(() => layoutRoom(items), [items]);
  const floorFaces = boxFaces(floor);

  return (
    <svg
      className="rm-svg"
      viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
      preserveAspectRatio="xMidYMid meet"
      role="presentation"
    >
      <defs>
        <linearGradient id="rm-top" x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0%" stopColor="rgba(255,248,236,0.2)" />
          <stop offset="100%" stopColor="rgba(255,248,236,0.1)" />
        </linearGradient>
        <linearGradient id="rm-front" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(255,244,228,0.125)" />
          <stop offset="100%" stopColor="rgba(255,244,228,0.05)" />
        </linearGradient>
        <linearGradient id="rm-side" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(255,240,220,0.07)" />
          <stop offset="100%" stopColor="rgba(255,240,220,0.026)" />
        </linearGradient>
        <linearGradient id="rm-slab-top" x1="0" y1="0" x2="0.5" y2="1">
          <stop offset="0%" stopColor="rgba(255,246,230,0.1)" />
          <stop offset="100%" stopColor="rgba(255,246,230,0.05)" />
        </linearGradient>
        <linearGradient id="rm-slab-edge" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(255,240,220,0.12)" />
          <stop offset="100%" stopColor="rgba(0,0,0,0.42)" />
        </linearGradient>
        {/* The room's own floor: darker than what stands on it, so the built form
            reads as standing rather than as inlaid. */}
        <linearGradient id="rm-floor-top" x1="0" y1="0" x2="0.4" y2="1">
          <stop offset="0%" stopColor="rgba(255,246,230,0.05)" />
          <stop offset="100%" stopColor="rgba(255,246,230,0.022)" />
        </linearGradient>
        <linearGradient id="rm-beacon" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="rgba(253,200,113,0.6)" />
          <stop offset="50%" stopColor="rgba(237,171,72,0.2)" />
          <stop offset="100%" stopColor="rgba(237,171,72,0)" />
        </linearGradient>
        <radialGradient id="rm-lamp">
          <stop offset="0%" stopColor="rgba(168,114,42,0.2)" />
          <stop offset="100%" stopColor="rgba(168,114,42,0)" />
        </radialGradient>
        <filter id="rm-contact" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="2.2" />
        </filter>
        <filter id="rm-glow" x="-120%" y="-120%" width="340%" height="340%">
          <feGaussianBlur stdDeviation="1.6" />
        </filter>
      </defs>

      {/* ------------------------------------------------------------- the floor */}
      <g className="rm-floor">
        <polygon className="rm-face" points={floorFaces.front} fill="url(#rm-slab-edge)" />
        <polygon className="rm-face" points={floorFaces.side} fill="url(#rm-slab-edge)" />
        <polygon className="rm-face rm-floor-top" points={floorFaces.top} fill="url(#rm-floor-top)" />
      </g>

      {/* Painter's order: back row first. */}
      {[...placed]
        .sort((a, b) => a.slab.at[0] + a.slab.at[2] - (b.slab.at[0] + b.slab.at[2]))
        .map((p) => (
          <RoomItemView
            key={p.item.key}
            placed={p}
            selected={selectedKey === p.item.key}
            dimmed={Boolean(selectedKey || hoveredKey) && selectedKey !== p.item.key && hoveredKey !== p.item.key}
            onHover={onHover}
            onSelect={onSelect}
          />
        ))}
    </svg>
  );
}

function RoomItemView({
  placed,
  selected,
  dimmed,
  onHover,
  onSelect,
}: {
  placed: Placed;
  selected: boolean;
  dimmed: boolean;
  onHover?: (key: string | null) => void;
  onSelect?: (key: string) => void;
}) {
  const { item, slab, volumes, labelAt } = placed;
  const f = boxFaces(slab);
  const tallest = Math.max(0, ...volumes.map((v) => v.size[1]));
  const crown = proj(
    slab.at[0] + slab.size[0] / 2,
    slab.at[1] + slab.size[1],
    slab.at[2] + slab.size[2] / 2,
  );

  return (
    <g
      className="rm-item"
      data-kind={item.kind}
      data-selected={selected || undefined}
      data-dimmed={dimmed || undefined}
      onMouseEnter={() => onHover?.(item.key)}
      onMouseLeave={() => onHover?.(null)}
      onClick={() => onSelect?.(item.key)}
      tabIndex={0}
      role="button"
      aria-label={`${item.heading}${item.detail ? ` — ${item.detail}` : ""}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect?.(item.key);
        }
      }}
    >
      <polygon
        className="rm-contact"
        points={groundQuad(slab)}
        filter="url(#rm-contact)"
        transform="translate(1.6, 2)"
      />

      {item.lit && (
        <ellipse
          className="rm-lamp-pool"
          cx={crown[0]}
          cy={crown[1]}
          rx={slab.size[0] * 0.72}
          ry={slab.size[2] * 0.42}
          fill="url(#rm-lamp)"
        />
      )}

      {/* The beacon rises BEFORE the built form, so the structure occludes it
          (owner review A1, and the same rule holds at room scale). */}
      {item.beacon && (
        <g className="rm-beacon">
          <path
            d={`M ${crown[0] - 0.26} ${crown[1]} L ${crown[0] - 0.09} ${crown[1] - (tallest + 3.6) * 0.94} L ${crown[0] + 0.09} ${crown[1] - (tallest + 3.6) * 0.94} L ${crown[0] + 0.26} ${crown[1]} Z`}
            fill="url(#rm-beacon)"
          />
          <circle
            className="rm-beacon-tip"
            cx={crown[0]}
            cy={crown[1] - (tallest + 3.6) * 0.94}
            r={0.36}
            filter="url(#rm-glow)"
          />
        </g>
      )}

      {/* the plinth */}
      <polygon className="rm-face" points={f.front} fill="url(#rm-slab-edge)" />
      <polygon className="rm-face" points={f.side} fill="url(#rm-slab-edge)" />
      <polygon className="rm-face rm-slab-top" points={f.top} fill="url(#rm-slab-top)" />

      {/* built form */}
      {volumes.map((v, i) => {
        const vf = boxFaces(v);
        return (
          <g className="rm-volume" key={i}>
            <polygon className="rm-face" points={vf.front} fill="url(#rm-front)" />
            <polygon className="rm-face" points={vf.side} fill="url(#rm-side)" />
            <polygon className="rm-face rm-volume-top" points={vf.top} fill="url(#rm-top)" />
          </g>
        );
      })}

      {/* A gold seam across a fixture's front face — the protected reserve, and
          nothing else in this product gets one (art bible §2.1). */}
      {item.seam && volumes[0] && <Seam box={volumes[0]} seam={item.seam} />}

      <polygon className="rm-select" points={groundQuad(slab)} />

      {/* ------------------------------------------------------- the flat label */}
      <g className="rm-label">
        <text className="rm-label-head" transform={groundTextTransform(labelAt.x, labelAt.z)}>
          {item.heading}
        </text>
        {item.detail && (
          <text className="rm-label-line" transform={groundTextTransform(labelAt.x, labelAt.z + 1.05)}>
            {item.detail}
          </text>
        )}
        {item.callout && (
          <text
            className="rm-label-callout"
            transform={groundTextTransform(labelAt.x, labelAt.z + (item.detail ? 2.1 : 1.05))}
          >
            {item.callout}
          </text>
        )}
      </g>
    </g>
  );
}

/** The reserve seam, drawn across the vault's lit face at its true fraction. */
function Seam({ box, seam }: { box: Box; seam: { at: number; of: number } }) {
  const [x, y, z] = box.at;
  const [w, h, d] = box.size;
  const frac = Math.max(0, Math.min(1, seam.at / seam.of));
  const sx = x + w * (1 - frac);
  const yTop = y + h;
  const pts = [
    proj(sx, yTop, z + d),
    proj(x + w, yTop, z + d),
    proj(x + w, y, z + d),
    proj(sx, y, z + d),
  ];
  return (
    <polygon
      className="rm-seam"
      points={pts.map((p) => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" ")}
    />
  );
}
