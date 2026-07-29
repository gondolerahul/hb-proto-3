/**
 * The Thread (LINE L6, wireframes §16–18) — Pragya's thread only: her
 * history, her live narrations, and the certified trays inline. No
 * per-agent threads.
 *
 * The certified path is byte-identical to the desk's: the trays section
 * IS TraySurface — same components, same ceremony (`StepUpCeremony`,
 * which in an installed PWA is Face/Touch ID: the biometric bar is the
 * platform passkey, decision 6's whole point), same refusal ladder.
 * Nothing tray-shaped is reimplemented for the pocket.
 *
 * Live events ride the same steward channel client the desk dock uses —
 * one session across devices (rule 1): a narration spoken at the desk
 * appears here, and vice versa.
 */
import { useEffect, useRef, useState } from "react";

import { fetchThreadHistory, type ThreadTurn } from "../api/line";
import { TraySurface } from "../app/TraySurface";
import { connectChannel } from "../steward/channel";
import {
  INITIAL_STEWARD_STATE,
  reduceSteward,
  setConnected,
  type StewardState,
} from "../steward/state";

export interface ThreadDeps {
  history: typeof fetchThreadHistory;
  connect: typeof connectChannel;
}

const REAL: ThreadDeps = {
  history: fetchThreadHistory,
  connect: connectChannel,
};

export function ThreadSurface({
  deps = REAL,
  onSay,
}: {
  deps?: ThreadDeps;
  /** Optional — the app passes the live channel's `say`; absent, the
   * thread is read-only (history + live events still arrive). */
  onSay?: (text: string) => void;
}): JSX.Element {
  const [turns, setTurns] = useState<ThreadTurn[] | null>(null);
  const [live, setLive] = useState<StewardState>(INITIAL_STEWARD_STATE);
  const [draft, setDraft] = useState("");
  const say = useRef(onSay);
  // Only a provided onSay overwrites — a re-render must not clobber the
  // channel's own closure back to undefined.
  if (onSay !== undefined) say.current = onSay;

  useEffect(() => {
    let alive = true;
    void deps
      .history()
      .then((data) => {
        if (alive) setTurns(data);
      })
      .catch(() => {
        if (alive) setTurns([]);
      });
    const channel = deps.connect({
      onEvent: (event) => setLive((previous) => reduceSteward(previous, event)),
      onConnected: (connected) =>
        setLive((previous) => setConnected(previous, connected)),
    });
    if (say.current === undefined) {
      say.current = (text) => channel.say(text);
    }
    return () => {
      alive = false;
      channel.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section data-part="thread" aria-label="Pragya's thread">
      <div
        className="vh-presence-mark"
        data-part="presence"
        data-state={live.connected ? live.presence : "off"}
        aria-label={`Pragya is ${live.connected ? live.presence : "away"}`}
      >
        ◐
      </div>
      <div className="vh-thread-scroll" data-part="thread-turns">
        {turns === null && <p className="vh-quiet">Opening the thread…</p>}
        {turns?.map((turn, index) => (
          <p
            key={`${turn.at}-${index}`}
            className={turn.role === "owner" ? "vh-thread-owner" : "vh-steward-line"}
            data-role={turn.role}
          >
            {turn.content}
          </p>
        ))}
        {live.lines.map((line, index) => (
          <p
            key={`live-${index}`}
            className={line.kind === "error" ? "vh-problem" : "vh-steward-line"}
            data-part="live-line"
          >
            {line.text}
          </p>
        ))}
      </div>
      <details data-part="thread-trays" open>
        <summary>decisions</summary>
        <TraySurface />
      </details>
      <form
        data-part="thread-say"
        onSubmit={(event) => {
          event.preventDefault();
          const text = draft.trim();
          if (text === "") return;
          say.current?.(text);
          setDraft("");
        }}
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="tell Pragya"
          aria-label="tell Pragya"
        />
        <button type="submit">send</button>
      </form>
    </section>
  );
}
