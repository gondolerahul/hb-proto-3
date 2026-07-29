/**
 * The shell — app-owned, never manifest-composed (D6 §1): a hostile
 * manifest cannot remove the user's way out of a surface. Depth 0 is the
 * Still Surface; the ladder's deeper rungs arrive with WORLD and DRIVER.
 */
import { useState } from "react";

import { getAccessToken, logout } from "../api/client";
import { PreSession } from "./PreSession";
import { StillSurface } from "./StillSurface";

export function App(): JSX.Element {
  const [inSession, setInSession] = useState(getAccessToken() !== null);

  if (!inSession) {
    return <PreSession onEntered={() => setInSession(true)} />;
  }

  return (
    <div className="vihara-shell-frame">
      <header className="vh-shell-bar" data-part="shell">
        <span className="vihara-wordmark-small">Vihara</span>
        <button
          type="button"
          className="vh-quiet-link"
          onClick={() => {
            logout();
            setInSession(false);
          }}
        >
          leave
        </button>
      </header>
      <main className="vh-depth0">
        <StillSurface />
      </main>
    </div>
  );
}
