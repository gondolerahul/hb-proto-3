import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./design/index.css";
import { BackgroundPick } from "./boards/BackgroundPick";

/**
 * Redesign R-1/R-3 entry.
 *
 * While the prototype is the deliverable, `main.tsx` mounts the board the
 * current round is up for review on. R-4 replaces this with the real shell.
 */
const root = document.getElementById("root");
if (!root) throw new Error("no #root");

createRoot(root).render(
  <StrictMode>
    <BackgroundPick />
  </StrictMode>,
);
