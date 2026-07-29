/**
 * The bundle gate (D7 §3.3) — the single highest-leverage performance rule,
 * and the one most likely to be broken by accident.
 *
 * Two numbers, from the device matrix:
 *  - The SHELL (everything a tier-C device downloads — every chunk except
 *    the quarantined "world" chunk) must fit in 220 KB gzipped. HARD FAIL.
 *  - The world chunk (three.js + r3f + world components) gets 600 KB. WARN.
 *
 * A tier-C device must never download three.js: the world chunk exists only
 * behind a dynamic import, so if it ever appears as a static dependency of
 * the entry graph this script cannot see that — but the eslint boundary
 * rule can, and the two gates together are the guarantee.
 */
import { promises as fs } from "node:fs";
import path from "node:path";
import { gzipSync } from "node:zlib";

const SHELL_BUDGET_BYTES = 220 * 1024;
const WORLD_BUDGET_BYTES = 600 * 1024;
// The Line entry (LINE L5) — phone-first, so it gets the same hard
// ceiling as the shell. Its chunks are the `line-*` entry graph; shared
// chunks count toward the SHELL (they download once and are cached).
const LINE_BUDGET_BYTES = 220 * 1024;

const distAssets = path.join(process.cwd(), "dist", "assets");

let entries;
try {
  entries = await fs.readdir(distAssets);
} catch {
  console.error(`bundle gate: ${distAssets} not found — run vite build first`);
  process.exit(1);
}

let shellBytes = 0;
let worldBytes = 0;
let lineBytes = 0;
for (const name of entries) {
  if (!name.endsWith(".js") && !name.endsWith(".css")) continue;
  const raw = await fs.readFile(path.join(distAssets, name));
  const gz = gzipSync(raw).length;
  if (name.startsWith("world-") || name.includes("world-")) worldBytes += gz;
  else if (name.startsWith("line-")) lineBytes += gz;
  else shellBytes += gz;
}

const kb = (n) => (n / 1024).toFixed(1);
console.log(
  `bundle gate: shell ${kb(shellBytes)} KB gz (budget 220), ` +
  `line ${kb(lineBytes)} KB gz (budget 220), ` +
  `world ${kb(worldBytes)} KB gz (budget 600)`);

if (shellBytes > SHELL_BUDGET_BYTES) {
  console.error(
    `bundle gate FAILED: the tier-C shell is ${kb(shellBytes)} KB gzipped ` +
    `(budget ${kb(SHELL_BUDGET_BYTES)} KB). Something heavy joined the ` +
    `entry graph — check for a static import of a world component.`);
  process.exit(1);
}
if (lineBytes > LINE_BUDGET_BYTES) {
  console.error(
    `bundle gate FAILED: the Line entry is ${kb(lineBytes)} KB gzipped ` +
    `(budget ${kb(LINE_BUDGET_BYTES)} KB). The pocket must stay phone-light.`);
  process.exit(1);
}
if (worldBytes > WORLD_BUDGET_BYTES) {
  console.warn(
    `bundle gate WARNING: the world chunk is ${kb(worldBytes)} KB gzipped ` +
    `(budget ${kb(WORLD_BUDGET_BYTES)} KB).`);
}
