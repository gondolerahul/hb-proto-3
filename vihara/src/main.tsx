import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./design/index.css";
import { Prototype } from "./app/Prototype";

/**
 * Redesign R-3 entry.
 *
 * The prototype IS the deliverable (decision D4), so this mounts it directly.
 * R-4 replaces `Prototype` with the real shell and swaps the fixtures for the
 * API client — the surfaces themselves carry across.
 */
const root = document.getElementById("root");
if (!root) throw new Error("no #root");

createRoot(root).render(
  <StrictMode>
    <Prototype />
  </StrictMode>,
);
