// Exercises Emergency, Billing and Records interactions against `npm run dev:mock` (in-memory mock writes only).
// Usage: PLAYWRIGHT_CORE=<path to playwright-core> node interaction-check.mjs [base-url]
import { createRequire } from "node:module";
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_CORE ?? "playwright-core");
const base = process.argv[2] ?? "http://127.0.0.1:5173";
const out = dirname(fileURLToPath(import.meta.url));
const results = [];
const check = (name, pass, detail = "") => {
  results.push({ name, pass, detail });
  console.log(`${pass ? "PASS" : "FAIL"}\t${name}${detail ? `\t${detail}` : ""}`);
};
async function signIn(browser, email) {
  const page = await (await browser.newContext({ viewport: { width: 1536, height: 1024 } })).newPage();
  await page.goto(`${base}/login`);
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("mock-password");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  return page;
}
const stepsText = (page) => page.locator(".er-steps").innerText();

const browser = await chromium.launch();

const staff = await signIn(browser, "emergency@mock.test");
await staff.goto(`${base}/emergency/dashboard`);
await staff.waitForLoadState("networkidle");
const counts = await staff.locator(".er-counts li strong").allInnerTexts();
check("header counts are derived from the loaded list", counts.join(",") === "2,3,1", `unassigned/P1–2/claimed = ${counts.join(",")}`);
check("submitted request offers Set priority as the primary step", (await staff.locator('.er-primary button[type="submit"]').innerText()) === "Review Set priority");
await staff.getByRole("button", { name: "Track request 7103" }).click();
await staff.locator(".er-primary").getByRole("button", { name: "Review Claim request" }).waitFor();
check("triaged request offers Claim as the primary step, with change priority and cancel secondary", /Change priority[\s\S]*Cancel request/.test(await stepsText(staff)));
await staff.getByRole("button", { name: "Review Claim request" }).click();
await staff.getByRole("button", { name: "Confirm Claim request" }).click();
await staff.locator(".er-primary").getByRole("button", { name: "Review Start processing" }).waitFor();
check("after an owner-confirmed claim the next step becomes Start processing (mock write)", /Release claim/.test(await stepsText(staff)), "release claim offered as secondary");
await staff.getByRole("button", { name: "Track request 7106" }).click();
await staff.getByText(/Claimed by another staff member/).waitFor();
check("another holder's claim shows no primary step", (await staff.locator(".er-primary").count()) === 0);
await staff.getByRole("button", { name: "Track request 7107" }).click();
await staff.locator(".er-primary").getByRole("button", { name: "Review Resolve request" }).waitFor();
check("own processing request offers Resolve as the primary step", true);
await staff.getByRole("button", { name: "Track request 7108" }).click();
await staff.getByText(/This request is resolved/).waitFor();
check("resolved request shows no actions", (await staff.locator(".er-steps details, .er-primary").count()) === 0);

const cashier = await signIn(browser, "billing@mock.test");
await cashier.goto(`${base}/billing/dashboard`);
await cashier.waitForLoadState("networkidle");
check("receipt groups consultation and pharmacy charges", (await cashier.locator(".cashier-lines__group").allInnerTexts()).map((text) => text.split(" (")[0]).join(",") === "Consultation,Pharmacy");
check("medicine charges show the Pharmacy name", (await cashier.locator(".cashier-lines tbody th").allInnerTexts()).includes("Paracetamol 500 mg tablets"));
await cashier.getByRole("button", { name: "View invoice 9702" }).click();
await cashier.locator(".cashier-context").getByText("Part paid").waitFor();
check("selecting an invoice updates the context band", true, "Invoice …9702 · Part paid");
const amount = cashier.getByLabel("Payment amount (₹)");
await amount.fill("100.5");
check("rupee input previews the exact paise submitted", (await cashier.locator(".paise-preview").innerText()).includes("10050 paise"));
await cashier.getByRole("tab", { name: "Tariff reference" }).click();
await cashier.locator(".cashier-price-table tbody tr").first().waitFor();
check("tariff reference labels historical revisions", (await cashier.locator(".cashier-price-table").innerText()).includes("Historical · revision 1"));
await cashier.getByRole("button", { name: "Change invoice" }).click();
check("Change invoice moves focus to the register", await cashier.evaluate(() => document.activeElement?.classList.contains("cashier-register")));

const patient = await signIn(browser, "patient@mock.test");
await patient.goto(`${base}/patient/records`);
await patient.waitForLoadState("networkidle");
check("patient band shows last visit and visit count", (await patient.locator(".dossier-band").innerText()).includes("13 October 2026"));
await patient.locator(".visit-entry", { hasText: "Amended" }).click();
await patient.locator(".record-versions li").nth(1).waitFor();
check("amended visit lists both versions in record history", (await patient.locator(".record-versions li").count()) === 2);
await patient.locator(".record-versions button", { hasText: "Original record" }).click();
await patient.locator(".dossier-notice").waitFor();
check("opening the earlier version shows the earlier-version notice", true);
await patient.locator(".visit-entry", { hasText: "14 Jun 2026" }).click();
await patient.locator(".dossier-rx[data-state='revoked']").waitFor();
check("revoked prescription stays visible with a Revoked label", (await patient.locator(".dossier-rx[data-state='revoked']").innerText()).includes("Revoked"));

await browser.close();
writeFileSync(join(out, "interaction-results.json"), JSON.stringify({ base, checked_at: new Date().toISOString(), results }, null, 2) + "\n");
if (results.some((item) => !item.pass)) process.exitCode = 1;
