import type { ReactNode } from "react";
import "./lifecycle.css";

/**
 * The scaffold half of scaffold-then-hydrate (R-4 part L, L5).
 *
 * D7 §3.1 is explicit, and it is a contract rather than a preference:
 *
 * > "First scaffold" is the moment the layout and component skeletons are on
 * > screen, **not the moment data arrives.**
 *
 * and it names the Glasshouse as the **only** surface permitted a visible
 * loading state, because a twin run is genuinely slow and pretending otherwise
 * would be the lie. That leaves seventeen surfaces whose pending state has to
 * be their own structure, standing, with the words not yet in it.
 *
 * **So there is no spinner in this module to reach for.** Not a discouraged
 * one, not one behind a flag — the file does not contain the shape. The
 * primitives here draw bars where text will be, in `vh-skeleton` from
 * `motion.css`, which is a sweep rather than a pulse for the reason written
 * beside it: a pulsing opacity on a dark ground reads as a fault, and a room
 * that is merely early is not faulty.
 *
 * Two smaller decisions:
 *
 *  - **The bars are `aria-hidden` and one live sentence speaks for them.** A
 *     screen reader hearing "blank blank blank" nineteen times has been told
 *     less than nothing; it hears "The Tray is still arriving" once, politely,
 *     and the surface announces itself again when the words land.
 *  - **Widths are presets, not an inline style.** §1.4 permits an inline
 *     `style` only for the stagger index. Five widths cover every skeleton, and
 *     a preset cannot drift into an arbitrary number nobody chose.
 */

export function Scaffold({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="lc-scaffold" data-lifecycle="scaffold">
      <p className="vh-sr-only" role="status">
        {label} is still arriving.
      </p>
      {/* The structure is decorative until it has content in it: it says where
          things will be, which is a spatial claim and not a readable one. */}
      <div aria-hidden="true">{children}</div>
    </div>
  );
}

/** One line of text that has not arrived. */
export function Bar({
  width = "full",
  tall = false,
}: {
  width?: "xs" | "sm" | "md" | "lg" | "full";
  tall?: boolean;
}) {
  return (
    <span
      className="lc-bar vh-skeleton"
      data-width={width === "full" ? undefined : width}
      data-tall={tall || undefined}
    />
  );
}

/** A paragraph that has not arrived. The last line is short on purpose — see
 *  `lifecycle.css`; without it a stack of bars reads as a barcode. */
export function Lines({ n = 3 }: { n?: number }) {
  return (
    <span className="lc-lines">
      {Array.from({ length: Math.max(1, n) }, (_, i) => (
        <Bar key={i} />
      ))}
    </span>
  );
}
