import { useCallback, useEffect, useState } from "react";
import { logout } from "../api/client";
import { Background } from "../background/Background";
import { Icon, type IconName } from "../components/Icon";
import { COMPANY, STILL } from "../fixtures/estate";
import { MorningStorySurface } from "./MorningStorySurface";
import { PocketDesk } from "./PocketDesk";
import { ThreadSurface } from "./ThreadSurface";
import {
  pushAvailability,
  subscribeToPush,
  type PushAvailability,
} from "./push";
import "./line.css";

/**
 * The Line · the pocket frame · C (D6 §16–18, R-3c C7).
 *
 * The chrome is app-owned for the same reason the estate's `Shell` is: a
 * manifest composes the *body*, and nothing else. The tabs, the mark, the echo
 * ribbon and the way out are the application, which is what stops a malformed
 * or hostile manifest from removing the user's exit — a property that matters
 * more here than on the desk, because a phone has no address bar to fall back
 * to once the Line is installed and running standalone.
 *
 * Three decisions a reader would otherwise have to reverse-engineer:
 *
 * 1. **C is not the estate at 390px.** There is no depth ladder and no ⌘K.
 *    Depth 3 does not exist on the Line by design — a phone-sized Undercroft is
 *    a worse Undercroft, not a more available one — and a palette keyed to a
 *    keyboard chord is navigation nobody can reach with a thumb. What replaces
 *    both is three tabs, always visible, in the bottom third of the screen.
 *    Thread sits in the middle: it is the most-used of the three, and the
 *    middle of a bottom bar is where a thumb already rests.
 *
 * 2. **Gold on this frame means exactly one thing: a hand is raised.** The
 *    active tab is warm-white over `--surface-2` (§4), not gold — which is what
 *    buys the tab bar the right to carry a beacon at all. Two golds in a 52px
 *    bar and neither of them means anything.
 *
 * 3. **The iOS ceiling is stated, not worked around.** iOS delivers Web Push
 *    only to an installed PWA, so `pushAvailability()` computes that answer
 *    *before* the user goes hunting for a prompt that will never appear. Every
 *    other branch of that state is a different true sentence, and the silence
 *    when a subscription already exists is the last one.
 */

type Tab = "morning" | "thread" | "desk";

const TABS: { id: Tab; label: string; icon: IconName }[] = [
  // `colleague`, not `clock`: the Morning Story is the Standup, one card per
  // colleague. `clock` already means elapsed time everywhere else in the product
  // and a tab bar is the wrong place to teach it a second meaning.
  { id: "morning", label: "Morning", icon: "colleague" },
  { id: "thread", label: "Thread", icon: "thread" },
  { id: "desk", label: "Desk", icon: "trend" },
];

/** The worker opens `/line.html#thread` from a notification — a push is a tray,
 *  and a tray is read in the thread (L8). The same rule restores whichever tab
 *  the app was closed on. */
function initialTab(): Tab {
  const wanted = window.location.hash.slice(1);
  return TABS.find((t) => t.id === wanted)?.id ?? "morning";
}

