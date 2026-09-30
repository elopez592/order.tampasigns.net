// Run only against an isolated local server with FakeGateway and demo accounts.
import {createRequire} from 'node:module';
import {mkdir,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(require.resolve('playwright',{paths:[process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES]}));
const root=process.env.PREVIEW_ROOT||'http://127.0.0.1:8765';
assert.match(root,/^http:\/\/(127\.0\.0\.1|localhost):\d+$/,'Use a local demo server only.');
const output=process.env.PREVIEW_OUTPUT||join(tmpdir(),'signshop-client-rewards-review');
const artwork=process.env.PREVIEW_ARTWORK||output+'/preview-artwork.png';
const previewEmail=process.env.PREVIEW_CLIENT_EMAIL||`preview.client.${Date.now()}@example.test`;
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const errors=[];
async function pageFor(){
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.route('https://fonts.googleapis.com/**',route=>route.fulfill({status:200,contentType:'text/css',body:''}));
  await context.route('https://fonts.gstatic.com/**',route=>route.abort());
  await context.route('https://checkout.stripe.com/**',route=>route.fulfill({status:200,contentType:'text/html',body:'<h1>Fake payment checkout</h1>'}));
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));return page;
}
async function waitText(page,text){await page.getByText(text,{exact:false}).first().waitFor();}
let customer,owner;
try{
  customer=await pageFor();owner=await pageFor();
  await customer.goto(root+'/account');
  const register=customer.locator('form[data-form="customer-register"]');
  await register.locator('[name="name"]').fill('Preview Client');
  await register.locator('[name="email"]').fill(previewEmail);
  await register.locator('[name="password"]').fill('LocalPreviewClientPassword2026');
  await register.getByRole('button',{name:'Create account',exact:true}).click();
  await waitText(customer,'Your next project starts');
  await customer.getByRole('link',{name:'Terms',exact:true}).waitFor();

  await owner.goto(root+'/staff');
  const login=owner.locator('form[data-form="login"]');
  await login.locator('[name="email"]').fill('owner@example.test');
  await login.locator('[name="password"]').fill('LocalPreviewOwnerPassword2026');
  await login.getByRole('button',{name:/Sign in/}).click();
  await owner.getByRole('link',{name:'Client rewards',exact:true}).click();
  const row=owner.locator('tr').filter({hasText:previewEmail});
  await row.getByRole('button',{name:'Adjust / history'}).click();
  const adjust=owner.locator('form[data-form="rewards-adjust"]');
  await adjust.locator('[name="credit"]').fill('50');
  await adjust.locator('[name="points"]').fill('1000');
  await adjust.locator('[name="reason"]').fill('Thank you for your repeat business · demo credit');
  await adjust.getByRole('button',{name:'Save adjustment'}).click();
  await owner.getByText('$50.00',{exact:true}).first().waitFor();
  await owner.locator('#modal [data-action="close"]').first().click();
  await owner.reload();
  await owner.locator('tr').filter({hasText:previewEmail}).getByText('$50.00',{exact:true}).waitFor();
  await owner.screenshot({path:output+'/Owner-Client-Rewards.png',fullPage:true});

  await customer.goto(root+'/products/die-cut-stickers');
  await customer.locator('#calculator [name="width"]').fill('1');
  await customer.locator('#calculator [name="height"]').fill('1');
  await customer.locator('#calculator [name="quantity"]').fill('50');
  await customer.locator('#calculator [name="quantity"]').press('Tab');
  await customer.getByText('$36.00',{exact:true}).first().waitFor();
  await customer.locator('#continue-btn').click();
  await customer.getByRole('link',{name:'View project',exact:true}).click();
  await customer.locator('[data-action="project-checkout"]').click();
  const checkout=customer.locator('form[data-form="public-order"]');
  await checkout.locator('[name="title"]').fill('Repeat sticker order');
  await checkout.locator('[name="artwork"]').setInputFiles(artwork);
  await customer.locator('#checkout-preview-review img').first().waitFor();
  assert.equal(await checkout.locator('[name="approve_uploads"]').count(),0);
  await checkout.locator('[name="reward_credit"]').fill('5');
  await checkout.locator('[name="reward_points"]').fill('100');
  await checkout.locator('[name="confirm"]').check();
  await customer.locator('#checkout-preview-review').screenshot({path:output+'/Upload-Proof-Checkout.png'});
  await customer.setViewportSize({width:390,height:844});
  await customer.locator('#checkout-preview-review').screenshot({path:output+'/Upload-Proof-Mobile.png'});
  assert.equal(await customer.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),true);
  await customer.setViewportSize({width:1440,height:1000});
  await checkout.getByRole('button',{name:'Approve artwork & go to payment'}).click();
  await customer.waitForURL('https://checkout.stripe.com/**',{timeout:20000});
  await customer.getByRole('heading',{name:'Fake payment checkout'}).waitFor();
  const job=await (await customer.request.get(root+'/api/portal/job')).json();
  assert.equal(job.proofs[0].status,'approved');
  assert.equal(job.proofs[0].decisions[0].method,'customer_upload_preview');
  assert.equal(job.proofs[0].terms_acceptance.version,'2026-09-30');
  assert.equal(job.proofs[0].terms_acceptance.signer_name,'Preview Client');
  assert.equal(job.proofs[0].terms_acceptance.terms.version,'2026-09-30');
  assert.equal(job.totals.paid_cents,0);
  assert.equal(job.totals.rewards_discount_cents,600);
  assert.equal(job.totals.total_cents,3225);
  assert.equal(job.checkout.can_pay,true);
  await customer.goto(root+'/portal');
  await customer.getByText('Artwork & terms approved',{exact:false}).first().waitFor();
  await customer.screenshot({path:output+'/Approved-Preview-Order.png',fullPage:true});
  await customer.goto(root+'/account');
  await waitText(customer,'Your next project starts');
  await customer.screenshot({path:output+'/Client-Rewards-Account.png',fullPage:true});
  const wallet=await (await customer.request.get(root+'/api/customer')).json();
  assert.equal(wallet.wallet.credit_cents,4500);
  assert.equal(wallet.wallet.points,900);
  assert.deepEqual(errors,[]);
  await writeFile(output+'/browser-results.json',JSON.stringify({passed:true,
    checks:['Owner manual credit and points','Client balance and history','Instant upload previews',
      'Explicit approval at checkout','Complete approved proof before payment','Direct automatic redirect to fake payment checkout',
      'Terms accepted with artwork and retained on the order',
      'Credits and points applied with adjusted tax','$35 cart minimum before rewards','Desktop/mobile layout'],
    job_id:job.id,proof_id:job.proofs[0].id,balance_due_cents:job.totals.balance_cents},null,2));
  console.log('PASS: real desktop/mobile customer and owner flows; uploaded proof approved before payment; rewards applied once.');
}catch(error){
  if(customer){await customer.screenshot({path:output+'/browser-failure.png',fullPage:true});console.log('Customer screen:',await customer.locator('body').innerText());}
  if(owner)console.log('Owner screen:',await owner.locator('body').innerText());
  throw error;
}finally{await browser.close();}
