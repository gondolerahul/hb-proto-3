import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../design/index.css";
import { Session } from "../app/Session";
import { LineApp } from "./LineApp";

/**
 * The Line's entry (R-3c C1/C2) — the second front door, not a second app.
 *
 * It loads the same design substrate as the estate, which is the whole reason
 * the two can share components: `TraySurface` renders on the phone because the
 * material vocabulary underneath it is byte-for-byte the same one.
 *
 * It goes through the SAME session gate the estate does. The Line shipped
 * without one and mounted `LineApp` unconditionally, so its default tab fired
 * reads with no access token — a 401 storm the unit tests could not see and the
 * sweep found on the first live walk. `Session` takes its destination as
 * children precisely so this entry can reuse the door without importing the
 * estate's surfaces into the Line's own budget.
 *
 * No `placeOf`: the Line has no surface URLs, so an expiry here names no room
 * rather than naming one the phone does not have.
 *
 * The service worker owns push and the offline shell (L5). Registration failure
 * degrades to a tab that simply is not installable — never an error the user has
 * to read, because there is nothing they could do about it.
 */
if ("serviceWorker" in navigator) {
  void navigator.serviceWorker.register("/line-sw.js").catch(() => undefined);
}

const root = document.getElementById("root");
if (!root) throw new Error("line: no #root");

createRoot(root).render(
  <StrictMode>
    <Session>
      <LineApp />
    </Session>
  </StrictMode>,
);
