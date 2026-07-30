import { useEffect, useRef } from "react";
import { BRAND_PALETTE, LEGACY_PALETTE, createHexField } from "./hexField";
import "./background.css";

/**
 * The two candidates of redesign decision D2, mounted behind everything.
 *
 * `variant="legacy"` is the owner's approved background with its own colours.
 * `variant="brand"` is the same scene re-keyed to gold + a cool neutral.
 * Nothing else differs — see `hexField.ts` and the verbatim test.
 *
 * `intensity` is the one addition the redesign makes: at `"quiet"` the field is
 * dimmed and its motion stilled behind dense working surfaces, because a
 * breathing floor under a table of invoices competes with the invoices. The
 * scene is untouched; the dimming is a CSS layer over it, so the approved look
 * is never re-graded — only veiled.
 */
export function Background({
  variant = "legacy",
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
