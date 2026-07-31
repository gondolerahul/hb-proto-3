import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Icon } from "../components/Icon";
import { fetchCompanyName } from "../api/identity";
import { useLiveEstate } from "../estate/useLiveEstate";
import { stillLine } from "../surfaces/StillSurface";
import "./shell.css";

/**
 * The shell — app-owned, never manifest-composed (D6 §1, carried forward).
 *
 * A manifest composes the *body*. The still line, the depth dial, ⌘K, the echo
 * ribbon, the way out and the presence mark are the application, which is what
 * stops a malformed or hostile manifest from removing the user's way out of a
 * surface.
 *
 * What the redesign changes here is entirely craft. The first build's chrome was
 * a flat dark strip with pill toggles — correct, and indistinguishable from any
 * other dark app. This one is a glass rail with a real edge, the depth ladder is
 * legible as a *ladder* rather than hidden behind a shortcut nobody discovers,
 * and the still line keeps its promise of being the same words as depth 0.
 *
 * **R-4 moves the palette out of this file** (`shell/Palette.tsx`), because the
 * frame does not exist at depth 0 and the navigator has to. The rail keeps the
 * trigger; the app owns the state and mounts the palette at every depth.
 *
 * **R-4 adds the way out.** `onLeave` is the estate's only logout control and it
 * does not confirm: on the desk this is a labelled button in a rail that takes a
 * deliberate click, and the cost of a mis-click is one login. The Line confirms
 * because a thumb on a 390px bar is a different risk.
 */

export type Depth = 0 | 1 | 2 | 3;

export interface ShellProps {
  depth: Depth;
  onDepth: (d: Depth) => void;
  breadcrumb?: { label: string; onClick?: () => void }[];
  echo?: string | null;
  onUndo?: () => void;
  /** Open the navigator. The chord itself is the app's — it has to work at
   *  depth 0, where this component is not mounted. */
  onPalette: () => void;
  onLeave: () => void;
  children: ReactNode;
}

export const DEPTH_LABELS: Record<Depth, string> = {
  0: "Still",
  1: "Terrace",
  2: "Rooms",
  3: "Undercroft",
};

