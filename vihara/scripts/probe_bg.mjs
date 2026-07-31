// Diagnostic: is the hex field actually rendering, and how bright?
// Reads the WebGL canvas back and reports max/mean channel values plus the
// renderer string, so "the port is wrong" can be told apart from "SwiftShader
// cannot do the bloom pass".
import puppeteer from "puppeteer";

const browser = await puppeteer.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--enable-unsafe-swiftshader", "--use-gl=angle"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 1000 });
page.on("pageerror", (e) => console.log("pageerror:", String(e).slice(0, 300)));
page.on("console", (m) => console.log(`console.${m.type()}:`, m.text().slice(0, 300)));

await page.goto("http://localhost:4044/", { waitUntil: "networkidle0" });
await page.mouse.move(800, 620);
await new Promise((r) => setTimeout(r, 3500));

const report = await page.evaluate(() => {
  const canvas = document.querySelector(".vh-bg-field canvas");
  if (!canvas) return { error: "no canvas in .vh-bg-field" };

  const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
  const dbg = gl?.getExtension("WEBGL_debug_renderer_info");

  // Copy through a 2D canvas: preserveDrawingBuffer is false, so reading the
  // WebGL buffer directly after a frame gives nothing. drawImage is valid.
  const c2 = document.createElement("canvas");
  c2.width = 400;
  c2.height = 250;
  const ctx = c2.getContext("2d");
  ctx.drawImage(canvas, 0, 0, 400, 250);
  const { data } = ctx.getImageData(0, 0, 400, 250);

  let maxR = 0, maxG = 0, maxB = 0, sum = 0, nonBlack = 0;
  for (let i = 0; i < data.length; i += 4) {
    maxR = Math.max(maxR, data[i]);
    maxG = Math.max(maxG, data[i + 1]);
    maxB = Math.max(maxB, data[i + 2]);
    const lum = data[i] + data[i + 1] + data[i + 2];
    sum += lum;
    if (lum > 12) nonBlack++;
  }
  const px = data.length / 4;
  return {
    cssSize: `${canvas.clientWidth}x${canvas.clientHeight}`,
    bufferSize: `${canvas.width}x${canvas.height}`,
    renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "unknown",
    maxChannel: { r: maxR, g: maxG, b: maxB },
    meanLuma: +(sum / px / 3).toFixed(2),
    nonBlackPct: +((nonBlack / px) * 100).toFixed(1),
  };
});

console.log(JSON.stringify(report, null, 2));
await browser.close();
