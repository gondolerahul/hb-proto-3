// Screenshot every Vihara surface + the five wireframe visuals.
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const OUT = process.argv[2] ?? "shots";
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  headless: true,
  args: [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--enable-unsafe-swiftshader",
    "--window-size=1440,900",
  ],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });

const shot = async (name, ms = 900) => {
  await new Promise((r) => setTimeout(r, ms));
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });
  console.log("shot", name);
};

// Navigation goes through the Places palette (POLISH L3).
const goPlace = async (label) => {
  await page.click('[data-part="places-toggle"]');
  await new Promise((r) => setTimeout(r, 300));
  await page.evaluate((text) => {
    const places = [...document.querySelectorAll(".vh-place")];
    const btn = places.find((b) =>
      b.querySelector("span")?.textContent.trim().includes(text),
    );
    if (btn) btn.click();
    else throw new Error(`no place ${text}`);
  }, label);
};

// ── wireframes first (the reference) ─────────────────────────────────
const wf = "/home/rahul/workspace/hb-proto-3/docs/product-road-map/increment-7/wireframes";
for (const name of ["still-visual", "estate-visual", "district-visual", "glasshouse-visual", "undercroft-visual"]) {
  await page.goto(`file://${wf}/${name}.html`, { waitUntil: "networkidle0" });
  await shot(`wf-${name}`, 1500);
}

// ── the app ──────────────────────────────────────────────────────────
await page.goto("http://localhost:4044/", { waitUntil: "networkidle0" });
await shot("app-presession", 1500);

// login
await page.type('input[type="email"]', "design.review@gochillaao.com");
await page.type('input[type="password"]', "Polish!2026review");
await page.click('button[type="submit"]');
await page.waitForSelector('[data-part="shell"]', { timeout: 15000 });
await shot("app-still", 2000);

const rooms = [
  ["the terrace", "app-terrace", 6000],
  ["registry halls", "app-halls", 3000],
  ["the standup", "app-standup", 2000],
  ["the boardroom", "app-board", 2000],
  ["the talent office", "app-talent", 2000],
  ["the gallery", "app-gallery", 2000],
  ["the library", "app-library", 2000],
  ["bridges & gates", "app-bridges", 2000],
  ["the glasshouse", "app-glasshouse", 2000],
  ["the undercroft", "app-undercroft", 2000],
  ["the study", "app-study", 2000],
];
for (const [label, name, wait] of rooms) {
  try {
    await goPlace(label);
    await shot(name, wait);
  } catch (err) {
    console.log("skip", name, String(err).slice(0, 80));
  }
}

// trays panel
try {
  await page.evaluate(() => {
    document.querySelector('[data-part="trays-toggle"]')?.click();
  });
  await shot("app-trays", 1200);
} catch {}

await browser.close();
console.log("done");
