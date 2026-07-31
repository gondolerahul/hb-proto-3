import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { Icon } from "../components/Icon";
import "./palette.css";

/**
 * ⌘K · the navigator (R-4 §4, N1) — promoted from a designed empty shell.
 *
 * It is app-owned chrome for the same reason the rest of `Shell` is: a manifest
 * composes the body and nothing else, so the way *out* of a surface cannot be
 * removed by one (D6 §1).
 *
 * Four decisions a reader would otherwise have to reverse-engineer:
 *
 *  1. **Mounted by the app, not by the frame.** The palette used to live inside
 *     `Shell`, which meant it did not exist at depth 0 — and depth 0 is the
 *     front door. A navigator you cannot reach from the front door is not the
 *     navigator. It renders at every depth now; `Shell` keeps only the trigger.
 *
 *  2. **One tabbable element, so the trap is structural rather than policed.**
 *     This is a combobox over a listbox: focus stays in the input the whole
 *     time, the rows are `tabIndex={-1}`, and Tab is swallowed. A trap built by
 *     enumerating focusables and wrapping them is a trap that leaks the moment
 *     somebody adds a control; this one has nowhere to leak to.
 *
 *  3. **A row is a real `<a href>`.** N2 says a surface is shareable — that is
 *     only true if the thing you can copy the link off is a link. Plain clicks
 *     are intercepted into `pushState`; a modifier click is left to the browser,
 *     which is what makes "open the Undercroft in another tab" work at all.
 *
 *  4. **Grouped by rung, not ranked by frecency.** The ladder is the product's
 *     spatial model; a palette that reorders itself by use teaches a different
 *     one, and no two sessions would agree on where anything is. The order is
 *     the estate's order, always.
 *
 * Gold budget: none is spent here. The active row is `--surface-2` plus a
 * hairline (§4 — gold is not "you selected this"); the only gold in the frame is
 * the focus ring, which §4 sanctions outright.
 */

export interface PaletteItem {
  id: string;
  label: string;
  /** What the place is for. Printed, and matched on. */
  note: string;
  /** The heading this row sits under. Consecutive rows sharing one render one. */
  group: string;
  /** The URL the row names. */
  href: string;
  /** A different document — let the browser navigate rather than `pushState`. */
  away?: boolean;
  /** Matched but never printed. */
  aka?: string;
}

/** Every term has to land somewhere, so "hall inv" finds the invoices hall and
 *  "hall x" finds nothing. Substring rather than fuzzy: a fuzzy matcher on
 *  fifteen rows mostly produces surprising near-misses. */
