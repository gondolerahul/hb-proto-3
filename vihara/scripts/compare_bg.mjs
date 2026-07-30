// Ground truth for redesign decision D2: does the ported background render the
// same as the legacy app it was copied from?
//
// Shoots both under identical headless conditions and reports pixel statistics
// for each, so "the port is wrong" and "software GL cannot do the bloom" are
// distinguishable rather than guessed at.
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const OUT = process.argv[2] ?? "shots";
mkdirSync(OUT, { recursive: true });

const TARGETS = [
  { name: "legacy-app", url: "http://localhost:4055/", selector: null },
  { name: "vihara-port", url: "http://localhost:4044/", selector: ".vh-bg-field canvas" },
];

const browser = await puppeteer.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--enable-unsafe-swiftshader", "--use-gl=angle"],
});

for (const t of TARGETS) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });
  page.on("pageerror", (e) => console.log(`  [${t.name}] pageerror:`, String(e).slice(0, 160)));

  // `networkidle0` never settles against a vite dev server (open HMR socket).
  await page.goto(t.url, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.mouse.move(800, 620);
  await new Promise((r) => setTimeout(r, 4000));

  const stats = await page.evaluate((sel) => {
    const canvas = sel
      ? document.querySelector(sel)
      : [...document.querySelectorAll("canvas")].sort(
          (a, b) => b.width * b.height - a.width * a.height,
        )[0];
    if (!canvas) return { error: "no canvas found" };

    const c2 = document.createElement("canvas");
    c2.width = 480;
    c2.height = 300;
    const ctx = c2.getContext("2d");
    ctx.drawImage(canvas, 0, 0, 480, 300);
    const { data } = ctx.getImageData(0, 0, 480, 300);

    let maxR = 0, maxG = 0, maxB = 0, sum = 0, lit = 0;
    for (let i = 0; i < data.length; i += 4) {
      maxR = Math.max(maxR, data[i]);
      maxG = Math.max(maxG, data[i + 1]);
      maxB = Math.max(maxB, data[i + 2]);
      const lum = data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
      sum += lum;
      if (lum > 24) lit++;
    }
    const px = data.length / 4;
    return {
      buffer: `${canvas.width}x${canvas.height}`,
      css: `${canvas.clientWidth}x${canvas.clientHeight}`,
      maxChannel: `r${maxR} g${maxG} b${maxB}`,
      meanLuma: +(sum / px).toFixed(2),
      litPct: +((lit / px) * 100).toFixed(1),
    };
  }, t.selector);

  console.log(t.name.padEnd(14), JSON.stringify(stats));
  await page.screenshot({ path: path.join(OUT, `cmp-${t.name}.png`) });
  await page.close();
}

await browser.close();
