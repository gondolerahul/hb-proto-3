// Quick verification shots: pre-session, still, terrace.
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const OUT = process.argv[2] ?? "shots";
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--enable-unsafe-swiftshader", "--window-size=1440,900"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
page.on("console", (msg) => {
  if (["error", "warning"].includes(msg.type())) console.log("console:", msg.type(), msg.text().slice(0, 160));
});
page.on("pageerror", (err) => console.log("pageerror:", String(err).slice(0, 200)));

const shot = async (name, ms = 1200) => {
  await new Promise((r) => setTimeout(r, ms));
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });
  console.log("shot", name);
};

await page.goto("http://localhost:4044/", { waitUntil: "networkidle0" });
await shot("q-presession", 1800);
await page.type('input[type="email"]', "design.review@gochillaao.com");
await page.type('input[type="password"]', "Polish!2026review");
await page.click('button[type="submit"]');
await page.waitForSelector('[data-part="shell"]', { timeout: 15000 });
await shot("q-still", 2500);
await page.click('[data-part="walk-in"]');
await shot("q-terrace", 6000);
await page.click('[data-part="places-toggle"]');
await shot("q-places", 800);
await browser.close();
console.log("done");
