/**
 * Surface-printed lettering (§13: names print on the ground / the plate,
 * never billboard) — canvas textures on flat planes, shared by every
 * W room (M2). Options cover the three registers the wireframes use:
 * the small mono label, the gold needs-you line, and the huge plate
 * figure.
 */
import { useMemo } from "react";
import * as THREE from "three";

export interface PlateTextOptions {
  /** Canvas px height of the glyphs (default 58 — the small label). */
  px?: number;
  color?: string;
  weight?: number;
  /** Extra letterspacing via double-spaced glyphs (default true). */
  tracked?: boolean;
  font?: "mono" | "display";
}

/** The wireframes' wall texture: fine horizontal lines on the glass
 * volumes (estate-visual's `wall-y` repeating gradient). */
export function useStripeTexture(
  spacing = 12,
  alpha = 0.08,
): THREE.CanvasTexture | null {
  return useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext("2d");
    if (ctx === null) return null;
    ctx.clearRect(0, 0, 64, 64);
    ctx.strokeStyle = `rgba(246, 241, 233, ${alpha})`;
    ctx.lineWidth = 1;
    for (let y = 0.5; y < 64; y += spacing) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(64, y);
      ctx.stroke();
    }
    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    return texture;
  }, [spacing, alpha]);
}

/** A soft radial light pool — the underglow that sells the float (§13),
 * finally VISIBLE the way the wireframes draw it. */
export function useGlowTexture(): THREE.CanvasTexture | null {
  return useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 128;
    canvas.height = 128;
    const ctx = canvas.getContext("2d");
    if (ctx === null) return null;
    const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    gradient.addColorStop(0, "rgba(246, 241, 233, 0.55)");
    gradient.addColorStop(0.5, "rgba(246, 241, 233, 0.18)");
    gradient.addColorStop(1, "rgba(246, 241, 233, 0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(canvas);
  }, []);
}

/** A deterministic star field for the night sky (estate-visual's .sky). */
export function starPositions(count = 180, seed = 7): Float32Array {
  let state = seed;
  const rnd = (): number => {
    state = (state * 16807) % 2147483647;
    return state / 2147483647;
  };
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const angle = rnd() * Math.PI * 2;
    const radius = 26 + rnd() * 22;
    positions[i * 3] = Math.cos(angle) * radius;
    positions[i * 3 + 1] = 6 + rnd() * 18;
    positions[i * 3 + 2] = Math.sin(angle) * radius;
  }
  return positions;
}

export function useNamePlate(
  text: string,
  options: PlateTextOptions = {},
): THREE.CanvasTexture | null {
  const { px = 58, color = "rgba(246, 241, 233, 0.85)", weight = 500, tracked = true, font = "mono" } = options;
  return useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 1024;
    canvas.height = Math.max(128, px * 2);
    const ctx = canvas.getContext("2d");
    if (ctx === null) return null;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const family =
      font === "display"
        ? "'Space Grotesk', sans-serif"
        : "'JetBrains Mono', monospace";
    ctx.font = `${weight} ${px}px ${family}`;
    ctx.fillStyle = color;
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    const drawn = tracked ? text.toUpperCase().split("").join("  ") : text;
    ctx.fillText(drawn, canvas.width / 2, canvas.height / 2, canvas.width - 40);
    const texture = new THREE.CanvasTexture(canvas);
    texture.anisotropy = 4;
    return texture;
  }, [text, px, color, weight, tracked, font]);
}
