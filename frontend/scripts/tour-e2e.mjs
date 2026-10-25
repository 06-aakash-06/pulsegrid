import { chromium } from 'playwright';
import { existsSync } from 'node:fs';
import { mkdir, readdir, rm } from 'node:fs/promises';
import { resolve } from 'node:path';

// Drives every role's Simulation Mode walkthrough by clicking only what the guide highlights.
const base = process.env.TOUR_E2E_URL || 'http://127.0.0.1:5173';
const out = resolve(process.env.TOUR_E2E_OUTPUT || '../docs/verification/simulation');
const sizes = [[1536, 864], [390, 844]].filter(([w]) => !process.env.TOUR_E2E_WIDTH || w === Number(process.env.TOUR_E2E_WIDTH));
const tours = (process.env.TOUR_E2E_ROLES || 'patient,receptionist,doctor,pharmacist,billing,emergency,admin,ops').split(',');

async function chromiumPath(root) {
  if (!existsSync(root)) return undefined;
  for (const entry of await readdir(root, { withFileTypes: true })) {
    const path = `${root}/${entry.name}`;
    if (entry.isDirectory()) { const found = await chromiumPath(path); if (found) return found; }
    else if (['chrome', 'chromium', 'chrome-headless-shell'].includes(entry.name)) return path;
  }
}

const browser = await chromium.launch({ headless: true, executablePath: await chromiumPath('/opt/pw-browsers') });
const results = [];
let failed = false;
try {
  for (const tour of tours) {
    for (const [width, height] of sizes) {
      const label = `${tour} ${width}`;
      const dir = `${out}/${tour}`;
      await mkdir(dir, { recursive: true });
      for (const file of await readdir(dir)) if (file.endsWith(`-${width}.png`)) await rm(`${dir}/${file}`);
      const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', (error) => errors.push(error.message));
      try {
        const reset = await page.request.post(`${base}/__mock/reset`);
        if (reset.status() !== 204) throw Error(`could not reset the sample hospital (${reset.status()}); run against npm run dev:mock`);
        await page.goto(`${base}/login`);
        await page.locator(`[data-tour="quick-sign-in-${tour}"]`).click();
        await page.locator('[data-tour="sign-in-submit"]').click();
        await page.waitForURL(`**/${tour}/dashboard`);
        await page.locator('[data-tour="simulation-switch"]').click();
        await page.locator(`[data-tour="simulation-tour-${tour}"]`).click();
        await page.locator('[data-tour="simulation-start"]').click();
        let steps = 0;
        for (let guard = 0; guard < 80; guard++) {
          const card = page.locator('[data-simulation-card]');
          const summary = page.locator('[data-simulation-summary]');
          await card.or(summary).first().waitFor({ timeout: 15000 });
          if (await summary.count()) break;
          const number = Number(await card.getAttribute('data-sim-step'));
          const total = Number(await card.getAttribute('data-sim-total'));
          const target = await card.getAttribute('data-sim-target');
          const advance = await card.getAttribute('data-sim-advance');
          const fill = await card.getAttribute('data-sim-fill');
          const choose = await card.getAttribute('data-sim-choose');
          // Wait until the highlighted element is rendered, the ring has settled on it, and it stays clickable.
          const check = await page.waitForFunction((id) => {
            const element = [...document.querySelectorAll(`[data-tour="${id}"]`)].find((node) => { const r = node.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !node.closest('details:not([open]) > :not(summary), [hidden], [inert]'); });
            const ring = document.querySelector('.simulation-ring');
            const fail = (problem) => { window.__tourProblem = problem; window.__tourStable = 0; return false; };
            if (!element || !ring) return fail('never appeared');
            const r = element.getBoundingClientRect(), g = ring.getBoundingClientRect();
            if (Math.abs(r.left - 6 - g.left) > 2 || Math.abs(r.top - 6 - g.top) > 2) return fail('ring did not reach it');
            const x = r.left + r.width / 2, y = r.top + r.height / 2;
            if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return fail(`off-screen at ${Math.round(x)},${Math.round(y)}`);
            const hit = document.elementFromPoint(x, y);
            if (!hit || !(hit === element || element.contains(hit))) return fail(`covered by ${hit?.outerHTML.slice(0, 120)}`);
            window.__tourStable = (window.__tourStable || 0) + 1;
            return window.__tourStable >= 3 ? { problem: null } : false;
          }, target, { timeout: 15000, polling: 100 }).then((handle) => handle.jsonValue()).catch(async () => ({ problem: await page.evaluate(() => window.__tourProblem || 'never appeared') }));
          await page.screenshot({ path: `${dir}/step-${String(number).padStart(2, '0')}-${width}.png` });
          if (check.problem) throw Error(`step ${number} (${target}): target ${check.problem}`);
          const element = page.locator(`[data-tour="${target}"]:not(details:not([open]) > :not(summary) *):not(details:not([open]) > :not(summary))`).locator('visible=true').first();
          if (fill) {
            const field = (await element.evaluate((node) => node.matches('input,textarea'))) ? element : element.locator('input,textarea').first();
            await field.fill(fill);
          }
          if (choose) await element.selectOption(choose);
          if (advance === 'manual') await card.locator('[data-sim-next]').click();
          else if (!choose) {
            // Click where a person would: the centre of the highlighted element, once nothing covers it.
            let clicked = false;
            for (let attempt = 0; attempt < 20 && !clicked; attempt++) {
              const point = await element.evaluate((node) => {
                const r = node.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
                const hit = document.elementFromPoint(x, y);
                return hit && (hit === node || node.contains(hit)) ? { x, y } : null;
              });
              if (point) { await page.mouse.click(point.x, point.y); clicked = true; }
              else await page.waitForTimeout(150);
            }
            if (!clicked) throw Error(`step ${number} (${target}): target stayed covered`);
          }
          steps = number;
          await page.waitForFunction((previous) => {
            const card = document.querySelector('[data-simulation-card]');
            return document.querySelector('[data-simulation-summary]') || (card && Number(card.getAttribute('data-sim-step')) !== previous);
          }, number, { timeout: 15000 }).catch(() => { throw Error(`step ${number} (${target}) did not advance after ${advance}`); });
          if (number === total) continue;
        }
        if (!(await page.locator('[data-simulation-summary]').count())) throw Error('summary card never appeared');
        await page.screenshot({ path: `${dir}/summary-${width}.png` });
        if (errors.length) throw Error(`page errors: ${errors.join('; ')}`);
        results.push({ tour, width, steps });
        console.log(`PASS ${label}: ${steps} steps`);
      } catch (error) {
        await page.screenshot({ path: `${dir}/failure-${width}.png` }).catch(() => {});
        failed = true;
        results.push({ tour, width, error: error.message });
        console.log(`FAIL ${label}: ${error.message}`);
      } finally {
        await context.close();
      }
    }
  }
} finally {
  await browser.close();
}
if (failed) process.exitCode = 1;
