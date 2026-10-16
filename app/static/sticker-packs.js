import {realWorkPhotosFor,productGalleryMarkup,setupProductPhotoGallery} from './product-photo-gallery.js?v=20261015-taquera-2';
import {validateWindowFiles,preflightArtwork} from './window-upload.js?v=20260930-previews-1';

const packMoney=cents=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100);
export function packPriceMarkup(pricing,quantity){
  if(!pricing)return '';
  return `<div class="notice info mt" aria-label="Sticker pack bundle price"><strong>Bundle price: ${packMoney(pricing.total_cents)}</strong> for ${quantity} packs <span class="muted">(${packMoney(pricing.total_cents/quantity)} per pack)</span><p class="field-hint">Includes stickers, cardstock headers, packaging, assembly and any selected design service. Tax and delivery are calculated at checkout. Your shop proof follows payment; printing starts after approval.</p></div>`;
}

// A pack is one cart line, including its designs and optional reference files.
export function createPackBuilder({page,esc,api,saveDesign,getDesign,addItem,showGallery=()=>false,getWholesaleToken=()=>null}){
  return async function packView(product,existing=null){
    const saved=existing?.window_artwork_id?await getDesign(existing.window_artwork_id):null;
    if(existing?.window_artwork_id&&!saved)throw new Error('Saved artwork is missing. Please reattach your pack files.');
    const spec=existing?.sticker_pack;
    const blank=index=>({name:`Sticker ${index+1}`,width:3,height:3,copies:1,design_requested:false,design_service:'artwork'});
    let rows=(spec?.stickers||[blank(0)]).map((s,i)=>{
      const index=saved?.row_file_indices?saved.row_file_indices[i]:i;
      return {...s,design_service:s.design_service|| (s.design_requested?'manual':'artwork'),file:Number.isInteger(index)?saved?.files[index]:undefined};
    });
    const headerIndex=saved?.header_file_index??rows.length;
    let header=spec?.header?{...spec.header,file:saved?.files[headerIndex]}:null;
    const designUnit=Number(product.config.pack_design_price??25)*100;
    const generationUnit=Number(product.config.pack_generation_price??12)*100;
    const gallery=showGallery()?`<section class="panel mb" data-product-preview data-product-slug="sticker-packs">${productGalleryMarkup('sticker-packs','Sticker packs','',realWorkPhotosFor('sticker-packs'))}</section>`:'';
    page('Build your sticker pack',`${gallery}<div class="notice info mb">Calculate your bundle price and check out right away. Every pack includes a cardstock header, bag and assembly. Package size may vary. Artwork can be uploaded now or after payment; a shop proof must be approved before printing.</div><form id="pack-builder" class="panel stack"><h2>1. Calculate your bundle</h2><div class="fields two"><label class="field"><span>Number of packs</span><input name="packs" type="number" min="1" max="100000" step="1" value="${existing?.quantity||50}" required></label><label class="field"><span>Different sticker designs</span><input id="pack-design-count" type="number" min="1" max="20" step="1" value="${rows.length}" required></label></div><p>Set each sticker's size and copies per pack. Maximum 4 inches per side. No artwork upload is needed to calculate your price.</p><div id="pack-rows" class="stack"></div><button type="button" class="btn light" id="pack-add-design">Add another sticker design</button><label class="field"><span>Upload artwork or references for multiple designs (optional)</span><input id="pack-files" type="file" accept=".png,.jpg,.jpeg,.pdf" multiple></label><p class="field-hint">PDF, PNG or JPG. Up to 50 MB each and 200 MB per bundle. Files fill designs without an attachment first.</p><h2>2. Custom header artwork (optional)</h2><label class="field"><span>Upload custom header artwork (optional)</span><input id="pack-header" type="file" accept=".png,.jpg,.jpeg,.pdf"></label><div id="pack-header-info"></div><p class="field-hint">A cardstock header is included with every bag. Leave the upload blank to use our standard header. Package size may vary; we fit custom artwork and send a proof after payment.</p><label class="field"><span>Design brief / pack name / finish / packaging notes</span><textarea name="notes" maxlength="1000" placeholder="For design help, describe your wording, style, colors and ideas. You can send references after checkout.">${esc(spec?.notes||'')}</textarea></label><strong id="pack-summary" aria-live="polite"></strong><div id="pack-price" aria-live="polite"></div><div id="pack-error" role="alert" class="form-error"></div><div class="row wrap"><button class="btn primary" type="submit" data-pack-checkout>Checkout now</button><button class="btn light" type="submit">${existing?'Save bundle changes':'Add bundle to project'}</button></div></form>`);
    if(gallery)setupProductPhotoGallery();
    const form=document.querySelector('#pack-builder'),error=form.querySelector('#pack-error');
    let priceTimer,priceRevision=0;
    const packSpec=()=>({stickers:rows.map(({file,...r})=>r),header:header?.file?{name:header.name}:null,notes:form.elements.notes.value});
    function summary(){
      const count=rows.reduce((n,r)=>n+Number(r.copies||0),0),quantity=Number(form.elements.packs.value||0);
      form.querySelector('#pack-summary').textContent=`${rows.length} designs · ${count} stickers per pack · ${count*quantity} stickers total · 1 cardstock header per pack`;
      clearTimeout(priceTimer);const revision=++priceRevision,price=form.querySelector('#pack-price');
      if(!rows.length){price.textContent='Add a sticker design to calculate your bundle price.';return;}
      price.textContent='Updating price…';
      priceTimer=setTimeout(async()=>{try{
        const quote=await api('/api/calculate','POST',{items:[{product_id:product.id,quantity,sticker_pack:packSpec()}],wholesale_token:getWholesaleToken()});
        if(revision===priceRevision&&price.isConnected)price.innerHTML=packPriceMarkup(quote.lines[0].sticker_pack_pricing,quantity);
      }catch(err){if(revision===priceRevision&&price.isConnected)price.textContent=err.message;}},300);
    }
    function render(){
      form.querySelector('#pack-design-count').value=rows.length;
      form.querySelector('#pack-add-design').disabled=rows.length>=20;
      form.querySelector('#pack-rows').innerHTML=rows.map((r,i)=>`<section class="panel"><div class="row between wrap"><strong>Sticker design ${i+1}</strong><button type="button" class="btn light" data-remove="${i}">Remove</button></div><label class="field"><span>Design name</span><input data-row="${i}" data-key="name" maxlength="100" value="${esc(r.name)}" required></label><div class="fields three">${[['width','Width (in)',.5,4],['height','Height (in)',.5,4],['copies','Copies per pack',1,100]].map(([key,label,min,max])=>`<label class="field"><span>${label}</span><input data-row="${i}" data-key="${key}" type="number" min="${min}" max="${max}" step="${key==='copies'?1:.01}" value="${esc(r[key])}" required></label>`).join('')}</div><label class="field"><span>Artwork for this design</span><select data-row="${i}" data-key="design_service"><option value="artwork"${r.design_service==='artwork'?' selected':''}>I have artwork — upload now or after payment</option><option value="generated"${r.design_service==='generated'?' selected':''}>Sticker generation — ${packMoney(generationUnit)} per design</option><option value="manual"${r.design_service==='manual'?' selected':''}>Manual custom design — ${packMoney(designUnit)} per design</option></select></label><label class="field"><span>Artwork or reference file (optional)</span><input type="file" data-pack-artwork-row="${i}" accept=".png,.jpg,.jpeg,.pdf"></label>${r.file?`<p class="field-hint">Attached: ${esc(r.file.name)} <button type="button" class="btn light small" data-clear-artwork="${i}">Remove attachment</button></p>`:''}<p class="field-hint">Design service is charged once per different design, regardless of the number of packs. Your proof is prepared after payment.</p></section>`).join('');
      form.querySelector('#pack-header-info').innerHTML=header?.file?`<p>${esc(header.name)} <button type="button" class="btn light" id="remove-pack-header">Remove custom artwork</button></p>`:'';
      summary();
    }
    form.addEventListener('input',e=>{
      if(e.target.dataset.row!==undefined){const key=e.target.dataset.key;rows[Number(e.target.dataset.row)][key]=e.target.value;
        if(key==='design_service')rows[Number(e.target.dataset.row)].design_requested=e.target.value!=='artwork';}
      if(e.target.id!=='pack-design-count')summary();
    });
    form.addEventListener('change',e=>{
      try{
        if(e.target.id==='pack-design-count'){
          const count=Number(e.target.value);if(!Number.isInteger(count)||count<1||count>20)throw new Error('Choose 1 to 20 different sticker designs.');
          while(rows.length<count)rows.push(blank(rows.length));rows=rows.slice(0,count);render();
        }
        if(e.target.dataset.packArtworkRow!==undefined){const file=e.target.files[0];if(file){validateWindowFiles([file]);rows[Number(e.target.dataset.packArtworkRow)].file=file;render();}}
      }catch(err){error.textContent=err.message;}
    });
    form.addEventListener('click',e=>{
      const remove=e.target.closest('[data-remove]'),clear=e.target.closest('[data-clear-artwork]');
      if(remove){rows.splice(Number(remove.dataset.remove),1);render();}
      if(clear){delete rows[Number(clear.dataset.clearArtwork)].file;render();}
      if(e.target.id==='pack-add-design'&&rows.length<20){rows.push(blank(rows.length));render();}
      if(e.target.id==='remove-pack-header'){header=null;form.querySelector('#pack-header').value='';render();}
    });
    form.querySelector('#pack-files').onchange=e=>{try{
      const files=[...e.target.files];validateWindowFiles(files);
      if(files.length>20-rows.filter(r=>r.file).length)throw new Error('Choose up to 20 designs per pack.');
      for(const file of files){let row=rows.find(r=>!r.file);if(!row){row=blank(rows.length);rows.push(row);}row.file=file;if(/^Sticker \d+$/.test(row.name))row.name=file.name;}
      render();error.textContent='';
    }catch(err){error.textContent=err.message;}finally{e.target.value='';}};
    form.querySelector('#pack-header').onchange=e=>{try{const file=e.target.files[0];if(file){validateWindowFiles([file]);header={file,name:file.name};render();}}catch(err){error.textContent=err.message;}finally{e.target.value='';}};
    form.onsubmit=async e=>{
      e.preventDefault();const buttons=[...form.querySelectorAll('[type="submit"]')];buttons.forEach(b=>b.disabled=true);error.textContent='';
      try{
        if(!rows.length)throw new Error('Add at least one sticker design.');
        const all=[...rows.map(r=>r.file).filter(Boolean),...(header?.file?[header.file]:[])];validateWindowFiles(all);
        if(all.reduce((n,f)=>n+f.size,0)>200*1024*1024)throw new Error('Keep the combined artwork under 200 MB.');
        const pack=packSpec(),item={product_id:product.id,width:1,height:1,quantity:Number(form.elements.packs.value),sticker_pack:pack,key:existing?.key||crypto.randomUUID()};
        await api('/api/calculate','POST',{items:[item],wholesale_token:getWholesaleToken()});
        const files=[],checks=[],row_file_indices=rows.map(()=>null);let header_file_index=null;
        for(const [i,r] of rows.entries())if(r.file){
          row_file_indices[i]=files.length;
          files.push(new File([r.file],`sticker-${i+1}-${r.width}x${r.height}in-${r.copies}per-pack-`+r.file.name.replace(/[\\/]/g,'-'),{type:r.file.type,lastModified:r.file.lastModified}));
          checks.push(await preflightArtwork(r.file,{width:Number(r.width),height:Number(r.height)}));
        }
        if(header?.file){header_file_index=files.length;files.push(new File([header.file],'custom-header-artwork-'+header.file.name.replace(/[\\/]/g,'-'),{type:header.file.type,lastModified:header.file.lastModified}));checks.push(await preflightArtwork(header.file));}
        item.window_artwork_id=crypto.randomUUID();
        await saveDesign({id:item.window_artwork_id,kind:'window-upload',product_id:product.id,files,checks,row_file_indices,header_file_index});
        await addItem(item,existing,{checkoutNow:!!e.submitter?.hasAttribute('data-pack-checkout')});
      }catch(err){error.textContent=err.message;}finally{buttons.forEach(b=>{if(b.isConnected)b.disabled=false;});}
    };
    render();
  };
}
