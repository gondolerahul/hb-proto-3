// Shoot a surface after clicking something in it — for reveal/selection states,
// which a keypress-only driver cannot reach.
//
//   node scripts/shoot_click.mjs <outDir> <name> <keys> <selector>
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const [OUT, name, keys = "", selector] = process.argv.slice(2);
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--enable-unsafe-swiftshader", "--use-gl=angle"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });
page.on("pageerror", (e) => console.log("pageerror:", String(e).slice(0, 200)));

await page.goto("http://localhost:4044/", { waitUntil: "domcontentloaded", timeout: 60000 });
await page.waitForSelector(".pn", { timeout: 30000 });
for (const k of keys) await page.keyboard.press(k);
await new Promise((r) => setTimeout(r, 1400));

if (selector) {
  await page.waitForSelector(selector, { timeout: 15000 });
  await page.click(selector);
  await new Promise((r) => setTimeout(r, 1200));
}

await page.screenshot({ path: path.join(OUT, `${name}.png`) });
console.log("shot", name, selector ? `(clicked ${selector})` : "");
await browser.close();
