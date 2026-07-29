/**
 * The procedural seal — portrait direction C, the automatic fallback the
 * owner ratified at R1 (art bible §7.1). A concentric dot arrangement,
 * deterministic from the entity id: no raster step, no asset store, no
 * drift between a colleague's portrait and its versions, and the Gallery
 * can render a colleague terminated years ago from nothing but its id.
 *
 * L7's disclosure is carried by the medium: a dot-field seal cannot be
 * mistaken for a photograph in any context, with no badge to crop off.
 * Rules that hold whichever direction wins (art bible §7.2): never
 * gold-glowing at rest — the seal is quiet gold-700 line-work; a raised
 * hand gets a beacon ABOVE the portrait, not a gilded face.
 */

export interface SealRing {
  radius: number;
  dots: number;
  dotRadius: number;
  phase: number;
}

export interface SealSpec {
  rings: SealRing[];
}

/** FNV-1a — stable, tiny, and plenty for decoration. */
function fnv1a(text: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/** Pure: the same id yields the same seal, forever. */
export function sealSpec(id: string): SealSpec {
  const hash = fnv1a(id);
  const ringCount = 3 + (hash % 2);
  const rings: SealRing[] = [];
  for (let ring = 0; ring < ringCount; ring += 1) {
    const seed = fnv1a(`${id}:${ring}`);
    rings.push({
      radius: 12 + ring * 9,
      dots: 6 + (seed % 11) + ring * 3,
      dotRadius: 1.4 + ((seed >>> 8) % 3) * 0.5,
      phase: ((seed >>> 16) % 360) * (Math.PI / 180),
    });
  }
  return { rings };
}

export function Seal({
  id,
  size = 48,
  label,
}: {
  id: string;
  size?: number;
  label?: string;
}): JSX.Element {
  const spec = sealSpec(id);
  const center = 50;
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      role="img"
      aria-label={label ?? "seal"}
      data-part="seal"
    >
      <circle
        cx={center}
        cy={center}
        r={4}
        fill="var(--gold-700, #a8722a)"
      />
      {spec.rings.map((ring, ringIndex) => (
        <g key={ringIndex}>
          {Array.from({ length: ring.dots }, (_, dotIndex) => {
            const angle = ring.phase + (dotIndex / ring.dots) * Math.PI * 2;
            return (
              <circle
                key={dotIndex}
                cx={center + Math.cos(angle) * ring.radius}
                cy={center + Math.sin(angle) * ring.radius}
                r={ring.dotRadius}
                fill="var(--gold-700, #a8722a)"
              />
            );
          })}
        </g>
      ))}
    </svg>
  );
}
