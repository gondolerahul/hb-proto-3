import { useCallback, useEffect, useRef, useState } from "react";

/**
 * One read of one thing, as a surface consumes it (R-4 part L, L5).
 *
 * The hydrate half of scaffold-then-hydrate. `useLiveEstate` already does this
 * for the estate projection plus its stream; this is the plain case — a single
 * request behind the seventeen surfaces that have no stream — and it keeps that
 * hook's vocabulary (`failed` / `ready` / `retry`) deliberately, so a reader who
 * has seen one recognises the other.
 *
 * It diverges on one word. The third phase is **`pending`, not `loading`**,
 * because on seventeen of eighteen surfaces there is no loading *state* to
 * render: D7 §3.1 puts the layout on screen first and lets the data fill it, and
 * a phase called `loading` is an invitation to draw a spinner that the device
 * matrix prohibits. The phase is a fact about the request, not a screen.
 *
 * Three decisions:
 *
 *  1. **`load` is captured once.** Callers pass an inline arrow; re-running the
 *     effect on every render would put the surface in a fetch loop that looks
 *     like a slow network. Swapping the reader mid-life would be a different
 *     resource, not a refreshed one — the same reasoning `useLiveEstate` gives
 *     for its `source` ref.
 *
 *  2. **A retry is a real second attempt.** It returns to `pending` and bumps a
 *     counter the effect depends on, rather than calling `load` from an event
 *     handler and racing the effect's own in-flight promise.
 *
 *  3. **A late answer to an abandoned attempt is dropped.** `alive` is checked
 *     after every await, so a slow first request cannot overwrite a fast retry
 *     — the bug where a screen recovers, then reverts to the failure it had
 *     already been retried out of.
 *
 * What it does *not* do, on purpose: cache, dedupe, refetch on focus, or hold
 * stale data across a retry. Where the last-known-good value matters — the
 * estate's numbers standing through a dropped wire — that lives in
 * `useLiveEstate`, which is the hook shaped for it.
 */

export type Resource<T> =
  | { phase: "pending" }
  | { phase: "failed"; reason: string; retry: () => void }
  | { phase: "ready"; value: T; retry: () => void };

/** What is said when the failure carries no words of its own. Never a code. */
export const UNANSWERED = "The estate did not answer.";

export function reasonOf(thrown: unknown): string {
  if (thrown instanceof Error && thrown.message !== "") return thrown.message;
  if (typeof thrown === "string" && thrown !== "") return thrown;
  return UNANSWERED;
}

export function useResource<T>(load: () => Promise<T>): Resource<T> {
  const read = useRef(load);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<Resource<T>>({ phase: "pending" });

  const retry = useCallback(() => {
    setState({ phase: "pending" });
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    let alive = true;

    read
      .current()
      .then((value) => {
        if (alive) setState({ phase: "ready", value, retry });
      })
      .catch((thrown: unknown) => {
        if (alive) setState({ phase: "failed", reason: reasonOf(thrown), retry });
      });

    return () => {
      alive = false;
    };
  }, [attempt, retry]);

  return state;
}
