import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { baseCentre, boxFaces, groundQuad, groundTextTransform, road, topCentre } from "./iso";
import { SHEEL, buildTerritory, type Plot, type PlotSeed } from "./layout";
import "./territory.css";

export type { TerritoryAnchor, TerritoryModel } from "./layout";
export { buildTerritory } from "./layout";

/**
 * The territory, drawn.
 *
 * Answers findings **RD-1** and **RD-2** structurally rather than cosmetically:
 *
 *   - **RD-2 — solid, lit volumes.** Every box is three real faces with their own
 *     gradient fills and a crisp top edge, standing on a raised slab with a
 *     contact shadow. Nothing is a wireframe.
 *   - **RD-1 — no text in here at all.** This component returns *only* geometry
 *     plus the projected anchors its caller needs. Labels are DOM, laid over the
 *     drawing in screen space by `TerraceSurface`. Nothing is painted onto the
 *     ground plane, so nothing is skewed and everything is selectable.
 *
 * Lighting model: one high warm key from the upper left, per art bible §4. Top
 * faces catch it, +z faces get fill, +x faces fall away. That is the whole model,
 * and keeping it to one key is what makes the estate read as one place rather
 * than as a collection of separately-shaded boxes.
 *
 * The ground is not drawn. The hex-field background shows through, so the estate
 * sits on the atmosphere — which is why contact shadows matter here more than
 * anywhere else in the product: they are what land it on a surface it does not
 * own.
 */

export interface TerritoryProps {
  districts: PlotSeed[];
  gatehouses: string[];
  /** Adds the twin plane at the estate's edge (art bible §5). */
  glasshouse?: boolean;
  /** The Sheel and its roads. Off for the district room's single-plot diorama. */
  sheel?: boolean;
  /**
   * Flat ground labels, keyed by plot (owner review A2). Rendered as real SVG
   * text lying on the floor beside each structure — selectable, in the
   * accessibility tree, and never over built form.
   */
  labels?: Record<string, GroundLabel>;
  /** Drag to pan, wheel to zoom (owner review A3). */
  navigable?: boolean;
  hoveredKey?: string | null;
  onHover?: (key: string | null) => void;
  onOpen?: (key: string) => void;
  night?: boolean;
}

/** One flat ground label: a heading line and up to two detail lines. */
export interface GroundLabel {
  heading: string;
  lines?: string[];
  /** Rendered in gold — reserved for "this needs you" (§2.1). */
  callout?: string | null;
  /** The twin's drained material (art bible §5). */
  drained?: boolean;
}

