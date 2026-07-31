/**
 * The live estate, as a surface consumes it (R-4 part S, S2–S3).
 *
 * One read of the estate projection, then the stream reduced over it. Two
 * readings come back and they answer different questions:
 *
 *  * `estate.as_of` — when the projection last changed.
 *  * `wire` — whether we are still watching it.
 *
 * A calm estate has an old `as_of` and a `live` wire. A broken one has an old
 * `as_of` and a `stale` wire. Collapsing those into a single "fresh" flag is
 * how a failure comes to look like peace, which is the failure part S exists to
 * prevent.
 *
 * **A reconnect re-reads the projection, on purpose.** The server's replay is
 * snapshot-on-connect and that snapshot is *beacons and pulse only*
 * (`diff_estate` returns early when `prev is None`). Traffic, weather,
 * treasuries and run states resume as diffs against a baseline this client
 * never saw, so without the re-read a district would sit on whatever numbers it
 * held when the wire dropped, indefinitely and invisibly. Beacons reconcile
 * idempotently by approval id, so the re-read and the replay cannot fight.
 *
 * **A failed re-read does not discard a good estate.** It leaves the numbers
 * standing and lets the wire reading carry the bad news — dropping to a failure
 * screen because a refresh failed would lose the last thing we honestly knew.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchEstate, type EstateSnapshot } from "../api/estate";
import { applyStreamEvent } from "./live";
import { subscribeEstateStream, type WireState } from "./sharedStream";
import type { Wire } from "./sse";

export type LiveEstate =
  | { phase: "loading" }
  | { phase: "failed"; reason: string; retry: () => void }
  | { phase: "ready"; estate: EstateSnapshot; wire: WireState };

export interface LiveEstateOptions {
  /** Injectable wire — tests drive the reducer with no network. Honoured on
   * the first subscribe only; see `subscribeEstateStream`. */
  wire?: Wire;
  /** Injectable projection read, for the same reason. */
  read?: () => Promise<EstateSnapshot>;
}

const UNREACHABLE = "The estate could not be reached.";

export function useLiveEstate(options?: LiveEstateOptions): LiveEstate {
  // Captured once. Swapping the data source mid-life would be a different
  // estate, not a refreshed one.
  const source = useRef({
    wire: options?.wire,
    read: options?.read ?? fetchEstate,
  });
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LiveEstate>({ phase: "loading" });

  const retry = useCallback(() => {
    setState({ phase: "loading" });
    setAttempt((previous) => previous + 1);
  }, []);

  useEffect(() => {
    let alive = true;
    let unsubscribe: (() => void) | null = null;
    let held = false;
    let connectedOnce = false;

    const read = async (): Promise<boolean> => {
      try {
        const estate = await source.current.read();
        if (!alive) return false;
        held = true;
        setState((previous) => ({
          phase: "ready",
          estate,
          wire: previous.phase === "ready" ? previous.wire : { status: "connecting" },
        }));
        return true;
      } catch {
        if (alive && !held) {
          setState({ phase: "failed", reason: UNREACHABLE, retry });
        }
        return false;
      }
    };

    void read().then((ok) => {
      if (!alive || !ok) return;
      unsubscribe = subscribeEstateStream(
        {
          onEvent: (event) => {
            setState((previous) => {
              if (previous.phase !== "ready") return previous;
              const estate = applyStreamEvent(previous.estate, event);
              // Identical object means the frame changed nothing this client
              // holds — no state, no render.
              return estate === previous.estate ? previous : { ...previous, estate };
            });
          },
          onWire: (wire) => {
            setState((previous) =>
              previous.phase === "ready" ? { ...previous, wire } : previous,
            );
            if (wire.status !== "live") return;
            if (connectedOnce) void read();
            connectedOnce = true;
          },
        },
        source.current.wire,
      );
    });

    return () => {
      alive = false;
      unsubscribe?.();
    };
  }, [attempt, retry]);

  return state;
}
