import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * D7 §3.3 makes one rule a **hard build gate**: a tier-C device never downloads
 * three.js.
 *
 * Quarantining three into its own rollup chunk is necessary and not sufficient. A
 * static `import` puts that chunk in the initial module graph, Vite emits a
 * `<link rel="modulepreload">` for it, and every device then fetches ~137 KB
 * gzipped whether or not it will ever run a frame. That is the gate failing while
 * the build output looks like it passes — which is exactly the shape of defect a
 * test has to catch, because reading the chunk list will not.
 *
 * So: the world chunk must exist (the budget needs something to measure) and must
 * NOT be preloaded from the entry HTML.
 *
 * Skipped when `dist/` is absent, so `npm test` does not require a build. CI runs
 * `build` before `test`, which is where this earns its keep.
 */
const DIST = path.resolve(__dirname, "..", "dist");

describe("the tier-C gate (D7 §3.3)", () => {
  const built = existsSync(path.join(DIST, "index.html"));

  it.runIf(built)("quarantines three.js into its own chunk", () => {
    const assets = readdirSync(path.join(DIST, "assets"));
    expect(assets.some((f) => /^world-.*\.js$/.test(f))).toBe(true);
  });

  it.runIf(built)("does not preload the world chunk from the entry HTML", () => {
    const html = readFileSync(path.join(DIST, "index.html"), "utf8");
    const preloads = [...html.matchAll(/rel="modulepreload"[^>]*href="([^"]+)"/g)].map(
      (m) => m[1]!,
    );
    const leaked = preloads.filter((h) => /world-.*\.js$/.test(h));
    expect(
      leaked,
      `the world chunk is preloaded (${leaked.join(", ")}) — three.js must be reached ` +
        `through a dynamic import behind probeTier(), or every device downloads it`,
    ).toEqual([]);
  });

  it.runIf(built)("keeps the shell under the 220 KB gzipped budget", async () => {
    const { gzipSync } = await import("node:zlib");
    const assets = readdirSync(path.join(DIST, "assets"));
    // The shell is everything the entry pulls in — never the world chunk.
    const shell = assets.filter((f) => !/^world-/.test(f) && /\.(js|css)$/.test(f));
    const bytes = shell.reduce(
      (n, f) => n + gzipSync(readFileSync(path.join(DIST, "assets", f))).byteLength,
      0,
    );
    expect(bytes, `shell is ${(bytes / 1024).toFixed(1)} KB gzipped`).toBeLessThan(220 * 1024);
  });
});