export function LineApp() {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [echo, setEcho] = useState<string | null>(null);
  const [push, setPush] = useState<PushAvailability | null>(null);
  const [refused, setRefused] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    void pushAvailability()
      .then(setPush)
      .catch(() => setPush({ state: "unsupported" }));
  }, []);

  // `replaceState`, not a hash change: the Android back gesture should leave the
  // app, not walk backwards through a tab history the user never built on
  // purpose. The hash is a bookmark of where you were, not a trail.
  useEffect(() => {
    window.history.replaceState(null, "", `#${tab}`);
  }, [tab]);

  useEffect(() => {
    if (!leaving) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLeaving(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [leaving]);

  const showEcho = useCallback((msg: string) => {
    setEcho(null);
    // One frame, so a repeat of the same message re-triggers the animation.
    requestAnimationFrame(() => setEcho(msg));
    window.setTimeout(() => setEcho(null), 4600);
  }, []);

  if (gone) {
    return (
      <>
        <Background intensity="hushed" />
        <div className="ln-gone">
          <div className="ln-gone-plate m-plate" data-raised>
            <span className="ln-mark" aria-hidden="true">
              <span className="ln-mark-dot" />
            </span>
            <span className="t-eyebrow">THE LINE</span>
            <h1 className="ln-gone-title t-display">You have left.</h1>
            <p className="ln-gone-note t-narrative">
              Nothing on this phone can act for you until you come back.
            </p>
            <button className="m-btn ln-gone-btn" onClick={() => setGone(false)}>
              Return to the Line
            </button>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      {/* The estate's own atmosphere, at the register a dense working surface
          gets. Hushed rather than full: the Line is read at arm's length in
          daylight, and a breathing floor under a 390px column competes with the
          column. Same scene, veiled — never re-graded. */}
      <Background intensity="hushed" />

      <div className="ln">
        <a className="vh-skip" href="#ln-body">
          Skip to the surface
        </a>

        {/* ==================================================== the rail */}
        <header className="ln-rail m-glass" data-strong>
          <span className="ln-mark" aria-hidden="true">
            <span className="ln-mark-dot" />
          </span>
          <span className="ln-company t-display">{COMPANY.name}</span>

          {/* Presence — never a face, never a floating avatar (D6 §1). */}
          <p className="ln-presence">
            <span className="ln-presence-mark" aria-hidden="true" />
            <span className="t-eyebrow">PRAGYA</span>
            <span className="vh-sr-only">is listening</span>
          </p>

          <button
            className="m-btn ln-leave"
            data-rank="quiet"
            onClick={() => setLeaving(true)}
          >
            Leave
          </button>
        </header>

        {/* ============================================ the push ceiling */}
        <PushNotice
          push={push}
          refused={refused}
          onSubscribe={() => {
            void subscribeToPush()
              // `false` is the server's gap — no VAPID key configured, so there
              // is nothing to subscribe to. A rejection is the phone's answer:
              // the person said no, which is a different sentence.
              .then((ok) => setPush({ state: ok ? "subscribed" : "unconfigured" }))
              .catch(() => setRefused(true));
          }}
        />

        {/* ================================================== the surface */}
        <main className="ln-body" id="ln-body" tabIndex={-1}>
          <div className="ln-swap vh-enter-fade" key={tab}>
            {tab === "morning" && <MorningStorySurface onEcho={showEcho} />}
            {tab === "thread" && <ThreadSurface onEcho={showEcho} />}
            {tab === "desk" && <PocketDesk onEcho={showEcho} />}
          </div>
        </main>

        {/* ================================================== the tab bar */}
        <nav className="ln-tabs m-glass" data-strong aria-label="The Line">
          {TABS.map((t) => {
            // The estate's own count, not a second one. STILL.handsRaised is the
            // binding the depth-0 line reads; the phone must never disagree with
            // the desk about how many things are waiting.
            const waiting = t.id === "thread" ? STILL.handsRaised : 0;
            return (
              <button
                key={t.id}
                className="ln-tab"
                data-active={tab === t.id || undefined}
                aria-current={tab === t.id ? "page" : undefined}
                onClick={() => setTab(t.id)}
              >
                <Icon name={t.icon} size={20} />
                <span className="ln-tab-label t-eyebrow">{t.label}</span>

                {waiting > 0 && (
                  <span className="ln-tab-hands">
                    <span className="m-lamp" data-lit data-breathing />
                    {/* Never colour alone: the numeral is the visible carrier,
                        the sentence below is the accessible one. */}
                    <span className="ln-tab-count t-mono">{waiting}</span>
                    <span className="vh-sr-only">, {waiting} waiting on you</span>
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* =============================================== the echo ribbon
            `data-renderer="C"` is not decoration: D6 §16–18 requires the Line's
            echoes to carry it so density learning cannot read a phone tap as an
            operator click. R-4 puts the same value on the bus. */}
        {echo && (
          <div
            className="ln-echo m-glass vh-echo"
            role="status"
            key={echo}
            data-renderer="C"
          >
            <span className="t-eyebrow">DONE</span>
            <span className="ln-echo-text">{echo}</span>
          </div>
        )}

        {/* ============================================== leaving, confirmed */}
        {leaving && (
          <div className="ln-scrim" onClick={() => setLeaving(false)}>
            <div
              className="ln-sheet m-plate"
              data-raised
              role="dialog"
              aria-modal="true"
              aria-labelledby="ln-leave-title"
              onClick={(e) => e.stopPropagation()}
            >
              <span className="t-eyebrow">LEAVE THE LINE</span>
              <h2 id="ln-leave-title" className="ln-sheet-title t-display">
                Leave this phone?
              </h2>
              <p className="ln-sheet-note t-narrative">
                You will have to sign in again before anything here can be
                approved.
              </p>
              <div className="ln-sheet-acts">
                <button
                  className="m-btn ln-sheet-act"
                  data-rank="quiet"
                  autoFocus
                  onClick={() => setLeaving(false)}
                >
                  Stay
                </button>
                <button
                  className="m-btn ln-sheet-act"
                  onClick={() => {
                    logout();
                    setLeaving(false);
                    setGone(true);
                  }}
                >
                  Leave
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

/**
 * What the Line can and cannot tell you, said out loud (R-3c §4).
 *
 * Five states, five different true sentences — and one of them is silence.
 * A banner that keeps talking after it got what it asked for is how a person
 * learns to stop reading banners, so `subscribed` renders nothing at all, and
 * so does the moment before the probe answers: a notice that appears and then
 * changes its mind reads as a fault.
 *
 * `unsupported` and `unconfigured` are platform gaps, and DESIGN_CONTRACT §7.4
 * says render the gap rather than draw a working feature over a known absence —
 * so they get a sentence in `t-mono` and no button, because a button that cannot
 * work is worse than no button.
 */
function PushNotice({
  push,
  refused,
  onSubscribe,
}: {
  push: PushAvailability | null;
  refused: boolean;
  onSubscribe: () => void;
}) {
  if (refused) {
    return (
      <aside className="ln-notice m-plate" role="status">
        <span className="m-lamp ln-notice-lamp" />
        <div className="ln-notice-body">
          <span className="t-eyebrow">NOTIFICATIONS</span>
          <p className="ln-notice-line t-mono">
            This phone refused notifications for the Line. Nothing will arrive
            until you allow them in your browser’s settings for this site.
          </p>
        </div>
      </aside>
    );
  }

  if (push === null || push.state === "subscribed") return null;

  if (push.state === "needs-install-first") {
    return (
      <aside className="ln-notice m-plate">
        <span className="m-lamp ln-notice-lamp" />
        <div className="ln-notice-body">
          <span className="t-eyebrow">ON IPHONE</span>
          <p className="ln-notice-line">
            A notification can only reach you once the Line is on your Home
            Screen.
          </p>
          <p className="ln-notice-how t-mono">
            Share, then “Add to Home Screen”.
          </p>
        </div>
      </aside>
    );
  }

  if (push.state === "ready") {
    return (
      <aside className="ln-notice m-plate">
        <span className="m-lamp ln-notice-lamp" />
        <div className="ln-notice-body">
          <span className="t-eyebrow">NOTIFICATIONS</span>
          <p className="ln-notice-line">
            Nothing will reach this phone until you say it may.
          </p>
          {/* No icon: the set has no bell, and `alert` is a warning triangle —
              a danger mark on a benign opt-in teaches the wrong thing about
              every other place the triangle appears. */}
          <button className="m-btn ln-notice-btn" onClick={onSubscribe}>
            Tell me when a decision waits
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside className="ln-notice m-plate">
      <span className="m-lamp ln-notice-lamp" />
      <div className="ln-notice-body">
        <span className="t-eyebrow">NOTIFICATIONS</span>
        <p className="ln-notice-line t-mono">
          {push.state === "unsupported"
            ? "This browser cannot receive push. The Line will not tell you when a decision is waiting."
            : "Push is not configured on this server. The Line will not tell you when a decision is waiting."}
        </p>
      </div>
    </aside>
  );
}
