// Shoot a surface under conditions the default sweep never exercises:
// reduced motion, and a narrow viewport.
//
// Both are claimed by CSS that has never been looked at. `prefers-reduced-motion`
// takes the no-scene path AND stops every animation; the sub-900px rules reflow
// the shell, hide the territory's labels, and turn several grids into columns.
// Claims in a stylesheet that nobody has rendered are claims.
//
//   node scripts/shoot_variants.mjs <outDir> "<nav label>" <name>
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const [OUT, label, name] = process.argv.slice(2);
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--enable-unsafe-swiftshader", "--use-gl=angle"],
});

const go = async (page, wanted) => {
  await page.goto("http://localhost:4044/", { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForSelector(".pn", { timeout: 30000 });
  await page.evaluate((w) => {
    const btn = [...document.querySelectorAll(".pn-item")].find(
      (b) => (b.querySelector(".pn-item-label")?.textContent || "").trim() === w,
    );
    btn?.click();
  }, wanted);
  await new Promise((r) => setTimeout(r, 1700));
};

// 1 — reduced motion, full width.
{
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000 });
  await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
  await go(page, label);
  await page.screenshot({ path: path.join(OUT, `${name}-reduced.png`) });
  console.log("shot", `${name}-reduced`);
  await page.close();
}

// 2 — narrow, motion allowed.
{
  const page = await browser.newPage();
  await page.setViewport({ width: 720, height: 1000 });
  await go(page, label);
  await page.screenshot({ path: path.join(OUT, `${name}-narrow.png`) });
  console.log("shot", `${name}-narrow`);
  await page.close();
}

await browser.close();
