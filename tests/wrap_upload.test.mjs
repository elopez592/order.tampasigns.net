import assert from 'node:assert/strict';
import {createWindowUploads, usesDirectArtwork} from '../app/static/window-upload.js';

const products = [
  {id:1,config:{supports_multiple_dimensions:true}},
  {id:10,config:{is_wrap:true,supports_multiple_dimensions:false}},
  {id:11,config:{is_wrap:true,quantity_only:true}},
  {id:12,config:{is_wrap:true,supports_multiple_dimensions:true}},
  {id:13,config:{is_wrap:true,artwork_upload_disabled:true}},
  {id:14,config:{quantity_only:true}}
];
for (const id of [1,10,11,12]) assert.equal(usesDirectArtwork(products.find(p=>p.id===id)),true);
for (const id of [13,14,99]) assert.equal(usesDirectArtwork(products.find(p=>p.id===id)),false);
assert.equal(usesDirectArtwork(null),false);
const saved=new Map();let project=[],html='',notice='';
const nodes={'#window-upload-input':{isConnected:true,files:[],value:''},'#window-upload-error':{isConnected:true,textContent:''},'#window-upload-files':{innerHTML:''}};
globalThis.document={querySelectorAll:()=>[],querySelector:s=>s==='form[data-form="public-order"] input[name="artwork"]'?{closest:()=>({insertAdjacentHTML:(_pos,value)=>{notice=value;}})}:nodes[s]||null};
const esc=v=>String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
// Node structuredClone(File) returns a Blob; real IndexedDB is exercised in the browser test.
const ctx={esc,showModal:(_title,body)=>{html=body;},toast:()=>{},getDesign:async id=>saved.get(id),saveDesign:async d=>saved.set(d.id,{...d,files:[...d.files]}),product:id=>products.find(p=>p.id===Number(id)),getProject:()=>project,persist:()=>{}};
const uploads=createWindowUploads(ctx);
const file=new File(['%PDF-1.4\noriginal-wrap'], 'Driver Side.pdf',{type:'application/pdf',lastModified:5});
for(const id of [10,11,12]){
  await uploads.actions['window-upload']({dataset:{productId:String(id)}});
  assert.match(html,/finished wrap artwork/);
  assert.match(html,/Driver Side, Passenger Side and Rear/);
  assert.doesNotMatch(html,/Canva|Left Window|storefront concept/);
  nodes['#window-upload-input'].files=[file];
  await nodes['#window-upload-input'].onchange({target:nodes['#window-upload-input']});
  const items=await uploads.prepareItems([{product_id:id,key:'wrap-'+id}]);
  assert.ok(items[0].window_artwork_id);
  project.push(...items);
  await uploads.clearDrafts(items);
}
const files=await uploads.filesFor(project);
assert.equal(files.length,3);
assert.equal(files[0].name,'items-1-Driver Side.pdf');
assert.equal(files[1].name,'items-2-Driver Side.pdf');
assert.equal(await files[0].text(),await file.text());
await uploads.checkoutHint(project);
assert.match(notice,/3 design files already attached/);
assert.doesNotMatch(notice,/window design/);
const reloaded=createWindowUploads(ctx);
assert.equal((await reloaded.filesFor(project)).length,3);
await reloaded.actions['window-upload']({dataset:{projectKey:'wrap-11',productId:'11'}});
await reloaded.actions['window-upload-remove']({dataset:{index:'0'}});
assert.equal((await reloaded.filesFor(project)).length,2);
await assert.rejects(()=>reloaded.actions['window-upload']({dataset:{productId:'13'}}),/not available/);
await assert.doesNotReject(()=>reloaded.actions['window-upload']({dataset:{productId:'14'}})); // Ordinary quantity-based products now accept uploads.
await reloaded.actions['window-upload']({dataset:{productId:'1'}});
assert.match(html,/Left Window/);
console.log('PASS: vehicle, trailer and legacy wraps use direct uploads; window compatibility, original files, reload, removal and disabled-product rules preserved.');
