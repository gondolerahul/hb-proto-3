/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * Vihara's build (D1 §2, §6).
 *
 * - Dev port 4044 (owner decision 2026-07-29; 02_stack_and_repo.md §6).
 * - `/api` proxies to the backend so the dev app and the SEAM endpoints
 *   share an origin — cookie-mode auth (VP-01) needs same-origin cookies.
 * - The World renderer, when it arrives (WORLD/G1), is a dynamic import;
 *   the manualChunks rule quarantines three.js so the tier-C bundle gate
 *   (scripts/check_bundle_budget.mjs) has a chunk boundary to measure.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 4044,
    strictPort: true,
    // Served publicly behind Apache at vihara.hirebuddha.com (deploy/apache);
    // Vite refuses unknown Host headers without this.
    allowedHosts: ["vihara.hirebuddha.com"],
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
  build: {
    rollupOptions: {
      // The Line (LINE L5) is a second entry sharing the C renderer and
      // the certified set — and never the world (the eslint boundary +
      // the line budget in check_bundle_budget.mjs hold it).
      input: { main: "index.html", line: "line.html" },
      output: {
        manualChunks(id: string) {
          if (
            id.includes("node_modules/three") ||
            id.includes("@react-three")
          ) {
            return "world";
          }
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    globals: false,
  },
});
