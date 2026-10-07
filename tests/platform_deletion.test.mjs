import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../app/static/platform.js',import.meta.url),'utf8').replace(/^import .*;\n/m,'');
async function setup({slug='pilot-shop',typed='pilot-shop',cancel='on',fail=false}={}){
 const root={innerHTML:''},error={textContent:''},message={textContent:''},button={disabled:false},calls=[];
 const form={dataset:{deleteCompany:slug},querySelector:s=>s==='button'?button:message};
 let renders=0;
 const company={slug,name:'Pilot Shop',url:'https://pilot.example.test',owner_email:'owner@example.test',usage:{staff:1,jobs:0},seats:1,connections:{},billing_mode:'stripe',revision:7};
 const context=vm.createContext({mountBilling:async()=>{},FormData:class{constructor(){return new Map([['confirm_slug',typed],['cancel_billing',cancel]]);}},document:{querySelector:s=>s==='#platform-app'?root:s==='#platform-error'?error:{},querySelectorAll:s=>s==='[data-delete-company]'?[form]:[]},fetch:async(path,options)=>{
  if(options.method==='DELETE'){calls.push({path,...options});return {ok:!fail,json:async()=>fail?{detail:'Cancellation failed; company retained'}:{ok:true}};}
  if(path==='/api/platform/companies')renders++;
  return {ok:true,json:async()=>path==='/api/session'?{csrf:'csrf-root',user:{platform_owner:true}}:{billing_message:'Subscriptions',companies: renders>1?[]:[company]}};
 }});
 await vm.runInContext(`(async()=>{${source}})()`,context);
 assert.match(root.innerHTML,/Delete company/);assert.match(root.innerHTML,/records and files are retained/);
 await form.onsubmit({preventDefault(){}});
 return {root,error,message,button,calls,renders};
}
{
 const t=await setup();assert.equal(t.calls.length,1);assert.equal(t.calls[0].path,'/api/platform/companies/pilot-shop');assert.equal(t.calls[0].headers['X-CSRF-Token'],'csrf-root');assert.deepEqual(JSON.parse(t.calls[0].body),{revision:7,confirm_slug:'pilot-shop',cancel_billing:true});assert.equal(t.renders,2);
}
{
 const t=await setup({typed:'other-company'});assert.equal(t.calls.length,0);assert.match(t.message.textContent,/exact company ID/);
}
{
 const t=await setup({fail:true});assert.equal(t.renders,1);assert.equal(t.button.disabled,false);assert.match(t.message.textContent,/company retained/);
}
console.log('PASS: owner removal requires exact typed company ID, sends revision and billing confirmation, retains failed deletions, and refreshes the company list.');
