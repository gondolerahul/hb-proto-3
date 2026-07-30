import React from "react";
import { createRoot } from "react-dom/client";

import { LineApp } from "./LineApp";
import "../tokens/tokens.css";
import "../app/app.css";

// The service worker owns push and the offline shell (L5). Registration
// failure degrades to a tab that simply is not installable — never an
// error the user has to read.
if ("serviceWorker" in navigator) {
  void navigator.serviceWorker.register("/line-sw.js").catch(() => undefined);
}

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("line: #root missing from line.html");
}

createRoot(rootElement).render(
  <React.StrictMode>
    <LineApp />
  </React.StrictMode>,
);
