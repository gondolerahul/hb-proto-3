// Visit every surface and report console errors, page errors, and anything that
// failed to render.
//
// A surface that typechecks can still throw at runtime — a null index, a missing
// fixture key, a bad `useMemo` dependency. This walks all of them so that class
// of defect is found by a script rather than by the owner.
//
// The app has two front doors and so does this: the estate's fifteen at `/`, and
// the Line's three tabs at `/line.html` (R-3c C8). The Line is walked at 390×844
// because C is not the estate at 1600px — a phone surface measured at desk width
// is a phone surface nobody has looked at.
//
// ## What R-4 changed, and what this now needs
//
// `PrototypeNav` is deleted (R-4 N4), so there is no strip of buttons to click.
// The estate is enumerated from the **⌘K palette** — the real navigator — and
// then visited **by URL**, which is only possible because N2 gave every surface
// one. Visiting by URL rather than by click is the stronger walk: each surface is
// entered by a cold load, so the session bootstrap and the deep link are swept
// alongside the render.
//
// And the app is now behind a session gate (R-4 A2). **This script needs
// credentials**, or it visits nothing:
//
//   VIHARA_SWEEP_EMAIL=… VIHARA_SWEEP_PASSWORD=… node scripts/sweep.mjs [outDir]
//
// It fails loudly rather than reporting a clean walk of zero surfaces — a sweep
// that silently stops visiting surfaces is worse than a red one, which is the
// lesson R-3c §1 already paid for once.
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const OUT = process.argv[2];
if (OUT) mkdirSync(OUT, { recursive: true });

const BASE = "http://localhost:4044";
const EMAIL = process.env.VIHARA_SWEEP_EMAIL;
const PASSWORD = process.env.VIHARA_SWEEP_PASSWORD;

// R-3c §1: the Line went unbuilt for a whole round because "fifteen" was a
// subtotal reported as a total, and a sweep that only enumerates what it finds
// agrees with whatever it finds — 16/16 was green the entire time three surfaces
// were missing. The total is written down here so that a surface which stops
// being mounted fails the sweep instead of quietly leaving the count.
// Fifteen estate surfaces plus the Line's three. (It was 19 while the review
// scaffold carried a sixteenth entry, `BackgroundPick`, whose decision D2 closed.)
const EXPECTED = 18;

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

/** Stop with one sentence saying what is missing, rather than walking nothing. */
function abort(message) {
  console.log(`✗ ${message}`);
  console.log("\nthe walk visited 0 surfaces");
  return browser.close().then(() => process.exit(1));
}

/**
 * Everything wrong with whatever is on screen right now.
 *
 * The bucket is drained rather than reset, so what a mount threw belongs to the
 * surface that was mounting — including the very first one, whose load errors an
 * up-front reset used to swallow.
 *
 * `gated` is the check R-4 made necessary: every estate surface is entered by a
 * cold load now, so a session that stops surviving the reload would leave a
 * login screen on each visit — and a login screen has plenty of text, so the
 * `filled` check alone would call all fifteen of them clean.
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
      gated: document.querySelector(".ps-card") !== null,
      spill: root.scrollWidth - root.clientWidth,
    };
  });

  const problems = bucket.splice(0);
  if (shape.gated) problems.push("GATED — the session did not survive the load");
  else if (!shape.filled) problems.push("EMPTY surface body");
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
await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded", timeout: 60000 });

// The gate resolves to one of two screens. Waiting for either — rather than for
// the estate — is what lets the failure below be a sentence instead of a timeout.
await page.waitForSelector(".ps-card, .st", { timeout: 30000 });

if (await page.$(".ps-card")) {
  if (!EMAIL || !PASSWORD) {
    await abort(
      "the app is behind the session gate and no credentials were given — set " +
        "VIHARA_SWEEP_EMAIL and VIHARA_SWEEP_PASSWORD (a seeded account; signup is rate-limited)",
    );
  }
  await page.type('.ps-card input[type="email"]', EMAIL);
  await page.type('.ps-card input[type="password"]', PASSWORD);
  await Promise.all([
    page.click(".ps-submit"),
    page.waitForSelector(".st, .ps-problem", { timeout: 30000 }),
  ]);
  if (await page.$(".ps-problem")) {
    const said = await page.$eval(".ps-problem", (n) => n.textContent.trim());
    await abort(`login was refused — the screen said: ${said}`);
  }
  // The bucket may hold the 401 that produced the login screen in the first
  // place. That is the gate working, not a defect on the first surface.
  bucket.splice(0);
}

/* The palette is the only enumeration of the estate now, and it is mounted at
   every depth — including depth 0, where there is no shell — so the chord is
   pressed here at the front door rather than after descending to a room. */
await page.keyboard.down("Control");
await page.keyboard.press("KeyK");
await page.keyboard.up("Control");

try {
  await page.waitForSelector(".pl-opt[data-surface]", { timeout: 10000 });
} catch {
  await abort("⌘K did not open the navigator — the estate cannot be enumerated");
}

const surfaces = await page.evaluate(() =>
  [...document.querySelectorAll(".pl-opt[data-surface]")].map((a) => ({
    label: (a.querySelector(".pl-opt-label")?.textContent || "").trim(),
    href: a.getAttribute("href"),
  })),
);

await page.keyboard.press("Escape");

for (const surface of surfaces) {
  // By URL, not by click: N2 made every surface addressable, so a cold load per
  // surface sweeps the deep link and the session bootstrap along with the render.
  await page.goto(`${BASE}${surface.href}`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForSelector(".sh-body, .st, .ps-card", { timeout: 30000 }).catch(() => undefined);
  await new Promise((r) => setTimeout(r, 1500));
  await record(surface.label, await problemsOf({ overflow: false }));
}

/* ========================================================== the Line · 390px */

// `isMobile`/`hasTouch` and not merely a narrow window: the Morning Story's deck
// is driven by touch events, and a viewport that reports no touch is one where
// the swipe handlers are never wired and never swept.
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
await page.goto(`${BASE}/line.html`, { waitUntil: "domcontentloaded", timeout: 60000 });

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
