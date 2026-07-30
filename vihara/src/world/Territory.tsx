import { Fragment, useMemo } from "react";
import { baseCentre, boxFaces, groundQuad, road, topCentre } from "./iso";
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
  hoveredKey?: string | null;
  onHover?: (key: string | null) => void;
  onOpen?: (key: string) => void;
  night?: boolean;
}

export function Territory({
  districts,
  gatehouses,
  glasshouse = true,
  hoveredKey,
  onHover,
  onOpen,
  night = true,
}: TerritoryProps) {
  const model = useMemo(
    () => buildTerritory(districts, gatehouses, glasshouse),
    [districts, gatehouses, glasshouse],
  );

  const { view } = model;

  return (
    <svg
      className="tv-svg"
      viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
      preserveAspectRatio="xMidYMid meet"
      data-night={night || undefined}
      role="presentation"
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
        {model.plots.filter((p) => p.key !== "sheel").map((p) => (
          <Fragment key={`road-${p.key}`}>
            <path className="tv-road" d={road(SHEEL.gate, p.gate)} data-twin={p.twin || undefined} />
            {p.traffic > 0 && <Traffic path={road(SHEEL.gate, p.gate)} rate={p.traffic} plotKey={p.key} />}
          </Fragment>
        ))}
      </g>

      {/* ============================================================== the plots */}
      {model.ordered.map((p) => (
        <PlotView
          key={p.key}
          plot={p}
          hovered={hoveredKey === p.key}
          dimmed={Boolean(hoveredKey) && hoveredKey !== p.key}
          night={night}
          onHover={onHover}
          onOpen={onOpen}
        />
      ))}
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
}: {
  plot: Plot;
  hovered: boolean;
  dimmed: boolean;
  night: boolean;
  onHover?: (key: string | null) => void;
  onOpen?: (key: string) => void;
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

      {/* ------------------------------------------------------------ the beacon */}
      {plot.beacon && (
        <g className="tv-beacon">
          <ellipse
            cx={crown[0]}
            cy={crown[1]}
            rx={plot.slab.size[0] * 1.1}
            ry={plot.slab.size[2] * 0.62}
            fill="url(#tv-beacon-pool)"
          />
          <path
            className="tv-beacon-shaft"
            d={`M ${crown[0] - 0.9} ${crown[1]} L ${crown[0] - 0.3} ${crown[1] - (tallest + 4.6) * 0.94} L ${crown[0] + 0.3} ${crown[1] - (tallest + 4.6) * 0.94} L ${crown[0] + 0.9} ${crown[1]} Z`}
            fill="url(#tv-beacon)"
          />
          <circle
            className="tv-beacon-tip"
            cx={crown[0]}
            cy={crown[1] - (tallest + 4.6) * 0.94}
            r={0.62}
            filter="url(#tv-glow)"
          />
          <circle
            className="tv-beacon-tip-core"
            cx={crown[0]}
            cy={crown[1] - (tallest + 4.6) * 0.94}
            r={0.28}
          />
        </g>
      )}

      {/* The hover ring. Warm-white, not gold — hovering is not a request. */}
      {interactive && <polygon className="tv-select" points={groundQuad(plot.slab)} />}
    </g>
  );
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
          r={0.26}
          style={{
            ["offsetPath" as string]: `path("${path}")`,
            animationDelay: `${(i / count) * 4.8}s`,
          }}
        />
      ))}
    </g>
  );
}
