import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Icon } from "../components/Icon";
import { COMPANY, STILL } from "../fixtures/estate";
import "./shell.css";

/**
 * The shell — app-owned, never manifest-composed (D6 §1, carried forward).
 *
 * A manifest composes the *body*. The still line, the depth dial, ⌘K, the echo
 * ribbon and the presence mark are the application, which is what stops a
 * malformed or hostile manifest from removing the user's way out of a surface.
 *
 * What the redesign changes here is entirely craft. The first build's chrome was
 * a flat dark strip with pill toggles — correct, and indistinguishable from any
 * other dark app. This one is a glass rail with a real edge, the depth ladder is
 * legible as a *ladder* rather than hidden behind a shortcut nobody discovers,
 * and the still line keeps its promise of being the same words as depth 0.
 */

export type Depth = 0 | 1 | 2 | 3;

export interface ShellProps {
  depth: Depth;
  onDepth: (d: Depth) => void;
  breadcrumb?: { label: string; onClick?: () => void }[];
  echo?: string | null;
  onUndo?: () => void;
  children: ReactNode;
}

const DEPTH_LABELS: Record<Depth, string> = {
  0: "Still",
  1: "Terrace",
  2: "Rooms",
  3: "Undercroft",
};

export function Shell({ depth, onDepth, breadcrumb = [], echo, onUndo, children }: ShellProps) {
  const [paletteOpen, setPaletteOpen] = useState(false);

  const rise = useCallback(() => onDepth(Math.max(0, depth - 1) as Depth), [depth, onDepth]);
  const descend = useCallback(() => onDepth(Math.min(3, depth + 1) as Depth), [depth, onDepth]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
        return;
      }
      if (e.key === "Escape") setPaletteOpen(false);
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
          <span className="sh-company t-display">{COMPANY.name}</span>

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

          {/* The still line, condensed. Same words as depth 0, always. */}
          {depth > 0 && (
            <p className="sh-still">
              <span className="t-subtle">{STILL.headline}</span>
              {STILL.handsRaised > 0 && (
                <>
                  <span className="sh-still-sep" aria-hidden="true">
                    ·
                  </span>
                  <span className="sh-still-hands">
                    <span className="m-lamp" data-lit data-breathing />
                    {STILL.handsRaised} waiting
                  </span>
                </>
              )}
            </p>
          )}
        </div>

        <div className="sh-rail-right">
          <button
            className="sh-palette-btn m-chip"
            onClick={() => setPaletteOpen(true)}
            aria-label="Open the command palette"
          >
            <Icon name="search" size={13} />
            <kbd>⌘K</kbd>
          </button>

          {/* Presence — never a face, never a floating avatar (D6 §1). */}
          <button className="sh-presence" aria-label="Pragya is listening">
            <span className="sh-presence-mark" data-state="listening" aria-hidden="true" />
            <span className="t-eyebrow">PRAGYA</span>
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

      {/* ==================================================== the ⌘K palette */}
      {paletteOpen && (
        <div className="sh-palette-scrim" onClick={() => setPaletteOpen(false)}>
          <div
            className="sh-palette m-glass"
            data-strong
            role="dialog"
            aria-label="Command palette"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sh-palette-input">
              <Icon name="search" size={16} className="t-subtle" />
              <input
                autoFocus
                placeholder="Ask, or type a command…"
                aria-label="Ask Pragya or type a command"
              />
              <span className="t-eyebrow">ESC</span>
            </div>
            <hr className="m-rule" />
            <p className="sh-palette-note t-mono">
              Anything typed here is also an utterance; anything said to Pragya is
              also a command.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
