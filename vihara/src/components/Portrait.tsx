/**
 * The colleague portrait — art bible §7 direction **A**.
 *
 * Two layers, and the order matters:
 *
 *  1. **A generated portrait**, if the id has one. `scripts/portraits.py` draws it
 *     on Vertex Imagen 4 from one locked style block plus a one-line persona, then
 *     traces the artwork onto a 112-dot lattice. These are real faces — a person,
 *     not a figure — and they are what §7.1 direction A always specified.
 *  2. **The procedural bust**, for every id that does not. Deterministic from the
 *     entity id, so nothing is ever portrait-less and adding a colleague can never
 *     break a surface while it waits for an art run.
 *
 * Owner review, 2026-07-30: the procedural bust alone was not personified enough.
 * It read as a *figure*; it did not read as a *person*. Correct — a generic
 * silhouette cannot carry a name. The bust stays as the floor precisely because it
 * is the thing that lets the ceiling be optional.
 *
 * Why the generated portrait is an `<img>` rather than inlined: a traced lattice is
 * ~180-270 KB of `<circle>` elements. Inlining twelve of those would put ~2.5 MB
 * into the JS bundle and thousands of nodes into the DOM; as a file it is cached,
 * fetched only when displayed, and never touches the bundle at all.
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

/**
 * The ids with a generated portrait promoted into `public/portraits/`.
 *
 * A literal rather than a fetch of `manifest.json`: the set is known at build
 * time, and fetching it would make every portrait wait a round trip to find out
 * whether it has a face. The manifest file remains the record of what was drawn
 * and by which persona — `scripts/portraits.py` writes both.
 *
 * An id missing from here is not an error; it falls through to the procedural
 * bust, which is the whole point of having one.
 */
const GENERATED = new Set([
  "pragya",
  "agt-013",
  "agt-021",
  "agt-038",
  "agt-041",
  "agt-046",
  "agt-055",
  "agt-092",
  "cand-8801",
  "cand-8814",
  "cand-8822",
  "cand-8830",
]);

/** Ids are cased inconsistently across fixtures (`AGT-046` vs `cand-8801`). */
const assetFor = (id: string): string | null =>
  GENERATED.has(id.toLowerCase()) ? `/portraits/${id.toLowerCase()}.svg` : null;

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
  const asset = assetFor(id);
  const label = title ?? `${id} — a generated portrait, not a photograph`;

  if (asset) {
    return (
      <img
        className={className ? `vh-portrait vh-portrait-img ${className}` : "vh-portrait vh-portrait-img"}
        src={asset}
        width={size}
        height={size}
        alt={label}
        data-drained={drained || undefined}
        loading="lazy"
        decoding="async"
        draggable={false}
      />
    );
  }

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
      aria-label={label}
      style={{ flex: "none" }}
    >
      {bust.dots.map((d, i) => (
        <circle key={i} cx={d.cx} cy={d.cy} r={d.r} className={`vh-pd${d.tone}`} />
      ))}
    </svg>
  );
}
