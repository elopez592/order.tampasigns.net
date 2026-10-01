import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../app/static/shop.js',import.meta.url),'utf8');
const functions=source.slice(source.indexOf('  function createCanvaTab()'),source.indexOf('  function allProducts()'));
function setup(api){
  const tabs=[],events=[],location={pathname:'/products/banner',search:'',href:'/products/banner'};
  const context=vm.createContext({api,location,canvaUrl:'https://www.canva.com/',toast:()=>{},sessionStorage:{setItem(){throw Error('Order tab storage must stay untouched');}},window:{open(url,target){events.push('open');const values=new Map();const tab={location:{href:url},opener:{},sessionStorage:{setItem:(k,v)=>values.set(k,v)},values,closed:false,close(){this.closed=true;}};tabs.push(tab);assert.equal(target,'_blank');return tab;}}});
  vm.runInContext(functions,context);return {context,tabs,events,location};
}
{
  const t=setup(async()=>{t.events.push('api');return {edit_url:'https://www.canva.com/design/test/edit'};});
  await t.context.openCanvaDesign(3.5,2,'Sticker');
  assert.deepEqual(t.events,['open','api']);assert.equal(t.tabs[0].location.href,'https://www.canva.com/design/test/edit');assert.equal(t.tabs[0].opener,null);assert.equal(t.location.href,'/products/banner');
}
{
  const t=setup(async path=>{if(path.endsWith('/design'))throw Error('Connect Canva');return {authorize_url:'https://www.canva.com/oauth/authorize'};});
  await t.context.openCanvaDesign(3.5,2,'Sticker');
  assert.equal(t.tabs[0].location.href,'https://www.canva.com/oauth/authorize');assert.equal(t.location.href,'/products/banner');assert.deepEqual(JSON.parse(t.tabs[0].values.get('pending_canva_design')),{width:3.5,height:2,label:'Sticker'});
}
{
  const t=setup(async()=>{throw Error('Canva is not configured');});await t.context.openCanvaDesign(3,2,'Banner');assert.equal(t.tabs[0].location.href,'https://www.canva.com/');assert.equal(t.location.href,'/products/banner');
}
{
  const t=setup(async()=>{throw Error('Service unavailable');});await assert.rejects(t.context.openCanvaDesign(3,2,'Banner'),/Service unavailable/);assert.equal(t.tabs[0].closed,true);
}
{
  const t=setup(async()=>{throw Error('API must not run');});t.context.window.open=()=>null;await assert.rejects(t.context.openCanvaDesign(3,2,'Banner'),/Allow pop-ups/);assert.equal(t.location.href,'/products/banner');
}
// The product handler must reserve its tab before recalculating asynchronous options.
const action=source.match(/'product-canva':(async\(\)=>\{.*\}),/)[1];
{
  const t=setup(async()=>({edit_url:'https://www.canva.com/design/product/edit'}));Object.assign(t.context,{recalculate:async()=>{assert.equal(t.tabs.length,1);},state:{currentQuoteItems:[{product_id:1,width:3.5,height:2}]},product:()=>({}),usesDirectArtwork:()=>false,publicProductName:()=> 'Sticker'});await vm.runInContext(`(${action})()`,t.context);assert.equal(t.tabs.length,1);assert.equal(t.location.href,'/products/banner');
}
console.log('PASS: Canva editor, connection, fallback and product actions preserve the ordering tab; tabs open before async work; blocked and failed launches handled.');
