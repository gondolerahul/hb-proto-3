import { Icon } from "../components/Icon";
import "./lifecycle.css";

/**
 * The failure state (R-4 part L, L3 — and the boundary's face for L4).
 *
 * > An estate with nothing in the tray and an estate that failed to load look
 * > identical if only one of them is designed. (D7/R-4 §5)
 *
 * That sentence is the whole brief for this file, and it is why `Failed` is not
 * `Empty` with a red word in it:
 *
 *  1. **A different material, not a different colour.** `Empty` wears the dot
 *     lattice — "we asked, and the answer is nothing". This wears the diagonal
 *     repair hatch `bridges.css` puts on a bridge with a dead credential —
 *     "something is broken, and it is not you". A person who has spent a week
 *     in the estate reads the two apart before reading either.
 *
 *  2. **The copy names the thing it is not.** Every failure sentence here says,
 *     in words, that this is *not* an empty room. That is the one reading that
 *     is actually dangerous: a tenant who concludes their tray is clear when in
 *     fact the tray never arrived has been misinformed by a calm screen.
 *
 *  3. **Nothing is invented and nothing is swallowed.** No count, no "0 items",
 *     no dash (§7.1). The machine's own words are printed in `t-mono` at
 *     caption size — evidence for whoever wants it, never the message — and
 *     `SurfaceBoundary` also puts them through `console.error`, so a crash
 *     leaves two trails and neither of them is silent.
 *
 * `role="status"` rather than `role="alert"`: §6 gives a result-reporting block
 * `status`, and a screen-reader user who has just navigated into this region is
 * better served by it being announced once, politely, than by an assertive
 * interruption of whatever they were reading.
 *
 * **`retry` is optional and is not faked.** Where the caller has no way to try
 * again, the button is absent rather than present and inert — a control that
 * does nothing is worse than no control, and this is the screen where trust is
 * already thin.
 */
export function Failed({
  what,
  reason,
  onRetry,
  crashed = false,
  alone = true,
  className,
}: {
  /** What could not be loaded, as a person would name it: "the Tray". */
  what: string;
  /** The machine's own words. `null`/absent when there genuinely are none. */
  reason?: string | null;
  /** Absent when there is nothing useful to retry. Never a dead button. */
  onRetry?: () => void;
  /** True when this is a render-time throw caught by `SurfaceBoundary` rather
   *  than a request that failed. Different cause, different sentence. */
  crashed?: boolean;
  /** Defaults true: a failure is nearly always the whole of what is on screen.
   *  Pass `false` for a single block inside an otherwise working surface. */
  alone?: boolean;
  className?: string;
}) {
  return (
    <div
      className={`m-plate lc-notice${className ? ` ${className}` : ""}`}
      data-state="failed"
      data-alone={alone || undefined}
      role="status"
    >
      {/* `alert` for both causes, and `clock` on `Empty`, because that is the
          pairing `bridges.css` already teaches: the triangle is a thing that
          broke, the clock is a thing nobody ever learned. */}
      <span className="lc-mark" aria-hidden="true">
        <Icon name="alert" size={15} />
      </span>

      <div className="lc-text">
        <span className="t-eyebrow">
          {crashed ? "THIS SURFACE STOPPED" : "COULD NOT LOAD"}
        </span>

        <p className="lc-title">
          <span className="m-lamp" data-negative aria-hidden="true" />
          {crashed
            ? `${what} stopped part-way through drawing itself.`
            : `We could not load ${what}.`}
        </p>

        <p className="lc-body">
          {crashed ? (
            <>
              Something inside this room threw while it was being drawn, so you
              are being told rather than left reading half a room.{" "}
              <strong>The rest of the estate is untouched</strong> — the rail,
              the depth ladder and every other room are still working, and
              nothing you did has been undone.
            </>
          ) : (
            <>
              <strong>This is not an empty {what}.</strong> The estate may well
              have something to show here; this screen asked for it and did not
              get an answer, so it is showing you nothing rather than guessing.
              Nothing has been changed.
            </>
          )}
        </p>

        {reason !== undefined && reason !== null && reason !== "" && (
          <p className="lc-reason">{reason}</p>
        )}

        {onRetry !== undefined && (
          <div className="lc-acts">
            <button className="m-btn" onClick={onRetry}>
              <Icon name="undo" size={13} />
              {crashed ? "Draw it again" : "Try again"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