export function Territory({
  districts,
  gatehouses,
  glasshouse = true,
  sheel = true,
  labels,
  navigable = false,
  hoveredKey,
  onHover,
  onOpen,
  night = true,
}: TerritoryProps) {
  const model = useMemo(
    () => buildTerritory(districts, gatehouses, glasshouse, sheel),
    [districts, gatehouses, glasshouse, sheel],
  );

  const { view } = model;
  const camera = useCamera(view, navigable);

  return (
    <svg
      ref={camera.ref}
      className="tv-svg"
      viewBox={camera.viewBox}
      preserveAspectRatio="xMidYMid meet"
      data-night={night || undefined}
      data-navigable={navigable || undefined}
      data-panning={camera.panning || undefined}
      onPointerDown={camera.onPointerDown}
      onPointerMove={camera.onPointerMove}
      onPointerUp={camera.onPointerUp}
      onPointerCancel={camera.onPointerUp}
      onDoubleClick={camera.reset}
      role={navigable ? "application" : "presentation"}
      aria-label={navigable ? "The estate. Drag to pan, scroll to zoom, double-click to reset." : undefined}
    >
      <defs>
        {/* -------------------------------------------------- face lighting */}
        <linearGradient id="tv-top" x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0%" stopColor="rgba(255,248,236,0.19)" />
          <stop offset="100%" stopColor="rgba(255,248,236,0.095)" />
        </linearGradient>
        <linearGradient id="tv-front" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(255,244,228,0.12)" />
          <stop offset="100%" stopColor="rgba(255,244,228,0.05)" />
        </linearGradient>
        <linearGradient id="tv-side" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(255,240,220,0.068)" />
          <stop offset="100%" stopColor="rgba(255,240,220,0.026)" />
        </linearGradient>

        {/* Slabs read as stone: flatter, cooler, and darker than built form. */}
        <linearGradient id="tv-slab-top" x1="0" y1="0" x2="0.5" y2="1">
          <stop offset="0%" stopColor="rgba(255,246,230,0.105)" />
          <stop offset="100%" stopColor="rgba(255,246,230,0.058)" />
        </linearGradient>
        <linearGradient id="tv-slab-edge" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(255,240,220,0.13)" />
          <stop offset="100%" stopColor="rgba(0,0,0,0.4)" />
        </linearGradient>

        {/* The twin: drained, never recoloured (art bible §5). */}
        <linearGradient id="tv-twin-top" x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0%" stopColor="rgba(228,232,236,0.1)" />
          <stop offset="100%" stopColor="rgba(228,232,236,0.045)" />
        </linearGradient>
        <linearGradient id="tv-twin-face" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(228,232,236,0.05)" />
          <stop offset="100%" stopColor="rgba(228,232,236,0.018)" />
        </linearGradient>

        {/* ------------------------------------------------------- the beacon
            Sanctioned gold (§2.1: hands raised). A shaft rather than a marker,
            because a shaft is visible over the whole estate from any angle and a
            marker is not. */}
        <linearGradient id="tv-beacon" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="rgba(253,200,113,0.62)" />
          <stop offset="45%" stopColor="rgba(237,171,72,0.24)" />
          <stop offset="100%" stopColor="rgba(237,171,72,0)" />
        </linearGradient>
        <radialGradient id="tv-beacon-pool">
          <stop offset="0%" stopColor="rgba(237,171,72,0.34)" />
          <stop offset="60%" stopColor="rgba(237,171,72,0.1)" />
          <stop offset="100%" stopColor="rgba(237,171,72,0)" />
        </radialGradient>

        {/* Lamplight at night — low, local, few (art bible §4). Kept faint:
            at 0.3 the pools merged into one wash and drowned the geometry. */}
        <radialGradient id="tv-lamp-pool">
          <stop offset="0%" stopColor="rgba(168,114,42,0.14)" />
          <stop offset="100%" stopColor="rgba(168,114,42,0)" />
        </radialGradient>

        <filter id="tv-contact" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="3.2" />
        </filter>
        <filter id="tv-glow" x="-120%" y="-120%" width="340%" height="340%">
          <feGaussianBlur stdDeviation="2.4" />
        </filter>
      </defs>

      {/* ================================================================ roads
          Drawn first so built form always occludes them. Warm-white ramp, never
          gold — a road is not asking for anything. */}
      <g className="tv-roads">
        {sheel && model.plots.filter((p) => p.key !== "sheel").map((p) => (
          <Fragment key={`road-${p.key}`}>
            <path className="tv-road" d={road(SHEEL.gate, p.gate)} data-twin={p.twin || undefined} />
            {p.traffic > 0 && <Traffic path={road(SHEEL.gate, p.gate)} rate={p.traffic} plotKey={p.key} />}
          </Fragment>
        ))}
      </g>

      {/* ============================================================== the plots */}
      {model.ordered.map((p) => {
        const anchor = model.anchors.find((a) => a.key === p.key);
        return (
          <PlotView
            key={p.key}
            plot={p}
            hovered={hoveredKey === p.key}
            dimmed={Boolean(hoveredKey) && hoveredKey !== p.key}
            night={night}
            onHover={onHover}
            onOpen={onOpen}
            label={labels?.[p.key]}
            anchor={anchor}
          />
        );
      })}
    </svg>
  );
}

