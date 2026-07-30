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
