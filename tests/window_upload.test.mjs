import assert from 'node:assert/strict';
import {createWindowUploads, validateWindowFiles, MAX_WINDOW_FILE_BYTES} from '../app/static/window-upload.js';
const saved = new Map();
let project = [], persistCount = 0, modalHTML = '', notices = '';
const nodes = {
  '#window-upload-input': {isConnected:true, disabled:false, files:[], value:''},
  '#window-upload-error': {isConnected:true, textContent:''},
  '#window-upload-files': {innerHTML:''}
};
globalThis.document = {
  querySelectorAll: () => [],
  querySelector: selector => selector === 'form[data-form="public-order"] input[name="artwork"]' ? {closest:() => ({insertAdjacentHTML:(_position, html) => {notices += html;}})} : nodes[selector] || null
};
const escape = value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const ctx = {
  esc:escape, showModal:(_title, html) => {modalHTML = html;}, toast:() => {},
  getDesign:async id => saved.get(id), saveDesign:async record => {saved.set(record.id, {...record, files:[...record.files]});},
  product:id => ({id, config:{supports_multiple_dimensions:id !== 3, artwork_upload_disabled:id === 2}}),
  getProject:() => project, persist:() => {persistCount++;}
};
const uploads = createWindowUploads(ctx);
const pdf = new File(['%PDF-1.4\nwindow artwork'], 'Left Window.pdf', {type:'application/pdf', lastModified:1});
const png = new File([new Uint8Array([137,80,78,71,13,10,26,10])], 'Right Window.png', {type:'image/png', lastModified:2});
validateWindowFiles([pdf, png]);
assert.throws(() => validateWindowFiles([{name:'bad.svg', size:5}]), /PDF, PNG or JPG/);
assert.throws(() => validateWindowFiles([{name:'empty.pdf', size:0}]), /non-empty/);
assert.throws(() => validateWindowFiles([{name:'huge.pdf', size:MAX_WINDOW_FILE_BYTES + 1}]), /50 MB/);
assert.match(uploads.button({product_id:1}), /Upload Design/);
assert.doesNotMatch(uploads.button({product_id:1}), /canva/i);
await uploads.actions['window-upload']({dataset:{productId:'1'}});
assert.match(modalHTML, /multiple/);
assert.match(modalHTML, /No Canva account/);
const choose = async files => {nodes['#window-upload-input'].files = files; await nodes['#window-upload-input'].onchange({target:nodes['#window-upload-input']});};
await choose([pdf, png]);
assert.equal(saved.get('window-upload-draft-1').files.length, 2);
await choose([pdf]);
assert.equal(saved.get('window-upload-draft-1').files.length, 2);
await choose([new File(['bad'], 'bad.svg')]);
assert.match(nodes['#window-upload-error'].textContent, /PDF, PNG or JPG/);
assert.equal(saved.get('window-upload-draft-1').files.length, 2);
project = await uploads.prepareItems([{product_id:1,key:'left'}, {product_id:1,key:'right'}]);
assert.equal(project[0].window_artwork_id, project[1].window_artwork_id);
const attachedId = project[0].window_artwork_id;
assert.notEqual(attachedId, 'window-upload-draft-1');
await uploads.clearDrafts(project);
assert.equal(saved.get('window-upload-draft-1').files.length, 0);
assert.equal(saved.get(attachedId).files.length, 2);
const output = await uploads.filesFor(project);
assert.equal(output.length, 2, 'Shared files should be sent only once.');
assert.equal(output[0].name, 'items-1-2-Left Window.pdf');
assert.equal(await output[0].text(), await pdf.text());
assert.deepEqual(await output[1].arrayBuffer(), await png.arrayBuffer());
await uploads.checkoutHint(project);
assert.match(notices, /2 window design files already attached/);
const reloaded = createWindowUploads(ctx);
assert.equal((await reloaded.filesFor(project)).length, 2);
await reloaded.actions['window-upload']({dataset:{productId:'1',projectKey:'left'}});
assert.match(modalHTML, /shared by 2 panes/);
await reloaded.actions['window-upload-remove']({dataset:{index:'0'}});
assert.equal((await reloaded.filesFor(project)).length, 1);
assert.equal(persistCount, 1);
project.push({product_id:1,key:'door'});
await reloaded.actions['window-upload']({dataset:{productId:'1',projectKey:'door'}});
await choose([pdf]);
assert.ok(project[2].window_artwork_id);
assert.notEqual(project[2].window_artwork_id, attachedId);
assert.equal((await reloaded.filesFor(project)).length, 2);
assert.deepEqual(await reloaded.filesFor([{product_id:2,window_artwork_id:attachedId}]), []);
await assert.rejects(() => reloaded.actions['window-upload']({dataset:{productId:'2'}}), /not available/);
await assert.doesNotReject(() => reloaded.actions['window-upload']({dataset:{productId:'3'}})); // Ordinary products now support direct upload too.
await assert.rejects(() => reloaded.filesFor([{product_id:1,window_artwork_id:'missing'}]), /missing/);
const fail = createWindowUploads({...ctx, saveDesign:async () => {throw new Error('Storage full');}});
await fail.actions['window-upload']({dataset:{productId:'1'}});
await choose([pdf]);
assert.match(nodes['#window-upload-error'].textContent, /Storage full/);
assert.equal(saved.get('window-upload-draft-1').files.length, 0);
console.log('PASS: validation, multiple files, deduplication, shared panes, persistence, checkout attachments, removal, reload, disabled products and failed storage.');
