/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * Vihara's build — redesign line.
 *
 * - Dev port 4044, unchanged from the first build so the Apache vhost and
 *   the owner's bookmarks keep working.
 * - `/api` proxies to the backend so the dev app and the SEAM endpoints
 *   share an origin — cookie-mode auth (VP-01) needs same-origin cookies.
 * - three.js is quarantined into its own chunk. The redesign's decision D1
 *   narrows what 3D is spent on, but the tier-C rule from D7 §3.3 stands:
 *   a tier-C device never downloads three, so the chunk boundary has to
 *   exist for the budget check to have something to measure.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 4044,
    strictPort: true,
    allowedHosts: ["vihara.hirebuddha.com"],
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("node_modules/three")) return "world";
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