function PlotView({
  plot,
  hovered,
  dimmed,
  night,
  onHover,
  onOpen,
  label,
  anchor,
}: {
  plot: Plot;
  hovered: boolean;
  dimmed: boolean;
  night: boolean;
  onHover?: (key: string | null) => void;
  onOpen?: (key: string) => void;
  label?: GroundLabel;
  anchor?: TerritoryAnchorLocal;
}) {
  const twin = Boolean(plot.twin);
  const slab = boxFaces(plot.slab);
  const base = baseCentre(plot.slab);
  const crown = topCentre(plot.slab);
  const tallest = Math.max(0, ...plot.volumes.map((v) => v.size[1]));
  const interactive = Boolean(onOpen) && plot.key !== "sheel";

  return (
    <g
      className="tv-plot"
      data-twin={twin || undefined}
      data-hovered={hovered || undefined}
      data-dimmed={dimmed || undefined}
      data-interactive={interactive || undefined}
      onMouseEnter={() => onHover?.(plot.key)}
      onMouseLeave={() => onHover?.(null)}
      onClick={interactive ? () => onOpen?.(plot.key) : undefined}
    >
      {/* Contact shadow. The cheapest mark on the surface and the one whose
          absence makes the whole estate float. */}
      <polygon
        className="tv-contact"
        points={groundQuad(plot.slab)}
        filter="url(#tv-contact)"
        transform="translate(2.5, 3)"
      />

      {/* Night lamplight, before the slab so the pool sits under it. */}
      {night && !twin && plot.volumes.length > 0 && (
        <ellipse
          className="tv-lamp-pool"
          cx={base[0]}
          cy={base[1]}
          rx={plot.slab.size[0] * 0.9}
          ry={plot.slab.size[2] * 0.55}
          fill="url(#tv-lamp-pool)"
        />
      )}

      {/* -------------------------------------------------------------- the slab */}
      <polygon className="tv-face" points={slab.front} fill={twin ? "url(#tv-twin-face)" : "url(#tv-slab-edge)"} />
      <polygon className="tv-face" points={slab.side} fill={twin ? "url(#tv-twin-face)" : "url(#tv-slab-edge)"} />
      <polygon
        className="tv-face tv-slab-top"
        points={slab.top}
        fill={twin ? "url(#tv-twin-top)" : "url(#tv-slab-top)"}
      />

      {/* ------------------------------------------------------------ the beacon
          Owner review A1: narrower, and drawn BEFORE the built form so the
          buildings occlude it. A shaft the district stands in front of reads as
          light rising from the place; a shaft in front of the buildings reads as
          a sticker on top of them. */
          }
      {plot.beacon && (
        <g className="tv-beacon">
          <ellipse
            cx={crown[0]}
            cy={crown[1]}
            rx={plot.slab.size[0] * 0.62}
            ry={plot.slab.size[2] * 0.34}
            fill="url(#tv-beacon-pool)"
          />
          <path
            className="tv-beacon-shaft"
            d={`M ${crown[0] - 0.34} ${crown[1]} L ${crown[0] - 0.12} ${crown[1] - (tallest + 5.2) * 0.94} L ${crown[0] + 0.12} ${crown[1] - (tallest + 5.2) * 0.94} L ${crown[0] + 0.34} ${crown[1]} Z`}
            fill="url(#tv-beacon)"
          />
          <circle
            className="tv-beacon-tip"
            cx={crown[0]}
            cy={crown[1] - (tallest + 5.2) * 0.94}
            r={0.5}
            filter="url(#tv-glow)"
          />
          <circle
            className="tv-beacon-tip-core"
            cx={crown[0]}
            cy={crown[1] - (tallest + 5.2) * 0.94}
            r={0.22}
          />
        </g>
      )}

      {/* -------------------------------------------------------- built form */}
      {plot.volumes.map((v, i) => {
        const f = boxFaces(v);
        return (
          <g className="tv-volume" key={i}>
            <polygon className="tv-face" points={f.front} fill={twin ? "url(#tv-twin-face)" : "url(#tv-front)"} />
            <polygon className="tv-face" points={f.side} fill={twin ? "url(#tv-twin-face)" : "url(#tv-side)"} />
            <polygon
              className="tv-face tv-volume-top"
              points={f.top}
              fill={twin ? "url(#tv-twin-top)" : "url(#tv-top)"}
            />
          </g>
        );
      })}

      {/* The hover ring. Warm-white, not gold — hovering is not a request. */}
      {interactive && <polygon className="tv-select" points={groundQuad(plot.slab)} />}

      {/* ------------------------------------------------------ the flat label
          Owner review A2. Real SVG text lying on the floor beside the plot —
          selectable, in the accessibility tree, and placed on clear ground
          outside the slab so it can never sit on built form. */}
      {label && anchor && <GroundLabelText label={label} anchor={anchor} />}
    </g>
  );
}

type TerritoryAnchorLocal = {
  labelAt: { x: number; z: number };
  anchorEnd: boolean;
};

/** Line advance in world units — successive lines run along world +z. */
const LINE = 1.15;

function GroundLabelText({
  label,
  anchor,
}: {
  label: GroundLabel;
  anchor: TerritoryAnchorLocal;
}) {
  const { x, z } = anchor.labelAt;
  const tf = (dz: number) => groundTextTransform(x, z + dz);
  // Same transform both ways; only the growth direction differs.
  const textAnchor = anchor.anchorEnd ? "end" : "start";

  let row = 0;
  return (
    <g
      className="tv-label"
      data-drained={label.drained || undefined}
      textAnchor={textAnchor}
    >
      <text className="tv-label-head" transform={tf(row * LINE)}>
        {label.heading}
      </text>
      {(label.lines ?? []).map((line) => {
        row += 1;
        return (
          <text className="tv-label-line" key={line} transform={tf(row * LINE)}>
            {line}
          </text>
        );
      })}
      {label.callout && (
        <text className="tv-label-callout" transform={tf((row + 1) * LINE)}>
          {label.callout}
        </text>
      )}
    </g>
  );
}

