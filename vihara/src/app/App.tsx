/**
 * The shell — app-owned, never manifest-composed (D6 §1): a hostile
 * manifest cannot remove the user's way out of a surface. The depth
 * ladder is one axis (spec §3): 0 the Still Surface, 1 the Terrace,
 * 2 a district room (its sheet, until DRIVER furnishes it).
 *
 * DRIVER D1 adds the two pieces of chrome the tray needs: the "waiting"
 * affordance (gold — this needs you — and absent at zero, art bible §2.1)
 * and the echo ribbon (L10's human-facing copy).
 */
import { useEffect, useState } from "react";

import { getAccessToken, logout } from "../api/client";
import { fetchTrayList } from "../api/trays";
import { BoardroomSurface } from "./BoardroomSurface";
import { DistrictSheet } from "./DistrictSheet";
import { DossierSurface } from "./DossierSurface";
import { GallerySurface } from "./GallerySurface";
import { HallsSurface } from "./HallsSurface";
import { PreSession } from "./PreSession";
import { subscribeRibbon } from "./ribbon";
import { StandupSurface } from "./StandupSurface";
import { TalentSurface } from "./TalentSurface";
import { StillSurface } from "./StillSurface";
import { TerraceSurface } from "./TerraceSurface";
import { TraySurface } from "./TraySurface";

type Depth =
  | { level: 0 }
  | { level: 1 }
  | { level: 1; room: "standup" }
  | { level: 2; district: string; dossier?: { id: string; name: string } }
  | { level: 2; room: "halls"; module?: string }
  | { level: 2; room: "board" }
  | { level: 2; room: "talent" }
  | { level: 2; room: "gallery" };

export function App(): JSX.Element {
  const [inSession, setInSession] = useState(getAccessToken() !== null);
  const [depth, setDepth] = useState<Depth>({ level: 0 });
  const [traysOpen, setTraysOpen] = useState(false);
  const [trayCount, setTrayCount] = useState<number | null>(null);
  const [ribbon, setRibbon] = useState<string | null>(null);

  useEffect(() => subscribeRibbon(setRibbon), []);

  useEffect(() => {
    if (!inSession) return;
    void fetchTrayList()
      .then((trays) => setTrayCount(trays.length))
      .catch(() => setTrayCount(null));
  }, [inSession]);

  if (!inSession) {
    return <PreSession onEntered={() => setInSession(true)} />;
  }

  return (
    <div className="vihara-shell-frame">
      <header className="vh-shell-bar" data-part="shell">
        <span className="vihara-wordmark-small">Vihara</span>
        <nav className="vh-depth-dial" aria-label="depth">
          <button
            type="button"
            className="vh-quiet-link"
            disabled={depth.level === 0}
            onClick={() => setDepth({ level: 0 })}
          >
            still
          </button>
          <button
            type="button"
            className="vh-quiet-link"
            disabled={depth.level === 1}
            onClick={() => setDepth({ level: 1 })}
          >
            terrace
          </button>
          <button
            type="button"
            className="vh-quiet-link"
            disabled={depth.level === 2 && "room" in depth}
            onClick={() => setDepth({ level: 2, room: "halls" })}
          >
            halls
          </button>
          <button
            type="button"
            className="vh-quiet-link"
            disabled={depth.level === 1 && "room" in depth}
            onClick={() => setDepth({ level: 1, room: "standup" })}
          >
            standup
          </button>
          <button
            type="button"
            className="vh-quiet-link"
            disabled={depth.level === 2 && "room" in depth && depth.room === "board"}
            onClick={() => setDepth({ level: 2, room: "board" })}
          >
            board
          </button>
          <button
            type="button"
            className="vh-quiet-link"
            disabled={depth.level === 2 && "room" in depth && depth.room === "talent"}
            onClick={() => setDepth({ level: 2, room: "talent" })}
          >
            talent
          </button>
          <button
            type="button"
            className="vh-quiet-link"
            disabled={depth.level === 2 && "room" in depth && depth.room === "gallery"}
            onClick={() => setDepth({ level: 2, room: "gallery" })}
          >
            gallery
          </button>
          {depth.level === 2 && "district" in depth && (
            <span className="vh-quiet">{depth.district}</span>
          )}
        </nav>
        <button
          type="button"
          className={
            trayCount !== null && trayCount > 0
              ? "vh-beacon-count"
              : "vh-quiet-link"
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
          className="vh-quiet-link"
          onClick={() => {
            logout();
            setInSession(false);
            setDepth({ level: 0 });
          }}
        >
          leave
        </button>
      </header>
      <main className={depth.level === 0 ? "vh-depth0" : "vh-depthN"}>
        {depth.level === 0 && (
          <>
            <StillSurface />
            <button
              type="button"
              className="vh-quiet-link"
              data-part="walk-in"
              onClick={() => setDepth({ level: 1 })}
            >
              walk the estate
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
      {ribbon !== null && (
        <footer className="vh-echo-ribbon" role="status" data-part="echo-ribbon">
          {ribbon}
        </footer>
      )}
    </div>
  );
}
