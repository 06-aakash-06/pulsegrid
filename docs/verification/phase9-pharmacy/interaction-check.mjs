// Exercises Pharmacy interactions against `npm run dev:mock` (mock data only; the reservation is an in-memory fixture write).
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

const browser = await chromium.launch();

const pharmacist = await signIn(browser, "pharmacist@mock.test");
await pharmacist.goto(`${base}/pharmacist/dashboard`);
await pharmacist.waitForLoadState("networkidle");
const upperName = () => pharmacist.locator(".counter-upper .selected-medicine-name").textContent();
check("first shelf medicine auto-selected", (await upperName()) === "Paracetamol 500 mg tablets", await upperName());

await pharmacist.getByRole("button", { name: /^Salbutamol 100 mcg inhaler/ }).click();
await pharmacist.waitForFunction(() => document.querySelector(".counter-upper .selected-medicine-name")?.textContent === "Salbutamol 100 mcg inhaler");
await pharmacist.waitForFunction(() => document.querySelectorAll(".batch-ledger tbody tr").length > 0, null, { timeout: 5000 }).catch(() => {});
const batchRows = await pharmacist.locator(".batch-ledger tbody tr").count();
check("carton selection updates right counter with that medicine's batches", batchRows === 2, `${batchRows} batch rows`);

await pharmacist.getByRole("button", { name: "Unavailable", exact: true }).click();
await pharmacist.waitForTimeout(300);
const unavailable = await pharmacist.locator(".shelf-slot").evaluateAll((slots) => slots.map((slot) => slot.getAttribute("data-availability")));
check("availability filter shows only matching medicines on the page", unavailable.length > 0 && unavailable.every((value) => value === "unavailable"), `${unavailable.length} slots`);
await pharmacist.getByRole("button", { name: "All", exact: true }).click();

await pharmacist.getByRole("button", { name: "Next shelf page" }).click();
await pharmacist.waitForFunction(() => document.querySelector(".cabinet-rail__pages > span")?.textContent === "Page 2" && document.querySelectorAll(".shelf-slot").length > 0);
const pageTwo = await pharmacist.locator(".shelf-slot").count();
check("pagination moves to shelf page 2", pageTwo === 2, `${pageTwo} medicines on page 2`);
await pharmacist.getByRole("button", { name: "Previous shelf page" }).click();
await pharmacist.waitForFunction(() => document.querySelector(".cabinet-rail__pages > span")?.textContent === "Page 1" && document.querySelectorAll(".shelf-slot").length > 2);
check("pagination returns to shelf page 1", (await pharmacist.locator(".shelf-slot").count()) === 12);

const search = pharmacist.getByRole("combobox", { name: "Find a medicine" });
await search.fill("pant");
await pharmacist.getByRole("option", { name: /Pantoprazole/ }).click();
await pharmacist.waitForFunction(() => document.querySelector(".counter-upper .selected-medicine-name")?.textContent?.startsWith("Pantoprazole"));
check("autocomplete selection updates right counter", true, await upperName());

await pharmacist.goto(`${base}/pharmacist/dashboard`);
await pharmacist.waitForLoadState("networkidle");
await pharmacist.getByRole("combobox", { name: "Find a medicine" }).focus();
const order = [];
for (let index = 0; index < 40; index += 1) {
  await pharmacist.keyboard.press("Tab");
  const zone = await pharmacist.evaluate(() => {
    const active = document.activeElement;
    return active?.closest(".medicine-cabinet") ? "cabinet" : active?.closest(".prescription-stand") ? "stand" : active?.closest(".counter-tray") ? "tray" : active?.closest(".pharmacy-room__right") ? "counter" : "other";
  });
  if (order.at(-1) !== zone) order.push(zone);
}
const sequence = order.filter((zone) => zone !== "other");
check("keyboard order runs cabinet → Rx stand → right counter", sequence.join(">").startsWith("cabinet>stand>") && sequence.includes("counter") && sequence.indexOf("counter") > sequence.indexOf("stand"), sequence.join(" > "));

await pharmacist.getByRole("link", { name: "Open dispensing workspace →" }).click();
await pharmacist.waitForURL(`${base}/pharmacist/prescriptions`);
await pharmacist.waitForLoadState("networkidle");
await pharmacist.getByLabel("Prescription ID", { exact: true }).fill("6001");
await pharmacist.waitForFunction(() => [...document.querySelectorAll(".prescription-stand input")].some((input) => input.value === "6001"));
await pharmacist.getByRole("button", { name: "Open", exact: true }).click();
await pharmacist.getByRole("button", { name: "Request medicines from prescription 6001" }).waitFor({ timeout: 10000 }).catch(async (error) => { await pharmacist.screenshot({ path: join(out, "interaction-failure.png") }); throw error; });
check("dispensing workspace opens and places the looked-up prescription on the counter", true);
await pharmacist.locator(".counter-upper .dispensing-reservation-title").waitFor();
check("current reservation appears in the right counter", /^Reservation …\d+$/.test(await pharmacist.locator(".counter-upper .dispensing-reservation-title").textContent()), await pharmacist.locator(".counter-upper .dispensing-reservation-title").textContent());

const patient = await signIn(browser, "patient@mock.test");
await patient.goto(`${base}/patient/pharmacy`);
await patient.waitForLoadState("networkidle");
await patient.getByLabel(/Amoxicillin 250 mg capsules quantity/).fill("3");
await patient.getByRole("button", { name: "Request reservation" }).click();
const receipt = patient.getByText(/Pharmacy returned reservation \d+, state reserved/);
await receipt.waitFor();
check("patient reservation request returns an owner-confirmed slip (mock write)", true, await receipt.textContent());
await patient.waitForFunction(() => document.querySelectorAll(".reservation-ticket").length >= 2, null, { timeout: 5000 }).catch(() => {});
const tickets = await patient.locator(".reservation-ticket").count();
check("reservation slip lists the new reservation alongside the existing one", tickets >= 2, `${tickets} active reservations`);
check("patient sees no dispensing controls", (await patient.getByRole("button", { name: /Dispense/ }).count()) === 0);

await browser.close();
writeFileSync(join(out, "interaction-results.json"), JSON.stringify({ base, checked_at: new Date().toISOString(), results }, null, 2) + "\n");
if (results.some((item) => !item.pass)) process.exitCode = 1;
