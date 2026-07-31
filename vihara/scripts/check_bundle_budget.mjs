// The bundle gate (D7 §3.3) — the single highest-leverage performance rule,
// and the one most likely to be broken by accident.
//
// Every HTML entry the build emits gets its own hard ceiling: 220 KB gzipped
// for everything a tier-C device must download before that page is usable.
// The redesign is growing a second entry (line.html, R-3c) and the Line is
// phone-first, so it gets the same ceiling as the shell rather than a share
// of one. Entries are therefore *discovered* — every dist/*.html is measured —
// instead of matched against hard-coded chunk-name prefixes, which is what
// made the first version of this gate go blind the moment a chunk was renamed.
//
// What counts toward an entry: its own JS and CSS, plus every chunk reachable
// from it by STATIC import, transitively. A chunk shared by both entries is
// counted in both — a cold visit to either page pays for it, and the budget
// is about that first paint, not about the second page's cache hit.
//
// What does not: anything reachable only through `await import()`. That tail
// (three.js and the world it draws) is reported against a soft 600 KB budget.
// This is the whole point of the quarantine — a tier-C device never downloads
// three.js. If a world component ever picks up a static import, its chunk
// joins an entry graph here and the 220 KB ceiling fails loudly.
//
//   npm run build      (vite build && node scripts/check_bundle_budget.mjs)
import { promises as fs } from "node:fs";
import path from "node:path";
import { gzipSync } from "node:zlib";

const ENTRY_BUDGET_BYTES = 220 * 1024;
const LAZY_BUDGET_BYTES = 600 * 1024;

const dist = path.join(process.cwd(), "dist");

// Rollup writes static edges as `...from"./chunk-HASH.js"` or a bare
// `import"./chunk-HASH.js"`. A dynamic edge is `import("./chunk-HASH.js")` —
// the paren after `import` is what keeps it out of this pattern, and out of
// the entry budget.
const STATIC_IMPORT = /(?:^|[\s;},])(?:import|export)\s*(?:[^'"()]*?\bfrom\s*)?["'](\.{1,2}\/[^"']+\.js)["']/g;
// Vite emits the entry's own assets as <script src> / <link href>, including
// the modulepreload links for its static chunks.
const HTML_ASSET = /(?:src|href)\s*=\s*["']([^"']+\.(?:js|css))["']/g;

const gzCache = new Map();
async function gzBytes(file) {
  if (!gzCache.has(file)) {
    gzCache.set(file, gzipSync(await fs.readFile(file)).length);
  }
  return gzCache.get(file);
}

async function exists(file) {
  try {
    return (await fs.stat(file)).isFile();
  } catch {
    return false;
  }
}

// Walk one entry's static graph, returning the set of dist-relative assets a
// browser must have in hand before the page runs.
async function staticGraph(htmlFile) {
  const html = await fs.readFile(htmlFile, "utf-8");
  const seen = new Set();
  const queue = [];

  for (const [, ref] of html.matchAll(HTML_ASSET)) {
    if (/^[a-z]+:\/\//i.test(ref)) continue; // a CDN asset is not our budget
    const file = path.join(dist, ref.replace(/^\//, ""));
    if (await exists(file)) queue.push(file);
  }

  while (queue.length) {
    const file = queue.pop();
    if (seen.has(file)) continue;
    seen.add(file);
    if (!file.endsWith(".js")) continue;
    const code = await fs.readFile(file, "utf-8");
    for (const [, spec] of code.matchAll(STATIC_IMPORT)) {
      const next = path.resolve(path.dirname(file), spec);
      if (!seen.has(next) && (await exists(next))) queue.push(next);
    }
  }
  return seen;
}

async function allAssets(dir) {
  const out = [];
  for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...(await allAssets(full)));
    else if (/\.(js|css)$/.test(entry.name)) out.push(full);
  }
  return out;
}

let htmlEntries;
try {
  htmlEntries = (await fs.readdir(dist))
    .filter((name) => name.endsWith(".html"))
    .map((name) => path.join(dist, name))
    .sort();
} catch {
  console.error(`bundle gate: ${dist} not found — run vite build first`);
  process.exit(1);
}
if (htmlEntries.length === 0) {
  console.error(`bundle gate: no HTML entry in ${dist} — nothing to measure`);
  process.exit(1);
}

const kb = (n) => (n / 1024).toFixed(1);
const reached = new Set();
const failures = [];

for (const htmlFile of htmlEntries) {
  const graph = await staticGraph(htmlFile);
  let bytes = 0;
  for (const file of graph) {
    reached.add(file);
    bytes += await gzBytes(file);
  }
  const name = path.basename(htmlFile);
  console.log(
    `bundle gate: ${name} ${kb(bytes)} KB gz across ${graph.size} static ` +
    `asset(s) (budget ${kb(ENTRY_BUDGET_BYTES)} KB)`,
  );
  if (bytes > ENTRY_BUDGET_BYTES) {
    failures.push(
      `bundle gate FAILED: the ${name} entry is ${kb(bytes)} KB gzipped ` +
      `(budget ${kb(ENTRY_BUDGET_BYTES)} KB). Something heavy joined its ` +
      `static graph — check for a static import of a world component.`,
    );
  }
}

let lazyBytes = 0;
const lazy = [];
for (const file of await allAssets(path.join(dist, "assets"))) {
  if (reached.has(file)) continue;
  lazy.push(path.basename(file));
  lazyBytes += await gzBytes(file);
}
console.log(
  `bundle gate: lazy tail ${kb(lazyBytes)} KB gz across ${lazy.length} ` +
  `chunk(s) (budget ${kb(LAZY_BUDGET_BYTES)} KB, warn only)` +
  (lazy.length ? ` — ${lazy.join(", ")}` : ""),
);

for (const message of failures) console.error(message);
if (failures.length) process.exit(1);
if (lazyBytes > LAZY_BUDGET_BYTES) {
  console.warn(
    `bundle gate WARNING: the lazy tail is ${kb(lazyBytes)} KB gzipped ` +
    `(budget ${kb(LAZY_BUDGET_BYTES)} KB).`,
  );
}
