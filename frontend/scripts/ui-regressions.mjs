import { chromium } from 'playwright';
import { readFile, stat, writeFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
const browser=await chromium.launch();
const base='http://127.0.0.1:5173';
const result=[];
try {
 for(const build of ['dev:mock','VITE_DEMO_MOCK']) {
  const context=await browser.newContext();const page=await context.newPage();
  if(build==='VITE_DEMO_MOCK') {
   const root=resolve('dist-demo');
   await page.route(`${base}/**`,async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.startsWith('/api/'))return route.continue();
    let file=resolve(root,`.${path}`);
    if(!file.startsWith(root+'/'))file=resolve(root,'index.html');
    try {if(!(await stat(file)).isFile())file=resolve(root,'index.html');}catch{file=resolve(root,'index.html');}
    const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.webp':'image/webp','.woff2':'font/woff2','.svg':'image/svg+xml'};
    await route.fulfill({body:await readFile(file),contentType:types[extname(file)]||'application/octet-stream'});
   });
  }
  await page.goto(`${base}/login`);await page.locator('#login-email').waitFor();
  for(const role of ['Patient','Receptionist','Doctor','Pharmacist','Billing','Emergency','Admin','Ops']) {
   await page.getByRole('button',{name:role,exact:true}).click();
   if(await page.locator('#login-email').inputValue()!==`${role.toLowerCase()}@mock.test` || await page.locator('#login-password').inputValue()!=='demo')throw Error(`${build}: ${role} autofill`);
  }
  await page.getByRole('button',{name:'Patient',exact:true}).click();await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL('**/patient/dashboard');await page.locator('.sign-out-button').waitFor();
  await page.locator('.sign-out-button').click();await page.waitForURL('**/login');await page.reload();await page.locator('#login-email').waitFor();
  const saved=await page.evaluate(()=>localStorage.getItem('pulsegrid_mock_session'));
  if(saved)throw Error(`${build}: persisted session survived sign out`);
  result.push(`PASS ${build}: all eight demo buttons fill both fields; sign out survives immediate reload`);
  await context.close();
 }
}finally{await browser.close();}
console.log(result.join('\n'));
await writeFile('../docs/verification/ui-cleanup/regression-output.txt',result.join('\n')+'\n');
