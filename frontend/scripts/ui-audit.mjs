import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import { existsSync } from 'node:fs';
import { mkdir, writeFile, readdir } from 'node:fs/promises';
import { resolve } from 'node:path';

const base = process.env.UI_AUDIT_URL || 'http://127.0.0.1:5173';
const out = resolve(process.env.UI_AUDIT_OUTPUT || '../docs/verification/ui-declutter');
await mkdir(`${out}/after`, { recursive: true });
// Prefer preinstalled Linux Chromium, otherwise use Playwright's managed browser.
async function chromiumPath(root) {
 if (!existsSync(root)) return undefined;
 for (const entry of await readdir(root, { withFileTypes: true })) {
  const path = `${root}/${entry.name}`;
  if (entry.isDirectory()) { const found = await chromiumPath(path); if (found) return found; }
  else if (['chrome', 'chromium', 'chrome-headless-shell'].includes(entry.name)) return path;
 }
}
const browser = await chromium.launch({ headless: true, executablePath: await chromiumPath('/opt/pw-browsers') });
const sizes = [[1536,864],[1280,800],[390,844]];
const roles = ['patient','receptionist','doctor','pharmacist','billing','emergency','admin','ops'];
const report = { base, pages: [], regressions: [], failures: [] };
const only = process.env.UI_AUDIT_ROLES?.split(',');
const selectedSizes = process.env.UI_AUDIT_WIDTH ? sizes.filter(([w])=>w===Number(process.env.UI_AUDIT_WIDTH)) : sizes;
const inspectLayout = () => {
     const errors=[];
     const describe = e => `${e.tagName.toLowerCase()}.${String(e.className).split(' ').slice(0,2).join('.')} ${(e.textContent||'').trim().slice(0,65)}`;
     const visible = e => {
      const s=getComputedStyle(e),r=e.getBoundingClientRect();
      return s.visibility!=='hidden' && s.display!=='none' && r.width>0 && r.height>0 && !e.closest('[aria-hidden="true"],.sr-only,details:not([open]) > :not(summary)');
     };
     const clipped = (r,e) => {
      for(let a=e.parentElement;a;a=a.parentElement) {
       const s=getComputedStyle(a),b=a.getBoundingClientRect();
       if (/(hidden|auto|scroll|clip)/.test(s.overflowX+s.overflowY) && (r.bottom<b.top || r.top>b.bottom || r.right<b.left || r.left>b.right)) return true;
      } return false;
     };
     if(document.documentElement.scrollWidth>innerWidth+1) errors.push(`horizontal-scroll: ${document.documentElement.scrollWidth}/${innerWidth}`);
     const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
     while(walker.nextNode()) {
      const node=walker.currentNode,e=node.parentElement;
      if(!node.textContent.trim() || !visible(e) || ['SCRIPT','STYLE','OPTION'].includes(e.tagName)) continue;
      const range=document.createRange();range.selectNodeContents(node);
      const rects=[...range.getClientRects()];
      if(!rects.length || rects.every(r=>clipped(r,e)))continue;
      const style=getComputedStyle(e);
      if(parseFloat(style.fontSize)<12) errors.push(`small-text: ${describe(e)} ${style.fontSize}`);
      let box=e;
      while(box && box!==document.body) {
       const s=getComputedStyle(box);
       if((parseFloat(s.borderTopWidth)>0 && s.borderTopStyle!=='none') || (s.backgroundColor!=='rgba(0, 0, 0, 0)' && s.backgroundColor!=='transparent'))break;
       box=box.parentElement;
      }
      if(!box || box===document.body)continue;
      const b=box.getBoundingClientRect();
      // Ellipsis and local scrollers intentionally clip long labels at their own boundaries.
      let clipsText=false;
      for(let a=e;a&&a!==box.parentElement;a=a.parentElement) {
       const s=getComputedStyle(a);
       if(/hidden|auto|scroll|clip/.test(s.overflowX+s.overflowY)) {clipsText=true;break;}
      }
      if(!clipsText && rects.some(r=>r.left<b.left-2 || r.right>b.right+2 || r.top<b.top-2 || r.bottom>b.bottom+2))errors.push(`text-escape: ${describe(e)} outside ${describe(box)}`);
     }
     const paintedRect = e => {
      const r=e.getBoundingClientRect();let left=r.left,right=r.right,top=r.top,bottom=r.bottom;
      for(let a=e.parentElement;a;a=a.parentElement) {
       const s=getComputedStyle(a),b=a.getBoundingClientRect();
       if(/hidden|auto|scroll|clip/.test(s.overflowX)){left=Math.max(left,b.left);right=Math.min(right,b.right);}
       if(/hidden|auto|scroll|clip/.test(s.overflowY)){top=Math.max(top,b.top);bottom=Math.min(bottom,b.bottom);}
      } return {left,right,top,bottom};
     };
     const elements=[...document.querySelectorAll('button,a,input,select,textarea,.hospital-panel,.patient-workflow__panel,.ops-panel,.dossier-sheet,.dossier-timeline,.dossier-side,.page-header')].filter(e=>visible(e) && !e.matches('.sidebar-scrim'));
     for(let i=0;i<elements.length;i++)for(let j=i+1;j<elements.length;j++) {
      const a=elements[i],b=elements[j];if(a.contains(b)||b.contains(a))continue;
      // Sticky footers float over the content they summarise; covered-control checks still apply.
      if(a.closest('[data-sticky-footer]')||b.closest('[data-sticky-footer]'))continue;
      const ar=paintedRect(a),br=paintedRect(b);
      if(clipped(ar,a)||clipped(br,b))continue;
      if(Math.min(ar.right,br.right)-Math.max(ar.left,br.left)>4 && Math.min(ar.bottom,br.bottom)-Math.max(ar.top,br.top)>4)errors.push(`overlap: ${describe(a)} / ${describe(b)}`);
     }
     return [...new Set(errors)];
};
try {
 for (const role of roles.filter(r=>!only || only.includes(r))) {
  for (const [width,height] of selectedSizes) {
   const context = await browser.newContext({ viewport:{width,height}, reducedMotion:'reduce' });
   const page = await context.newPage();
   await page.goto(`${base}/login`);
   const demo = page.locator('.auth-demo__roles button').filter({hasText:new RegExp(`^${role==='ops'?'Ops':role[0].toUpperCase()+role.slice(1)}$`)});
   await demo.click();
   if (await page.locator('#login-email').inputValue()!==`${role}@pulsegrid.test` || await page.locator('#login-password').inputValue()!=='demo') throw Error(`Demo autofill failed: ${role}`);
   await page.getByRole('button',{name:'Sign in',exact:true}).click();
   await page.waitForURL(`**/${role}/dashboard`);
   await page.locator('.workspace-nav a').first().waitFor({state:'attached'});
   const routes = await page.locator('.workspace-nav a').evaluateAll(links=>links.map(a=>a.getAttribute('href')));
   for (const route of routes.filter(r=>!process.env.UI_AUDIT_ROUTES || process.env.UI_AUDIT_ROUTES.split(',').includes(r))) {
    await page.goto(`${base}${route}`);
    await page.locator('.workspace-content').waitFor();
    await page.waitForTimeout(500);
    await page.evaluate(()=>document.fonts.ready);
    const failures = await page.evaluate(inspectLayout);
    const content = await page.evaluate(() => {
     const hits=[], justified=[];
     const pattern=/\b\d{4,}\b|…\d{3,}|revision|owner|version|projected|reconcil|IANA|Positive decimal|MOCK-/gi;
     const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&!e.closest('[hidden],[aria-hidden="true"],.sr-only,details:not([open]) > :not(summary)');};
     const walker=document.createTreeWalker(document.querySelector('.workspace-content'),NodeFilter.SHOW_TEXT);
     while(walker.nextNode()) {
      const n=walker.currentNode,e=n.parentElement,t=n.textContent.trim();
      if(!t||!visible(e)||['SCRIPT','STYLE','OPTION'].includes(e.tagName))continue;
      const range=document.createRange();range.selectNodeContents(n);if(!range.getBoundingClientRect().width)continue;
      if([...function*(a){for(;a;a=a.parentElement)yield a;}(e)].some(a=>a.matches('details')&&/Details|Advanced/i.test(a.querySelector(':scope > summary')?.textContent||'')))continue;
      for(const m of t.matchAll(pattern)) {
       const value=m[0];
       const isYear=/^\d{4}$/.test(value)&&Number(value)>=1900&&Number(value)<=2100&&(e.closest('time[datetime]')||/\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/.test(t)||/^\d{4}-\d{2}-\d{2}/.test(t)||e.closest('.month-calendar,.schedule-title,.calendar-strip'));
       const isDose=/^\d+$/.test(value)&&new RegExp(value+'\\s*(IU|mg|mcg|mL)\\b','i').test(t);
       if(isYear||isDose||e.closest('[role="alert"]'))justified.push({text:t,reason:isYear?'Calendar date':isDose?'Medicine strength':'Required error or stale-state message'});
       else hits.push(`developer-text: ${e.tagName.toLowerCase()} ${t.slice(0,220)}`);
      }
     }
     const refresh=[...document.querySelectorAll('.workspace-content button')].filter(e=>visible(e)&&/\bRefresh(?:ing)?\b/i.test(e.textContent));
     if(refresh.length>1)hits.push(`refresh-count: ${refresh.length}`);
     return {hits:[...new Set(hits)],justified,refreshCount:refresh.length};
    });
    failures.push(...content.hits);
    if(!process.env.UI_AUDIT_TEXT_ONLY) {
    // Test hit targets in their actual scroll position, including controls below the fold.
    const controls=page.locator('button,a,input,select,textarea');
    for(let i=0;i<await controls.count();i++) {
     const control=controls.nth(i);
     if(!await control.isVisible())continue;
     const issue=await control.evaluate(e=>{
      if(e.closest('.skip-link,[aria-hidden="true"],details:not([open]) > :not(summary)'))return null;
      e.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
      const r=e.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
      if(x<0||x>=innerWidth||y<0||y>=innerHeight)return `offscreen-control: ${e.outerHTML.slice(0,160)}`;
      const hit=document.elementFromPoint(x,y);
      return hit && (e===hit||e.contains(hit)) ? null : `covered: ${e.outerHTML.slice(0,140)} by ${hit?.outerHTML.slice(0,140)}`;
     });
     if(issue)failures.push(issue);
    }
    // Sample the actual backdrop at three document heights. Fixed image coverage
    // must remain present and identical as content moves over it.
    const backgrounds=[];
    const max=await page.evaluate(()=>Math.max(0,document.documentElement.scrollHeight-innerHeight));
    for(const y of [0,max/2,max]) {
     await page.evaluate(y=>scrollTo(0,y),y);
     backgrounds.push(await page.locator('.workspace-shell').evaluate(e=>{
      const s=getComputedStyle(e,'::before');return {position:s.position,inset:s.inset,image:s.backgroundImage,size:s.backgroundSize};
     }));
    }
    const hide = await page.addStyleTag({content:'.workspace-content,.workspace-content *,.workspace-sidebar,.workspace-sidebar *,.hospital-header,.hospital-header *,.skip-link {visibility:hidden!important}'});
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    const patches=[];
    for(const y of [0,max/2,max]) {
     await page.evaluate(y=>scrollTo(0,y),y);
     await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
     const raster=await page.screenshot();
     if(process.env.UI_AUDIT_DEBUG) await writeFile(`/tmp/pg-audit-${patches.length}.png`,raster);
     const png=PNG.sync.read(raster);
     const patch=[];
     for(let py=Math.floor(height*.3);py<height*.7;py+=13)for(let px=Math.floor(width*.2);px<width*.8;px+=13){const i=(py*png.width+px)*4;patch.push([...png.data.subarray(i,i+3)].join(','));}
     patches.push(patch);
    }
    await hide.evaluate(e=>e.remove());
    if(patches.some(p=>new Set(p).size<8) || patches.some(p=>p.filter((c,i)=>c!==patches[0][i]).length>p.length*.01)) failures.push(`background-seam: raster samples differ or become flat (${patches.map(p=>new Set(p).size).join(',')}; differences ${patches.map(p=>p.filter((c,i)=>c!==patches[0][i]).length).join(',')})`);
    if(backgrounds.some(b=>b.position!=='fixed'||b.inset!=='0px'||!b.image.includes('url(')||!b.size.includes('cover')) || new Set(backgrounds.map(JSON.stringify)).size!==1)failures.push('background-seam: backdrop is not a continuous fixed cover image');
    await page.evaluate(()=>scrollTo(0,0));
    }
    if(route==='/patient/appointments') {
     for(const name of ['My Appointments','Book Appointment']) {
      const tab=page.getByRole('button',{name,exact:true});
      if(await tab.count()) {
       await tab.scrollIntoViewIfNeeded();const box=await tab.boundingBox();
       await page.mouse.click(box.x+box.width/2,box.y+box.height/2);
       await page.waitForTimeout(100);
       if(await tab.getAttribute('aria-pressed')!=='true')failures.push(`mouse-tab: ${name}`);
      }
     }
     report.regressions.push(`${width}: appointment mouse hit boxes`);
    }
    await page.evaluate(()=>scrollTo(0,0));
    await page.locator('.workspace-nav').evaluate(nav=>{const active=nav.querySelector('[aria-current=page]');nav.scrollTop=active ? Math.max(0,active.offsetTop-nav.offsetTop-nav.clientHeight/2) : 0;});
    await page.screenshot({path:`${out}/after/${route.slice(1).replaceAll('/','-')}-${width}.png`,fullPage:true});
    if(width<900) {
     await page.getByRole('button',{name:'Open navigation menu',exact:true}).click();
     failures.push(...(await page.evaluate(inspectLayout)).map(f=>`drawer: ${f}`));
     const links=page.locator('.workspace-nav a');
     for(let i=0;i<await links.count();i++) {
      const link=links.nth(i);await link.scrollIntoViewIfNeeded();
      const hit=await link.evaluate(e=>{const r=e.getBoundingClientRect(),p=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return p===e||e.contains(p);});
      if(!hit)failures.push(`drawer: covered navigation row ${i+1}`);
     }
     await page.screenshot({path:`${out}/after/${route.slice(1).replaceAll('/','-')}-${width}-drawer.png`});
     await page.locator('.menu-toggle').click();
    }
    const record={role,route,width,height,refreshCount:content.refreshCount,justified:content.justified,failures:[...new Set(failures)]};report.pages.push(record);
    if(record.failures.length)report.failures.push(record);
    await writeFile(`${out}/audit-report.json`,JSON.stringify(report,null,2)+'\n');
    console.log(`${record.failures.length?'FAIL':'PASS'} ${width} ${route} (${record.failures.length})`);
    for(const failure of record.failures)console.log(`  ${failure}`);
   }
   if(width<900)await page.getByRole('button',{name:'Open navigation menu',exact:true}).click();
   await page.locator('.sign-out-button').click();await page.waitForURL('**/login');await page.reload();await page.waitForURL('**/login');
   await page.locator('#login-email').waitFor();
   if(await page.locator('#login-email').count()!==1)throw Error(`Sign out restoration failure: ${role}`);
   report.regressions.push(`${role}/${width}: demo autofill and sign out survive reload`);
   await context.close();
  }
 }
} finally {
 await browser.close();
 await writeFile(`${out}/audit-report.json`,JSON.stringify(report,null,2)+'\n');
 console.log(`Audited ${report.pages.length} route/viewports; ${report.failures.length} failed.`);
}
if(report.failures.length)process.exitCode=1;
