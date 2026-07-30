/**
 * A generic manifest-driven surface: ask SEAM for the composition, run the
 * ladder, render, bind. Every sheet surface in the depth ladder rides
 * this; the Still Surface keeps its own wrapper (it adds the beacon act).
 */
import { useEffect, useMemo, useState } from "react";

import { fetchEstate, fetchManifest } from "../api/genui";
import type { Assessment } from "../manifest/refusals";
import type { WireScaffold } from "../manifest/schema";
import { BindingContext, estateResolver } from "../renderers/bindings";
import { RenderManifest } from "../renderers/RenderManifest";

type State =
  | { phase: "loading" }
  | { phase: "failed"; reason: string }
  | {
      phase: "ready";
      manifest: WireScaffold;
      assessment: Assessment;
      estate: Record<string, unknown>;
    };

export function ManifestSurface({
  surface,
  renderer = "S",
}: {
  surface: string;
  renderer?: "S" | "C";
}): JSX.Element {
  const [state, setState] = useState<State>({ phase: "loading" });

  useEffect(() => {
    let alive = true;
    setState({ phase: "loading" });
    void (async () => {
      try {
        const [fetched, estate] = await Promise.all([
          fetchManifest(surface, renderer),
          fetchEstate(),
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
          setState({ phase: "failed", reason: "This surface could not be reached." });
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [surface, renderer]);

  const resolver = useMemo(
    () => estateResolver(state.phase === "ready" ? state.estate : null),
    [state],
  );

  if (state.phase === "loading") return <p className="vh-quiet">…</p>;
  if (state.phase === "failed") {
    return (
      <p role="alert" className="vh-problem">
        {state.reason}
      </p>
    );
  }
  return (
    <BindingContext.Provider value={resolver}>
      <RenderManifest manifest={state.manifest} assessment={state.assessment} />
    </BindingContext.Provider>
  );
}
