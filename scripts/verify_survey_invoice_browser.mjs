// Run only against a temporary local demo. Never send to production clients.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
const require=createRequire(import.meta.url);
const {chromium}=require(require.resolve('playwright',{paths:[process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES]}));
const {expect}=require(require.resolve('playwright/test',{paths:[process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES]}));
const root='http://127.0.0.1:8765';
assert(process.env.EMPLOYEE_PREVIEW_PYTHON&&process.env.EMPLOYEE_PREVIEW_SERVER&&process.env.EMPLOYEE_PREVIEW_PHOTO);
const server=spawn(process.env.EMPLOYEE_PREVIEW_PYTHON,[process.env.EMPLOYEE_PREVIEW_SERVER],{cwd:process.cwd(),env:{...process.env,PYTHONPATH:process.cwd()},stdio:['ignore','ignore','pipe']});
let logs='',browser;server.stderr.on('data',chunk=>logs=(logs+chunk).slice(-5000));
const checks=[],errors=[],output='docs/previews';
async function login(context,owner=false,mobile=false){
 const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(15000);
 await page.goto(root+(mobile?'/staff/app':'/staff'));
 await page.locator('[name="email"]').fill(owner?'owner@example.test':'crew@example.test');
 await page.locator('[name="password"]').fill(owner?'LocalFieldPreviewOwnerPassword2026':'LocalFieldPreviewStaffPassword2026');
 await page.getByRole('button',{name:/Sign in/}).click();
 await expect(page.locator('.bottom-nav, .sidebar')).toBeVisible();
 return page;
}
async function api(page,path,data){
 const session=await (await page.request.get(root+'/api/session')).json();
 const response=data===undefined?await page.request.get(root+path):await page.request.post(root+path,{headers:{'X-CSRF-Token':session.csrf},data});
 assert(response.ok(),path+' '+await response.text());return response.json();
}
async function createProject(page,client,title,items){
 const payload={contact_id:client,title,request_key:crypto.randomUUID(),items};
 const price=await api(page,'/api/staff/estimates/calculate',payload);
 return (await api(page,'/api/staff/estimates',{...payload,fingerprint:price.fingerprint})).job_id;
}
async function survey(page,client,job,label,width,height,unit='in'){
 return api(page,'/api/staff/surveys',{client_key:crypto.randomUUID(),contact_id:client,job_id:job,title:label+' survey',address:'123 Sample Street',surface_notes:'Glass in good condition.',measurements:[{panel_key:crypto.randomUUID(),label,width,height,unit,quantity:1,product_id:4,notes:'Checked during the sample site visit.'}]});
}
try{
 for(let i=0;i<100;i++){try{if((await fetch(root+'/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,150));if(i===99)throw Error(logs);}
 const launch={headless:true,args:['--no-sandbox']};if(process.env.EMPLOYEE_CHROMIUM_EXECUTABLE)launch.executablePath=process.env.EMPLOYEE_CHROMIUM_EXECUTABLE;
 browser=await chromium.launch(launch);await mkdir(output,{recursive:true});
 async function context(viewport,isMobile=false){const ctx=await browser.newContext({viewport,isMobile,hasTouch:isMobile});await ctx.route('https://fonts.googleapis.com/**',r=>r.fulfill({status:200,contentType:'text/css',body:''}));await ctx.route('https://fonts.gstatic.com/**',r=>r.abort());return ctx;}
 const deskContext=await context({width:1360,height:1000}),desktop=await login(deskContext,true);
 const client=(await api(desktop,'/api/staff/clients',{name:'Sample Site Client',email:'onsite.browser@example.test'})).id;
 const jid=await createProject(desktop,client,'On-site survey approval demo',[{product_id:4,width:'36',height:'72',quantity:1,description:'Left window'},{product_id:4,width:'36',height:'80',quantity:1,description:'Door'}]);
 const left=await survey(desktop,client,jid,'Left window','3','6','ft'),door=await survey(desktop,client,jid,'Door','36','80');
 await api(desktop,`/api/staff/surveys/${door.id}/action`,{action:'submit',version:door.version});
 const csrf=(await api(desktop,'/api/session')).csrf;
 const uploaded=await desktop.request.post(root+`/api/staff/surveys/${left.id}/files`,{headers:{'X-CSRF-Token':csrf},multipart:{client_key:'browser-review-photo',file:{name:'sample-panel.png',mimeType:'image/png',buffer:await (await import('node:fs/promises')).readFile(process.env.EMPLOYEE_PREVIEW_PHOTO)}}});assert(uploaded.ok());
 await desktop.goto(root+'/staff#job/'+jid);await desktop.getByRole('heading',{name:'On-site survey approval demo',exact:true}).waitFor();
 await desktop.getByRole('button',{name:'Record completed survey',exact:true}).click();
 const modal=desktop.locator('#modal');await expect(modal).toContainText('Left window survey');await expect(modal).toContainText('Door survey');
 await expect(modal.locator('img[alt="Survey photo"]')).toBeVisible();
 await expect(modal.locator('[data-review-survey]')).toHaveCount(2);
 await modal.locator('[name="note"]').fill('Reviewed both saved field surveys against the shown quote.');
 await modal.locator('[name="confirm"]').check();
 await modal.locator('[data-review-survey]').first().check();
 await modal.getByRole('button',{name:'Save completed survey',exact:true}).click();
 await expect(modal).toBeVisible();assert.equal((await api(desktop,`/api/staff/jobs/${jid}`)).site_survey.status,'requested');
 checks.push('Desktop shows saved measurements/photos and requires review of every survey');
 await modal.locator('[data-review-survey]').last().check();
 await modal.getByRole('button',{name:'Save completed survey',exact:true}).click();
 await expect(modal).not.toBeVisible();await expect(desktop.getByRole('button',{name:'Record completed survey',exact:true})).toHaveCount(0);
 assert.equal((await api(desktop,`/api/staff/jobs/${jid}`)).site_survey.status,'complete');
 await desktop.screenshot({path:output+'/Employee-App-Survey-Reviewed-Desktop.png'});
 checks.push('Owner completes draft and submitted field surveys directly from desktop');
 const phoneContext=await context({width:390,height:844},true),phone=await login(phoneContext,false,true);
 await phone.goto(root+'/staff/app#job/'+jid);await phone.getByRole('heading',{name:'On-site survey approval demo',exact:true}).waitFor();
 await phone.getByRole('button',{name:'Approve price & send invoice',exact:true}).click();
 const dialog=phone.locator('#employee-dialog');await expect(dialog).toContainText('Total · Tax included');
 await expect(dialog.locator('[name="recipient"]')).toHaveValue('onsite.browser@example.test');
 await dialog.locator('[name="customer_name"]').fill('Client approving at the site');await dialog.locator('[name="confirm"]').check();
 await phone.screenshot({path:output+'/Employee-App-On-Site-Invoice.png'});
 await dialog.getByRole('button',{name:'Record approval & send invoice',exact:true}).click();
 await expect(dialog).toContainText('Invoice saved. The email could not be sent');
 const link=await dialog.locator('[data-action="copy-invoice-link"]').getAttribute('data-value');
 const invoices=(await api(phone,`/api/staff/jobs/${jid}/invoices`)).invoices;assert.equal(invoices.length,1);assert.equal(invoices[0].status,'issued');
 const accepted=await api(phone,`/api/staff/jobs/${jid}`);assert.equal(accepted.accepted_name,'Client approving at the site');assert.equal(accepted.accepted_version,accepted.quote_version);assert.equal(accepted.proofs.length,0);assert.equal(accepted.totals.paid_cents,0);
 checks.push('Employee records on-site price approval and creates one issued invoice');
 const retry=phone.waitForResponse(r=>r.url().endsWith(`/api/staff/invoices/${invoices[0].id}/send`)&&r.request().method()==='POST');
 await dialog.getByRole('button',{name:'Retry invoice email',exact:true}).click();await retry;
 await expect(dialog).toContainText('Invoice saved. The email could not be sent');assert.equal((await api(phone,`/api/staff/jobs/${jid}/invoices`)).invoices.length,1);
 checks.push('Unavailable email is reported truthfully and retry preserves the invoice');
 const clientContext=await context({width:390,height:844},true),customer=await clientContext.newPage();customer.on('pageerror',e=>errors.push(e.message));
 await customer.goto(link);await customer.waitForURL(root+`/api/invoices/${invoices[0].id}`);await expect(customer.getByRole('heading',{name:'Invoice',exact:true})).toBeVisible();
 await expect(customer.locator('body')).toContainText(invoices[0].number);await expect(customer.getByRole('button',{name:'Print / Save PDF'})).toBeVisible();
 await customer.screenshot({path:output+'/Employee-App-Client-Invoice.png'});
 await customer.getByRole('link',{name:'View order & payment'}).click();await expect(customer.getByRole('link',{name:new RegExp('View invoice '+invoices[0].number)})).toBeVisible();
 await expect(customer.getByRole('button',{name:'Review & accept quote',exact:true})).toHaveCount(0);
 checks.push('Private emailed link opens the invoice; portal retains price acceptance and invoice access');
 const ownerContext=await context({width:390,height:844},true),ownerPhone=await login(ownerContext,true,true);
 const second=await createProject(ownerPhone,client,'Mobile owner survey review',[{product_id:4,width:'48',height:'24',quantity:1}]);
 await survey(ownerPhone,client,second,'Entry sign','48','24');
 await ownerPhone.goto(root+'/staff/app#job/'+second);await ownerPhone.getByRole('heading',{name:'Mobile owner survey review',exact:true}).waitFor();
 await ownerPhone.getByRole('button',{name:'Review & complete survey',exact:true}).click();
 const ownerDialog=ownerPhone.locator('#employee-dialog');await ownerDialog.locator('[data-review-survey]').check();await ownerDialog.locator('[name="note"]').fill('Reviewed the saved entry sign measurement.');await ownerDialog.locator('[name="confirm"]').check();
 await ownerPhone.screenshot({path:output+'/Employee-App-Survey-Review-Mobile.png'});
 await ownerDialog.getByRole('button',{name:'Save completed survey',exact:true}).click();await expect(ownerDialog).not.toBeVisible();
 assert.equal((await api(ownerPhone,`/api/staff/jobs/${second}`)).site_survey.status,'complete');checks.push('Owner reviews and completes saved survey from mobile project');
 await api(ownerPhone,`/api/staff/jobs/${second}/quote`,{version:1,charges_verified:false,deposit_percent:'50',shipping:'0',tax:'0'});
 await ownerPhone.reload();await ownerPhone.getByRole('heading',{name:'Mobile owner survey review',exact:true}).waitFor();await ownerPhone.getByRole('button',{name:'Approve price & send invoice',exact:true}).click();
 await expect(ownerDialog.locator('[name="charges_reviewed"]')).toBeVisible();await ownerDialog.locator('[name="charges_reviewed"]').check();await ownerDialog.locator('[name="confirm"]').check();
 await ownerDialog.getByRole('button',{name:'Record approval & send invoice',exact:true}).click();await expect(ownerDialog).toContainText('Invoice saved.');assert((await api(ownerPhone,`/api/staff/jobs/${second}`)).charges_verified);
 checks.push('Owner can explicitly review displayed charges before on-site invoicing');
 await ownerPhone.getByRole('button',{name:'Close dialog',exact:true}).click().catch(()=>ownerDialog.evaluate(n=>n.close()));
 for(const viewport of [{width:360,height:740},{width:844,height:390}]){await phone.setViewportSize(viewport);await dialog.evaluate(n=>n.close());await phone.goto(root+'/staff/app#job/'+jid);await phone.getByRole('heading',{name:'On-site survey approval demo',exact:true}).waitFor();await phone.getByRole('button',{name:'Send client invoice',exact:true}).click();assert(await phone.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));assert(await dialog.evaluate(n=>n.scrollWidth<=n.clientWidth));}
 assert.deepEqual(errors,[]);await writeFile(output+'/survey-invoice-browser-checks.json',JSON.stringify({checks,errors,productionWrites:false,viewports:[{width:1360,height:1000},{width:390,height:844},{width:360,height:740},{width:844,height:390}]},null,2));
 console.log(JSON.stringify({passed:true,checks:checks.length,errors,productionWrites:false}));
}finally{if(browser)await browser.close();server.kill('SIGTERM');}
