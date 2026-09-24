import assert from 'node:assert/strict';
import {createWindowUploads, supportsArtworkUpload, usesDirectArtwork} from '../app/static/window-upload.js';
const products = [{id:1,config:{}},{id:2,config:{finished_apparel:true}},{id:3,config:{quantity_only:true}},{id:4,config:{is_wrap:true}},{id:5,config:{supports_multiple_dimensions:true}},{id:6,config:{artwork_upload_disabled:true,supports_multiple_dimensions:true}},{id:7,config:{contour_customizer:true}}];
for (const p of products) assert.equal(supportsArtworkUpload(p),p.id<6);
assert.equal(supportsArtworkUpload(undefined),false);
assert.equal(supportsArtworkUpload({id:99}),false);
const records=new Map();let project=[],html='',title='',notice='';
const nodes={'#window-upload-input':{isConnected:true,value:'',files:[]},'#window-upload-error':{isConnected:true,textContent:''},'#window-upload-files':{innerHTML:''}};
globalThis.document={querySelectorAll:()=>[],querySelector:s=>s==='form[data-form="public-order"] input[name="artwork"]'?{closest:()=>({insertAdjacentHTML:(_pos,value)=>notice=value})}:nodes[s]||null};
const esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const ctx={esc,showModal:(t,h)=>{title=t;html=h;},toast:()=>{},getDesign:async id=>records.get(id),saveDesign:async d=>records.set(d.id,structuredClone(d)),product:id=>products.find(p=>p.id===Number(id)),getProject:()=>project,persist:()=>{}};
let uploads=createWindowUploads(ctx);
const file=new File(['%PDF-1.4\nexact original artwork'], 'Front.pdf',{type:'application/pdf',lastModified:1});
async function choose(files){nodes['#window-upload-input'].files=files;await nodes['#window-upload-input'].onchange({target:nodes['#window-upload-input']});}
for(const id of [1,2,3]){
  assert.equal(usesDirectArtwork(products.find(p=>p.id===id)),false,'Canva must not be suppressed for ordinary products');
  assert.match(uploads.button({product_id:id}),/Upload File/);
  await uploads.actions['window-upload']({dataset:{productId:String(id)}});
  assert.equal(title,'Upload File');
  assert.doesNotMatch(html,/Left Window|Driver Side|storefront concept/);
  assert.match(html,/Front and Back/);
  await choose([file]);
  const items=await uploads.prepareItems([{product_id:id,key:'item-'+id}]);
  project.push(...items);await uploads.clearDrafts(items);
  assert.ok(items[0].window_artwork_id);
}
let files=await uploads.filesFor(project);
assert.equal(files.length,3);
for(let i=0;i<3;i++){assert.equal(files[i].name,`items-${i+1}-Front.pdf`);assert.equal(await files[i].text(),await file.text());}
await uploads.checkoutHint(project);assert.match(notice,/3 design files already attached/);assert.doesNotMatch(notice,/window design/);
uploads=createWindowUploads(ctx);
assert.equal((await uploads.filesFor(project)).length,3);
await uploads.actions['window-upload']({dataset:{productId:'1'}});
await choose([new File(['%PDF-1.4\nsecond artwork'],'Second.pdf',{type:'application/pdf'})]);
project.push(...await uploads.prepareItems([{product_id:1,key:'item-1-again'}]));
assert.notEqual(project[0].window_artwork_id,project[3].window_artwork_id);
assert.equal(await (await uploads.filesFor([project[0]]))[0].text(),await file.text());
await uploads.actions['window-upload']({dataset:{projectKey:'item-2'}});
await uploads.actions['window-upload-remove']({dataset:{index:'0'}});
assert.equal((await uploads.filesFor(project)).length,3);
await choose([file]);assert.equal((await uploads.filesFor(project)).length,4);
for(const id of [6,7,99]){assert.equal(uploads.button({product_id:id}),'');await assert.rejects(()=>uploads.actions['window-upload']({dataset:{productId:String(id)}}),/not available/);}
assert.deepEqual(await uploads.filesFor([{product_id:6,window_artwork_id:project[0].window_artwork_id}]),[]);
assert.match(uploads.button({product_id:4}),/Upload Design/);
assert.match(uploads.button({product_id:5}),/Upload Design/);
await assert.rejects(()=>uploads.filesFor([{product_id:1,window_artwork_id:'missing'}]),/missing/);
console.log('PASS: uploads alongside Canva, unchanged original bytes, generic and apparel copy, isolated cart items, repeat products, reload, removals, checkout and no-artwork exclusions.');