function matches(item: PaletteItem, query: string): boolean {
  const hay = `${item.label} ${item.note} ${item.aka ?? ""}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter((t) => t.length > 0)
    .every((term) => hay.includes(term));
}

export function Palette({
  items,
  onGo,
  onClose,
}: {
  items: readonly PaletteItem[];
  /** A same-document row was chosen. */
  onGo: (item: PaletteItem) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const shown = useMemo(() => items.filter((i) => matches(i, query)), [items, query]);

  /* Runs of one group, with each row's index into `shown` carried along — the
     cursor is one number over the flat list, and the grouping is only how it is
     drawn and announced. `role="group"` is real ARIA inside a listbox, so the
     rung a surface sits on reaches a screen reader too rather than being a
     visual convenience the heading whispers to nobody. */
  const groups = useMemo(() => {
    const out: { name: string; rows: { item: PaletteItem; index: number }[] }[] = [];
    shown.forEach((item, index) => {
      const last = out[out.length - 1];
      if (last !== undefined && last.name === item.group) last.rows.push({ item, index });
      else out.push({ name: item.group, rows: [{ item, index }] });
    });
    return out;
  }, [shown]);

  /* Focus goes in on mount and comes back out on unmount. Restoring it is the
     half that gets forgotten: dismissing a dialog into `document.body` drops a
     keyboard user at the top of the page, which is a worse place than where
     they opened it from. */
  useEffect(() => {
    const opener = document.activeElement;
    inputRef.current?.focus();
    return () => {
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, []);

  /* `block: "nearest"` so arrowing down a long list scrolls by one row rather
     than centring — centring makes the list feel like it is fleeing. The
     optional call is for jsdom, which ships no `scrollIntoView`; a keyboard
     navigator has to be testable without a layout engine. */
  useEffect(() => {
    listRef.current?.querySelector("[data-active]")?.scrollIntoView?.({ block: "nearest" });
  }, [active]);

  const choose = useCallback(
    (item: PaletteItem) => {
      if (item.away) {
        window.location.assign(item.href);
        return;
      }
      onGo(item);
      onClose();
    },
    [onGo, onClose],
  );

  function onKeyDown(e: ReactKeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }
    // The trap. There is exactly one tabbable node in here, so refusing Tab is
    // the whole implementation.
    if (e.key === "Tab") {
      e.preventDefault();
      return;
    }
    if (shown.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % shown.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i - 1 + shown.length) % shown.length);
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(shown.length - 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = shown[active];
      if (item !== undefined) choose(item);
    }
  }

  const activeId = shown[active] !== undefined ? `pl-opt-${shown[active]!.id}` : undefined;

  return (
    <div className="pl-scrim" onMouseDown={onClose}>
      <div
        className="pl m-glass"
        data-strong
        role="dialog"
        aria-modal="true"
        aria-label="Go to a surface"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="pl-field">
          <Icon name="search" size={16} className="t-subtle pl-field-icon" />
          {/* A well, not a bare line of text. Focus lives here permanently — it
              is the only tabbable node in the dialog — so the sanctioned gold
              focus ring is on screen the whole time the palette is open, and a
              ring around nothing reads as an alarm. Around a field it reads as
              a field. */}
          <input
            ref={inputRef}
            className="pl-input m-well"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
            placeholder="Go to…"
            aria-label="Filter surfaces"
            role="combobox"
            aria-expanded
            aria-controls="pl-list"
            aria-autocomplete="list"
            {...(activeId !== undefined ? { "aria-activedescendant": activeId } : {})}
            autoComplete="off"
            spellCheck={false}
          />
          <span className="t-eyebrow pl-esc">ESC</span>
        </div>

        <hr className="m-rule" />

        <div className="pl-list" id="pl-list" role="listbox" aria-label="Surfaces" ref={listRef}>
          {groups.map((group) => (
            <div key={group.name} role="group" aria-label={group.name}>
              <p className="pl-group t-eyebrow" aria-hidden="true">
                {group.name}
              </p>
              {group.rows.map(({ item, index }) => (
                <a
                  key={item.id}
                  id={`pl-opt-${item.id}`}
                  className="pl-opt"
                  data-surface={item.away === true ? undefined : item.id}
                  data-active={index === active || undefined}
                  role="option"
                  aria-selected={index === active}
                  tabIndex={-1}
                  href={item.href}
                  onMouseMove={() => setActive(index)}
                  onClick={(e) => {
                    // A modifier click is the browser's — that is what makes a
                    // row openable in a new tab, which is half of "shareable".
                    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
                    e.preventDefault();
                    choose(item);
                  }}
                >
                  <span className="pl-opt-label">{item.label}</span>
                  <span className="pl-opt-note t-mono">{item.note}</span>
                  {item.away === true && <Icon name="forward" size={12} className="pl-opt-away" />}
                </a>
              ))}
            </div>
          ))}

          {shown.length === 0 && (
            <p className="pl-none">
              Nothing in the estate answers to “{query}”. The Terrace holds the
              districts; the Undercroft holds the machinery.
            </p>
          )}
        </div>

        <hr className="m-rule" />

        {/* §7.4 — the gap gets said rather than drawn over. The box used to
            promise that anything typed here was also an utterance to Pragya. It
            is not, and will not be until the ask/answer path is wired; a palette
            that claims to listen and does not is worse than one that admits it
            only walks. */}
        <p className="pl-note t-mono">
          This box goes to places, not to Pragya — asking her from here is not
          wired yet. ↑↓ to move · Enter to go · Esc to close.
        </p>
      </div>
    </div>
  );
}
