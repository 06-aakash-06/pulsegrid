// Captures Pharmacy (and regression) screens against `npm run dev:mock`.
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
const roles = {
  patient: { email: "patient@mock.test", route: "/patient/pharmacy" },
  pharmacist: { email: "pharmacist@mock.test", route: "/pharmacist/dashboard" },
};
const extra = [
  ["pharmacist", "pharmacist-inventory", "/pharmacist/inventory"],
  ["pharmacist", "pharmacist-prescriptions", "/pharmacist/prescriptions"],
];
const regression = [
  ["reception", "/patient/dashboard"],
  ["consultation", "/patient/doctors"],
  ["waiting", "/patient/queue"],
];
const regions = {
  header: ".hospital-header",
  pageHeading: ".department-page > .page-heading",
  wallSign: ".pharmacy-wall-sign",
  searchPanel: ".pharmacy-search-counter, .cabinet-rail",
  cabinet: ".medicine-shelves, .shelf-face",
  medicineDetails: ".dispensing-counter, .counter-upper",
  rxStand: ".prescription-stand",
  rightLedger: ".pharmacy-inventory-ledger, .patient-dispensing-workspace, .counter-lower",
  fulfilmentSlip: ".patient-dispensing-workspace .patient-workflow__item, .reservation-slip-panel",
};

async function settle(page) {
  await page.waitForLoadState("networkidle");
  await page.waitForFunction(() => !document.querySelector('[role="status"]')?.textContent?.startsWith("Loading"), null, { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(500);
}

async function measure(page) {
  return page.evaluate((regionSelectors) => {
    const rect = (element) => {
      if (!element) return null;
      const box = element.getBoundingClientRect();
      return { top: Math.round(box.top + scrollY), bottom: Math.round(box.bottom + scrollY), left: Math.round(box.left), right: Math.round(box.right) };
    };
    const result = { overflowX: document.documentElement.scrollWidth > innerWidth, scrollWidth: document.documentElement.scrollWidth, innerWidth, scrollHeight: document.documentElement.scrollHeight, regions: {} };
    for (const [name, selector] of Object.entries(regionSelectors)) result.regions[name] = rect(document.querySelector(selector));
    const marked = document.querySelector("[data-rx-primary]");
    const primary = marked?.matches("button, select, a")
      ? marked
      : marked?.querySelector("button, select, a") ?? document.querySelector(".prescription-stand a.button, .prescription-stand button, .prescription-stand select");
    result.rxPrimary = rect(primary);
    result.rxPrimaryLabel = primary?.textContent?.trim().slice(0, 60) ?? primary?.getAttribute("aria-label") ?? null;
    return result;
  }, regions);
}

async function signIn(browser, email) {
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1536, height: 1024 } });
  const page = await context.newPage();
  await page.goto(`${base}/login`);
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("mock-password");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  return { context, page };
}

const browser = await chromium.launch();
const report = { label, base, captured_at: new Date().toISOString(), captures: [] };
async function capture(page, name, route, width, height) {
  await page.setViewportSize({ width, height });
  await page.goto(`${base}${route}`);
  await settle(page);
  const file = `${label}-${name}-${width}x${height}.png`;
  await page.screenshot({ path: join(out, file) });
  report.captures.push({ file, route, width, height, ...(await measure(page)) });
}

for (const [role, { email, route }] of Object.entries(roles)) {
  const { context, page } = await signIn(browser, email);
  for (const [width, height] of sizes) await capture(page, role, route, width, height);
  for (const [extraRole, name, extraRoute] of extra) if (extraRole === role) await capture(page, name, extraRoute, 1536, 1024);
  if (role === "patient") for (const [name, regressionRoute] of regression) await capture(page, `regression-${name}`, regressionRoute, 1536, 1024);
  await context.close();
}
await browser.close();
writeFileSync(join(out, `${label}-measurements.json`), JSON.stringify(report, null, 2) + "\n");
for (const item of report.captures) {
  console.log(`${item.file}\toverflowX=${item.overflowX}\trxPrimaryBottom=${item.rxPrimary?.bottom ?? "n/a"}\theight=${item.scrollHeight}`);
}
