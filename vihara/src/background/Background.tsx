import { useEffect, useRef, useState } from "react";
import { probeTier, tierRunsWorld, type Tier } from "./tier";
import "./background.css";

/**
 * The estate's atmosphere, mounted behind everything.
 *
 * **Decision D2 closed 2026-07-30: the owner picked the brand re-key**, so
 * `"brand"` is the default and the product's only background. `"legacy"` stays
 * selectable — it is the artifact the pick was made against, and keeping it
 * runnable is what keeps the verbatim test meaningful rather than decorative.
 * The two differ in exactly four colour values; see `renderers/world/hexField.ts`.
 *
 * ## Why the scene lives in `renderers/world/` and this file does not
 *
 * D1 §3's class directories are what make D7 §3.3's rule *lintable*: only
 * `components/world/` and `renderers/world/` may name three.js. So the scene
 * sits there and this component — which every surface mounts — stays in the
 * shell's half of the boundary, where the lint would catch a static import.
 * A rule that named `background/` instead would be describing where the code
 * happened to be rather than constraining where three.js may go.
 *
 * ## Why the scene is loaded, not imported
 *
 * D7 §3.3 makes one rule a hard gate: *a tier-C device never downloads three.js.*
 * Quarantining three into its own chunk is necessary and **not sufficient** — a
 * static import puts that chunk in the initial module graph and Vite emits a
 * `modulepreload` for it, so every device fetches 137 KB gzipped whether or not it
 * will ever run a frame. The build looked like it passed the gate while failing it.
 *
 * So `hexField` is reached through `await import()` behind `probeTier()`, and
 * `tests/tier_gate.test.ts` asserts the built `index.html` does not preload the
 * world chunk. On tier C nothing is fetched and the CSS layer carries the look,
 * which is the same path `prefers-reduced-motion` already took.
 *
 * `intensity` is the one addition the redesign makes: at `quiet`/`hushed` the field
 * is veiled behind dense working surfaces, because a breathing floor under a table
 * of invoices competes with the invoices. The scene is never re-graded — only
 * veiled — which is what keeps "ported verbatim" literally true.
 */
export function Background({
  variant = "brand",
  intensity = "full",
}: {
  variant?: "legacy" | "brand";
  intensity?: "full" | "quiet" | "hushed";
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [tier, setTier] = useState<Tier | null>(null);

  useEffect(() => setTier(probeTier()), []);

  useEffect(() => {
    const el = ref.current;
    if (!el || tier === null || !tierRunsWorld(tier)) return;

    let teardown: (() => void) | undefined;
    let cancelled = false;

    // The one place three.js enters the graph, and it is asynchronous by design.
    void import("../renderers/world/hexField").then(
      ({ createHexField, BRAND_PALETTE, LEGACY_PALETTE }) => {
        if (cancelled || !ref.current) return;
        teardown = createHexField(
          ref.current,
          variant === "brand" ? BRAND_PALETTE : LEGACY_PALETTE,
        );
      },
    );

    return () => {
      cancelled = true;
      teardown?.();
    };
  }, [variant, tier]);

  return (
    <div
      className="vh-bg"
      data-variant={variant}
      data-intensity={intensity}
      /* `still` is the honest name for "no scene here": tier C, reduced motion, or
         the probe not yet run. The CSS layer styles it as a deliberate look rather
         than as a scene that failed to arrive. */
      data-still={tier !== null && !tierRunsWorld(tier) ? "" : undefined}
      aria-hidden="true"
    >
      <div className="vh-bg-field" ref={ref} />
      <div className="vh-bg-veil" />
    </div>
  );
}
