/**
 * The Terrace (depth 1) behind the tier gate (WORLD W7).
 *
 * The gate's rules, all D7's: the tier is probed, never sniffed, and the
 * user overrides it in either direction (never gates capability); the map
 * arrives as a DYNAMIC import so a tier-C device never downloads
 * three.js; demotion is OFFERED on a sustained frame breach, never
 * imposed — a map that silently becomes a list has broken the user's
 * model of where things are; and a second context loss switches to the
 * sheet AND says so. The keyboard skip-list keeps every district
 * reachable without the canvas (D7 §6).
 */
import { lazy, Suspense, useEffect, useState } from "react";

import { emitEcho } from "../api/genui";
import { decideTier, storeTierOverride, type DeviceTier } from "./tier";
import { useLiveEstate } from "../estate/useLiveEstate";
import { ManifestSurface } from "./ManifestSurface";

// The quarantine's door: the world chunk exists only behind this line.
const WorldTerrace = lazy(() => import("../renderers/world/WorldTerrace"));

export function TerraceSurface({
  onEnterDistrict,
}: {
  onEnterDistrict: (code: string) => void;
}): JSX.Element {
  const [tier, setTier] = useState<DeviceTier | null>(null);
  const [mode, setMode] = useState<"map" | "sheet">("map");
  const [offer, setOffer] = useState<string | null>(null);
  const live = useLiveEstate();

  useEffect(() => {
    void decideTier().then((decision) => {
      setTier(decision.effective);
      if (decision.effective === "C" || decision.effective === "D") {
        setMode("sheet");
      }
    });
  }, []);

  if (tier === null || live.phase === "loading") {
    return <p className="vh-quiet">…</p>;
  }
  if (live.phase === "failed") {
    return (
      <p role="alert" className="vh-problem">
        {live.reason}
      </p>
    );
  }

  const wantsMap = mode === "map" && (tier === "A" || tier === "B");

  return (
    <div className="vh-terrace" data-part="terrace" data-tier={tier}>
      <div className="vh-terrace-controls">
        <button
          type="button"
          className="vh-quiet-link"
          onClick={() => {
            const next = wantsMap ? "sheet" : "map";
            setMode(next);
            // An explicit choice is a stated preference (D7 §2.1) — it
            // survives the session through LEARN's surface.* namespace.
            void storeTierOverride(next === "map" ? "A" : "C");
            void emitEcho({
              sentence:
                next === "sheet"
                  ? "switched the terrace to the list"
                  : "switched the terrace to the map",
              action_ref: { kind: "terrace.mode", surface_id: "terrace" },
            });
          }}
        >
          {wantsMap ? "rather have the list?" : "show the map"}
        </button>
      </div>

      {offer !== null && wantsMap && (
        <div role="status" className="vh-demotion-offer">
          <span>{offer}</span>
          <button
            type="button"
            onClick={() => {
              setMode("sheet");
              setOffer(null);
              void emitEcho({
                sentence: "accepted the slow-map offer and took the list",
                action_ref: { kind: "terrace.demote", surface_id: "terrace" },
              });
            }}
          >
            take the list
          </button>
          <button type="button" onClick={() => setOffer(null)}>
            keep the map
          </button>
        </div>
      )}

      {wantsMap ? (
        <>
          <Suspense fallback={<p className="vh-quiet">raising the territory…</p>}>
            <div className="vh-world-frame" data-part="world-frame">
              <WorldTerrace
                estate={live.estate}
                quality={tier === "A" ? "full" : "reduced"}
                onEnterDistrict={onEnterDistrict}
                onSustainedBreach={() =>
                  setOffer("this is running slowly — would you rather have the list?")
                }
                onContextLost={() => {
                  setMode("sheet");
                  void emitEcho({
                    sentence: "the map stopped responding — here's the list",
                    action_ref: { kind: "terrace.context_lost", surface_id: "terrace" },
                  });
                }}
              />
            </div>
          </Suspense>
          {/* Keyboard traversal without the canvas (D7 §6): every district
              reachable as a real button. */}
          <nav aria-label="districts" className="vh-district-skiplist">
            {live.estate.districts.map((district) => (
              <button
                key={district.process_code}
                type="button"
                onClick={() => onEnterDistrict(district.process_code)}
              >
                {district.name}
              </button>
            ))}
          </nav>
        </>
      ) : (
        <ManifestSurface surface="terrace.sheet" />
      )}
    </div>
  );
}
