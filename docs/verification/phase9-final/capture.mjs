// Final Phase 9 sweep against `npm run dev:mock`: every department and role at four viewports, with automated checks.
// Usage: PLAYWRIGHT_CORE=<path to playwright-core> node capture.mjs [base-url]
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_CORE ?? "playwright-core");
const base = process.argv[2] ?? "http://127.0.0.1:5173";
const out = dirname(fileURLToPath(import.meta.url));
mkdirSync(out, { recursive: true });

const sizes = [[1536, 1024], [1440, 900], [1280, 800], [390, 844]];
export const subjects = [
  { name: "reception-patient", department: "Reception", email: "patient@mock.test", route: "/patient/dashboard", primary: ".appointment-slip", reference: "home.png" },
  { name: "consultation-patient", department: "Consultation", email: "patient@mock.test", route: "/patient/doctors", primary: ".reference-consultation button", reference: "consultation.png" },
  { name: "appointments-book", department: "Appointments", email: "patient@mock.test", route: "/patient/appointments", primary: "button.available-slot:not([disabled])", reference: "appointment.png" },
  { name: "appointments-manage", department: "Appointments", email: "patient@mock.test", route: "/patient/appointments?view=upcoming", primary: ".appointment-row__actions button", reference: "resehduele waiting and walkin.png" },
  { name: "appointments-reschedule", department: "Appointments", email: "patient@mock.test", route: "/patient/appointments?view=reschedule", primary: ".reschedule-pick__row", reference: "resehduele waiting and walkin.png" },
  { name: "appointments-walkin", department: "Appointments", email: "receptionist@mock.test", route: "/receptionist/appointments?view=walk-in", primary: ".walkin-patient-search button", reference: "resehduele waiting and walkin.png" },
  { name: "waiting-patient", department: "Waiting Room", email: "patient@mock.test", route: "/patient/queue", primary: ".checkin-kiosk button, .checkin-kiosk a", reference: "waiting room.png" },
  { name: "pharmacy-patient", department: "Pharmacy", email: "patient@mock.test", route: "/patient/pharmacy", primary: "[data-rx-primary]", reference: "pharmacy.png" },
  { name: "pharmacy-pharmacist", department: "Pharmacy", email: "pharmacist@mock.test", route: "/pharmacist/dashboard", primary: "[data-rx-primary] button", reference: "pharmacy.png" },
  { name: "billing-patient", department: "Billing", email: "patient@mock.test", route: "/patient/billing", primary: "[data-check='billing-balance']", reference: "billing.png" },
  { name: "billing-staff", department: "Billing", email: "billing@mock.test", route: "/billing/dashboard", primary: "[data-check='billing-balance']", reference: "billing.png" },
  { name: "emergency-patient", department: "Emergency", email: "patient@mock.test", route: "/patient/emergency", primary: ".er-intake button[type='submit']", reference: "emergency.png" },
  { name: "emergency-staff", department: "Emergency", email: "emergency@mock.test", route: "/emergency/dashboard", primary: "[data-check='emergency-primary'] button[type='submit']", reference: "emergency.png" },
  { name: "records-patient", department: "Medical Records", email: "patient@mock.test", route: "/patient/records", primary: "[data-check='records-dossier-header']", reference: "medicalrecords.png" },
  { name: "records-doctor", department: "Medical Records", email: "doctor@mock.test", route: "/doctor/consultations", primary: "[data-check='records-dossier-header']", reference: "medicalrecords.png" },
  { name: "control-admin", department: "Control Room", email: "admin@mock.test", route: "/admin/control-room", primary: ".ops-tile", reference: "controlroom.png" },
  { name: "control-ops", department: "Control Room", email: "ops@mock.test", route: "/ops/dashboard", primary: ".ops-tile", reference: "controlroom.png" },
  { name: "traces-admin", department: "Control Room", email: "admin@mock.test", route: "/admin/traces", primary: ".ops-trace-row", reference: "controlroom.png" },
  { name: "traces-ops", department: "Control Room", email: "ops@mock.test", route: "/ops/traces", primary: ".ops-trace-row", reference: "controlroom.png" },
];

function audit({ primary, mobile }) {
  const hidden = (element) => !!element.closest('[aria-hidden="true"], .sr-only, .skip-link, details:not([open]) > :not(summary)') || element.getClientRects().length === 0;
  const visibleBox = (element) => {
    const box = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return box.width > 0 && box.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  };
  const describe = (element) => {
    const region = element.closest(".hospital-header") ? "header" : element.closest(".workspace-sidebar") ? "directory" : "main";
    return `${region} ${element.tagName.toLowerCase()}${element.className && typeof element.className === "string" ? "." + element.className.trim().split(/\s+/).slice(0, 2).join(".") : ""}`;
  };
  const small = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const element = node.parentElement;
    if (!node.textContent.trim() || !element || hidden(element) || !visibleBox(element)) continue;
    const size = parseFloat(getComputedStyle(element).fontSize);
    if (size < 12) small.push({ at: describe(element), size, text: node.textContent.trim().slice(0, 40) });
  }
  const targets = [];
  if (mobile) {
    for (const element of document.querySelectorAll("button, a[href], summary, select, input:not([type='hidden'])")) {
      if (hidden(element) || !visibleBox(element)) continue;
      const box = element.getBoundingClientRect();
      const isInput = element.matches("input, select");
      if (box.height < 40 || (!isInput && box.width < 40)) targets.push({ at: describe(element), width: Math.round(box.width), height: Math.round(box.height), text: (element.textContent || element.getAttribute("aria-label") || "").trim().slice(0, 40) });
    }
  }
  const primaryElement = primary ? document.querySelector(primary) : null;
  const primaryBox = primaryElement?.getBoundingClientRect();
  return {
    overflowX: document.documentElement.scrollWidth > innerWidth,
    scrollHeight: document.documentElement.scrollHeight,
    smallText: small,
    smallTargets: targets,
    primaryBottom: primaryBox ? Math.round(primaryBox.bottom + scrollY) : null,
  };
}

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

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const browser = await chromium.launch();
  const report = { base, captured_at: new Date().toISOString(), captures: [] };
  for (const subject of subjects) {
    const page = await pageFor(browser, subject.email);
    for (const [width, height] of sizes) {
      await page.setViewportSize({ width, height });
      await page.goto(`${base}${subject.route}`);
      await settle(page);
      const file = `${subject.name}-${width}x${height}.png`;
      await page.screenshot({ path: join(out, file) });
      const result = await page.evaluate(audit, { primary: width === 1536 ? subject.primary : null, mobile: width === 390 });
      const failures = [];
      if (result.overflowX) failures.push("horizontal overflow");
      if (result.smallText.length) failures.push(`${result.smallText.length} text nodes < 12px`);
      if (result.smallTargets.length) failures.push(`${result.smallTargets.length} targets < 40px`);
      if (width === 1536 && (result.primaryBottom === null || result.primaryBottom > 1024)) failures.push(`primary action bottom ${result.primaryBottom ?? "missing"}`);
      report.captures.push({ subject: subject.name, department: subject.department, route: subject.route, width, height, file, ...result, failures });
      console.log(`${file}\t${failures.length ? "FAIL " + failures.join("; ") : "ok"}`);
    }
  }
  await browser.close();
  writeFileSync(join(out, "measurements.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(`${report.captures.filter((item) => item.failures.length).length} of ${report.captures.length} captures with failures`);
}
