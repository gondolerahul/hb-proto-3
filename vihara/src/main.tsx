import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./design/index.css";
import { Session } from "./app/Session";
import { Prototype } from "./app/Prototype";
import { parseRoute, ROOT, surfaceOf } from "./app/routes";

/** The estate names the room you were in when the session ended — N2 already
 *  put it in the address bar, so nothing needs storing. The Line has no surface
 *  URLs and passes nothing. */
function placeOfEstate(): string | null {
  const def = surfaceOf(parseRoute(window.location.pathname).surface);
  return def.id === ROOT.id ? null : def.label;
}

/**
 * The estate's entry.
 *
 * R-3 mounted `Prototype` unconditionally, because the prototype was the
 * deliverable (D4). R-4 §3 puts the app behind a door: nothing renders until
 * `Session` has tried the refresh cookie once, and what renders after that is
 * either the estate or a login screen. This file keeps only the mount — the
 * decision is in `app/Session.tsx`, where a test can reach it without mounting
 * the whole application as a module side effect.
 *
 * The Line has its own entry (`line.html` → `src/line/main.tsx`) and its own
 * budget; that is a second front door, not a route.
 */
const root = document.getElementById("root");
if (!root) throw new Error("no #root");

createRoot(root).render(
  <StrictMode>
    <Session placeOf={placeOfEstate}>
      <Prototype />
    </Session>
  </StrictMode>,
);
