/**
 * The shell — app-owned, never manifest-composed (D6 §1): a hostile
 * manifest cannot remove the user's way out of a surface. The depth
 * ladder is one axis (spec §3): 0 the Still Surface, 1 the Terrace,
 * 2 a district room (its sheet, until DRIVER furnishes it).
 */
import { useState } from "react";

import { getAccessToken, logout } from "../api/client";
import { ManifestSurface } from "./ManifestSurface";
import { PreSession } from "./PreSession";
import { StillSurface } from "./StillSurface";
import { TerraceSurface } from "./TerraceSurface";

type Depth =
  | { level: 0 }
  | { level: 1 }
  | { level: 2; district: string };

export function App(): JSX.Element {
  const [inSession, setInSession] = useState(getAccessToken() !== null);
  const [depth, setDepth] = useState<Depth>({ level: 0 });

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
          {depth.level === 2 && (
            <span className="vh-quiet">{depth.district}</span>
          )}
        </nav>
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
        {depth.level === 1 && (
          <TerraceSurface
            onEnterDistrict={(district) => setDepth({ level: 2, district })}
          />
        )}
        {depth.level === 2 && (
          <ManifestSurface surface={`district.${depth.district}`} />
        )}
      </main>
    </div>
  );
}
