/**
 * The colleague portrait — art bible §7 direction **A**, generated.
 *
 * R1 chose direction A (halftone gold-dot bust) as the house style with C (the
 * abstract seal) as the automatic fallback, and made the A rasters a pre-G1
 * obligation blocked on an image pipeline. Owner review C (2026-07-30) asked for
 * agents to be **more personified** than the seal.
 *
 * This is direction A without the pipeline: a shoulder-up figure whose form is
 * carried by **dot density**, sampled on a hex lattice and generated
 * deterministically from the entity id. No raster, no ADC, no asset store, no
 * drift between a colleague's portrait and its versions, and a colleague
 * terminated two years ago still renders.
 *
 * ## Why this satisfies L7 rather than skirting it
 *
 * L7 requires portraits "unmistakably non-human" and disclosed as AI **by their
 * medium**. A halftone dot field discloses itself at a glance, in any crop, at
 * any size, with no badge to lose and no label to localise. Features are never
 * drawn — the dots imply a head, a neck and shoulders, and stop. It reads as a
 * person the way a newspaper halftone reads as a person, which is to say
 * legibly and obviously as a reproduction.
 *
 * ## Why it stays inside the gold budget
 *
 * §2.1 forbids gold on "portraits at rest", and §2.1a keeps the exemption to the
 * atmosphere layer only. So the ramp here is the **deep half** of the gold scale
 * (`--gold-600`…`--gold-900`) with a single lit rim following the one warm key
 * from the upper left. The brightest dot in a portrait sits below the dimmest
 * beacon: gold as *material*, never as light. A room full of colleagues cannot
 * out-shout one raised hand.
 */

