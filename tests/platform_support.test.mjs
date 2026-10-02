import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../app/static/platform.js',import.meta.url),'utf8');
async function setup({blocked=false,fail=false}={}){
 const root={innerHTML:''},error={textContent:''},form={},button={dataset:{support:'pilot-shop'}},events=[];
 const popup={opener:{},location:{replace(url){events.push(['navigate',url]);}},close(){events.push(['close']);}};
 const context=vm.createContext({document:{querySelector:s=>s==='#platform-app'?root:s==='#platform-error'?error:form,querySelectorAll:s=>s==='[data-support]'?[button]:[]},window:{open(){events.push(['open']);return blocked?null:popup;}},fetch:async(path,options)=>{
  if(path.endsWith('/support')){events.push(['api']);assert.equal(options.headers['X-CSRF-Token'],'csrf-root');assert.equal(options.method,'POST');return {ok:!fail,json:async()=>fail?{detail:'Company is paused'}:{url:'https://pilot.example.test/staff#support=one-use'}};}
  return {ok:true,json:async()=>path==='/api/session'?{csrf:'csrf-root',user:{platform_owner:true}}:{billing_message:'Manual billing',companies:[{slug:'pilot-shop',name:'Pilot Shop',url:'https://pilot.example.test',owner_email:'owner@example.test',usage:{staff:1,jobs:0},seats:5,connections:{}}]}};
 }});
 await vm.runInContext(`(async()=>{${source}})()`,context);assert.match(root.innerHTML,/Manage company/);assert.match(root.innerHTML,/Company sign-in/);
 await button.onclick();return {events,popup,error,button};
}
{
 const t=await setup();assert.deepEqual(t.events.map(x=>x[0]),['open','api','navigate']);assert.equal(t.popup.opener,null);assert.equal(t.button.disabled,false);
}
{
 const t=await setup({blocked:true});assert.deepEqual(t.events,[['open']]);assert.match(t.error.textContent,/Allow pop-ups/);
}
{
 const t=await setup({fail:true});assert.deepEqual(t.events.map(x=>x[0]),['open','api','close']);assert.equal(t.error.textContent,'Company is paused');assert.equal(t.button.disabled,false);
}
const appSource=readFileSync(new URL('../app/static/app.js',import.meta.url),'utf8');
const boot=appSource.slice(appSource.indexOf('async function boot(){'),appSource.lastIndexOf('boot();'));
{
 const events=[],state={},location={pathname:'/staff',hash:'#support=one-use'};
 const context=vm.createContext({state,location,URLSearchParams,history:{replaceState(){events.push('clear-fragment');location.hash='';}},window:{TampaAnalytics:{excludeStaff(){}}},app:{},route:async()=>events.push('route'),api:async(path,method,body)=>{
  if(path==='/api/session')return {csrf:'csrf-company',user:{support_company:'pilot-shop'}};
  if(path==='/api/auth/platform-support'){assert.equal(location.hash,'');assert.equal(state.csrf,'csrf-company');assert.equal(body.token,'one-use');events.push('exchange');return {csrf:'support-csrf'};}
  if(path==='/api/customer')return {customer:null};return {};
 }});
 await vm.runInContext(`${boot};boot()`,context);assert.deepEqual(events,['clear-fragment','exchange','route']);assert.equal(state.user.support_company,'pilot-shop');
}
console.log('PASS: support launch preserves platform tab, opens before await, handles errors, and clears the token before exchange.');
