/**
 * The live estate hook: one read of the estate model, then the SSE stream
 * reduced over it. The stream's failure mode is honest staleness — the
 * `live` flag says whether the wire is up, and a surface can say "as of a
 * moment ago" instead of pretending (nothing fails silent).
 */
import { useEffect, useState } from "react";

import { fetchEstate } from "../api/genui";
import type { EstateSnapshot } from "../renderers/world/layout";
import { applyStreamEvent } from "./live";
import { subscribeEstateStream } from "./sharedStream";

export type LiveEstate =
  | { phase: "loading" }
  | { phase: "failed"; reason: string }
  | { phase: "ready"; estate: EstateSnapshot; live: boolean };

export function useLiveEstate(): LiveEstate {
  const [state, setState] = useState<LiveEstate>({ phase: "loading" });

  useEffect(() => {
    let alive = true;
    let dispose: (() => void) | null = null;
    void (async () => {
      try {
        const estate = (await fetchEstate()) as unknown as EstateSnapshot;
        if (!alive) return;
        setState({ phase: "ready", estate, live: false });
        try {
          dispose = subscribeEstateStream((event) => {
            setState((previous) =>
              previous.phase === "ready"
                ? {
                    phase: "ready",
                    estate: applyStreamEvent(previous.estate, event),
                    live: true,
                  }
                : previous,
            );
          });
        } catch {
          // No stream is a slower estate, not a broken one.
        }
      } catch {
        if (alive) {
          setState({ phase: "failed", reason: "The estate could not be reached." });
        }
      }
    })();
    return () => {
      alive = false;
      dispose?.();
    };
  }, []);

  return state;
}
