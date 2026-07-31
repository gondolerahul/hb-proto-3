import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { getAccessToken, refreshAccessToken } from "../api/client";
import { PreSession } from "./PreSession";
import { SESSION_ENDED, type SessionEnding } from "./session";
import "./presession.css";

/**
 * The session gate (R-4 §3, A2/A4) — what `main.tsx` mounts, and the only
 * decision made before the app exists.
 *
 * It lives in `app/` rather than inside `main.tsx` for one reason: `main.tsx`'s
 * module side effect is `createRoot`, so a test that imported it would mount the
 * whole application into a real DOM. The gate has to be assertable on its own
 * (`tests/access.test.tsx`), so `main.tsx` keeps the mount and this keeps the
 * decision.
 *
 * Three decisions a reader would otherwise have to reverse-engineer:
 *
 *  1. **A failed refresh is a state, not an error (A4).** `refreshAccessToken`
 *     never throws by design; there is nothing here to catch and nothing to
 *     report. "No session" is the ordinary condition of a first visit, and the
 *     screen it produces is a login screen — not a banner, not a retry, not an
 *     error boundary. The one thing this must never do is treat a cold visitor
 *     as a fault.
 *
 *  2a. **The door is shared; what is behind it is not.** Both entries need the
 *     same bootstrap, the same "a failed refresh is a state" rule and the same
 *     login screen — the Line shipped without any of it and fired its first
 *     reads with no token, which the sweep caught as a 401 storm on its default
 *     tab. So the gate takes its destination as `children` rather than naming
 *     one: `main.tsx` hands it the estate, `line/main.tsx` hands it the Line.
 *     Importing `Prototype` here would have pulled the estate's fifteen surfaces
 *     into the Line's own 220 KB budget, which is the entire reason the Line is
 *     a second HTML entry and not a route.
 *
 *  2. **The URL is the memory of where you were.** VP-01 forbids storage, and it
 *     turns out none is needed: N2 already puts the surface in the address bar,
 *     so an expiry leaves it there and `Prototype` reads it again after the next
 *     login. The two endings differ, and `session.ts` says why.
 *
 *  3. **The bootstrap frame is the brand block, not a spinner.** D7 §3.1's
 *     scaffold-then-hydrate applies to the door too: both destinations open with
 *     the mark in the same place, so painting it immediately makes the login
 *     screen *fill in* rather than replace. A spinner in front of one round-trip
 *     is a spinner nobody is glad to have seen.
 */

type Phase = "bootstrapping" | "in" | "out";

export interface SessionProps {
  /** The app behind the door. */
  children: ReactNode;
  /** Where the session ended, for the "you will land back on…" line. The estate
   *  reads it off the address bar; the Line has no depth ladder and no surface
   *  URLs, so it passes nothing and the line is simply absent rather than
   *  naming a room the phone does not have. */
  placeOf?: () => string | null;
}

export function Session({ children, placeOf }: SessionProps) {
  const [phase, setPhase] = useState<Phase>("bootstrapping");
  /** Where the session ended, when it ended somewhere worth naming. */
  const [returningTo, setReturningTo] = useState<string | null>(null);
  const phaseRef = useRef<Phase>("bootstrapping");
  phaseRef.current = phase;

  /* The bootstrap. One attempt: the refresh cookie is either there and valid or
     it is not, and retrying a definite "no" only delays the login screen. */
  useEffect(() => {
    let live = true;
    void refreshAccessToken().then((ok) => {
      if (live) setPhase(ok ? "in" : "out");
    });
    return () => {
      live = false;
    };
  }, []);

  const end = useCallback((how: SessionEnding) => {
    if (phaseRef.current !== "in") return;
    if (how === "left") {
      window.history.replaceState(null, "", "/");
      setReturningTo(null);
    } else {
      setReturningTo(placeOf?.() ?? null);
    }
    setPhase("out");
  }, [placeOf]);

  useEffect(() => {
    const onEnded = (e: Event) => {
      const how = (e as CustomEvent<SessionEnding>).detail;
      end(how === "left" ? "left" : "expired");
    };
    window.addEventListener(SESSION_ENDED, onEnded);
    return () => window.removeEventListener(SESSION_ENDED, onEnded);
  }, [end]);

  /* The other way a session ends is quietly: a request 401s, the client's own
     refresh fails, and it drops the token. Nothing announces that. Re-reading
     the token when the tab comes back is the cheap honest check — the common
     shape of an expiry is a laptop that was shut, and this catches it on the way
     back in rather than on the next click that fails. */
  useEffect(() => {
    const check = () => {
      if (document.visibilityState === "visible" && getAccessToken() === null) end("expired");
    };
    window.addEventListener("focus", check);
    document.addEventListener("visibilitychange", check);
    return () => {
      window.removeEventListener("focus", check);
      document.removeEventListener("visibilitychange", check);
    };
  }, [end]);

  if (phase === "bootstrapping") {
    return (
      <main className="ps">
        <div className="ps-col">
          <header className="ps-brand">
            <span className="ps-mark" aria-hidden="true">
              <span className="ps-mark-dot" />
            </span>
            <p className="ps-word">Vihara</p>
          </header>
        </div>
      </main>
    );
  }

  if (phase === "out") {
    return (
      <PreSession
        returningTo={returningTo}
        onEntered={() => {
          setReturningTo(null);
          setPhase("in");
        }}
      />
    );
  }

  return <>{children}</>;
}