/** FNV-1a, 32-bit. Stable, and enough to decorrelate short ids. */
function fnv1a(str: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

/** xorshift32. Deterministic, never seeded from anything ambient. */
function rng(seed: number): () => number {
  let s = seed || 1;
  return () => {
    s ^= s << 13;
    s >>>= 0;
    s ^= s >>> 17;
    s ^= s << 5;
    s >>>= 0;
    return s / 0x100000000;
  };
}

interface Dot {
  cx: number;
  cy: number;
  r: number;
  /** 0 = lit rim, 1 = mid, 2 = deep shadow. */
  tone: 0 | 1 | 2;
}

/**
 * The bust's form, as an inside-ness field.
 *
 * Returns 0 outside and rises toward 1 at the core of the mass. Dot radius reads
 * that value, which is what makes density carry the form: the silhouette's edge
 * is a scatter of small dots and its centre is a solid field, exactly as a
 * halftone behaves.
 */
function buildBust(id: string): { dots: Dot[]; label: string } {
  const seed = fnv1a(id);
  const rnd = rng(seed);

  // Per-identity proportions. Ranges are deliberately narrow — these are people
  // in one house style, not a character generator.
  const headRx = 16.5 + rnd() * 4.5;
  const headRy = 19 + rnd() * 4;
  const headCy = 30 + rnd() * 3;
  const tilt = (rnd() - 0.5) * 0.22; // radians, a slight turn of the head
  const neckW = 7.2 + rnd() * 2.4;
  const shoulderTop = headCy + headRy + 7 + rnd() * 3;
  // Shoulders reach most of the frame's width. At 27 the figure read as a small
  // person in a large box rather than as a bust filling its plate.
  const shoulderHalf = 35 + rnd() * 8;
  const slope = 0.28 + rnd() * 0.3;
  // A crown mass — the silhouette above the skull. The single strongest cue that
  // two portraits are two different people.
  const crownLift = 1.5 + rnd() * 5.5;
  const crownWiden = rnd() * 3.2;

  const cx0 = 50;
  const cos = Math.cos(tilt);
  const sin = Math.sin(tilt);

  const headField = (x: number, y: number) => {
    const dx = x - cx0;
    const dy = y - headCy;
    // Rotate into the head's own frame so the tilt affects the mass, not just
    // an outline.
    const rx = dx * cos + dy * sin;
    const ry = -dx * sin + dy * cos;
    // The crown widens and lifts the upper half only.
    const upper = ry < 0;
    const a = headRx + (upper ? crownWiden : 0);
    const b = headRy + (upper ? crownLift : 0);
    const d = (rx * rx) / (a * a) + (ry * ry) / (b * b);
    return d <= 1 ? 1 - Math.sqrt(d) : 0;
  };

  const neckField = (x: number, y: number) => {
    const top = headCy + headRy - 3;
    if (y < top || y > shoulderTop + 3) return 0;
    const half = neckW / 2;
    const d = Math.abs(x - cx0) / half;
    return d <= 1 ? 1 - d : 0;
  };

  const bodyField = (x: number, y: number) => {
    if (y < shoulderTop) return 0;
    const t = (y - shoulderTop) / (100 - shoulderTop);
    // Shoulders rise from the neck and flatten out — a slope, not a triangle.
    const half = neckW / 2 + (shoulderHalf - neckW / 2) * Math.min(1, t / slope);
    const d = Math.abs(x - cx0) / half;
    if (d > 1) return 0;
    // Rounded shoulder tops, so the mass does not read as a box.
    const shoulderRound = Math.min(1, (y - shoulderTop) / 5);
    return (1 - d * 0.72) * shoulderRound;
  };

  const dots: Dot[] = [];
  const STEP = 3.6;
  const ROWS = Math.ceil(100 / (STEP * 0.87));

  for (let row = 0; row < ROWS; row++) {
    const y = row * STEP * 0.87 + 1.6;
    // Hex lattice: alternate rows offset by half a step. A square lattice reads
    // as a grid laid over a person; a hex lattice reads as a screen.
    const xOff = row % 2 === 0 ? 0 : STEP / 2;
    for (let x = xOff + 1.2; x < 100; x += STEP) {
      const f = Math.max(headField(x, y), neckField(x, y), bodyField(x, y));
      if (f <= 0.02) continue;

      /* Radius carries the form. The floor keeps the silhouette's edge present
         as a scatter rather than letting it vanish, which is what stops the
         figure reading as a blob. */
      const r = 0.62 + Math.min(1, f * 1.35) * 1.14;

      /* Tone follows the one warm key from the upper left (art bible §4), so the
         portrait is lit by the same light as the territory. */
      const key = (50 - x) * 0.011 + (headCy - y) * 0.009 + f * 0.55;
      const tone: 0 | 1 | 2 = key > 0.5 ? 0 : key > 0.2 ? 1 : 2;

      dots.push({ cx: +x.toFixed(2), cy: +y.toFixed(2), r: +r.toFixed(2), tone });
    }
  }

  return { dots, label: `${id} — a generated portrait, not a photograph` };
}

const cache = new Map<string, { dots: Dot[]; label: string }>();

export function Portrait({
  id,
  size = 44,
  /** The Gallery and the twin drain their portraits: the past and the not-yet-real
      share a material, because neither is currently true (art bible §5, §7.2). */
  drained = false,
  className,
  title,
}: {
  id: string;
  size?: number;
  drained?: boolean;
  className?: string;
  title?: string;
}) {
  // ~700 dots per bust and portraits recur in every list; the field is a pure
  // function of the id, so it is computed once per identity per session.
  let bust = cache.get(id);
  if (!bust) {
    bust = buildBust(id);
    cache.set(id, bust);
  }

  return (
    <svg
      className={className ? `vh-portrait ${className}` : "vh-portrait"}
      width={size}
      height={size}
      viewBox="0 0 100 100"
      data-drained={drained || undefined}
      role="img"
      aria-label={title ?? bust.label}
      style={{ flex: "none" }}
    >
      {bust.dots.map((d, i) => (
        <circle key={i} cx={d.cx} cy={d.cy} r={d.r} className={`vh-pd${d.tone}`} />
      ))}
    </svg>
  );
}
