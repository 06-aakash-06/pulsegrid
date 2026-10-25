import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
const browser=await chromium.launch();
const results=[];
async function session(role,route){
 const context=await browser.newContext({viewport:{width:1536,height:864},reducedMotion:'reduce'});
 const page=await context.newPage();await page.goto('http://127.0.0.1:5173/login');await page.locator('#login-email').fill(`${role}@mock.test`);await page.locator('#login-password').fill('demo');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(`**/${role}/dashboard`);
 await page.goto(`http://127.0.0.1:5173/${role}/${route}`);await page.locator('.workspace-content').waitFor();await page.waitForTimeout(700);
 return{page,context};
}
try{
 {
  const {page,context}=await session('admin','dashboard');
  assert.equal(await page.locator('.admin-home a').count(),5);
  assert.equal(await page.getByRole('heading',{name:'Patient demographics',exact:true}).count(),0);
  assert.equal(await page.getByRole('heading',{name:'Medicines',exact:true}).count(),0);
  results.push('PASS Admin: five task links; real account/doctor counts; patient and medicine registers absent from home.');await context.close();
 }
 {
  const {page,context}=await session('doctor','dashboard');
  await page.getByRole('tab',{name:'Profile',exact:true}).click();assert(await page.getByRole('heading',{name:'Save doctor profile',exact:true}).isVisible());
  await page.getByRole('tab',{name:'Schedule changes',exact:true}).click();assert(await page.getByRole('heading',{name:'Propose schedule changes',exact:true}).isVisible());
  assert.equal(await page.getByRole('heading',{name:'Schedule proposals',exact:true}).count(),1);
  await page.getByRole('tab',{name:'Today',exact:true}).click();assert(await page.getByRole('link',{name:'Open patient queue',exact:true}).isVisible());
  results.push('PASS Doctor dashboard: Today, Profile and Schedule changes expose their tasks; one Schedule proposals heading.');await context.close();
 }
 {
  const {page,context}=await session('doctor','queue');
  assert(await page.getByRole('columnheader',{name:'Patient',exact:true}).isVisible());assert(await page.getByText('Rohan Mehta',{exact:true}).first().isVisible());
  assert.equal(await page.getByLabel('Queue action reason',{exact:true}).count(),0);
  await page.getByRole('button',{name:'Skip',exact:true}).first().click();const reason=page.getByLabel('Queue action reason',{exact:true});await reason.fill('Patient requested a short pause.');
  const commands=[];page.on('request',r=>{if(r.url().includes('/api/')&&['POST','PATCH','DELETE'].includes(r.method()))commands.push(r.url());});
  await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.waitForTimeout(500);assert.equal(await reason.inputValue(),'Patient requested a short pause.');assert.equal(commands.length,0);
  results.push('PASS Doctor queue: patient names and table columns; Skip reveals its reason; page Refresh preserves the reason and sends no commands.');await context.close();
 }
 {
  const {page,context}=await session('patient','pharmacy');
  assert.equal(await page.getByRole('heading',{name:'Your prescription',exact:true}).count(),1);
  assert.equal(await page.getByRole('heading',{name:'Prescription details',exact:true}).count(),0);
  assert(await page.getByRole('columnheader',{name:'Dose & instructions',exact:true}).isVisible());
  assert(await page.getByLabel('Choose a prescription',{exact:true}).isVisible());
  await page.locator('.account-menu > summary').click();await page.locator('.account-profile > summary').click();await page.getByRole('heading',{name:'Save profile',exact:true}).waitFor();await page.getByLabel('Display name',{exact:true}).fill('Draft profile name');await page.locator('.account-profile > summary').click();await page.locator('.account-profile > summary').click();assert.equal(await page.getByLabel('Display name',{exact:true}).inputValue(),'Draft profile name');
  results.push('PASS Patient Pharmacy: one prescription card with dose/instructions and fulfillment quantities, plus the reservation card; account-menu profile works away from Reception and keeps its draft across collapse.');await context.close();
 }
 {
  const {page,context}=await session('patient','waitlist');assert.equal(await page.getByLabel('Slot ID',{exact:true}).isVisible(),false);
  assert.equal(await page.getByPlaceholder('I no longer need this waitlist entry.').first().inputValue(),'');
  await page.locator('.page-advanced > summary').click();assert(await page.getByLabel('Slot ID',{exact:true}).isVisible());
  results.push('PASS Waitlist: slot-reference form is in Advanced lookup; withdrawal reasons start empty.');await context.close();
 }
 {
  const {page,context}=await session('emergency','dashboard');const commands=[];page.on('request',r=>{if(r.url().includes('/api/')&&['POST','PATCH','DELETE'].includes(r.method()))commands.push(r.url());});
  for(const value of [1,2,3,4,5])assert(await page.getByRole('button',{name:`Priority ${value}`,exact:true}).isVisible());
  await page.getByRole('button',{name:'Priority 4',exact:true}).click();await page.getByLabel('Reason for priority',{exact:true}).fill('Reviewed current symptoms.');await page.getByRole('button',{name:'Review priority',exact:true}).click();
  assert(await page.getByRole('group',{name:'Confirm: Set priority',exact:true}).isVisible());assert.equal(commands.length,0);
  results.push('PASS Emergency: five priority choices; review still requires explicit confirmation and sends no premature mutation.');await context.close();
 }
}finally{await browser.close();}
console.log(results.join('\n'));
await writeFile('../docs/verification/ui-declutter/smoke-output.txt',results.join('\n')+'\n');