/**
 * Drag to pan, wheel to zoom, double-click to reset (owner review A3).
 *
 * The camera moves the **viewBox**, not a CSS transform, so zooming is a true
 * vector zoom: strokes stay hairline-crisp and text stays text at every scale.
 * A CSS `scale()` would resample the whole drawing and soften every edge the
 * material system works to keep sharp.
 *
 * Zoom is anchored on the pointer, which is the only behaviour that feels like
 * looking rather than like a slider — the point under the cursor stays put.
 */
function useCamera(
  base: { x: number; y: number; w: number; h: number },
  enabled: boolean,
) {
  const ref = useRef<SVGSVGElement>(null);
  const [box, setBox] = useState(base);
  const [panning, setPanning] = useState(false);
  const drag = useRef<{ px: number; py: number; box: typeof base } | null>(null);

  /* A new estate (different districts) reframes rather than keeping a stale pan
     — but by *value*, not by identity. `view` is rebuilt whenever `districts`
     changes identity, so depending on the frame object would throw the user's
     pan away on any parent render that merely re-created the array. Pulling the
     four numbers out is what lets the dependency list say exactly that. */
  const { x: baseX, y: baseY, w: baseW, h: baseH } = base;
  useEffect(() => {
    setBox({ x: baseX, y: baseY, w: baseW, h: baseH });
  }, [baseX, baseY, baseW, baseH]);

  const MIN = 0.35; // deepest zoom-in, as a fraction of the framed estate
  const MAX = 1.8; // furthest out

  const onWheel = useCallback(
    (e: WheelEvent) => {
      if (!enabled) return;
      const svg = ref.current;
      if (!svg) return;
      e.preventDefault();

      const rect = svg.getBoundingClientRect();
      setBox((b) => {
        const factor = Math.exp(e.deltaY * 0.0014);
        const scale = b.w / baseW;
        const next = Math.min(MAX, Math.max(MIN, scale * factor));
        const w = baseW * next;
        const h = baseH * next;

        /* Anchor on the pointer. `preserveAspectRatio="xMidYMid meet"` letterboxes,
           so the mapping from client pixels to user units has to account for the
           unused margin — using rect directly would drift the anchor point. */
        const fit = Math.min(rect.width / b.w, rect.height / b.h);
        const usedW = b.w * fit;
        const usedH = b.h * fit;
        const ox = (rect.width - usedW) / 2;
        const oy = (rect.height - usedH) / 2;
        const ux = b.x + (e.clientX - rect.left - ox) / fit;
        const uy = b.y + (e.clientY - rect.top - oy) / fit;

        const kx = (ux - b.x) / b.w;
        const ky = (uy - b.y) / b.h;
        return { x: ux - kx * w, y: uy - ky * h, w, h };
      });
    },
    [enabled, baseW, baseH],
  );

  // Non-passive, because a passive wheel listener cannot preventDefault and the
  // page would scroll underneath the zoom.
  useEffect(() => {
    const svg = ref.current;
    if (!svg || !enabled) return;
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [onWheel, enabled]);

  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!enabled || e.button !== 0) return;
    drag.current = { px: e.clientX, py: e.clientY, box };
    setPanning(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    const svg = ref.current;
    if (!d || !svg) return;
    const rect = svg.getBoundingClientRect();
    const fit = Math.min(rect.width / d.box.w, rect.height / d.box.h);
    setBox({
      ...d.box,
      x: d.box.x - (e.clientX - d.px) / fit,
      y: d.box.y - (e.clientY - d.py) / fit,
    });
  };

  const onPointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    drag.current = null;
    setPanning(false);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  };

  return {
    ref,
    viewBox: `${box.x.toFixed(2)} ${box.y.toFixed(2)} ${box.w.toFixed(2)} ${box.h.toFixed(2)}`,
    panning,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    reset: () => setBox(base),
  };
}

/**
 * Signal traffic — dots travelling the road.
 *
 * Count scales with the rate, so a busy road looks busy. `offset-path` rather
 * than `<animateMotion>` because SMIL ignores `prefers-reduced-motion` and CSS
 * does not, and the global reduced-motion block in motion.css then stops these
 * without this component knowing anything about it.
 */
function Traffic({ path, rate, plotKey }: { path: string; rate: number; plotKey: string }) {
  const count = Math.min(5, Math.max(1, Math.round(rate / 12)));
  return (
    <g className="tv-traffic">
      {Array.from({ length: count }, (_, i) => (
        <circle
          key={`${plotKey}-${i}`}
          className="tv-traffic-dot"
          r={0.14}
          style={{
            ["offsetPath" as string]: `path("${path}")`,
            animationDelay: `${(i / count) * 4.8}s`,
          }}
        />
      ))}
    </g>
  );
}
