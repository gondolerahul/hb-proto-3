/**
 * The shell — app-owned, never manifest-composed (D6 §1): a hostile
 * manifest cannot remove the user's way out of a surface. The depth
 * ladder is one axis (spec §3): 0 the Still Surface, 1 the Terrace,
 * 2 a district room (its sheet, until DRIVER furnishes it).
 *
 * DRIVER D1 adds the two pieces of chrome the tray needs: the "waiting"
 * affordance (gold — this needs you — and absent at zero, art bible §2.1)
 * and the echo ribbon (L10's human-facing copy).
 *
 * POLISH L3 (2026-07-30, after the screenshot round): the chrome is the
 * wireframes' HUD, not a nav bar — the tenant's name and the gold mark
 * top-left, quiet controls top-right, a glass Places palette (⌘K) for
 * every room, Escape rising one depth, the mono depth path bottom-left.
 * Eleven permanent room links read as a dev scaffold; a HUD reads as a
 * product. Navigation stays complete: palette + terrace + skiplist.
 */
import { useEffect, useState } from "react";

import { getAccessToken, logout } from "../api/client";
import { fetchCompanyName } from "../api/identity";
import { fetchTrayList } from "../api/trays";
import { Atmosphere } from "../atmosphere/Atmosphere";
import { StewardDock, type Navigation } from "../steward/StewardDock";
import { BoardroomSurface } from "./BoardroomSurface";
import { BridgesSurface } from "./BridgesSurface";
import { DistrictSheet } from "./DistrictSheet";
import { DossierSurface } from "./DossierSurface";
import { GallerySurface } from "./GallerySurface";
import { GlasshouseSurface } from "./GlasshouseSurface";
import { HallsSurface } from "./HallsSurface";
import { LibrarySurface } from "./LibrarySurface";
import {
  fetchEstateStanding,
  gateFromStanding,
  STILL_LOCKED_SENTENCE,
  type OnboardingGate,
} from "./onboarding";
import { PreSession } from "./PreSession";
import { announce, useRibbon } from "./ribbon";
import { StandupSurface } from "./StandupSurface";
import { TalentSurface } from "./TalentSurface";
import { StillSurface } from "./StillSurface";
import { StudySurface } from "./StudySurface";
import { TerraceSurface } from "./TerraceSurface";
import { TraySurface } from "./TraySurface";
import { UndercroftSurface } from "./UndercroftSurface";

type Depth =
  | { level: 0 }
  | { level: 1 }
  | { level: 1; room: "standup" }
  | { level: 2; district: string; dossier?: { id: string; name: string } }
  | { level: 2; room: "halls"; module?: string }
  | { level: 2; room: "board" }
  | { level: 2; room: "talent" }
  | { level: 2; room: "gallery" }
  | { level: 2; room: "library" }
  | { level: 2; room: "bridges" }
  | { level: 2; room: "study" }
  | { level: 2; room: "glasshouse" }
  | { level: 3 };

