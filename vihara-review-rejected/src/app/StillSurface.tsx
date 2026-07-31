/**
 * The Still Surface (depth 0) — the default of every session, and G0's
 * round trip made visible: a manifest asked of SEAM, assessed by the
 * refusal ladder, rendered through the Sheet renderer, fed by the estate
 * read model, echoing the first manual act to the echo bus (L10).
 *
 * Loaders are injectable so the round trip is testable without a wire;
 * the defaults are the real SEAM clients.
 */
import { useEffect, useMemo, useState } from "react";

import { emitEcho, fetchEstate, fetchManifest } from "../api/genui";
import type { Assessment } from "../manifest/refusals";
import type { WireScaffold } from "../manifest/schema";
import { BindingContext, estateResolver } from "../renderers/bindings";
import { RenderManifest } from "../renderers/RenderManifest";

export interface StillLoaders {
  manifest: typeof fetchManifest;
  estate: typeof fetchEstate;
  echo: typeof emitEcho;
}

const REAL: StillLoaders = {
  manifest: fetchManifest,
  estate: fetchEstate,
  echo: emitEcho,
};

type State =
  | { phase: "loading" }
  | { phase: "failed"; reason: string }
  | {
      phase: "ready";
      manifest: WireScaffold;
      assessment: Assessment;
      estate: Record<string, unknown>;
    };

export function StillSurface({
  loaders = REAL,
}: {
  loaders?: StillLoaders;
}): JSX.Element {
  const [state, setState] = useState<State>({ phase: "loading" });

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const [fetched, estate] = await Promise.all([
          loaders.manifest("still", "S"),
          loaders.estate(),
        ]);
        if (!alive) return;
        if ("kind" in fetched) {
          setState({ phase: "failed", reason: fetched.reason });
          return;
        }
        setState({
          phase: "ready",
          manifest: fetched.manifest,
          assessment: fetched.assessment,
          estate,
        });
      } catch {
        if (alive) {
          setState({
            phase: "failed",
            reason: "The estate could not be reached.",
          });
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [loaders]);

  const resolver = useMemo(
    () =>
      estateResolver(state.phase === "ready" ? state.estate : null),
    [state],
  );

  if (state.phase === "loading") {
    return <p className="vh-quiet">…</p>;
  }
  if (state.phase === "failed") {
    // Fail visible — a blank still surface would read as "all is well".
    return (
      <p role="alert" className="vh-problem" data-part="still-failed">
        {state.reason}
      </p>
    );
  }

  const beacons = Array.isArray(state.estate["beacons"])
    ? (state.estate["beacons"] as unknown[])
    : [];

  return (
    <BindingContext.Provider value={resolver}>
      <RenderManifest manifest={state.manifest} assessment={state.assessment} />
      {beacons.length > 0 && (
        <button
          type="button"
          className="vh-beacon-count"
          data-part="beacon-count"
          onClick={() =>
            void loaders.echo({
              sentence: "opened the tray list from the still surface",
              action_ref: { kind: "still.open_trays", surface_id: "still" },
            })
          }
        >
          {beacons.length} waiting
        </button>
      )}
    </BindingContext.Provider>
  );
}
