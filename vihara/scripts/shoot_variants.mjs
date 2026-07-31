// Shoot a surface under conditions the default sweep never exercises:
// reduced motion, and a viewport the surface was not designed at.
//
// Both are claimed by CSS that has never been looked at. `prefers-reduced-motion`
// takes the no-scene path AND stops every animation; the sub-900px rules reflow
// the shell, hide the territory's labels, and turn several grids into columns.
// Claims in a stylesheet that nobody has rendered are claims.
//
// The Line inverts the second axis. 390×844 is its reference and not its
// exception, so that is where both motion states get shot; what has never been
// rendered there is the `min-width: 640px` block, which turns the tab bar into
// three fixed columns for the tablet that taps a push. Same harness, because the
// two front doors are one product and a surface with its own shooter is a
// surface that stops being shot.
//
//   node scripts/shoot_variants.mjs <outDir> "<nav label>" <name>
//   node scripts/shoot_variants.mjs <outDir> line:"<tab label>" <name>
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const [OUT, target, name] = process.argv.slice(2);
mkdirSync(OUT, { recursive: true });

const onLine = target.startsWith("line:");
const label = onLine ? target.slice("line:".length) : target;

/** The D7 phone reference. `isMobile`/`hasTouch` and not merely 390px wide: the
 *  Morning Story's deck is driven by touch events, and a viewport that reports no
 *  touch is one where the swipe is never wired and so never seen. */
const PHONE = { width: 390, height: 844, deviceScaleFactor: 1, isMobile: true, hasTouch: true };

const browser = await puppeteer.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--enable-unsafe-swiftshader", "--use-gl=angle"],
});

// Both doors wait on the element that carries the navigation before pressing
// anything. A click dispatched before React attaches is swallowed silently, and
// what comes back is a clean-looking shot of a surface that was never opened.
const go = async (page) => {
  const door = onLine ? "http://localhost:4044/line.html" : "http://localhost:4044/";
  await page.goto(door, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForSelector(onLine ? ".ln-tabs .ln-tab" : ".pn", { timeout: 30000 });
  await page.evaluate(
    ([sel, tag, wanted]) => {
      const btn = [...document.querySelectorAll(sel)].find(
        (b) => (b.querySelector(tag)?.textContent || "").trim() === wanted,
      );
      btn?.click();
    },
    onLine ? [".ln-tab", ".ln-tab-label", label] : [".pn-item", ".pn-item-label", label],
  );
  await new Promise((r) => setTimeout(r, 1700));
};

const shoot = async (suffix, viewport, reduced) => {
  const page = await browser.newPage();
  await page.setViewport(viewport);
  if (reduced) {
    await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
  }
  await go(page);
  await page.screenshot({ path: path.join(OUT, `${name}-${suffix}.png`) });
  console.log("shot", `${name}-${suffix}`);
  await page.close();
};

if (onLine) {
  await shoot("reduced", PHONE, true);
  await shoot("phone", PHONE, false);
  // The ≥640px claim, at the width the estate's narrow shot already uses.
  await shoot("wide", { width: 720, height: 1000 }, false);
} else {
  await shoot("reduced", { width: 1600, height: 1000 }, true);
  await shoot("narrow", { width: 720, height: 1000 }, false);
}

await browser.close();
