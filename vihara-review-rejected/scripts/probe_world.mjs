import puppeteer from "puppeteer";
const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox","--disable-dev-shm-usage","--enable-unsafe-swiftshader"] });
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900 });
await page.goto("http://localhost:4044/", { waitUntil: "networkidle0" });
await page.type('input[type="email"]', "design.review@gochillaao.com");
await page.type('input[type="password"]', "Polish!2026review");
await page.click('button[type="submit"]');
await page.waitForSelector('[data-part="shell"]', { timeout: 15000 });
await page.click('[data-part="walk-in"]');
await new Promise(r => setTimeout(r, 6000));
const info = await page.evaluate(() => {
  const frame = document.querySelector('.vh-world-frame');
  const canvas = frame?.querySelector('canvas');
  const main = document.querySelector('main');
  const terrace = document.querySelector('.vh-terrace');
  const rect = (el) => el ? { w: Math.round(el.getBoundingClientRect().width), h: Math.round(el.getBoundingClientRect().height) } : null;
  const wrapper = canvas?.parentElement;
  const chain = [];
  let node = canvas;
  for (let i = 0; i < 5 && node; i++) {
    chain.push({
      tag: node.tagName,
      cls: node.className && node.className.toString().slice(0, 60),
      style: node.getAttribute && node.getAttribute("style"),
      h: Math.round(node.getBoundingClientRect().height),
      pos: getComputedStyle(node).position,
    });
    node = node.parentElement;
  }
  return {
    chain,
    main: rect(main), terrace: rect(terrace), frame: rect(frame),
    wrapper: rect(wrapper),
    wrapperStyle: wrapper?.getAttribute("style"),
    wrapperComputedHeight: wrapper ? getComputedStyle(wrapper).height : null,
    frameComputedHeight: frame ? getComputedStyle(frame).height : null,
    canvasCss: rect(canvas),
    canvasBuffer: canvas ? { w: canvas.width, h: canvas.height } : null,
    dpr: window.devicePixelRatio,
  };
});
console.log(JSON.stringify(info, null, 2));
await browser.close();
