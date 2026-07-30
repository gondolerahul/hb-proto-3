/**
 * The district room (POLISH M2) — the W+S pair D6 §5 draws: the floating
 * plate room on tier A/B (full-bleed, DistrictRoom behind a dynamic
 * import), the furnished sheet as the first-class flip and the tier-C/D
 * product (L9). The live-runs panel and the colleague chips are DOM over
 * the world — the wireframe's own composition — and every colleague
 * stays reachable without the canvas (D7 §6).
 */
import { lazy, Suspense, useEffect, useState } from "react";

import { fetchEstate } from "../api/genui";
import { fetchExecutions, type RunSummary } from "../api/entities";
import { setWorldCanvasActive } from "../atmosphere/worldActive";
import { applyStreamEvent } from "../estate/live";
import { subscribeEstateStream } from "../estate/sharedStream";
import type { EstateSnapshot } from "../renderers/world/layout";
import { DistrictSheet } from "./DistrictSheet";
import { emitEcho } from "../api/genui";
import { decideTier, storeTierOverride, type DeviceTier } from "./tier";

const DistrictRoom = lazy(() => import("../renderers/world/DistrictRoom"));

function minutes(run: RunSummary): string {
  if (run.execution_time_ms === null) return "";
  const total = Math.round(run.execution_time_ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function DistrictSurface({
  code,
  onOpenDossier,
}: {
  code: string;
  onOpenDossier: (colleague: { id: string; name: string }) => void;
}): JSX.Element {
  const [tier, setTier] = useState<DeviceTier | null>(null);
  const [mode, setMode] = useState<"room" | "sheet">("room");
  const [estate, setEstate] = useState<EstateSnapshot | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);

  useEffect(() => {
    void decideTier().then((decision) => {
      setTier(decision.effective);
      if (decision.effective === "C" || decision.effective === "D") {
        setMode("sheet");
      }
    });
  }, []);

  const roomUp = mode === "room" && (tier === "A" || tier === "B");

  useEffect(() => {
    setWorldCanvasActive(roomUp);
    return () => setWorldCanvasActive(false);
  }, [roomUp]);

  useEffect(() => {
    if (!roomUp) return;
    let alive = true;
    let dispose: (() => void) | null = null;
    void (async () => {
      try {
        const snapshot = (await fetchEstate()) as unknown as EstateSnapshot;
        if (!alive) return;
        setEstate(snapshot);
        try {
          dispose = subscribeEstateStream((event) => {
            setEstate((previous) =>
              previous === null ? previous : applyStreamEvent(previous, event),
            );
          });
        } catch {
          // No stream is a slower room, not a broken one.
        }
      } catch {
        if (alive) setMode("sheet");
      }
    })();
    void fetchExecutions()
      .then((loaded) => {
        if (alive) setRuns(loaded.slice(0, 6));
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      dispose?.();
    };
  }, [code, roomUp]);

  if (tier === null) {
    return <p className="vh-quiet">…</p>;
  }

  if (!roomUp) {
    return (
      <>
        <div className="vh-terrace-controls">
          {(tier === "A" || tier === "B") && (
            <button
              type="button"
              className="vh-quiet-link"
              onClick={() => {
                setMode("room");
                void storeTierOverride("A");
              }}
            >
              show the room
            </button>
          )}
        </div>
        <DistrictSheet code={code} onOpenDossier={onOpenDossier} />
      </>
    );
  }

  const district = estate?.districts.find(
    (candidate) => candidate.process_code === code,
  );

  return (
    <div className="vh-district-room" data-part="district-room">
      {district !== undefined && (
        <div className="vh-world-frame" data-part="world-frame">
          <Suspense
            fallback={<p className="vh-quiet">entering the district…</p>}
          >
            <DistrictRoom
              district={district}
              phase={estate?.estate.phase === "night" ? "night" : "day"}
              quality={tier === "A" ? "full" : "reduced"}
              onOpenDossier={onOpenDossier}
              onSustainedBreach={() => {
                setMode("sheet");
                void emitEcho({
                  sentence: "the room ran slowly — here's the sheet",
                  action_ref: { kind: "district.demote", surface_id: `district.${code}` },
                });
              }}
              onContextLost={() => {
                setMode("sheet");
                void emitEcho({
                  sentence: "the room stopped responding — here's the sheet",
                  action_ref: {
                    kind: "district.context_lost",
                    surface_id: `district.${code}`,
                  },
                });
              }}
            />
          </Suspense>
        </div>
      )}

      <div className="vh-terrace-controls">
        <button
          type="button"
          className="vh-quiet-link"
          onClick={() => {
            setMode("sheet");
            void emitEcho({
              sentence: "switched the district to the sheet",
              action_ref: { kind: "district.mode", surface_id: `district.${code}` },
            });
          }}
        >
          rather have the sheet?
        </button>
      </div>

      {district !== undefined && district.weather.sentence !== null && (
        <p className="vh-room-line" data-part="district-weather">
          {district.weather.sentence}
        </p>
      )}

      {runs.length > 0 && (
        <aside className="vh-live-panel" data-part="live-runs">
          <span className="vh-eyebrow">live runs</span>
          <ul>
            {runs.map((run) => (
              <li key={run.id}>
                <span className="vh-live-label">
                  {run.status} · {run.id.slice(0, 8)}
                </span>
                <span className="vh-mono">{minutes(run)}</span>
              </li>
            ))}
          </ul>
        </aside>
      )}

      {/* Every colleague reachable without the canvas (D7 §6). */}
      {district !== undefined && district.colleagues.length > 0 && (
        <nav aria-label="colleagues" className="vh-district-skiplist">
          {district.colleagues.map((colleague) => (
            <button
              key={colleague.entity_id}
              type="button"
              onClick={() =>
                onOpenDossier({ id: colleague.entity_id, name: colleague.name })
              }
            >
              {colleague.name}
              {colleague.hand_raised ? " ◈" : ""}
            </button>
          ))}
        </nav>
      )}
    </div>
  );
}
