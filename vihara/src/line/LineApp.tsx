/**
 * The Line (LINE L5–L9) — the pocket shell: three tabs, one thread,
 * app-owned chrome (a hostile manifest cannot remove the way out).
 * Depth 3 does not exist here — the Undercroft is desktop-only, by
 * design (wireframes §16–18).
 *
 * The push banner computes the honest iOS answer BEFORE the user hunts
 * for a prompt that will never come: install first, then notifications
 * (the exit demo's "demonstrated rather than discovered").
 */
import { useEffect, useState } from "react";

import { getAccessToken, logout } from "../api/client";
import { PreSession } from "../app/PreSession";
import { MorningStorySurface } from "./MorningStorySurface";
import { PocketDesk } from "./PocketDesk";
import {
  pushAvailability,
  subscribeToPush,
  type PushAvailability,
} from "./push";
import { ThreadSurface } from "./ThreadSurface";

type Tab = "thread" | "morning" | "desk";

export function LineApp(): JSX.Element {
  const [inSession, setInSession] = useState(getAccessToken() !== null);
  const [tab, setTab] = useState<Tab>(
    window.location.hash === "#thread" ? "thread" : "morning",
  );
  const [push, setPush] = useState<PushAvailability | null>(null);

  useEffect(() => {
    if (!inSession) return;
    void pushAvailability()
      .then(setPush)
      .catch(() => setPush({ state: "unsupported" }));
  }, [inSession]);

  if (!inSession) {
    return <PreSession onEntered={() => setInSession(true)} />;
  }

  return (
    <div className="vh-line-frame" data-part="line-shell">
      <header className="vh-shell-bar">
        <span className="vihara-wordmark-small">The Line</span>
        <nav className="vh-depth-dial" aria-label="line tabs">
          <button
            type="button"
            className="vh-quiet-link"
            disabled={tab === "morning"}
            onClick={() => setTab("morning")}
          >
            morning
          </button>
          <button
            type="button"
            className="vh-quiet-link"
            disabled={tab === "thread"}
            onClick={() => setTab("thread")}
          >
            thread
          </button>
          <button
            type="button"
            className="vh-quiet-link"
            disabled={tab === "desk"}
            onClick={() => setTab("desk")}
          >
            desk
          </button>
        </nav>
        <button
          type="button"
          className="vh-quiet-link"
          onClick={() => {
            logout();
            setInSession(false);
          }}
        >
          leave
        </button>
      </header>
      {push !== null && push.state === "needs-install-first" && (
        <p className="vh-quiet" data-part="push-ios-ceiling">
          On iPhone, notifications arrive only after you add the Line to
          your Home Screen — Share, then “Add to Home Screen”.
        </p>
      )}
      {push !== null && push.state === "ready" && (
        <button
          type="button"
          data-part="push-subscribe"
          onClick={() => {
            void subscribeToPush().then((subscribed) =>
              setPush({ state: subscribed ? "subscribed" : "unconfigured" }),
            );
          }}
        >
          get told when a decision waits
        </button>
      )}
      <main className="vh-line-main">
        {tab === "thread" && <ThreadSurface />}
        {tab === "morning" && <MorningStorySurface />}
        {tab === "desk" && <PocketDesk />}
      </main>
    </div>
  );
}
