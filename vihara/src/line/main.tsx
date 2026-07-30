import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../design/index.css";
import { LineApp } from "./LineApp";

/**
 * The Line's entry (R-3c C1/C2) — the second front door, not a second app.
 *
 * It loads the same design substrate as the estate, which is the whole reason
 * the two can share components: `TraySurface` renders on the phone because the
 * material vocabulary underneath it is byte-for-byte the same one.
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
    <LineApp />
  </StrictMode>,
);
