// Measures text size, target size and computed contrast inside the Pharmacy room against `npm run dev:mock`.
// Usage: PLAYWRIGHT_CORE=<path to playwright-core> node readability-check.mjs [base-url]
import { createRequire } from "node:module";
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_CORE ?? "playwright-core");
const base = process.argv[2] ?? "http://127.0.0.1:5173";
const out = dirname(fileURLToPath(import.meta.url));
const pages = [
  ["patient@mock.test", "/patient/pharmacy"],
  ["pharmacist@mock.test", "/pharmacist/dashboard"],
  ["pharmacist@mock.test", "/pharmacist/prescriptions"],
];

function audit() {
  const parse = (value) => {
    const match = value.match(/rgba?\(([^)]+)\)/);
    if (!match) return null;
    const [r, g, b, a = 1] = match[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r, g, b, a };
  };
  const luminance = ({ r, g, b }) => {
    const channel = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  };
  const blend = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  // Opaque material is required behind operational text, so the first opaque fill (or gradient stop) is the surface.
  const surface = (element) => {
    const layers = [];
    for (let node = element; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      const gradient = style.backgroundImage.match(/rgba?\([^)]+\)/g);
      if (gradient && style.backgroundImage.startsWith("linear-gradient")) {
        const stops = gradient.map(parse);
        const lightest = stops.reduce((a, b) => (luminance(a) > luminance(b) ? a : b));
        const darkest = stops.reduce((a, b) => (luminance(a) < luminance(b) ? a : b));
        return { layers, fills: [lightest, darkest], node };
      }
      const color = parse(style.backgroundColor);
      if (color && color.a > 0) {
        layers.push(color);
        if (color.a >= 0.99) return { layers, fills: [color], node };
      }
    }
    return { layers, fills: [{ r: 255, g: 255, b: 255, a: 1 }], node: null };
  };
  const hidden = (element) => !!element.closest('[aria-hidden="true"], .sr-only') || element.getClientRects().length === 0;
  const room = document.querySelector(".pharmacy-room");
  const texts = [];
  const walker = document.createTreeWalker(room, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const element = node.parentElement;
    if (!node.textContent.trim() || !element || hidden(element) || element.closest("details:not([open]) > :not(summary)")) continue;
    const style = getComputedStyle(element);
    const size = parseFloat(style.fontSize);
    const bold = Number(style.fontWeight) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const { layers, fills } = surface(element);
    const foreground = parse(style.color);
    const ratios = fills.map((fill) => {
      const background = layers.slice().reverse().reduce((under, layer) => blend(layer, under), fill);
      const text = foreground.a < 1 ? blend(foreground, background) : foreground;
      const [l1, l2] = [luminance(text), luminance(background)].sort((a, b) => b - a);
      return (l1 + 0.05) / (l2 + 0.05);
    });
    texts.push({ text: node.textContent.trim().slice(0, 40), size, large, ratio: Math.min(...ratios), required: large ? 3 : 4.5 });
  }
  const targets = [...room.querySelectorAll("button, a[href], select, input, summary")]
    .filter((element) => !hidden(element) && !element.closest("details:not([open]) > :not(summary)"))
    .map((element) => ({ label: (element.textContent || element.getAttribute("aria-label") || element.getAttribute("placeholder") || element.tagName).trim().slice(0, 40), height: Math.round(element.getBoundingClientRect().height), width: Math.round(element.getBoundingClientRect().width), tag: element.tagName }));
  const small = texts.filter((item) => item.size < 12);
  const lowContrast = texts.filter((item) => item.ratio < item.required);
  return {
    textNodes: texts.length,
    minFontSize: Math.min(...texts.map((item) => item.size)),
    belowTwelve: small,
    minContrast: Math.min(...texts.map((item) => item.ratio)).toFixed(2),
    lowContrast,
    targets: targets.length,
    minTargetHeight: Math.min(...targets.map((item) => item.height)),
    targetsBelow40: targets.filter((item) => item.height < 40),
  };
}

const browser = await chromium.launch();
const report = { base, checked_at: new Date().toISOString(), viewport: "1536x1024", pages: [] };
for (const [email, route] of pages) {
  const page = await (await browser.newContext({ viewport: { width: 1536, height: 1024 }, reducedMotion: "reduce" })).newPage();
  await page.goto(`${base}/login`);
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("mock-password");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.goto(`${base}${route}`);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(600);
  const result = await page.evaluate(audit);
  report.pages.push({ route, email, ...result });
  console.log(`${route}\ttext=${result.textNodes}\tminFont=${result.minFontSize}\t<12px=${result.belowTwelve.length}\tminContrast=${result.minContrast}\tlowContrast=${result.lowContrast.length}\tminTarget=${result.minTargetHeight}\t<40px=${result.targetsBelow40.length}`);
  for (const item of result.belowTwelve) console.log("  small:", JSON.stringify(item));
  for (const item of result.lowContrast) console.log("  contrast:", JSON.stringify(item));
  for (const item of result.targetsBelow40) console.log("  target:", JSON.stringify(item));
}
await browser.close();
writeFileSync(join(out, "readability-results.json"), JSON.stringify(report, null, 2) + "\n");
