// The checkout review is the approval step. Uploading alone is not consent.
export function suggestedLines(filename, lines) {
  const needed=lines.map((line,index)=>line.artwork_upload_disabled?null:index).filter(index=>index!==null);
  const grouped=/^items-((?:\d+-)*\d+)-/.exec(filename);
  const single=/^item-(\d+)-/.exec(filename);
  const indexes=grouped?grouped[1].split('-').map(n=>Number(n)-1):single?[Number(single[1])-1]:needed.length===1?needed:[];
  return [...new Set(indexes)].filter(index=>needed.includes(index));
}

export function validateCoverage(files, lines) {
  const needed=lines.map((line,index)=>line.artwork_upload_disabled?null:index).filter(index=>index!==null);
  const approved=files.filter(file=>file.approved);
  if(!approved.length)throw new Error('Choose the finished artwork files to approve, or request a shop proof.');
  if(approved.some(file=>!file.line_indices.length))throw new Error('Assign every approved file to its product.');
  const covered=new Set(approved.flatMap(file=>file.line_indices));
  const missing=needed.filter(index=>!covered.has(index));
  if(missing.length)throw new Error('Artwork is missing for item '+missing.map(index=>index+1).join(', ')+'. Attach it, or request a shop proof.');
  return approved;
}

export function createCheckoutProof({state,esc,shop,toast}) {
  let files=[],urls=[],sequence=0,loading=false,previewError='';
  function clear(){for(const url of urls)URL.revokeObjectURL(url);urls=[];files=[];sequence++;loading=false;previewError='';}
  async function refresh(){
    const target=document.querySelector('#checkout-preview-review'),form=target?.closest('form');
    if(!target||!form)return;
    loading=true;previewError='';resetApproval(form);
    const current=++sequence;
    if(form.elements.artwork)form.elements.artwork.onchange=()=>refresh().catch(error=>toast(error.message,true));
    const submitted=[...(form.elements.artwork?.files||[])];
    try{
    const generated=await shop().designFiles(submitted,state.currentQuoteItems);
    if(current!==sequence||!target.isConnected)return;
    for(const url of urls)URL.revokeObjectURL(url);urls=[];
    const lines=state.quote.lines;
    files=[...submitted,...generated].map(file=>({file,line_indices:suggestedLines(file.name,lines),approved:!/photo-mockup|reference/i.test(file.name)}));
    if(files.length>60)throw new Error('A project supports up to 60 artwork files. Use multi-page PDFs for larger packages.');
    target.innerHTML=files.length?`<div class="eyebrow">YOUR PRODUCTION PROOF</div><h3 class="mt-sm">Review your files and finished sizes</h3><p class="field-hint mt-sm">Check every printed side and every page of a PDF. Assign files to the matching products. Approving here saves these exact files as your proof.</p>
      <div class="checkout-proof-files">${files.map((item,index)=>{
        const url=URL.createObjectURL(item.file);urls.push(url);
        const raster=/\.(png|jpe?g)$/i.test(item.file.name);
        return `<article class="checkout-proof-file"><a href="${esc(url)}" target="_blank" rel="noopener" class="checkout-file-preview" aria-label="Open ${esc(item.file.name)}">${raster?`<img src="${esc(url)}" alt="Artwork preview: ${esc(item.file.name)}">`:'<span>PDF<br><small>Open & review every page ↗</small></span>'}</a><div><strong class="file-name">${esc(item.file.name)}</strong><label class="check mt-sm"><input type="checkbox" data-proof-file="${index}" ${item.approved?'checked':''}><span>Include this file in my approved proof</span></label><fieldset class="proof-file-mapping"><legend>Print this file on:</legend>${lines.map((line,lineIndex)=>line.artwork_upload_disabled?'':`<label class="check"><input type="checkbox" data-proof-line="${lineIndex}" data-proof-index="${index}" ${item.line_indices.includes(lineIndex)?'checked':''}><span>Item ${lineIndex+1} · ${esc(line.name)} · ${esc(line.width)} × ${esc(line.height)} in · Qty ${line.quantity}${line.shirt_color?' · '+esc(line.shirt_color):''}${line.print_locations?.length?' · '+esc(line.print_locations.join(', ')):''}</span></label>`).join('')}</fieldset></div></article>`;
      }).join('')}</div>${state.canBuy?`<label class="field mt"><span>How should we handle this artwork?</span><select name="artwork_approval_mode"><option value="preview">Use these previews as my proof</option><option value="shop">Request a shop proof before printing</option></select></label><label class="check mt-sm" id="preview-approval-check"><input name="approve_uploads" type="checkbox" required ${form.elements.site_survey_requested?.checked?'disabled':''}><span>I reviewed all selected files, every printed side, the dimensions, quantity, spelling, layout and placement. I approve this artwork to print as supplied and understand changes after printing require a new paid order. I accept the Artwork, Sizing & Production Terms below.</span></label><p class="field-hint">Your approved preview is final for this artwork and scope. A second approval of the same artwork is not required. Any changed artwork needs a new approval.</p>`:'<p class="field-hint mt">Your custom project will receive a shop proof once the scope and any site survey are confirmed.</p>'}`:'<p class="field-hint">Attach finished artwork to review and approve it now, or upload it later in your private order page.</p>';
    target.querySelectorAll('[data-proof-file]').forEach(input=>input.onchange=()=>{files[Number(input.dataset.proofFile)].approved=input.checked;resetApproval(form);});
    target.querySelectorAll('[data-proof-line]').forEach(input=>input.onchange=()=>{const item=files[Number(input.dataset.proofIndex)],line=Number(input.dataset.proofLine);item.line_indices=input.checked?[...new Set([...item.line_indices,line])]:item.line_indices.filter(index=>index!==line);resetApproval(form);});
    const mode=form.elements.artwork_approval_mode;
    if(mode)mode.onchange=()=>{const check=target.querySelector('#preview-approval-check');check.hidden=mode.value!=='preview';form.elements.approve_uploads.required=mode.value==='preview';resetApproval(form);};
    }catch(error){
      if(current!==sequence)return;
      for(const url of urls)URL.revokeObjectURL(url);urls=[];files=[];
      previewError=error.message||'The artwork previews could not be prepared. Please attach your files again.';
      target.innerHTML=`<p class="field-hint">${esc(previewError)}</p>`;
      throw error;
    }finally{if(current===sequence)loading=false;}
  }
  function resetApproval(form){if(form.elements.approve_uploads)form.elements.approve_uploads.checked=false;}
  function submission(form,buy){
    if(loading)throw new Error('Your artwork previews are still preparing. Please wait before submitting.');
    if(previewError)throw new Error(previewError);
    const approve=buy&&files.length&&form.elements.artwork_approval_mode?.value==='preview';
    if(approve){
      validateCoverage(files,state.quote.lines);
      if(!form.elements.approve_uploads?.checked)throw new Error('Review and check the artwork approval box before continuing.');
    }
    return {files:[...files],approve:!!approve};
  }
  return {clear,refresh,submission};
}
