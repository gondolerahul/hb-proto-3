// Shoot a surface after a sequence of clicks — for multi-beat flows that a
// single click cannot reach (the Boardroom's tabling exchange).
//
//   node scripts/shoot_flow.mjs <outDir> <name> <keys> <sel1> <sel2> ...
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const [OUT, name, keys = "", ...selectors] = process.argv.slice(2);
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
await new Promise((r) => setTimeout(r, 1000));

for (const sel of selectors) {
  // `nth:` picks one of a repeated selector — the option chips are identical.
  const m = sel.match(/^nth:(\d+):(.*)$/);
  if (m) {
    const [, idx, real] = m;
    await page.waitForSelector(real, { timeout: 15000 });
    const els = await page.$$(real);
    const el = els[Number(idx)];
    if (!el) throw new Error(`no element ${idx} for ${real} (found ${els.length})`);
    await el.click();
  } else {
    await page.waitForSelector(sel, { timeout: 15000 });
    await page.click(sel);
  }
  await new Promise((r) => setTimeout(r, 500));
}

await new Promise((r) => setTimeout(r, 900));
await page.screenshot({ path: path.join(OUT, `${name}.png`) });
console.log("shot", name, `(${selectors.length} clicks)`);
await browser.close();
