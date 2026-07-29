/**
 * Re-copy the design-system token source into vihara/src/tokens/ (SUB T2).
 * The source of truth stays docs/product-road-map/increment-7/
 * buddha-cognitive-lab-design-system/project/; the vitest two-copies gate
 * fails when the mirror drifts. Run after any design-system change:
 *   node scripts/sync_tokens.mjs
 */
import { promises as fs } from "node:fs";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname);
const repo = path.resolve(here, "..", "..");
const source = path.join(
  repo, "docs", "product-road-map", "increment-7",
  "buddha-cognitive-lab-design-system", "project");
const target = path.join(here, "..", "src", "tokens");

await fs.copyFile(
  path.join(source, "colors_and_type.css"),
  path.join(target, "colors_and_type.css"));
await fs.copyFile(
  path.join(source, "styles.css"),
  path.join(target, "styles.css"));
await fs.cp(
  path.join(source, "fonts"), path.join(target, "fonts"),
  { recursive: true });
console.log("tokens synced from the design system");
