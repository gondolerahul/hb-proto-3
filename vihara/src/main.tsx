import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./design/index.css";
import { Session } from "./app/Session";

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
    <Session />
  </StrictMode>,
);
