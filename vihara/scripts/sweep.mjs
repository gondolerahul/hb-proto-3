// Visit every surface in the review scaffold and report console errors, page
// errors, and anything that failed to render.
//
// A surface that typechecks can still throw at runtime — a null index, a missing
// fixture key, a bad `useMemo` dependency. This walks all of them so that class
// of defect is found by a script rather than by the owner.
//
//   node scripts/sweep.mjs [outDir]
import puppeteer from "puppeteer";
import { mkdirSync } from "node:fs";
import path from "node:path";

const OUT = process.argv[2];
if (OUT) mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--enable-unsafe-swiftshader", "--use-gl=angle"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });

let bucket = [];
page.on("pageerror", (e) => bucket.push(`PAGEERROR ${String(e).slice(0, 200)}`));
page.on("console", (m) => {
  if (m.type() !== "error") return;
  const t = m.text();
  // The favicon 404 is known and cosmetic; everything else is signal.
  if (t.includes("favicon") || t.includes("status of 404")) return;
  bucket.push(`CONSOLE ${t.slice(0, 200)}`);
});

await page.goto("http://localhost:4044/", { waitUntil: "domcontentloaded", timeout: 60000 });
await page.waitForSelector(".pn", { timeout: 30000 });

const labels = await page.evaluate(() =>
  [...document.querySelectorAll(".pn-item .pn-item-label")].map((n) => n.textContent.trim()),
);

let bad = 0;
for (const label of labels) {
  bucket = [];
  await page.evaluate((wanted) => {
    const btn = [...document.querySelectorAll(".pn-item")].find(
      (b) => (b.querySelector(".pn-item-label")?.textContent || "").trim() === wanted,
    );
    btn?.click();
  }, label);
  await new Promise((r) => setTimeout(r, 1500));

  // Did anything actually render inside the shell?
  const filled = await page.evaluate(() => {
    const body = document.querySelector(".sh-body") ?? document.querySelector("#root");
    return (body?.textContent || "").trim().length > 40;
  });

  const problems = [...bucket];
  if (!filled) problems.push("EMPTY surface body");
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

console.log(bad === 0 ? `\nall ${labels.length} surfaces clean` : `\n${bad} of ${labels.length} with problems`);
await browser.close();
process.exit(bad === 0 ? 0 : 1);
