// Shoot a surface by its review-scaffold label.
//
//   node scripts/shoot_surface.mjs <outDir> <name> "<nav label>" [clickSelector]
//
// The keyboard shortcut only reaches surfaces 1-9 (single keypress), so past nine
// the scaffold has to be clicked. Matching on the visible label also keeps these
// invocations readable when the surface order changes.
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const [OUT, name, label, clickSelector] = process.argv.slice(2);
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--enable-unsafe-swiftshader", "--use-gl=angle"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });
page.on("pageerror", (e) => console.log("pageerror:", String(e).slice(0, 220)));

await page.goto("http://localhost:4044/", { waitUntil: "domcontentloaded", timeout: 60000 });
await page.waitForSelector(".pn", { timeout: 30000 });

const clicked = await page.evaluate((wanted) => {
  const btn = [...document.querySelectorAll(".pn-item")].find((b) =>
    (b.querySelector(".pn-item-label")?.textContent || "").trim() === wanted,
  );
  if (!btn) return false;
  btn.click();
  return true;
}, label);
if (!clicked) throw new Error(`no nav item labelled "${label}"`);

await new Promise((r) => setTimeout(r, 1600));

if (clickSelector) {
  await page.waitForSelector(clickSelector, { timeout: 15000 });
  await page.click(clickSelector);
  await new Promise((r) => setTimeout(r, 1100));
}

await page.screenshot({ path: path.join(OUT, `${name}.png`) });
console.log("shot", name);
await browser.close();
