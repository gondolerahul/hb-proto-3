/**
 * The atmosphere mount (POLISH P2) — vignette, energy floor, watermark,
 * behind everything at every depth. The wireframes carry this layer on
 * all five approved visuals; the app finally does too.
 *
 * Rules held here rather than by callers:
 * - reduced motion → one static frame, painted once (data-static pins it);
 * - the world canvas live → the whole layer hides (worldActive.ts — the
 *   one-GL-context rule);
 * - per-depth dimming from the scene description, so the floor recedes as
 *   surfaces grow dense instead of competing with them;
 * - pointer-events: none and aria-hidden — atmosphere is never content.
 */
import { useEffect, useRef, useState } from "react";

import { startFloor, type FloorController } from "./floor2d";
import { DEPTH_DIM } from "./scene";
import { subscribeWorldCanvas } from "./worldActive";
import "./atmosphere.css";

export interface AtmosphereProps {
  context: "shell" | "presession" | "line";
  depthLevel?: 0 | 1 | 2 | 3;
}

export function Atmosphere({ context, depthLevel }: AtmosphereProps): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const controllerRef = useRef<FloorController | null>(null);
  const [worldLive, setWorldLive] = useState(false);
  const [reduced] = useState(
    () =>
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => subscribeWorldCanvas(setWorldLive), []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) return;
    const controller = startFloor(canvas, { animate: !reduced });
    controllerRef.current = controller;
    return () => {
      controller.dispose();
      controllerRef.current = null;
    };
  }, [reduced]);

  useEffect(() => {
    const controller = controllerRef.current;
    if (controller === null) return;
    if (worldLive) controller.pause();
    else controller.resume();
  }, [worldLive]);

  const dim =
    context === "shell"
      ? DEPTH_DIM[String(depthLevel ?? 0) as "0" | "1" | "2" | "3"]
      : DEPTH_DIM[context];

  return (
    <div
      className="vh-atmosphere"
      data-part="atmosphere"
      data-hidden={worldLive}
      data-static={reduced}
      aria-hidden="true"
    >
      <div className="vh-vignette" />
      <div className="vh-floorwrap" style={{ opacity: dim }}>
        <canvas ref={canvasRef} data-part="atmosphere-floor" />
      </div>
      <div className="vh-watermark">
        {/* The dotted-B — the brand's one ornament, watermark, never
            redrawn. Synced from the DS under the two-copies gate. */}
        <img src="/brand-mark.svg" alt="" />
      </div>
    </div>
  );
}
