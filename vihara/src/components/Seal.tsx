import { useMemo } from "react";

/**
 * The seal — art bible §7 direction **C**, the automatic fallback.
 *
 * R1 chose direction A (the halftone bust, now `components/Portrait`) as the
 * house style with C as the fallback, and the rule is per-entity: a colleague
 * with a defined persona gets a bust; **everything else gets a seal** — a
 * gateway, a Meta-Agent role, a newly seeded agent, a connector. Nothing in the
 * product is ever portrait-less and nothing waits on an art pipeline.
 *
 * A concentric dot arrangement struck from the entity id. Deterministic, so the
 * same id yields the same mark in every surface; procedural, so a colleague
 * terminated two years ago still renders in the Gallery with no asset store.
 *
 * Lifted out of `DossierSurface` on 2026-07-30 — it was authored there when the
 * dossier was its only consumer, and a shared idiom living inside one surface is
 * how two idioms for the same thing eventually appear.
 */

/**
 * A colleague drawn as a personal seal: concentric rings of gold dots, struck
 * into a dark ground, generated deterministically from the entity id.
 *
 * Why this shape: L7 requires a portrait that is disclosed as AI *by its
 * medium* — a dot lattice cannot be mistaken for a photograph in any crop, at
 * any size, with no badge to lose. And §2.1a keeps portraits un-glowing at
 * rest, so the seal is built from the deep half of the gold ramp with exactly
 * one bright "signature" ring per identity — gold as material, never as light.
 *
 * The geometry is machined, not random: every ring has an even dot count and
 * exact spacing, and each id's individuality comes from four deterministic
 * marks — which ring is the bright one, the interlock phase between rings,
 * an alternating outer ring, and a keyway (a gap of one or two dots) cut into
 * one ring the way a physical seal carries its registration notch.
 */

function fnv1a(str: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** Small deterministic PRNG — the seal must be identical on every render. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface SealDot {
  cx: number;
  cy: number;
  r: number;
  /** 0 = bright (signature), 1 = mid, 2 = deep. Mapped to the ramp in CSS. */
  tone: 0 | 1 | 2;
}

function sealDots(id: string): SealDot[] {
  const rnd = mulberry32(fnv1a(id) || 1);
  const C = 48; // viewBox 96 centre
  const dots: SealDot[] = [];

  // The centre strike — the only dot allowed to be large.
  dots.push({ cx: C, cy: C, r: +(2.6 + rnd() * 1.1).toFixed(2), tone: 0 });

  const RINGS = 5;
  const signature = Math.floor(rnd() * RINGS);
  const keywayRing = 1 + Math.floor(rnd() * (RINGS - 1));

  for (let k = 0; k < RINGS; k++) {
    const radius = 10.5 + k * 8; // 10.5 … 42.5, inside the 48 ground
    // Even dot count scaled with circumference → constant, machined spacing.
    const count = 2 * Math.max(3, Math.round((radius * (0.55 + rnd() * 0.25)) / 2));
    const phase = rnd() < 0.5 ? 0 : Math.PI / count; // half-step interlock
    const keywayAt = Math.floor(rnd() * count);
    const keywayLen = 1 + Math.floor(rnd() * 2);
    const alternating = k === RINGS - 1 && rnd() < 0.6;
    const dotR = 2.3 - k * 0.2 + (k === signature ? 0.35 : 0);
    const tone: SealDot["tone"] = k === signature ? 0 : rnd() < 0.5 ? 1 : 2;

    for (let i = 0; i < count; i++) {
      if (k === keywayRing && (i - keywayAt + count) % count < keywayLen) {
        continue; // the keyway — this identity's registration notch
      }
      const a = phase + (i * 2 * Math.PI) / count - Math.PI / 2;
      const r = alternating && i % 2 === 1 ? dotR * 0.55 : dotR;
      dots.push({
        cx: +(C + radius * Math.cos(a)).toFixed(2),
        cy: +(C + radius * Math.sin(a)).toFixed(2),
        r: +r.toFixed(2),
        tone,
      });
    }
  }
  return dots;
}

/**
 * The family's portrait. `tone="drained"` is the Gallery/twin material (art
 * bible §7.2): the past and the not-yet-real share it, because neither is
 * currently true. Pass `label` when the seal is the only thing naming the
 * person; omit it when a name sits beside it.
 */
export function Seal({
  id,
  size = 56,
  tone = "live",
  label,
  className,
}: {
  id: string;
  size?: number;
  tone?: "live" | "drained";
  label?: string;
  className?: string;
}) {
  const dots: SealDot[] = useMemo(() => sealDots(id), [id]);
  return (
    <span
      className={className ? `do-seal ${className}` : "do-seal"}
      data-tone={tone}
      {...(label ? { role: "img" as const, "aria-label": label } : { "aria-hidden": true })}
    >
      <svg width={size} height={size} viewBox="0 0 96 96" focusable="false">
        {dots.map((d, i) => (
          <circle key={i} cx={d.cx} cy={d.cy} r={d.r} className={`do-seal-d${d.tone}`} />
        ))}
      </svg>
    </span>
  );
}

