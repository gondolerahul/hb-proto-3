import { useEffect, useRef } from "react";
import { BRAND_PALETTE, LEGACY_PALETTE, createHexField } from "./hexField";
import "./background.css";

/**
 * The estate's atmosphere, mounted behind everything.
 *
 * **Decision D2 closed 2026-07-30: the owner picked the brand re-key**, so
 * `"brand"` is the default and the product's only background. `"legacy"` stays
 * selectable — it is the artifact the pick was made against, and keeping it
 * runnable is what keeps the verbatim test meaningful rather than decorative.
 * The two differ in exactly four colour values; see `hexField.ts`.
 *
 * `intensity` is the one addition the redesign makes: at `"quiet"` the field is
 * dimmed and its motion stilled behind dense working surfaces, because a
 * breathing floor under a table of invoices competes with the invoices. The
 * scene is untouched; the dimming is a CSS layer over it, so the approved look
 * is never re-graded — only veiled.
 */
export function Background({
  variant = "brand",
  intensity = "full",
}: {
  variant?: "legacy" | "brand";
  intensity?: "full" | "quiet" | "hushed";
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    return createHexField(el, variant === "brand" ? BRAND_PALETTE : LEGACY_PALETTE);
  }, [variant]);

  return (
    <div className="vh-bg" data-variant={variant} data-intensity={intensity} aria-hidden="true">
      <div className="vh-bg-field" ref={ref} />
      <div className="vh-bg-veil" />
    </div>
  );
}
