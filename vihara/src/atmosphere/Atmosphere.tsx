/**
 * The atmosphere mount (POLISH P2/P3) — vignette, energy floor, watermark,
 * behind everything at every depth. The wireframes carry this layer on
 * all five approved visuals; the app finally does too.
 *
 * Two engines, one scene description (scene.ts):
 * - Canvas-2D — every tier, the reduced-motion static frame, and the
 *   paint that shows while the GL chunk loads;
 * - the GL port (owner decision 2) — tier A/B, in the SHELL only. The
 *   pre-session screen must not spend the world chunk on a login, and
 *   the Line stays phone-light; both are pinned by test.
 *
 * Rules held here rather than by callers:
 * - reduced motion → one static frame (data-static pins it);
 * - the world canvas live → the whole layer hides (worldActive.ts — the
 *   one-GL-context rule);
 * - a GL fallback (context loss ×2, sustained FPS breach, no WebGL) swaps
 *   to the 2D floor in place, silently, and never retries this session;
 * - per-depth dimming from the one scene table;
 * - pointer-events: none and aria-hidden — atmosphere is never content.
 */
import { lazy, Suspense, useEffect, useRef, useState } from "react";

import { decideTier, type DeviceTier } from "../app/tier";
import { startFloor, type FloorController } from "./floor2d";
import { DEPTH_DIM } from "./scene";
import { subscribeWorldCanvas } from "./worldActive";
import "./atmosphere.css";

// The quarantine's door (D7 §3.3): the GL floor lives in renderers/world/
// — the only tree allowed to import three.js — behind a dynamic import.
const AtmosphereFloor = lazy(
  () => import("../renderers/world/AtmosphereFloor"),
);

export interface AtmosphereProps {
  context: "shell" | "presession" | "line";
  depthLevel?: 0 | 1 | 2 | 3;
}

/** Pure — where the GL floor is allowed to run (15_polish.md §4). */
export function chooseEngine(
  context: AtmosphereProps["context"],
  tier: DeviceTier | null,
  reduced: boolean,
): "gl" | "2d" {
  if (reduced) return "2d";
  if (context !== "shell") return "2d";
  return tier === "A" || tier === "B" ? "gl" : "2d";
}

function TwoDFloor({
  dim,
  paused,
  reduced,
}: {
  dim: number;
  paused: boolean;
  reduced: boolean;
}): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const controllerRef = useRef<FloorController | null>(null);

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
    if (paused) controller.pause();
    else controller.resume();
  }, [paused]);

  return (
    <div className="vh-floorwrap" style={{ opacity: dim }}>
      <canvas ref={canvasRef} data-part="atmosphere-floor" />
    </div>
  );
}

export function Atmosphere({ context, depthLevel }: AtmosphereProps): JSX.Element {
  const [worldLive, setWorldLive] = useState(false);
  const [engine, setEngine] = useState<"gl" | "2d">("2d");
  const fellBack = useRef(false);
  const [reduced] = useState(
    () =>
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => subscribeWorldCanvas(setWorldLive), []);

  useEffect(() => {
    if (chooseEngine(context, "A", reduced) === "2d") return;
    let alive = true;
    decideTier()
      .then((decision) => {
        if (alive && !fellBack.current) {
          setEngine(chooseEngine(context, decision.effective, reduced));
        }
      })
      .catch(() => {
        // No probe, no GL — the 2D floor is already painting.
      });
    return () => {
      alive = false;
    };
  }, [context, reduced]);

  const dim =
    context === "shell"
      ? DEPTH_DIM[String(depthLevel ?? 0) as "0" | "1" | "2" | "3"]
      : DEPTH_DIM[context];

  const twoD = <TwoDFloor dim={dim} paused={worldLive} reduced={reduced} />;

  return (
    <div
      className="vh-atmosphere"
      data-part="atmosphere"
      data-hidden={worldLive}
      data-static={reduced}
      data-engine={engine}
      aria-hidden="true"
    >
      <div className="vh-vignette" />
      {engine === "gl" ? (
        <Suspense fallback={twoD}>
          <div className="vh-glfloor" style={{ opacity: dim }}>
            <AtmosphereFloor
              onFallback={() => {
                fellBack.current = true;
                setEngine("2d");
              }}
            />
          </div>
        </Suspense>
      ) : (
        twoD
      )}
      <div className="vh-watermark">
        {/* The dotted-B — the brand's one ornament, watermark, never
            redrawn. Synced from the DS under the two-copies gate. */}
        <img src="/brand-mark.svg" alt="" />
      </div>
    </div>
  );
}
