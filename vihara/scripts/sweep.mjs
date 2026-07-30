// Visit every surface in the review scaffold and report console errors, page
// errors, and anything that failed to render.
//
// A surface that typechecks can still throw at runtime — a null index, a missing
// fixture key, a bad `useMemo` dependency. This walks all of them so that class
// of defect is found by a script rather than by the owner.
//
// The app has two front doors and so does this: the estate's sixteen at `/`, and
// the Line's three tabs at `/line.html` (R-3c C8). The Line is walked at 390×844
// because C is not the estate at 1600px — a phone surface measured at desk width
// is a phone surface nobody has looked at.
//
//   node scripts/sweep.mjs [outDir]
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const OUT = process.argv[2];
if (OUT) mkdirSync(OUT, { recursive: true });

// R-3c §1: the Line went unbuilt for a whole round because "fifteen" was a
// subtotal reported as a total, and a sweep that only enumerates what it finds
// agrees with whatever it finds — 16/16 was green the entire time three surfaces
// were missing. The total is written down here so that a surface which stops
// being mounted fails the sweep instead of quietly leaving the count.
const EXPECTED = 19;

const browser = await puppeteer.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--enable-unsafe-swiftshader", "--use-gl=angle"],
});
const page = await browser.newPage();

const bucket = [];
page.on("pageerror", (e) => bucket.push(`PAGEERROR ${String(e).slice(0, 200)}`));
page.on("console", (m) => {
  if (m.type() !== "error") return;
  const t = m.text();
  // The favicon 404 is known and cosmetic; everything else is signal.
  if (t.includes("favicon") || t.includes("status of 404")) return;
  bucket.push(`CONSOLE ${t.slice(0, 200)}`);
});

let seen = 0;
let bad = 0;

/**
 * Everything wrong with whatever is on screen right now.
 *
 * The bucket is drained rather than reset, so what a mount threw belongs to the
 * surface that was mounting — including the very first one, whose load errors an
 * up-front reset used to swallow.
 *
 * `overflow` is asked only of the Line: 390px is the D7 phone reference and
 * R-3c §6 makes "no horizontal scroll at that width" a gate, so this is where it
 * gets measured. The estate's equivalent is 900px and is not what this walk is at.
 */
async function problemsOf({ overflow }) {
  const shape = await page.evaluate(() => {
    const body =
      document.querySelector(".sh-body") ??
      document.querySelector(".ln-body") ??
      document.querySelector("#root");
    const root = document.documentElement;
    return {
      filled: (body?.textContent || "").trim().length > 40,
      spill: root.scrollWidth - root.clientWidth,
    };
  });

  const problems = bucket.splice(0);
  if (!shape.filled) problems.push("EMPTY surface body");
  if (overflow && shape.spill > 0) problems.push(`SCROLLS horizontally, by ${shape.spill}px`);
  return problems;
}

/** One line of the report, and the frame beside it. */
async function record(label, problems) {
  seen++;
  if (problems.length) {
    bad++;
    console.log(`✗ ${label}`);
    for (const p of problems) console.log(`    ${p}`);
  } else {
    console.log(`✓ ${label}`);
  }
  if (OUT) {
    await page.screenshot({
      path: path.join(OUT, `sweep-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.png`),
    });
  }
}

/* ======================================================== the estate · 1600px */

await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });
await page.goto("http://localhost:4044/", { waitUntil: "domcontentloaded", timeout: 60000 });
await page.waitForSelector(".pn", { timeout: 30000 });

const labels = await page.evaluate(() =>
  [...document.querySelectorAll(".pn-item .pn-item-label")].map((n) => n.textContent.trim()),
);

for (const label of labels) {
  await page.evaluate((wanted) => {
    const btn = [...document.querySelectorAll(".pn-item")].find(
      (b) => (b.querySelector(".pn-item-label")?.textContent || "").trim() === wanted,
    );
    btn?.click();
  }, label);
  await new Promise((r) => setTimeout(r, 1500));
  await record(label, await problemsOf({ overflow: false }));
}

/* ========================================================== the Line · 390px */

// `isMobile`/`hasTouch` and not merely a narrow window: the Morning Story's deck
// is driven by touch events, and a viewport that reports no touch is one where
// the swipe handlers are never wired and never swept.
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
await page.goto("http://localhost:4044/line.html", { waitUntil: "domcontentloaded", timeout: 60000 });

// The tab bar, not the body: the Line's whole navigation is three buttons — there
// is no ⌘K and no depth ladder to fall back on — and a tab pressed before React
// attaches is a click that silently does nothing, after which the sweep would
// report a clean surface it had never actually opened.
await page.waitForSelector(".ln-tabs .ln-tab", { timeout: 30000 });
await new Promise((r) => setTimeout(r, 1200));

const tabs = await page.evaluate(() =>
  [...document.querySelectorAll(".ln-tab .ln-tab-label")].map((n) => n.textContent.trim()),
);

for (const tab of tabs) {
  await page.evaluate((wanted) => {
    const btn = [...document.querySelectorAll(".ln-tab")].find(
      (b) => (b.querySelector(".ln-tab-label")?.textContent || "").trim() === wanted,
    );
    btn?.click();
  }, tab);
  await new Promise((r) => setTimeout(r, 1500));
  await record(`The Line · ${tab}`, await problemsOf({ overflow: true }));
}

/* ===================================================================== tally */

if (seen !== EXPECTED) {
  bad++;
  console.log(`✗ the walk found ${seen} surfaces, not ${EXPECTED} — one has stopped being mounted`);
}
console.log(bad === 0 ? `\nall ${seen} surfaces clean` : `\n${bad} of ${seen} with problems`);
await browser.close();
process.exit(bad === 0 ? 0 : 1);
