// Captures Emergency, Billing and Records (plus regression departments) against `npm run dev:mock`.
// Usage: PLAYWRIGHT_CORE=<path to playwright-core> node capture.mjs <before|after> [base-url]
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_CORE ?? "playwright-core");
const label = process.argv[2] ?? "after";
const base = process.argv[3] ?? "http://127.0.0.1:5173";
const out = dirname(fileURLToPath(import.meta.url));
mkdirSync(out, { recursive: true });

const sizes = [[1536, 1024], [1440, 900], [1280, 800], [390, 844]];
const subjects = [
  { name: "emergency-staff", email: "emergency@mock.test", route: "/emergency/dashboard", check: "emergency-primary" },
  { name: "emergency-patient", email: "patient@mock.test", route: "/patient/emergency" },
  { name: "billing-staff", email: "billing@mock.test", route: "/billing/dashboard", check: "billing-balance" },
  { name: "billing-patient", email: "patient@mock.test", route: "/patient/billing", check: "billing-balance" },
  { name: "records-patient", email: "patient@mock.test", route: "/patient/records", check: "records-dossier-header" },
  { name: "records-doctor", email: "doctor@mock.test", route: "/doctor/consultations", check: "records-dossier-header" },
];
const extra = [
  { name: "billing-staff-invoices", email: "billing@mock.test", route: "/billing/invoices", check: "billing-balance" },
];
const regression = [
  { name: "regression-reception", email: "patient@mock.test", route: "/patient/dashboard" },
  { name: "regression-consultation", email: "patient@mock.test", route: "/patient/doctors" },
  { name: "regression-waiting", email: "patient@mock.test", route: "/patient/queue" },
  { name: "regression-pharmacy-patient", email: "patient@mock.test", route: "/patient/pharmacy" },
  { name: "regression-pharmacy-pharmacist", email: "pharmacist@mock.test", route: "/pharmacist/dashboard" },
];

async function settle(page) {
  await page.waitForLoadState("networkidle");
  await page.waitForFunction(() => ![...document.querySelectorAll('[role="status"]')].some((node) => node.textContent?.startsWith("Loading")), null, { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(500);
}

const contexts = new Map();
async function pageFor(browser, email) {
  if (contexts.has(email)) return contexts.get(email);
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1536, height: 1024 } });
  const page = await context.newPage();
  await page.goto(`${base}/login`);
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("mock-password");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  contexts.set(email, page);
  return page;
}

const browser = await chromium.launch();
const report = { label, base, captured_at: new Date().toISOString(), captures: [] };
async function capture({ name, email, route, check }, width, height) {
  const page = await pageFor(browser, email);
  await page.setViewportSize({ width, height });
  await page.goto(`${base}${route}`);
  await settle(page);
  const file = `${label}-${name}-${width}x${height}.png`;
  await page.screenshot({ path: join(out, file) });
  const measured = await page.evaluate((checkName) => {
    const target = checkName ? document.querySelector(`[data-check="${checkName}"]`) : null;
    const box = target?.getBoundingClientRect();
    return {
      overflowX: document.documentElement.scrollWidth > innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      scrollHeight: document.documentElement.scrollHeight,
      check: checkName ?? null,
      checkTop: box ? Math.round(box.top + scrollY) : null,
      checkBottom: box ? Math.round(box.bottom + scrollY) : null,
      checkText: target?.textContent?.trim().replace(/\s+/g, " ").slice(0, 60) ?? null,
    };
  }, check);
  report.captures.push({ file, route, width, height, ...measured });
}

for (const subject of subjects) for (const [width, height] of sizes) await capture(subject, width, height);
for (const subject of [...extra, ...regression]) await capture(subject, 1536, 1024);
await browser.close();
writeFileSync(join(out, `${label}-measurements.json`), JSON.stringify(report, null, 2) + "\n");
let failures = 0;
for (const item of report.captures) {
  const foldFail = item.width === 1536 && item.check && (item.checkBottom === null || item.checkBottom > 1024);
  if (item.overflowX || foldFail) failures += 1;
  console.log(`${item.file}\toverflowX=${item.overflowX}\t${item.check ?? "-"} bottom=${item.checkBottom ?? "n/a"}\theight=${item.scrollHeight}${item.overflowX || foldFail ? "\tFAIL" : ""}`);
}
console.log(`${failures} failing captures`);
