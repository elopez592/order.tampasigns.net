import {realWorkPhotosFor,productGalleryMarkup,setupProductPhotoGallery} from './product-photo-gallery.js?v=20261015-1';
import {validateWindowFiles, preflightArtwork} from './window-upload.js?v=20260930-previews-1';

// Each bundle is one cart line. Files use the existing private upload pipeline.
export function createPackBuilder({page,esc,api,saveDesign,getDesign,addItem,showGallery=()=>false}) {
  return async function packView(product, existing=null) {
    const saved=existing?.window_artwork_id?await getDesign(existing.window_artwork_id):null;
    if(existing&&!saved)throw new Error('Saved artwork is missing. Please reattach your pack files.');
    const spec=existing?.sticker_pack;
    let rows=(spec?.stickers||[]).map((s,i)=>({...s,file:saved.files[i]}));
    let header=spec?.header?{...spec.header,file:saved.files[rows.length]}:null;
    const gallery=showGallery()?`<section class="panel mb" data-product-preview data-product-slug="sticker-packs">${productGalleryMarkup('sticker-packs','Sticker packs','',realWorkPhotosFor('sticker-packs'))}</section>`:'';
    page('Build your sticker pack',`${gallery}<div class="notice info mb">Choose your designs and sizes, then request one quote for printing, bagging and optional custom headers. Final pricing and the production proof are confirmed before payment.</div><form id="pack-builder" class="panel stack"><label class="field"><span>Number of packs</span><input name="packs" type="number" min="1" max="100000" step="1" value="${existing?.quantity||50}" required></label><h2>1. Add your stickers</h2><p>Upload multiple files at once. Each design can have its own finished size and number of copies in every pack.</p><label class="field"><span>Choose sticker artwork (up to 20 designs)</span><input id="pack-files" type="file" accept=".png,.jpg,.jpeg,.pdf" multiple></label><p class="field-hint">PDF, PNG or JPG. Up to 50 MB each and 200 MB per bundle. Sizes are in inches.</p><div id="pack-rows" class="stack"></div><h2>2. Optional package header</h2><label class="field"><span>Upload custom fold-over header</span><input id="pack-header" type="file" accept=".png,.jpg,.jpeg,.pdf"></label><div id="pack-header-info"></div><div class="fields two"><label class="field"><span>Header width (in)</span><input name="header_width" type="number" min="1" max="24" step=".01" value="${esc(header?.width||5.25)}"></label><label class="field"><span>Header height, flat before folding (in)</span><input name="header_height" type="number" min="1" max="24" step=".01" value="${esc(header?.height||4)}"></label></div><p class="field-hint">Example: 5.25 × 4 inches flat folds to 5.25 × 2 inches. Upload both panels in one file; include bleed and indicate the fold. Leave blank for a pack without a custom header.</p><label class="field"><span>Pack name / finish / packaging notes</span><textarea name="notes" maxlength="1000">${esc(spec?.notes||'')}</textarea></label><strong id="pack-summary" aria-live="polite"></strong><div id="pack-error" role="alert" class="form-error"></div><button class="btn primary" type="submit">${existing?'Save bundle changes':'Add bundle to project'}</button></form>`);
    if(gallery)setupProductPhotoGallery();
    const form=document.querySelector('#pack-builder'),error=form.querySelector('#pack-error');
    function summary(){const count=rows.reduce((n,r)=>n+Number(r.copies||0),0);form.querySelector('#pack-summary').textContent=`${rows.length} designs · ${count} stickers per pack · ${count*Number(form.elements.packs.value||0)} stickers total${header?' · 1 header per pack':''}`;}
    function render(){
      form.querySelector('#pack-rows').innerHTML=rows.map((r,i)=>`<section class="panel"><div class="row between wrap"><strong>${i+1}. ${esc(r.name)}</strong><button type="button" class="btn light" data-remove="${i}">Remove</button></div><div class="fields three">${[['width','Width (in)',.5,7],['height','Height (in)',.5,7],['copies','Copies per pack',1,100]].map(([key,label,min,max])=>`<label class="field"><span>${label}</span><input data-row="${i}" data-key="${key}" type="number" min="${min}" max="${max}" step="${key==='copies'?1:.01}" value="${esc(r[key])}" required></label>`).join('')}</div></section>`).join('');
      form.querySelector('#pack-header-info').innerHTML=header?`<p>${esc(header.name)} <button type="button" class="btn light" id="remove-pack-header">Remove header</button></p>`:'';
      summary();
    }
    form.addEventListener('input',e=>{if(e.target.dataset.row!==undefined)rows[Number(e.target.dataset.row)][e.target.dataset.key]=e.target.value;summary();});
    form.addEventListener('click',e=>{const remove=e.target.closest('[data-remove]');if(remove){rows.splice(Number(remove.dataset.remove),1);render();}if(e.target.id==='remove-pack-header'){header=null;form.querySelector('#pack-header').value='';render();}});
    form.querySelector('#pack-files').onchange=e=>{try{const files=[...e.target.files];validateWindowFiles(files);if(rows.length+files.length>20)throw new Error('Choose up to 20 designs per pack.');rows.push(...files.map(file=>({file,name:file.name,width:3,height:3,copies:1})));render();error.textContent='';}catch(err){error.textContent=err.message;}finally{e.target.value='';}};
    form.querySelector('#pack-header').onchange=e=>{try{const file=e.target.files[0];if(file){validateWindowFiles([file]);header={file,name:file.name};render();}}catch(err){error.textContent=err.message;}finally{e.target.value='';}};
    form.onsubmit=async e=>{
      e.preventDefault();const button=form.querySelector('[type="submit"]');button.disabled=true;error.textContent='';
      try{
        if(!rows.length)throw new Error('Upload at least one sticker design.');
        const all=[...rows.map(r=>r.file),...(header?[header.file]:[])];validateWindowFiles(all);
        if(all.reduce((n,f)=>n+f.size,0)>200*1024*1024)throw new Error('Keep the combined artwork under 200 MB.');
        const pack={stickers:rows.map(({file,...r})=>r),header:header?{name:header.name,width:form.elements.header_width.value,height:form.elements.header_height.value}:null,notes:form.elements.notes.value};
        const item={product_id:product.id,width:1,height:1,quantity:Number(form.elements.packs.value),sticker_pack:pack,key:existing?.key||crypto.randomUUID()};
        await api('/api/calculate','POST',{items:[item]});
        const files=[],checks=[];
        for(const [i,r] of [...rows,...(header?[{...header,...pack.header}]:[])].entries()){
          const prefix=i<rows.length?`sticker-${i+1}-${r.width}x${r.height}in-${r.copies}per-pack-`:`header-${r.width}x${r.height}in-flat-`;
          files.push(new File([r.file],prefix+r.name.replace(/[\\/]/g,'-'),{type:r.file.type,lastModified:r.file.lastModified}));
          checks.push(await preflightArtwork(r.file,{width:Number(r.width),height:Number(r.height)}));
        }
        item.window_artwork_id=crypto.randomUUID();
        await saveDesign({id:item.window_artwork_id,kind:'window-upload',product_id:product.id,files,checks});
        await addItem(item,existing);
      }catch(err){error.textContent=err.message;}finally{if(button.isConnected)button.disabled=false;}
    };
    render();
  };
}