export function App(): JSX.Element {
  const [inSession, setInSession] = useState(getAccessToken() !== null);
  const [depth, setDepth] = useState<Depth>({ level: 0 });
  const [traysOpen, setTraysOpen] = useState(false);
  const [trayCount, setTrayCount] = useState<number | null>(null);
  // 120ms in, 4s dwell, 400ms out (art bible §9) — the hook holds the leave.
  const { sentence: ribbon, leaving: ribbonLeaving } = useRibbon();

  useEffect(() => {
    if (!inSession) return;
    void fetchTrayList()
      .then((trays) => setTrayCount(trays.length))
      .catch(() => setTrayCount(null));
  }, [inSession]);

  // Onboarding staged in the world (P7): depth 0 is the reward at stage
  // 9 — before that a session opens onto the Terrace's ghost estate.
  const [gate, setGate] = useState<OnboardingGate>({
    stillLocked: false,
    stage: null,
  });
  useEffect(() => {
    if (!inSession) return;
    void fetchEstateStanding().then((standing) => {
      const next = gateFromStanding(standing);
      setGate(next);
      if (next.stillLocked) setDepth({ level: 1 });
    });
  }, [inSession]);

  const goStill = (): void => {
    if (!gate.stillLocked) {
      setDepth({ level: 0 });
      return;
    }
    // The standing may have changed since the session opened — re-ask
    // before refusing, and refuse with the reason said out loud.
    void fetchEstateStanding().then((standing) => {
      const next = gateFromStanding(standing);
      setGate(next);
      if (next.stillLocked) announce(STILL_LOCKED_SENTENCE);
      else setDepth({ level: 0 });
    });
  };

  // ── the HUD's identity + the Places palette (POLISH L3) ──────────────
  const [companyName, setCompanyName] = useState<string | null>(null);
  const [placesOpen, setPlacesOpen] = useState(false);

  useEffect(() => {
    if (!inSession) return;
    void fetchCompanyName().then(setCompanyName);
  }, [inSession]);

  // Escape rises one depth (the ladder is one axis); ⌘K opens the palette.
  const rise = (): void => {
    if (depth.level === 3) setDepth({ level: 1 });
    else if (depth.level === 2 && "district" in depth && depth.dossier) {
      setDepth({ level: 2, district: depth.district });
    } else if (depth.level === 2) setDepth({ level: 1 });
    else if (depth.level === 1) {
      if ("room" in depth) setDepth({ level: 1 });
      else if (!gate.stillLocked) setDepth({ level: 0 });
    }
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPlacesOpen((open) => !open);
        return;
      }
      if (event.key === "Escape") {
        if (placesOpen) setPlacesOpen(false);
        else if (traysOpen) setTraysOpen(false);
        else rise();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });


  if (!inSession) {
    return <PreSession onEntered={() => setInSession(true)} />;
  }

  const navigateFromSteward = (navigation: Navigation): void => {
    if (navigation.type === "focus" && navigation.district !== undefined) {
      setDepth({ level: 2, district: navigation.district });
      return;
    }
    if (navigation.surfaceId === "terrace") {
      setDepth({ level: 1 });
      return;
    }
    if (navigation.surfaceId?.startsWith("district.") === true) {
      setDepth({
        level: 2,
        district: navigation.surfaceId.split(".", 2)[1] ?? "",
      });
    }
  };

  const PLACES: { label: string; whisper: string; go: () => void }[] = [
    { label: "the terrace", whisper: "the estate, walkable", go: () => setDepth({ level: 1 }) },
    { label: "the standup", whisper: "yesterday, colleague by colleague", go: () => setDepth({ level: 1, room: "standup" }) },
    { label: "registry halls", whisper: "every record, by module", go: () => setDepth({ level: 2, room: "halls" }) },
    { label: "the boardroom", whisper: "propositions and minutes", go: () => setDepth({ level: 2, room: "board" }) },
    { label: "the talent office", whisper: "hire, and part ways", go: () => setDepth({ level: 2, room: "talent" }) },
    { label: "the gallery", whisper: "seasons and monuments", go: () => setDepth({ level: 2, room: "gallery" }) },
    { label: "the library", whisper: "what the estate knows", go: () => setDepth({ level: 2, room: "library" }) },
    { label: "bridges & gates", whisper: "connections and channels", go: () => setDepth({ level: 2, room: "bridges" }) },
    { label: "the glasshouse", whisper: "rehearse without consequence", go: () => setDepth({ level: 2, room: "glasshouse" }) },
    { label: "the undercroft", whisper: "the engine room", go: () => setDepth({ level: 3 }) },
    { label: "the study", whisper: "you — keys, notices, billing", go: () => setDepth({ level: 2, room: "study" }) },
  ];

  const depthPath =
    depth.level === 0
      ? "vihara · still surface · depth 0"
      : depth.level === 1
        ? `vihara · ${"room" in depth ? "the standup" : "the terrace"} · depth 1`
        : depth.level === 2 && "district" in depth
          ? `vihara · ${depth.district}${depth.dossier ? " · dossier" : ""} · depth 2`
          : depth.level === 2 && "room" in depth
            ? `vihara · ${depth.room} · depth 2`
            : "vihara · the undercroft · depth 3";

  const contextRef: Record<string, unknown> =
    depth.level === 2 && "district" in depth
      ? { kind: "district", id: depth.district }
      : depth.level === 2 && "room" in depth
        ? { kind: "room", id: depth.room }
        : { kind: "estate", id: null };

  // One key per place on the ladder: a depth change remounts <main>, and
  // the 320ms crossfade-and-rise (art bible §9) runs on arrival.
  const depthKey =
    depth.level === 2 && "district" in depth
      ? `2:${depth.district}:${depth.dossier?.id ?? ""}`
      : depth.level === 2 && "room" in depth
        ? `2:${depth.room}`
        : depth.level === 1 && "room" in depth
          ? "1:standup"
          : String(depth.level);

  return (
    <div className="vihara-shell-frame">
      <Atmosphere context="shell" depthLevel={depth.level} />
      <header className="vh-hud" data-part="shell">
        <span className="vh-hud-left">
          <span className="vh-hud-mark" aria-hidden="true" />
          <span className="vh-hud-co">{companyName ?? "Vihara"}</span>
        </span>
        <nav className="vh-hud-right" aria-label="shell">
          <button
            type="button"
            className={
              trayCount !== null && trayCount > 0
                ? "vh-beacon-count"
                : "vh-hud-link"
            }
            data-part="trays-toggle"
            onClick={() => setTraysOpen((open) => !open)}
          >
            {trayCount !== null && trayCount > 0
              ? `${trayCount} waiting`
              : "trays"}
          </button>
          <button
            type="button"
            className="vh-hud-link"
            data-part="places-toggle"
            aria-expanded={placesOpen}
            onClick={() => setPlacesOpen((open) => !open)}
          >
            places <kbd className="vh-kbd">⌘K</kbd>
          </button>
          <button
            type="button"
            className="vh-hud-link"
            data-part="study-toggle"
            onClick={() => setDepth({ level: 2, room: "study" })}
          >
            study
          </button>
          <button
            type="button"
            className="vh-hud-link"
            onClick={() => {
              logout();
              setInSession(false);
              setDepth({ level: 0 });
            }}
          >
            leave
          </button>
        </nav>
      </header>
      {placesOpen && (
        <nav className="vh-places" data-part="places" aria-label="places">
          {!gate.stillLocked && depth.level !== 0 && (
            <button
              type="button"
              className="vh-place"
              onClick={() => {
                setPlacesOpen(false);
                goStill();
              }}
            >
              <span>the still surface</span>
              <small>silence, earned</small>
            </button>
          )}
          {PLACES.map((place) => (
            <button
              key={place.label}
              type="button"
              className="vh-place"
              onClick={() => {
                setPlacesOpen(false);
                place.go();
              }}
            >
              <span>{place.label}</span>
              <small>{place.whisper}</small>
            </button>
          ))}
        </nav>
      )}
      <main
        key={depthKey}
        className={depth.level === 0 ? "vh-depth0" : "vh-depthN"}
        onClick={(event) => {
          // The wireframe's rule: at depth 0, "go deeper · click anywhere"
          // — anywhere that is not itself a control.
          if (depth.level !== 0) return;
          if ((event.target as HTMLElement).closest("button, a, input")) return;
          setDepth({ level: 1 });
        }}
      >
        {depth.level === 0 && (
          <>
            <StillSurface />
            <button
              type="button"
              className="vh-quiet-link"
              data-part="walk-in"
              onClick={() => setDepth({ level: 1 })}
            >
              go deeper · click anywhere
            </button>
          </>
        )}
        {depth.level === 1 && !("room" in depth) && (
          <TerraceSurface
            onEnterDistrict={(district) => setDepth({ level: 2, district })}
          />
        )}
        {depth.level === 1 && "room" in depth && (
          <StandupSurface
            onOpenDossier={(colleague) =>
              setDepth({
                level: 2,
                district: colleague.district,
                dossier: { id: colleague.id, name: colleague.name },
              })
            }
          />
        )}
        {depth.level === 2 && "district" in depth && (
          depth.dossier !== undefined ? (
            <>
              <button
                type="button"
                className="vh-quiet-link"
                onClick={() =>
                  setDepth({ level: 2, district: depth.district })
                }
              >
                ← back to {depth.district}
              </button>
              <DossierSurface entityId={depth.dossier.id} />
            </>
          ) : (
            <DistrictSheet
              code={depth.district}
              onOpenDossier={(colleague) =>
                setDepth({
                  level: 2,
                  district: depth.district,
                  dossier: colleague,
                })
              }
            />
          )
        )}
        {depth.level === 2 && "room" in depth && depth.room === "halls" && (
          <HallsSurface initialModule={depth.module} />
        )}
        {depth.level === 2 && "room" in depth && depth.room === "talent" && (
          <TalentSurface />
        )}
        {depth.level === 2 && "room" in depth && depth.room === "gallery" && (
          <GallerySurface />
        )}
        {depth.level === 2 && "room" in depth && depth.room === "library" && (
          <LibrarySurface />
        )}
        {depth.level === 2 && "room" in depth && depth.room === "bridges" && (
          <BridgesSurface />
        )}
        {depth.level === 2 && "room" in depth && depth.room === "study" && (
          <StudySurface />
        )}
        {depth.level === 2 && "room" in depth && depth.room === "glasshouse" && (
          <GlasshouseSurface />
        )}
        {depth.level === 3 && <UndercroftSurface />}
        {depth.level === 2 && "room" in depth && depth.room === "board" && (
          <BoardroomSurface
            onOpenPlanningHall={() =>
              setDepth({ level: 2, room: "halls", module: "Planning" })
            }
          />
        )}
      </main>
      {traysOpen && (
        <aside className="vh-tray-panel" data-part="tray-panel">
          <TraySurface onCount={setTrayCount} />
        </aside>
      )}
      <StewardDock
        onNavigate={navigateFromSteward}
        onTrayDelivered={() => {
          setTrayCount((count) => (count ?? 0) + 1);
          setTraysOpen(true);
        }}
        depthLevel={depth.level}
        contextRef={contextRef}
      />

      <span className="vh-depth-path" aria-hidden="true">
        {depthPath}
      </span>

      {ribbon !== null && (
        <footer
          className="vh-echo-ribbon"
          role="status"
          data-part="echo-ribbon"
          data-leaving={ribbonLeaving}
        >
          {ribbon}
        </footer>
      )}
    </div>
  );
}
