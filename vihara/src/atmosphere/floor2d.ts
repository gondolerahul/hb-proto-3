/**
 * The Canvas-2D energy floor (POLISH P2) — the legacy background system's
 * look at Canvas-2D cost: warm light drifting under matte hex tiles, the
 * construction the wireframes ported and R2 approved. This renderer runs
 * on every tier; the GL port (P3) replaces it only where the tier gate
 * allows and falls back here on context loss.
 *
 * Painting is deliberately fixed-resolution (FLOOR.width × height): the
 * canvas sits under a perspective transform and a fog gradient, so extra
 * pixels buy nothing the eye can see and cost exactly what VG-22's p75
 * floor cannot spare.
 */
import { FLOOR, luminanceAt, seededBlobs, type LightBlob } from "./scene";

export interface FloorController {
  /** Stop painting (world canvas live, tab hidden); idempotent. */
  pause(): void;
  /** Resume painting; repaints immediately, idempotent. */
  resume(): void;
  dispose(): void;
}

const INERT: FloorController = {
  pause: () => undefined,
  resume: () => undefined,
  dispose: () => undefined,
};

function hexPath(): Path2D {
  const path = new Path2D();
  const r = FLOOR.hexRadius - FLOOR.gap;
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i;
    const x = r * Math.cos(angle);
    const y = r * Math.sin(angle);
    if (i === 0) path.moveTo(x, y);
    else path.lineTo(x, y);
  }
  path.closePath();
  return path;
}

/**
 * Start painting the floor onto `canvas`. With `animate: false` (reduced
 * motion, and the tier-D path) exactly one frame is painted — the art
 * bible's rule that reduced motion loses atmosphere, never information,
 * inverted: this IS atmosphere, so it keeps a still image and loses only
 * the drift.
 */
export function startFloor(
  canvas: HTMLCanvasElement,
  options: { animate: boolean; seed?: number; now?: () => Date },
): FloorController {
  const ctx = canvas.getContext("2d");
  if (ctx === null) {
    // jsdom, or a canvas-starved browser: the vignette still stands and
    // nothing throws — atmosphere degrades to silence, never to an error.
    return INERT;
  }
  canvas.width = FLOOR.width;
  canvas.height = FLOOR.height;

  const blobs: LightBlob[] = seededBlobs(options.seed);
  const hex = hexPath();
  const now = options.now ?? ((): Date => new Date());
  const columns = Math.ceil(FLOOR.width / (FLOOR.hexRadius * 1.5)) + 2;
  const rows = Math.ceil(FLOOR.height / (FLOOR.hexRadius * Math.sqrt(3))) + 2;

  let elapsed = 0;
  let frameHandle: number | null = null;
  let paused = false;
  let disposed = false;

  const paint = (): void => {
    const lum = luminanceAt(now());
    ctx.fillStyle = FLOOR.backdrop;
    ctx.fillRect(0, 0, FLOOR.width, FLOOR.height);

    for (const blob of blobs) {
      const x = blob.x + Math.sin(elapsed * blob.dx + blob.phase) * 150;
      const y = blob.y + Math.cos(elapsed * blob.dy + blob.phase) * 95;
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, blob.r);
      const alpha = (blob.bright ? 0.36 : 0.3) * lum.glow;
      gradient.addColorStop(0, `rgba(${FLOOR.light},${alpha})`);
      gradient.addColorStop(1, `rgba(${FLOOR.light},0)`);
      ctx.fillStyle = gradient;
      ctx.fillRect(x - blob.r, y - blob.r, blob.r * 2, blob.r * 2);
    }

    // Matte tiles over the light: day lifts the tile face, never the glow.
    const dayness = (lum.face - 1) / 1.3;
    ctx.fillStyle = dayness > 0.5 ? FLOOR.tileDay : FLOOR.tile;
    const vertical = FLOOR.hexRadius * Math.sqrt(3);
    for (let row = 0; row < rows; row++) {
      for (let column = 0; column < columns; column++) {
        const x = column * FLOOR.hexRadius * 1.5;
        const y = row * vertical + (column % 2 === 1 ? vertical / 2 : 0);
        ctx.save();
        ctx.translate(x, y);
        ctx.fill(hex);
        ctx.restore();
      }
    }
  };

  const frame = (): void => {
    frameHandle = null;
    if (paused || disposed) return;
    elapsed += 0.016;
    paint();
    frameHandle = requestAnimationFrame(frame);
  };

  const onVisibility = (): void => {
    if (document.hidden) {
      if (frameHandle !== null) cancelAnimationFrame(frameHandle);
      frameHandle = null;
    } else if (!paused && !disposed && options.animate && frameHandle === null) {
      frameHandle = requestAnimationFrame(frame);
    }
  };

  paint();
  if (options.animate) {
    frameHandle = requestAnimationFrame(frame);
    document.addEventListener("visibilitychange", onVisibility);
  }

  return {
    pause: (): void => {
      paused = true;
      if (frameHandle !== null) cancelAnimationFrame(frameHandle);
      frameHandle = null;
    },
    resume: (): void => {
      if (disposed || !paused) return;
      paused = false;
      paint();
      if (options.animate && frameHandle === null) {
        frameHandle = requestAnimationFrame(frame);
      }
    },
    dispose: (): void => {
      disposed = true;
      if (frameHandle !== null) cancelAnimationFrame(frameHandle);
      frameHandle = null;
      if (options.animate) {
        document.removeEventListener("visibilitychange", onVisibility);
      }
    },
  };
}
