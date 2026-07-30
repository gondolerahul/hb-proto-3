// Screenshot the dev server. Used for the redesign's review rounds — the whole
// point of decision D4 is that boards are judged as pixels, not as prose.
//
//   node scripts/shoot.mjs <outDir> [<name>:<setupKey> ...]
//
// The board reads its state from keystrokes, so a "setup" here is the sequence
// of keys to press before shooting.
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const OUT = process.argv[2] ?? "shots";
const SHOTS = process.argv.slice(3);
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  headless: true,
  args: [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    // SwiftShader: no GPU on the dev VM, but the scene still has to render.
    "--enable-unsafe-swiftshader",
    "--use-gl=angle",
    "--window-size=1600,1000",
  ],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });
page.on("pageerror", (e) => console.log("pageerror:", String(e).slice(0, 200)));
page.on("console", (m) => {
  if (m.type() === "error") console.log("console.error:", m.text().slice(0, 200));
});

// `networkidle0` never settles against a vite dev server — the HMR socket
// stays open. `domcontentloaded` plus the per-shot dwell is what works.
await page.goto("http://localhost:4044/", { waitUntil: "domcontentloaded", timeout: 60000 });
// Park the mouse mid-canvas so the tile lift is visible in the shot.
await page.mouse.move(800, 620);

for (const spec of SHOTS.length ? SHOTS : ["default:"]) {
  const [name, keys = ""] = spec.split(":");
  for (const k of keys) await page.keyboard.press(k);
  // The floor breathes on a 20s cycle and bloom needs a few frames to settle.
  await new Promise((r) => setTimeout(r, 3200));
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });
  console.log("shot", name, keys ? `(keys: ${keys})` : "");
}

await browser.close();
