// The two-copies gate for the brand tokens.
//
// The source of truth is the design system, in
// docs/product-road-map/increment-7/buddha-cognitive-lab-design-system/
// project/. Vihara keeps a mirror so the app builds without reaching outside
// its own tree, and a mirror that drifts means Vihara renders a brand nobody
// ratified. So: this script writes the mirror, `--check` proves it has not
// moved, and neither the mirror nor the source is ever hand-edited.
//
//   npm run sync:tokens     rewrite the mirror from the design system
//   npm run check:tokens    fail if the mirror has drifted
//
// The mirror is byte-identical except for one rewrite: the design system
// references its faces relatively (url('fonts/…')) because it ships as a
// folder, while Vihara serves them from public/ at /fonts. That rewrite is
// declared here and asserted below, so it stays the ONLY licensed deviation —
// see src/design/index.css, which says the same thing to a reader of the CSS.
//
// Two files the rejected build mirrored are deliberately not mirrored here:
//  - styles.css: the redesign does not use the design system's global layer.
//    src/design/material.css is Vihara's own material vocabulary (RD-5), not
//    a copy of anything, so there is no second copy to keep honest.
//  - the dotted-B watermark: nothing in the redesign renders it yet. Mirror
//    it when something does, not before.
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const app = path.join(here, "..");
const repo = path.resolve(app, "..");
const source = path.join(
  repo, "docs", "product-road-map", "increment-7",
  "buddha-cognitive-lab-design-system", "project");

const TOKENS_SOURCE = path.join(source, "colors_and_type.css");
const TOKENS_MIRROR = path.join(app, "src", "design", "tokens.brand.css");
const FONTS_SOURCE = path.join(source, "fonts");
const FONTS_MIRROR = path.join(app, "public", "fonts");

const check = process.argv.includes("--check");
const drift = [];
const rel = (p) => path.relative(app, p);

// The one licensed deviation, applied on the way in.
async function mirroredTokens() {
  const css = await fs.readFile(TOKENS_SOURCE, "utf-8");
  const rewritten = css.replaceAll("url('fonts/", "url('/fonts/");
  // If the design system ever writes a face URL some other way (double
  // quotes, a nested folder), the rewrite above would miss it and the mirror
  // would 404 at runtime with nothing to show for it. Fail here instead.
  const missed = [...rewritten.matchAll(/url\(\s*["']?(?!\/|data:|https?:)([^"')]+)/g)]
    .map(([, ref]) => ref);
  if (missed.length) {
    console.error(
      `token sync: ${rel(TOKENS_SOURCE)} has relative url(${missed[0]}) that ` +
      "this script does not know how to rewrite — teach it before syncing.");
    process.exit(1);
  }
  return rewritten;
}

const tokens = await mirroredTokens();
if (check) {
  const current = await fs.readFile(TOKENS_MIRROR, "utf-8").catch(() => null);
  if (current !== tokens) drift.push(rel(TOKENS_MIRROR));
} else {
  await fs.writeFile(TOKENS_MIRROR, tokens);
}

// The faces themselves are copied verbatim — no rewrite, so a plain compare.
await fs.mkdir(FONTS_MIRROR, { recursive: true });
for (const name of await fs.readdir(FONTS_SOURCE)) {
  const from = path.join(FONTS_SOURCE, name);
  const to = path.join(FONTS_MIRROR, name);
  if (check) {
    const [a, b] = await Promise.all([
      fs.readFile(from),
      fs.readFile(to).catch(() => null),
    ]);
    if (b === null || !a.equals(b)) drift.push(rel(to));
  } else {
    await fs.copyFile(from, to);
  }
}

if (!check) {
  console.log("token sync: mirror rewritten from the design system");
} else if (drift.length) {
  console.error(
    `token sync FAILED: ${drift.length} file(s) drifted from the design ` +
    `system — ${drift.join(", ")}. Run \`npm run sync:tokens\` and commit ` +
    "the result; never hand-edit the mirror.");
  process.exit(1);
} else {
  console.log("token sync: mirror matches the design system");
}
