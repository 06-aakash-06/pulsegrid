// Keyboard pass against `npm run dev:mock`: tab order regions, visible focus, Escape on the search dialog (desktop) and the directory drawer (mobile).
// Usage: PLAYWRIGHT_CORE=<path to playwright-core> node keyboard-check.mjs [base-url]
import { createRequire } from "node:module";
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { subjects } from "./capture.mjs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_CORE ?? "playwright-core");
const base = process.argv[2] ?? "http://127.0.0.1:5173";
const out = dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch();
const results = [];
const pages = new Map();
async function pageFor(email) {
  if (pages.has(email)) return pages.get(email);
  const context = await browser.newContext({ viewport: { width: 1536, height: 1024 }, reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto(`${base}/login`);
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("mock-password");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  pages.set(email, page);
  return page;
}
const focusInfo = () => {
  const active = document.activeElement;
  if (!active || active === document.body) return null;
  const style = getComputedStyle(active);
  const visible = (style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0) || style.boxShadow !== "none";
  const region = active.closest(".skip-link") ? "skip" : active.closest(".hospital-header") ? "header" : active.closest(".workspace-sidebar") ? "directory" : active.closest("main") ? "main" : "other";
  return { region, visible, label: (active.getAttribute("aria-label") || active.textContent || active.tagName).trim().slice(0, 40) };
};
for (const subject of subjects) {
  const page = await pageFor(subject.email);
  await page.setViewportSize({ width: 1536, height: 1024 });
  await page.goto(`${base}${subject.route}`);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(400);
  await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
  await page.mouse.click(1, 1);
  const order = [];
  const missing = [];
  for (let index = 0; index < 45; index += 1) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate(focusInfo);
    if (!info) continue;
    if (order.at(-1) !== info.region) order.push(info.region);
    if (!info.visible) missing.push(info.label);
  }
  const expected = ["skip", "header", "directory", "main"];
  const sequence = order.filter((region, index) => order.indexOf(region) === index);
  const logical = expected.filter((region) => sequence.includes(region)).join(">") === sequence.filter((region) => expected.includes(region)).join(">");
  await page.keyboard.press(process.platform === "darwin" ? "Meta+k" : "Control+k");
  const searchOpen = await page.evaluate(() => !!document.querySelector("dialog.command-search[open]"));
  await page.keyboard.press("Escape");
  const searchClosed = await page.evaluate(() => !document.querySelector("dialog.command-search[open]"));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(200);
  const menu = page.getByRole("button", { name: "Open navigation menu" });
  await menu.focus();
  await page.keyboard.press("Enter");
  const drawerOpen = await page.evaluate(() => !!document.querySelector('[role="dialog"][aria-modal="true"].workspace-sidebar') && document.querySelector(".workspace-main")?.hasAttribute("inert"));
  await page.keyboard.press("Escape");
  await page.waitForTimeout(100);
  const drawerClosed = await page.evaluate(() => !document.querySelector('.workspace-sidebar[role="dialog"]') && document.activeElement?.classList.contains("menu-toggle"));
  const result = { subject: subject.name, route: subject.route, regionOrder: sequence, logical, focusWithoutIndicator: missing, searchEscape: searchOpen && searchClosed, drawerEscape: drawerOpen && drawerClosed };
  results.push(result);
  console.log(`${subject.name}\torder=${sequence.join(">")}\tlogical=${logical}\tno-indicator=${missing.length}\tsearchEsc=${result.searchEscape}\tdrawerEsc=${result.drawerEscape}`);
}
await browser.close();
writeFileSync(join(out, "keyboard-results.json"), JSON.stringify({ base, checked_at: new Date().toISOString(), results }, null, 2) + "\n");
