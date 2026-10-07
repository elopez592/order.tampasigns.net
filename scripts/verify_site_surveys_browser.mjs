// Exercise only an isolated local preview; never create test data on a live shop.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir,mkdtemp,readFile,writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
const require=createRequire(import.meta.url);
const {chromium}=require(require.resolve('playwright',{paths:[process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES]}));
const {expect}=require(require.resolve('playwright/test',{paths:[process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES]}));
const root='http://127.0.0.1:8765', output=process.env.SURVEY_PREVIEW_OUT;
assert(output&&process.env.SURVEY_PREVIEW_PHOTO&&process.env.SURVEY_PREVIEW_PYTHON&&process.env.SURVEY_PREVIEW_DATA, 'Provide scratch preview paths and a Python interpreter.');
const dataDir=await mkdtemp(process.env.SURVEY_PREVIEW_DATA+'-');
const server=spawn(process.env.SURVEY_PREVIEW_PYTHON,['run.py','--demo','--port','8765'],{cwd:process.cwd(),env:{...process.env,APP_ENV:'development',PUBLIC_URL:root,DATA_DIR:dataDir,ADMIN_EMAIL:'owner@example.test',ADMIN_PASSWORD:'LocalSurveyBrowserPassword2026'},stdio:['ignore','ignore','pipe']});
for(let i=0;i<100;i++){try{if((await fetch(root+'/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));if(i===99){server.kill();throw Error('Local preview server did not start.');}}
const launch={headless:true,args:['--no-sandbox']};if(process.env.SURVEY_CHROMIUM_EXECUTABLE)launch.executablePath=process.env.SURVEY_CHROMIUM_EXECUTABLE;
if(process.env.SURVEY_CHROMIUM_MODULE){const {default:binary}=await import(process.env.SURVEY_CHROMIUM_MODULE);launch.args=binary.args;launch.executablePath=process.env.SURVEY_CHROMIUM_EXECUTABLE||await binary.executablePath();}
let browser;
try{browser=await chromium.launch(launch);}catch(error){server.kill();throw error;}
const context=await browser.newContext({viewport:{width:1440,height:1050}});
await context.route('https://fonts.googleapis.com/**',r=>r.fulfill({status:200,contentType:'text/css',body:''}));
await context.route('https://fonts.gstatic.com/**',r=>r.abort());
const page=await context.newPage(), errors=[], checks=[];
page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
async function api(path,data) {
  const session=await (await page.request.get(root+'/api/session')).json();
  const response=data===undefined?await page.request.get(root+path):await page.request.post(root+path,{headers:{'X-CSRF-Token':session.csrf},data});
  assert(response.ok(), path+' '+await response.text());return response.json();
}
try {
  await mkdir(output,{recursive:true});await page.goto(root+'/staff#surveys');
  await page.locator('[name="email"]').fill('owner@example.test');
  await page.locator('[name="password"]').fill('LocalSurveyBrowserPassword2026');
  await page.getByRole('button',{name:'Sign in',exact:false}).click();
  await expect(page.getByRole('heading',{name:'Site Surveys',exact:true})).toBeVisible();
  await expect(page.getByText('Your site surveys will appear here.',{exact:true})).toBeVisible();
  checks.push('Direct survey section opens after staff sign-in and has a useful empty state');
  const cid=(await api('/api/staff/clients',{name:'Sample Customer',company:'QA Signs',email:'survey.preview@example.test'})).id;
  const estimate={contact_id:cid,title:'Storefront glass project',request_key:crypto.randomUUID(),items:[{product_id:4,width:'36',height:'72',quantity:1}]};
  const price=await api('/api/staff/estimates/calculate',estimate);
  const jid=(await api('/api/staff/estimates',{...estimate,fingerprint:price.fingerprint})).job_id;
  const saved=[];
  for(let i=0;i<13;i++){
    const s=await api('/api/staff/surveys',{client_key:crypto.randomUUID(),contact_id:cid,job_id:i===0?jid:null,
      title:i===0?'Storefront survey':i===1?'Door measurements':'Sample site visit '+i,
      address:'123 Sample Street, Tampa',site_contact:'Site manager · 813-555-0100',
      access_notes:'Install before the store opens.\nUse the side entrance.',surface_notes:'Glass is clean; top pane only.',removal_required:true,
      measurements:[{panel_key:'left',label:'Left window',width:'3',height:'6',unit:'ft',quantity:1,product_id:4,notes:'Keep the decal below the frame.'},{panel_key:'door',label:'Door top glass',width:'24',height:'30',unit:'in',quantity:1}]});
    saved.push(s);
  }
  await api(`/api/staff/surveys/${saved[1].id}/action`,{action:'submit',version:saved[1].version});
  const csrf=(await api('/api/session')).csrf;
  for(const [key,panel_key,name] of [['panel','left','left-window.png'],['general','','building.png']]){
    const r=await page.request.post(root+`/api/staff/surveys/${saved[0].id}/files`,{headers:{'X-CSRF-Token':csrf},multipart:{client_key:key,panel_key,file:{name,mimeType:'image/png',buffer:await readFile(process.env.SURVEY_PREVIEW_PHOTO)}}});assert(r.ok(),await r.text());
  }
  const pdf=await page.request.post(root+`/api/staff/surveys/${saved[0].id}/files`,{headers:{'X-CSRF-Token':csrf},multipart:{client_key:'plan',file:{name:'site-plan.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\n%%EOF')}}});assert(pdf.ok());
  await page.reload();await expect(page.locator('.survey-card')).toHaveCount(12);
  await expect(page.getByText('13 surveys',{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Next',exact:true}).click();await expect(page.locator('.survey-card')).toHaveCount(1);
  await page.getByRole('link',{name:'Previous',exact:true}).click();await expect(page.locator('.survey-card')).toHaveCount(12);
  checks.push('Saved surveys include standalone visits and paginate without losing records');
  await page.locator('select[name="status"]').selectOption('submitted');await page.getByRole('button',{name:'Search',exact:true}).click();
  await expect(page.locator('.survey-card')).toHaveCount(1);await expect(page.locator('.survey-card')).toContainText('Door measurements');
  await page.locator('select[name="status"]').selectOption('');await page.locator('input[name="q"]').fill('storefront');await page.getByRole('button',{name:'Search',exact:true}).click();
  await expect(page.locator('.survey-card')).toHaveCount(1);
  await expect(page.locator('.survey-card')).toContainText('Storefront survey');
  await page.waitForFunction(()=>document.querySelector('.survey-cover img')?.naturalWidth>0);
  assert(await page.evaluate(()=>{const cover=document.querySelector('.survey-cover').getBoundingClientRect(),image=document.querySelector('.survey-cover img').getBoundingClientRect();return image.bottom<=cover.bottom+1;}),'Preview must stay inside its card image area');
  await page.screenshot({path:output+'/site-surveys-desktop.png',fullPage:true});
  checks.push('Search and status filters select the intended survey');
  await page.getByRole('link',{name:'View survey',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Storefront survey',exact:true})).toBeVisible();
  await expect(page.locator('.page-heading')).toContainText('QA Signs');
  await expect(page.locator('.survey-measurements')).toContainText('3 × 6 ft');
  await expect(page.locator('.survey-measurements')).toContainText('36.0000 × 72.0000 in');
  await expect(page.locator('.survey-measurements')).toContainText('Door top glass');
  await expect(page.locator('.survey-notes')).toContainText('Use the side entrance.');
  await expect(page.locator('.survey-photo-grid figure')).toHaveCount(2);
  await expect(page.locator('.survey-document')).toContainText('site-plan.pdf');
  await page.waitForFunction(()=>[...document.querySelectorAll('.survey-photo img')].every(img=>img.complete&&img.naturalWidth>0));
  await page.screenshot({path:output+'/site-survey-detail-desktop.png',fullPage:true});
  await page.locator('.survey-photo-grid [data-action="survey-photo"]').first().click();
  await expect(page.locator('#modal')).toBeVisible();
  await expect(page.locator('#modal')).toContainText('1 / 2');
  await page.getByRole('button',{name:'Next',exact:true}).click();await expect(page.locator('#modal')).toContainText('2 / 2');
  await expect(page.getByRole('button',{name:'Next',exact:true})).toBeDisabled();
  const file=await page.getByRole('link',{name:'Download photo',exact:true}).getAttribute('href');
  const response=await page.request.get(root+file);assert(response.ok()&&response.headers()['content-disposition'].startsWith('attachment;'));
  await page.screenshot({path:output+'/site-survey-photo-viewer.png'});
  await page.getByRole('button',{name:'Close dialog',exact:true}).click();
  checks.push('Panel photos, general photos and PDFs open correctly; full photos can be downloaded');
  await page.getByRole('button',{name:'Open client',exact:true}).click();await expect(page.locator('#modal')).toContainText('QA Signs');await page.getByRole('button',{name:'Close dialog',exact:true}).click();
  await page.locator('.page-heading').getByRole('link',{name:/Open JOB-/}).click();await expect(page.getByRole('heading',{name:'Storefront glass project',exact:true})).toBeVisible();
  await page.getByRole('link',{name:'View saved site surveys & photos',exact:false}).click();await expect(page.locator('.survey-card')).toHaveCount(1);
  checks.push('Client and job links work, and the job returns to its own saved surveys');
  await page.setViewportSize({width:390,height:844});await page.getByRole('link',{name:'View survey',exact:true}).click();
  await expect(page.locator('.survey-photo-grid figure')).toHaveCount(2);await page.screenshot({path:output+'/site-survey-detail-mobile.png',fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Detail should fit a narrow screen');
  await page.locator('.survey-photo-grid [data-action="survey-photo"]').first().click();await expect(page.locator('#modal')).toBeVisible();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Photo viewer should fit a narrow screen');
  await page.getByRole('button',{name:'Close dialog',exact:true}).click();
  await page.goto(root+'/staff#surveys');await expect(page.locator('.survey-card')).toHaveCount(12);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'List should fit a narrow screen');
  await page.screenshot({path:output+'/site-surveys-mobile.png',fullPage:true});
  checks.push('List, measurements and photo viewer fit a 390px screen');
  const visitor=await browser.newContext();assert.equal((await visitor.request.get(root+file)).status(),401);
  assert.deepEqual(errors,[]);checks.push('No browser script errors; signed-out visitors cannot download survey photos');
  await writeFile(output+'/site-surveys-browser-checks.json',JSON.stringify({checks,errors},null,2));console.log(JSON.stringify({checks,errors},null,2));
} finally {await browser.close();server.kill();}
