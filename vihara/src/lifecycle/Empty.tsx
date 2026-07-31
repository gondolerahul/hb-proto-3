import { Icon, type IconName } from "../components/Icon";
import "./lifecycle.css";

/**
 * The collection-level empty state (R-4 part L, L2).
 *
 * DESIGN_CONTRACT §7.3: *a surface with little to show says so in prose, never
 * an empty chart.* Until now that was a rule each surface kept or broke on its
 * own, and seven of them could not keep it at all because they crashed before
 * they could render it — `TraySurface` carries the words "Nothing needs you."
 * three lines below the `TRAY[0]!` that threw.
 *
 * Three decisions a reader could not recover from the markup:
 *
 *  1. **It wears the dot lattice from `bridges.css`.** That surface established
 *     the lattice as the register for "a gauge with nothing behind it" and the
 *     diagonal hatch as "under repair", and it was careful that the two never
 *     read alike. An empty collection and a failed load are the same pair of
 *     meanings one level up, so they inherit the same pair of textures rather
 *     than inventing a third and a fourth. `Failed` is the hatch; this is the
 *     lattice. The distinction survives a glance and survives greyscale.
 *
 *  2. **The lamp is unlit and the sentence carries the meaning.** An absence is
 *     not a fault state — the same reasoning `BoardroomSurface` applies to
 *     `no-comparison` and `TalentSurface` to `untested`. A terracotta lamp here
 *     would teach a person that nothing-in-the-tray is something to fix, which
 *     is the exact opposite of what a quiet estate means.
 *
 *  3. **There is no heading element.** A block that hard-codes `<h3>` lands
 *     inside eighteen different outlines and is wrong in most of them. The
 *     title is a paragraph at title weight, exactly as `bridges.css`'s
 *     credential block does it, and the surrounding section keeps its own
 *     heading.
 *
 * **Not a live region**, unlike `Failed`. `BridgesSurface` already settled this
 * for the estate — "this is standing state, and four announcing regions on one
 * surface is noise". An empty collection is a standing condition reachable by
 * heading and by reading order; a failure is an event with a result, and §6
 * gives the second one `role="status"` and not the first.
 *
 * The copy is the caller's, always. There is no default sentence and no
 * `props.children` fallback: "Nothing here" is not designed copy, and a
 * component that supplies one guarantees eighteen surfaces will use it.
 */
export function Empty({
  icon = "clock",
  title,
  body,
  note,
  act,
  alone = false,
  className,
}: {
  /** From `Icon.tsx`'s `PATHS` only. Defaults to the clock the Bridges surface
   *  uses for "nothing has ever written this". */
  icon?: IconName;
  /** The state, in one sentence. "Nothing needs you." */
  title: string;
  /** Why it is empty, and what would change it. Prose, at reading measure. */
  body: string;
  /** Optionally a machine-side fact — a filter that is on, a count, a date. */
  note?: string;
  /** The one act that would fill it, if there is one. Never invented. */
  act?: { label: string; onClick: () => void; icon?: IconName };
  /** True when this is the whole of a surface rather than one block inside it. */
  alone?: boolean;
  className?: string;
}) {
  return (
    <div
      className={`m-well lc-notice${className ? ` ${className}` : ""}`}
      data-state="empty"
      data-alone={alone || undefined}
    >
      <span className="lc-mark" aria-hidden="true">
        <Icon name={icon} size={15} />
      </span>

      <div className="lc-text">
        <p className="lc-title">
          <span className="m-lamp" aria-hidden="true" />
          {title}
        </p>
        <p className="lc-body">{body}</p>
        {note !== undefined && <p className="lc-reason">{note}</p>}
        {act !== undefined && (
          <div className="lc-acts">
            <button className="m-btn" data-rank="quiet" onClick={act.onClick}>
              {act.icon !== undefined && <Icon name={act.icon} size={13} />}
              {act.label}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