export function Shell({
  depth,
  onDepth,
  breadcrumb = [],
  echo,
  onUndo,
  onPalette,
  onLeave,
  children,
}: ShellProps) {
  /* The rail's two readings. `useLiveEstate` shares one connection through
     `sharedStream`, so mounting it here does not open a second — the rail and
     whichever surface is below it read the same stream, which is also what
     stops them disagreeing about how many hands are up. */
  const live = useLiveEstate();
  const [company, setCompany] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void fetchCompanyName().then((name) => {
      if (alive) setCompany(name);
    });
    return () => {
      alive = false;
    };
  }, []);

  const rise = useCallback(() => onDepth(Math.max(0, depth - 1) as Depth), [depth, onDepth]);
  const descend = useCallback(() => onDepth(Math.min(3, depth + 1) as Depth), [depth, onDepth]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key === "ArrowUp") {
        e.preventDefault();
        rise();
      }
      if (meta && e.key === "ArrowDown") {
        e.preventDefault();
        descend();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rise, descend]);

  return (
    <div className="sh" data-depth={depth}>
      <a className="vh-skip" href="#sh-body">
        Skip to the surface
      </a>

      {/* ================================================== the still line rail */}
      <header className="sh-rail m-glass" data-strong>
        <div className="sh-rail-left">
          <span className="sh-mark" aria-hidden="true">
            <span className="sh-mark-dot" />
          </span>
          {/* Absent until `/auth/me` answers, and absent forever if it cannot:
              a placeholder company name on the rail of every room is a lie the
              owner reads all day. `fetchCompanyName` is fail-soft by design. */}
          {company !== null && (
            <span className="sh-company t-display">{company}</span>
          )}

          {breadcrumb.length > 0 && (
            <nav className="sh-crumbs" aria-label="Breadcrumb">
              {breadcrumb.map((c, i) => (
                <span className="sh-crumb" key={c.label}>
                  <Icon name="chevron" size={12} className="sh-crumb-sep" />
                  {c.onClick ? (
                    <button className="sh-crumb-btn" onClick={c.onClick}>
                      {c.label}
                    </button>
                  ) : (
                    <span aria-current={i === breadcrumb.length - 1 ? "page" : undefined}>
                      {c.label}
                    </span>
                  )}
                </span>
              ))}
            </nav>
          )}

          {/* The still line, condensed. Same words as depth 0, ALWAYS — which is
              why `stillLine` is imported from the surface that owns it rather
              than re-derived here. D6 §1 makes this a requirement and not a
              convenience: two copies of that sentence is how the rail and the
              front door come to disagree about the estate.

              It renders only once the estate has answered. A headline and a
              hands count are readings, and the rail printing either before it
              has one would be inventing them — which is the same rule the
              surfaces below it follow, applied to their chrome. */}
          {depth > 0 && live.phase === "ready" && (
            <p className="sh-still">
              <span className="t-subtle">{stillLine(live.estate)}</span>
              {live.estate.beacons.length > 0 && (
                <>
                  <span className="sh-still-sep" aria-hidden="true">
                    ·
                  </span>
                  <span className="sh-still-hands">
                    <span className="m-lamp" data-lit data-breathing />
                    {live.estate.beacons.length} waiting
                  </span>
                </>
              )}
            </p>
          )}
        </div>

        <div className="sh-rail-right">
          <button
            className="sh-palette-btn m-chip"
            onClick={onPalette}
            aria-label="Go to a surface"
          >
            <Icon name="search" size={13} />
            <kbd>⌘K</kbd>
          </button>

          {/* Presence — never a face, never a floating avatar (D6 §1). */}
          <button className="sh-presence" aria-label="Pragya is listening">
            <span className="sh-presence-mark" data-state="listening" aria-hidden="true" />
            <span className="t-eyebrow">PRAGYA</span>
          </button>

          <button className="m-btn sh-leave" data-rank="quiet" onClick={onLeave}>
            Leave
          </button>
        </div>
      </header>

      {/* ==================================================== the depth ladder */}
      <nav className="sh-dial" aria-label="Depth">
        <button
          className="sh-dial-btn"
          onClick={rise}
          disabled={depth === 0}
          aria-label="Rise a level"
          title="Rise · ⌘↑"
        >
          <Icon name="up" size={14} />
        </button>
        <ol className="sh-dial-rungs">
          {([0, 1, 2, 3] as Depth[]).map((d) => (
            <li key={d}>
              <button
                className="sh-rung"
                data-active={d === depth || undefined}
                data-passed={d < depth || undefined}
                onClick={() => onDepth(d)}
                aria-current={d === depth ? "true" : undefined}
              >
                <span className="sh-rung-tick" aria-hidden="true" />
                <span className="sh-rung-label t-eyebrow">{DEPTH_LABELS[d]}</span>
              </button>
            </li>
          ))}
        </ol>
        <button
          className="sh-dial-btn"
          onClick={descend}
          disabled={depth === 3}
          aria-label="Descend a level"
          title="Descend · ⌘↓"
        >
          <Icon name="down" size={14} />
        </button>
      </nav>

      {/* ============================================================== the body */}
      <main className="sh-body" id="sh-body" tabIndex={-1}>
        {children}
      </main>

      {/* ======================================================= the echo ribbon */}
      {echo && (
        <div className="sh-echo m-glass vh-echo" role="status" key={echo}>
          <span className="t-eyebrow">DONE</span>
          <span className="sh-echo-text">{echo}</span>
          {onUndo && (
            <button className="sh-echo-undo m-btn" data-rank="quiet" onClick={onUndo}>
              <Icon name="undo" size={13} />
              Undo
            </button>
          )}
        </div>
      )}
    </div>
  );
}
