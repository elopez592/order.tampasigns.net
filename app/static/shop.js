import {createWindowUploads, usesDirectArtwork} from './window-upload.js?v=20260926-preflight-1';
import {createEmbroidery, embroidered} from './embroidery.js?v=20260926-embroidery-wheel-1';

// Customer project cart and artwork attachments.
export function createShop(ctx) {
  const {state,app,api,esc,money,input,select,formFooter,showModal,closeModal,toast,publicHeader,publicProductName,productPath,setPublicSeo,storefrontProductsFor,productIcon,productImage,realWorkGallery,calculatorView,recalculate,currentItems,orderModal,actions,forms}=ctx;
  const $=s=>document.querySelector(s);
  const $$=s=>[...document.querySelectorAll(s)];
  const read=()=>{try{const v=JSON.parse(localStorage.getItem('tampa_project')||'[]');return Array.isArray(v)?v:[];}catch{return [];}};
  let project=read(),draft=null,artImage=null,bgImage=null;
  const persist=()=>localStorage.setItem('tampa_project',JSON.stringify(project));
  const product=id=>state.catalog.products.find(p=>p.id===Number(id));
  const page=(title,body)=>{app.innerHTML=publicHeader()+`<main class="public-page"><div class="row between wrap mb"><h1>${esc(title)}</h1><a class="btn light" href="/products">Browse all products</a></div>${body}</main>`;};
  const canvaUrl='https://www.canva.com/';
  const canvaGuide=(width,height,label='this product')=>`<div class="notice info mt"><strong>Want more design freedom?</strong><br>Design in Canva opens a custom-size artboard at <strong>${esc(width)} × ${esc(height)} in</strong> for ${esc(label)} when Canva is connected. Download a PDF Print or high-resolution PNG and upload it back to this project.</div>`;
  const canvaButton=(width,height,label,extraClass='')=>`<button type="button" class="btn light ${extraClass}" data-action="canva-open" data-width="${esc(width)}" data-height="${esc(height)}" data-label="${esc(label)}">Design in Canva</button>`;
  const multiPanelArtwork=p=>!!p?.config?.supports_multiple_dimensions;
  const wrapArtworkNote='<div class="notice info mt"><strong>Have a design for your wrap?</strong><br>Upload your finished artwork, logo, concept or reference photos. Name separate files for each side or panel. Need artwork created? Request design help and we will review the scope with you.</div>';
  const multiPanelNote='<div class="notice info mt"><strong>Have a design for your windows?</strong><br>Upload finished artwork, a multi-page PDF, or separate files for each pane. You can also upload a storefront concept or request design help. We will review the layout and alignment before production.</div>';
  const db=new Promise((resolve,reject)=>{const r=indexedDB.open('tampa_designs',1);r.onupgradeneeded=()=>r.result.createObjectStore('designs',{keyPath:'id'});r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(new Error('Design storage is unavailable in this browser.'));});
  async function storage(mode,operation){const database=await db;return new Promise((resolve,reject)=>{const tx=database.transaction('designs',mode),r=operation(tx.objectStore('designs'));tx.oncomplete=()=>resolve(r.result);tx.onerror=()=>reject(new Error('Unable to save artwork. Your browser storage may be full.'));});}
  const saveDesign=d=>storage('readwrite',s=>s.put(d));
  const getDesign=id=>storage('readonly',s=>s.get(id));
  const windowUploads=createWindowUploads({esc,showModal,toast,getDesign,saveDesign,product,getProject:()=>project,persist});
  const embroidery=createEmbroidery({getDesign,saveDesign,product,esc,toast,onChange:recalculate});
  const designs=()=>storage('readonly',s=>s.getAll());
  const imageFor=color=>'/static/shirts/'+String(color||'White').toLowerCase().replaceAll(' ','-')+'.jpg';
  const shirtItem=()=>{const f=$('#calculator'),sizes=Object.fromEntries($$('[data-shirt-size]').map(e=>[e.dataset.shirtSize,Number(e.value)])),p=product(state.selectedProduct);return {product_id:state.selectedProduct,width:12,height:12,quantity:Object.values(sizes).reduce((a,b)=>a+b,0),shirt_color:f.elements.shirt_color.value,size_quantities:sizes,print_locations:$$('input[name="print_locations"]:checked').map(e=>e.value),...(embroidered(p)&&embroidery.selection()?{embroidery_preview:embroidery.selection()}:{})};};
  function setupProduct(p){
    const f=$('#calculator');if(!f)return;
    if(p.config.finished_apparel){
      const kind=p.config.apparel_kind||'custom_shirt',colors=Object.keys(p.config.shirt_colors||{}),sizes=p.config.shirt_sizes||[],defaultColor=colors.includes('White')?'White':colors[0],defaultSize=sizes.includes('M')?'M':sizes[0];
      const placements=kind==='custom_shirt'?[['front','Full front · $30 per shirt'],['back','Full back · $30 per shirt'],['left_chest','Left chest · $25 per shirt']]:(p.config.placement_options||[]).map(o=>[o.id,o.label]);
      const locationType=kind==='custom_shirt'?'checkbox':'radio',locationTitle=kind==='custom_shirt'?'Print locations (choose one or more)':'Embroidery placement';
      const itemLabel=kind==='embroidered_hat'?'Hat':kind==='embroidered_polo'?'Polo':kind==='embroidered_hoodie'?'Hoodie':'Shirt';
      f.innerHTML=`${select('shirt_color',itemLabel+' color',colors.map(c=>[c,c]),defaultColor)}<h3 class="mt mb">Choose sizes and quantities</h3><div class="shirt-sizes">${sizes.map(s=>`<label class="field"><span>${esc(s)}</span><input data-shirt-size="${esc(s)}" type="number" min="0" max="100000" step="1" value="${s===defaultSize?1:0}" required></label>`).join('')}</div><fieldset class="print-locations mt"><legend>${locationTitle}</legend>${placements.map(([v,l],i)=>`<label><input type="${locationType}" name="print_locations" value="${esc(v)}" ${i===0?'checked':''}> ${esc(l)}</label>`).join('')}</fieldset>${p.config.digitizing_fee&&Number(p.config.digitizing_fee)>0?`<div class="notice info mt">A one-time ${money(Number(p.config.digitizing_fee)*100)} digitizing fee is added on top of the product price for this embroidery order.</div>`:''}<div id="calc-feedback" class="form-error"></div>`;
      if(kind==='custom_shirt')$('.product-preview').innerHTML=`<img class="shirt-sample" src="${imageFor(defaultColor)}" alt="${esc(defaultColor)} Gildan Heavy Cotton 5000 sample"><span class="preview-label">Gildan 5000 · Supplier sample</span>`;
      f.addEventListener('change',e=>{if(kind==='custom_shirt'&&e.target.name==='shirt_color')$('.shirt-sample').src=imageFor(e.target.value);recalculate();});
    }
    if(p.config.contour_customizer)f.insertAdjacentHTML('afterend','<p class="field-hint mt">Upload your PNG or JPEG artwork when submitting the project. We will generate an approximate contour outline preview for review; the final cut path may differ slightly after production setup.</p>');
    if(!p.config.artwork_upload_disabled&&!p.config.contour_customizer){
      if(usesDirectArtwork(p))f.insertAdjacentHTML('afterend',`${p.config.is_wrap?wrapArtworkNote:multiPanelNote}<div class="row wrap mt">${windowUploads.button({product_id:p.id})}<button type="button" class="btn light" data-action="design-quote">Request design help</button></div>`);
      else if(embroidered(p))f.insertAdjacentHTML('afterend',`<p class="field-hint mt-sm">Have a vector or PDF logo too? ${windowUploads.button({product_id:p.id})} Attach it as an extra reference for our digitizer.</p>`);
      else f.insertAdjacentHTML('afterend',`<div class="row wrap mt"><button type="button" class="btn light" data-action="product-canva">Design in Canva</button>${windowUploads.button({product_id:p.id})}</div><p class="field-hint mt-sm">Already have artwork? Use Upload File. Or design in Canva, export PDF Print or a high-resolution PNG, and attach it here.</p>`);
    }
    if(embroidered(p))embroidery.setup(p).catch(e=>toast(e.message,true));
    windowUploads.refresh().catch(e=>toast(e.message,true));
  }
  async function add(){
    await recalculate();if(!state.quote)throw new Error('Complete your product options first.');
    if(project.length+state.currentQuoteItems.length>30)throw new Error('A project supports up to 30 product lines.');
    const items=await embroidery.prepareItems(await windowUploads.prepareItems(state.currentQuoteItems.map(item=>({...item,key:crypto.randomUUID()}))));
    project.push(...items);persist();window.TampaAnalytics?.track('add_to_cart');
    await windowUploads.clearDrafts(items).catch(e=>toast(e.message,true));
    showModal('Added to your project',`<p>Your project now has ${project.length} item${project.length===1?'':'s'}.</p><div class="row mt"><button class="btn light" data-action="close">Keep shopping</button><a class="btn primary" href="/project">View project</a></div>`);
    const count=$('[data-project-count]');if(count)count.textContent=project.length;
  }
  async function quoteProject(){
    const q=await api('/api/calculate','POST',{items:project,wholesale_token:state.wholesaleToken});
    state.quote=q;state.currentQuoteItems=structuredClone(project);state.canBuy=!q.review_required&&q.meets_minimum_order&&state.catalog.checkout?.available;return q;
  }
  function projectArtworkAction(line,index){
    const p=product(line.product_id);
    if(line.artwork_upload_disabled)return '';
    if(embroidered(p))return `<button class="btn light" data-action="embroidery-view" data-index="${index}">View embroidery preview</button>${windowUploads.button(project[index])}`;
    if(p?.config.contour_customizer)return '<span class="badge blue">Upload artwork at checkout</span>';
    if(usesDirectArtwork(p))return `${windowUploads.button(project[index])}<button class="btn light" data-action="design-quote">Request design help</button>`;
    return `${canvaButton(line.width,line.height,publicProductName(p))}${windowUploads.button(project[index])}`;
  }
  function projectArtworkHint(line){
    const p=product(line.product_id);
    if(line.artwork_upload_disabled)return '';
    if(embroidered(p))return '<p class="field-hint mt">Your logo and digital mockup are saved for this garment and will be attached when you submit. Upload extra file accepts an optional PDF or vector export as an additional digitizing reference. Remove and add this garment again to change the mockup.</p>';
    if(p?.config.contour_customizer)return '<p class="field-hint mt">Upload PNG/JPEG artwork at checkout and we will attach an approximate contour outline preview. Final cut paths may differ slightly after shop review.</p>';
    if(p?.config.is_wrap)return '<p class="field-hint mt">Upload your wrap artwork, logo or references. Label separate files by side or panel; we will review fit and placement before production.</p>';
    if(multiPanelArtwork(p))return '<p class="field-hint mt">For multiple panes or full storefront coverage, upload your overall concept, logo, measurements or references. We will split and align the artwork for production.</p>';
    return '<p class="field-hint mt">Use Upload File to attach finished artwork. For Canva designs, export PDF Print or a high-resolution PNG first. Attached files are included when you submit this project.</p>';
  }
  async function projectView(){
    page('Your project',project.length?'<p>Updating your prices…</p>':'<section class="panel"><h2>Make something great.</h2><p class="mt">Add products, artwork and quantities here, then submit everything together.</p><a class="btn primary mt" href="/products">Find a product</a></section>');
    if(!project.length)return;
    let q;try{q=await quoteProject();}catch(e){page('Your project',`<div class="notice mb">${esc(e.message)} Remove the affected item and add it again with current options.</div>${project.map((item,i)=>`<div class="panel mb">${esc(product(item.product_id)?.name||'Unavailable product')} <button class="btn light" data-action="project-remove" data-index="${i}">Remove</button></div>`).join('')}`);return;}
    page('Your project',`<div class="project-layout"><section class="stack">${q.lines.map((line,i)=>`<article class="panel"><div class="row between wrap"><h2>${esc(publicProductName(product(line.product_id)))}</h2><strong>${line.quote_only?'Quote required':money(line.sell_cents)}</strong></div><p class="muted mt-sm">${esc(line.description||`${line.width} × ${line.height} in`)}</p><div class="row wrap mt"><label class="field"><span>${line.finished_apparel?'Total garments':'Quantity'}</span><input type="number" min="1" max="100000" step="1" data-project-quantity="${i}" value="${line.quantity}" ${line.finished_apparel?'readonly':''}></label>${projectArtworkAction(line,i)}<button class="btn ghost" data-action="project-remove" data-index="${i}">Remove</button></div>${projectArtworkHint(line)}${line.finished_apparel?`<div class="shirt-sizes mt">${Object.entries(line.size_quantities).map(([s,n])=>`<label class="field"><span>${esc(s)}</span><input type="number" min="0" step="1" max="100000" data-project-size="${esc(s)}" data-index="${i}" value="${n}"></label>`).join('')}</div>`:''}</article>`).join('')}</section><aside class="panel estimate-card"><div class="eyebrow">PROJECT ESTIMATE</div><div class="metric large">${money(q.subtotal_cents)}</div>${q.lines.some(l=>l.quote_only)?'<p class="notice mt">This is a starting estimate. We will confirm final pricing for quote-only items.</p>':''}<p class="muted mt">${q.lines.length} product lines. Tax and delivery confirmed at checkout or in your quote.</p>${!q.meets_minimum_order?`<p class="notice mt">Your project minimum is ${money(q.minimum_order_cents)}. Add more items or request a reviewed quote.</p>`:''}<button class="btn primary wide mt" data-action="project-checkout">${state.canBuy?'Review project & checkout':'Submit project for a quote'}</button><a class="btn light wide mt" href="/products">Add more products</a><p class="field-hint mt">Your project is saved in this browser. Submitted projects appear in your signed-in customer account.</p></aside></div>`);
    await windowUploads.refresh();
    $$('[data-project-quantity], [data-project-size]').forEach(e=>e.addEventListener('change',async()=>{const n=Number(e.value);if(!Number.isInteger(n)||n< (e.dataset.projectSize?0:1)||n>100000){toast('Enter a valid whole quantity.',true);return;}const index=Number(e.dataset.index??e.dataset.projectQuantity);if(e.dataset.projectSize){project[index].size_quantities[e.dataset.projectSize]=n;project[index].quantity=Object.values(project[index].size_quantities).reduce((a,b)=>a+b,0);}else project[index].quantity=n;persist();await projectView();}));
  }
  async function openCanvaDesign(width,height,label,options={}){
    const safeWidth=Number(width),safeHeight=Number(height),safeLabel=String(label||'Tampa Signs artwork');
    if(!safeWidth||!safeHeight)throw new Error('Complete your size before opening Canva.');
    try{
      const created=await api('/api/canva/design','POST',{width:safeWidth,height:safeHeight,title:`Tampa Signs - ${safeLabel} - ${safeWidth}x${safeHeight} in`});
      if(options.redirect)location.href=created.edit_url;else window.open(created.edit_url,'_blank','noopener');
      toast(`Canva artboard created at ${created.width_px} x ${created.height_px}px (${created.scale_label}). Export PDF Print or PNG, then upload it to this project.`);
    }catch(error){
      if(/connect canva/i.test(error.message)){
        const next=location.pathname+location.search;
        sessionStorage.setItem('pending_canva_design',JSON.stringify({width:safeWidth,height:safeHeight,label:safeLabel}));
        try{
          const r=await api('/api/canva/connect','POST',{return_path:next});
          location.href=r.authorize_url;
        }catch(connectError){
          if(/not configured/i.test(connectError.message)){
            window.open(canvaUrl,'_blank','noopener');
            toast(`Canva is not connected to the shop yet. Use custom size ${safeWidth} x ${safeHeight} in for ${safeLabel}, then upload the exported PDF/PNG.`,true);
            return;
          }
          throw connectError;
        }
        return;
      }
      if(/not configured/i.test(error.message)){
        window.open(canvaUrl,'_blank','noopener');
        toast(`Canva is not connected to the shop yet. Use custom size ${safeWidth} x ${safeHeight} in for ${safeLabel}, then upload the exported PDF/PNG.`,true);
        return;
      }
      throw error;
    }
  }
  async function resumeCanva(){
    const params=new URLSearchParams(location.search);
    const status=params.get('canva');
    if(!status)return;
    const detail=params.get('canva_error')||'';
    params.delete('canva');
    params.delete('canva_error');
    const clean=location.pathname+(params.size?'?'+params.toString():'')+location.hash;
    history.replaceState(null,'',clean);
    if(status==='connected'){
      const raw=sessionStorage.getItem('pending_canva_design');
      if(!raw){toast('Canva is connected. Choose Design in Canva again to open your artboard.');return;}
      sessionStorage.removeItem('pending_canva_design');
      const pending=JSON.parse(raw);
      await openCanvaDesign(pending.width,pending.height,pending.label,{redirect:true});
      return;
    }
    if(status==='denied')toast(detail||'Canva connection was cancelled. Choose Design in Canva again when you are ready.',true);
    else toast(detail?`Canva could not finish connecting: ${detail}`:'Canva could not finish connecting. Please try Design in Canva again.',true);
  }
  function allProducts(){setPublicSeo();const products=state.catalog.products.filter(p=>!(p.name.toLowerCase()==='vehicle wraps'&&state.catalog.products.some(x=>x.name.toLowerCase()==='partial vehicle wraps')));page('All products',`<p class="muted mb">Everything we make, in one place.</p><div class="row wrap mb"><button class="btn primary" data-action="help-choose">Help me choose</button><button class="btn light" data-action="sample-kit">Request a material sample kit</button><a class="btn light" href="/industries">Shop by industry</a></div>${realWorkGallery()}<div class="all-products-grid">${products.map(p=>`<article class="panel product-catalog-card"><a class="catalog-image-link" href="${productPath(p)}" aria-label="View ${esc(publicProductName(p))}">${productImage(p,'catalog')}</a><div class="eyebrow">${esc((p.config.storefront_categories||[]).join(' / '))}</div><h2 class="mt"><a href="${productPath(p)}">${esc(publicProductName(p))}</a></h2><p class="muted mt">${esc(p.config.description)}</p><a class="btn primary mt" href="${productPath(p)}" data-action="browse-product" data-id="${p.id}">Customize & add to project</a></article>`).join('')}</div>`);}
  const industryProfiles={
    restaurants:{name:'Restaurants & Food Service',intro:'Menus, windows, storefront visibility, event graphics and vehicle branding.',categories:['Storefront','Events','Vehicles'],needs:['Storefront window graphics and tint','Menus, A-frame inserts and banners','Delivery vehicle graphics','Event and promotional signage']},
    contractors:{name:'Contractors & Construction',intro:'Job-site identification, fleet branding and repeatable project signage.',categories:['Construction signs','Fleet Services','Vehicles'],needs:['Construction and job-site signs','Truck / van graphics','USDOT lettering','Repeat signage for new locations']},
    realtors:{name:'Realtors & Property Sales',intro:'Fast, repeatable signs and event graphics for listings and open houses.',categories:['Signs','Events'],needs:['Yard and directional signs','A-frame inserts','Banners and event signage','Reusable brand artwork']},
    fleets:{name:'Fleets & Service Companies',intro:'Keep vehicles consistent while making repeat orders easy.',categories:['Fleet Services','Vehicles'],needs:['Full / partial wraps','Large decals and lettering','USDOT sets','Saved fleet brand assets']},
    storefronts:{name:'Storefronts & Retail',intro:'Windows, rigid signs, tint and promotional displays for customer-facing locations.',categories:['Storefront'],needs:['Window graphics','Storefront tint','A-frame inserts','ACM / rigid signs']},
    events:{name:'Events & Promotions',intro:'Portable signage, apparel and graphics for launches, shows and activations.',categories:['Events','Apparel'],needs:['Banners and roll-ups','Foam boards','A-frame inserts','Printed / embroidered apparel']},
    property:{name:'Property Management',intro:'A repeatable system for multiple buildings, tenants and locations.',categories:['Signs','Storefront','Construction signs'],needs:['Directional and property signs','Window graphics / tint','Unit and site updates','Saved location notes']},
    startups:{name:'New Businesses',intro:'A guided path from logo and storefront needs to launch-day signage.',categories:['Storefront','Signs','Events','Apparel'],needs:['Storefront graphics','Exterior / interior signs','Launch banners','Staff apparel']}
  };
  function industryCards(){return Object.entries(industryProfiles).map(([slug,item])=>`<a class="panel industry-card" href="/industries/${slug}"><div class="eyebrow">INDUSTRY GUIDE</div><h2>${esc(item.name)}</h2><p class="muted">${esc(item.intro)}</p><span class="link">See recommended products →</span></a>`).join('');}
  function industriesView(){setPublicSeo();page('Solutions by industry',`<p class="muted mb">Start with the business problem instead of guessing a material or product name.</p><div class="industry-grid">${industryCards()}</div><section class="custom-quote-cta mt"><div><div class="eyebrow">QUICK PRODUCT FINDER</div><h2>Still not sure?</h2><p>Tell us where the graphics are going and we will take you to the best product family to start with.</p></div><button class="btn primary" data-action="help-choose">Help me choose</button></section>`);}
  function industryView(slug){
    const item=industryProfiles[slug];if(!item)return industriesView();
    const products=state.catalog.products.filter(p=>(p.config.storefront_categories||[]).some(category=>item.categories.includes(category))).slice(0,12);
    page(item.name,`<section class="industry-hero panel"><div class="eyebrow">BUILT FOR YOUR WORKFLOW</div><h2>${esc(item.intro)}</h2><div class="industry-needs">${item.needs.map(need=>`<span>✓ ${esc(need)}</span>`).join('')}</div></section><div class="all-products-grid mt">${products.map(p=>`<article class="panel product-catalog-card"><a class="catalog-image-link" href="${productPath(p)}">${productImage(p,'catalog')}</a><h2 class="mt"><a href="${productPath(p)}">${esc(publicProductName(p))}</a></h2><p class="muted mt">${esc(p.config.description)}</p><a class="btn primary mt" href="${productPath(p)}">Customize & add to project</a></article>`).join('')}</div><section class="custom-quote-cta mt"><div><div class="eyebrow">MULTI-LOCATION / COMMERCIAL</div><h2>Need repeatable ordering?</h2><p>Customer accounts can save company, location, fleet, brand, PO and authorized-buyer notes for future projects.</p></div><a class="btn light" href="/account">Set up my account</a></section>`);
  }
  function showProductFinder(){showModal('Help me choose',`<form data-form="product-finder" class="stack"><div class="notice info">You do not need to know the material name. Pick what you are branding and we will take you to the strongest product category to start with.</div>${select('surface','What are you branding?',[['storefront','Storefront / windows'],['vehicle','Car, truck or van'],['fleet','Multiple vehicles'],['construction','Job site / construction'],['event','Event / temporary promotion'],['apparel','Shirts, polos, hats or hoodies'],['sign','General sign / rigid panel'],['sticker','Stickers / decals']],'storefront')}<label class="field"><span>Anything special?</span><textarea name="notes" maxlength="1000" placeholder="Installation, multiple locations, unusual surface, deadline, etc."></textarea></label>${formFooter('Show my best starting point')}</form>`);}
  function sampleKitModal(){showModal('Request a material sample kit',`<form data-form="sample-kit-request" class="stack"><div class="notice info">Tell us what you are comparing. We will review availability, contents and any charge before anything is prepared or shipped.</div><div class="fields">${input('customer_name','Name',state.customer?.name||'','text','required maxlength="120"')}${input('customer_email','Email',state.customer?.email||'','email','required maxlength="254"')}</div>${select('interest','What do you want to compare?',[['mixed','Mixed sign & print materials'],['window','Window vinyl / perforated vinyl / tint'],['vinyl','Vinyl, laminate and reflective options'],['boards','Rigid boards / ACM / foam board'],['wrap','Vehicle wrap materials'],['apparel','Apparel / embroidery examples']],'mixed')}<label class="field"><span>Notes</span><textarea name="notes" maxlength="2000" placeholder="Project type, quantities, colors, durability questions, or shipping/pickup preference."></textarea></label>${formFooter('Request sample kit')}</form>`);}
  async function accountView(){
    const r=await api('/api/customer');state.customer=r.customer;
    if(!state.customer){
      page('Sign in',`<div class="account-grid"><section class="panel"><h2>Customer sign in</h2><form data-form="customer-login" class="stack mt">${input('email','Email','','email','required autocomplete="email"')}${input('password','Password','','password','required autocomplete="current-password" maxlength="128"')}${formFooter('Sign in')}</form><p class="field-hint">For help accessing your account, contact the shop.</p></section><section class="panel"><h2>Create a customer account</h2><form data-form="customer-register" class="stack mt">${input('name','Name','','text','required maxlength="120" autocomplete="name"')}${input('email','Email','','email','required autocomplete="email"')}${input('password','Password (12+ characters)','','password','required minlength="12" maxlength="128" autocomplete="new-password"')}${formFooter('Create account')}</form></section></div>`);
      app.querySelector('main').insertAdjacentHTML('beforeend',`<section class="panel mt"><h2>Wholesale account</h2><p class="muted mt">${state.wholesaleToken?'Signed in as '+esc(state.wholesaleName):'Sign in with your approved wholesale username and password.'}</p><button class="btn light mt" data-action="${state.wholesaleToken?'wholesale-clear':'wholesale-login'}">${state.wholesaleToken?'Sign out of wholesale':'Wholesale sign in'}</button></section>`);
      return;
    }
    const profile=r.profile||{},assets=r.saved_assets||[];
    page('Your account',`<section class="account-hero panel"><div><div class="eyebrow">CUSTOMER WORKSPACE</div><h2>${esc(state.customer.name)}</h2><p class="muted">${esc(state.customer.email)}</p></div><div class="row wrap"><button class="btn light" data-action="sample-kit">Request sample kit</button><button class="btn light" data-action="customer-logout">Sign out</button></div></section>
      <div class="account-dashboard mt">
        <section><h2 class="mb">Your submitted projects</h2>${r.orders.length?r.orders.map(o=>`<article class="panel mb"><div class="row between wrap"><div><strong>${esc(o.number||('JOB-'+String(o.id).padStart(4,'0')))} · ${esc(o.title)}</strong><p class="muted">${esc(String(o.stage||'received').replaceAll('_',' '))}${o.due_date?' · requested '+esc(o.due_date):''}${o.priority==='rush'?' · rush requested':''}</p></div><div class="row wrap"><button class="btn light" data-action="customer-reorder" data-id="${o.id}">Reorder</button><button class="btn primary" data-action="customer-order" data-id="${o.id}">View project</button></div></div></article>`).join(''):'<p class="panel">Projects submitted while signed in will appear here.</p>'}</section>
        <aside class="stack"><section class="panel"><h3>Saved artwork</h3><p class="field-hint mt-sm">Artwork from your submitted projects is kept here for reference and future reorders. Reorders still receive a new proof.</p>${assets.length?assets.slice(0,12).map(a=>`<a class="file-row" href="/api/customer/assets/${a.id}" target="_blank" rel="noopener"><div class="grow"><strong>${esc(a.filename)}</strong><div class="muted tiny">${esc(a.job_number)} · ${(a.size/1048576).toFixed(2)} MB</div></div><span>↗</span></a>`).join(''):'<p class="muted mt">No saved artwork yet.</p>'}</section></aside>
      </div>
      <section class="panel mt"><div class="row between wrap"><div><div class="eyebrow">COMMERCIAL PROFILE</div><h2>Make repeat ordering faster.</h2></div><span class="badge ${profile.account_type==='commercial'?'green':''}">${profile.account_type==='commercial'?'Commercial account':'Standard account'}</span></div><form data-form="customer-profile" class="stack mt">${select('account_type','Account type',[['standard','Standard customer'],['commercial','Commercial / multi-project']],profile.account_type||'standard')}<div class="fields">${input('company','Company / organization',profile.company||'','text','maxlength="160"')}${input('po_number','Default PO number (optional)',profile.po_number||'','text','maxlength="120"')}</div><label class="field"><span>Locations / properties</span><textarea name="locations" maxlength="4000" placeholder="Store names, addresses, unit numbers, property notes...">${esc(profile.locations||'')}</textarea></label><label class="field"><span>Fleet / vehicles</span><textarea name="fleet_notes" maxlength="4000" placeholder="Vehicle numbers, year/make/model, assigned locations...">${esc(profile.fleet_notes||'')}</textarea></label><label class="field"><span>Brand standards / saved instructions</span><textarea name="brand_notes" maxlength="4000" placeholder="Brand colors, approved logo notes, repeat production instructions...">${esc(profile.brand_notes||'')}</textarea></label><div class="fields"><label class="field"><span>Authorized buyers / contacts</span><textarea name="authorized_buyers" maxlength="2000">${esc(profile.authorized_buyers||'')}</textarea></label><label class="field"><span>Tax-exempt certificate / reference</span><textarea name="tax_exempt_note" maxlength="1000">${esc(profile.tax_exempt_note||'')}</textarea></label></div><p class="field-hint">Tax-exempt information is a reference for shop verification only. It does not automatically remove tax from checkout.</p>${formFooter('Save account profile')}</form></section>`);
  }
  const loadImage=src=>new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(new Error('Unable to load this image. Use a PNG, JPEG or WebP file.'));im.src=src;});
  const layer=()=>draft.sides[draft.side];
  function draw(){
    const canvas=$('#studio-canvas');if(!canvas||!draft)return;const c=canvas.getContext('2d'),d=layer();c.clearRect(0,0,700,700);c.fillStyle='#f2f5f5';c.fillRect(0,0,700,700);
    const isShirt=product(draft.product_id)?.config.finished_apparel;
    if(isShirt){if(draft.side==='front'&&bgImage)c.drawImage(bgImage,80,0,540,700);else {c.fillStyle=product(draft.product_id).config.shirt_colors[draft.color]||'#fff';c.strokeStyle='#829094';c.lineWidth=2;c.beginPath();c.moveTo(230,100);c.lineTo(145,125);c.lineTo(60,250);c.lineTo(155,310);c.lineTo(200,245);c.lineTo(200,625);c.lineTo(500,625);c.lineTo(500,245);c.lineTo(545,310);c.lineTo(640,250);c.lineTo(555,125);c.lineTo(470,100);c.quadraticCurveTo(350,155,230,100);c.closePath();c.fill();c.stroke();}}
    else {c.fillStyle='white';c.fillRect(50,80,600,540);c.strokeStyle='#ccd7d8';c.strokeRect(50,80,600,540);}
    c.save();c.translate(d.x,d.y);c.rotate(d.rotation*Math.PI/180);if(artImage){const h=d.scale*artImage.height/artImage.width;c.drawImage(artImage,-d.scale/2,-h/2,d.scale,h);}c.restore();
    if(d.text){c.fillStyle=d.textColor;c.font=`bold ${d.fontSize*96/72}px ${d.font}`;c.textAlign='center';c.fillText(d.text,d.textX,d.textY,550);}
    c.fillStyle='#263638';c.font='15px sans-serif';c.textAlign='center';c.fillText(`${draft.side==='back'?'Back':'Front'} · Placement preview — final proof follows`,350,685);
  }
  async function studioViewLegacy(options={}){
    const existing=options.id?await getDesign(options.id):null;
    const p=product(options.product_id||existing?.product_id||state.selectedProduct)||state.catalog.products[0];
    draft=existing||{id:crypto.randomUUID(),product_id:p.id,name:publicProductName(p)+' design',color:options.color||'White',side:'front',sides:{}};
    draft.projectKey=options.projectKey||draft.projectKey||null;
    for(const side of ['front','back'])draft.sides[side]??={image:null,x:350,y:335,scale:190,rotation:0,text:'',textX:350,textY:445,textColor:'#16b2b4',fontSize:24,font:'sans-serif'};
    artImage=layer().image?await loadImage(layer().image):null;bgImage=p.config.finished_apparel?await loadImage(imageFor(draft.color)):null;
    page('Design studio',`<p class="muted mb">Upload your artwork, position it, and add text. Save a draft or attach it to your project.</p><div class="studio-layout"><section class="panel"><canvas id="studio-canvas" width="700" height="700" aria-label="Artwork placement preview"></canvas><p class="field-hint">Drag artwork to position it. A shop-reviewed proof is required before production.</p></section><section class="panel stack"><h2>${esc(publicProductName(p))}</h2><label class="field"><span>Design name</span><input id="design-name" maxlength="100" value="${esc(draft.name)}"></label>${p.config.finished_apparel?`<label class="field"><span>View</span><select id="design-side"><option value="front" ${draft.side==='front'?'selected':''}>Front</option><option value="back" ${draft.side==='back'?'selected':''}>Back</option></select></label>`:''}<label class="field"><span>Upload artwork (PNG or JPEG; max 50 MB)</span><input id="design-upload" type="file" accept="image/png,image/jpeg"></label><label class="field"><span>Artwork size</span><input data-layer="scale" type="range" min="30" max="500" value="${layer().scale}"></label><label class="field"><span>Rotation</span><input data-layer="rotation" type="range" min="-180" max="180" value="${layer().rotation}"></label><div class="fields"><label class="field"><span>Horizontal position</span><input data-layer="x" type="range" min="60" max="640" value="${layer().x}"></label><label class="field"><span>Vertical position</span><input data-layer="y" type="range" min="90" max="620" value="${layer().y}"></label></div><label class="field"><span>Add text</span><input data-layer="text" maxlength="80" value="${esc(layer().text)}"></label><div class="fields"><label class="field"><span>Text color</span><input data-layer="textColor" type="color" value="${layer().textColor}"></label><label class="field"><span>Text size (pt)</span><input data-layer="fontSize" type="number" min="8" max="300" step="1" inputmode="numeric" value="${layer().fontSize}"></label></div><label class="field"><span>Text style</span><select data-layer="font">${['sans-serif','serif','monospace'].map(f=>`<option ${layer().font===f?'selected':''}>${f}</option>`).join('')}</select></label><label class="field"><span>Text height</span><input data-layer="textY" type="range" min="150" max="600" value="${layer().textY}"></label><button class="btn light" data-action="studio-clear-art">Remove artwork</button><button class="btn primary" data-action="studio-save">Save ${draft.projectKey?'to project':'draft'}</button><p class="field-hint">Text size is saved in points. Drafts are stored in this browser; production files can also be uploaded when submitting your project.</p></section></div><section id="saved-designs" class="mt"></section>`);
    draw();
    $$('[data-layer]').forEach(e=>e.addEventListener('input',()=>{layer()[e.dataset.layer]=['text','textColor','font'].includes(e.dataset.layer)?e.value:Number(e.value);draw();}));
    $('#design-upload').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;if(!['image/png','image/jpeg'].includes(f.type)||f.size>50*1024*1024)throw new Error('Choose a PNG or JPEG image up to 50 MB.');const url=URL.createObjectURL(f);let im;try{im=await loadImage(url);}finally{URL.revokeObjectURL(url);}const canvas=document.createElement('canvas'),scale=Math.min(1,2500/Math.max(im.width,im.height));canvas.width=im.width*scale;canvas.height=im.height*scale;canvas.getContext('2d').drawImage(im,0,0,canvas.width,canvas.height);layer().image=canvas.toDataURL('image/png');layer().original=f;artImage=await loadImage(layer().image);draw();}catch(e){toast(e.message,true);}};
    if($('#design-side'))$('#design-side').onchange=async e=>{draft.name=$('#design-name').value;draft.side=e.target.value;await saveDesign(draft);await studioView({id:draft.id});};
    const canvas=$('#studio-canvas');let drag=false;canvas.onpointerdown=e=>{drag=true;canvas.setPointerCapture(e.pointerId);};canvas.onpointerup=()=>drag=false;canvas.onpointercancel=()=>drag=false;canvas.onpointermove=e=>{if(!drag)return;const r=canvas.getBoundingClientRect();layer().x=Math.max(60,Math.min(640,(e.clientX-r.left)*700/r.width));layer().y=Math.max(90,Math.min(620,(e.clientY-r.top)*700/r.height));draw();};
    const saved=await designs();$('#saved-designs').innerHTML=`<h2>Saved designs</h2><div class="row wrap mt">${saved.map(d=>`<button class="btn light" data-action="studio-load" data-id="${esc(d.id)}">${esc(d.name)}</button>`).join('')||'<p>No saved designs yet.</p>'}</div>`;
  }
  let studioSelection='artwork';
  const clamp=(value,min,max)=>Math.max(min,Math.min(max,Number(value)||0));
  function newStudioSide(width,height){return {image:null,original:null,art:{x:width/2,y:height/2,width:Math.max(.5,width*.55),rotation:0},text:{value:'',x:width/2,y:height*.72,points:24,rotation:0,color:'#16b2b4',font:'Arial, sans-serif',align:'center',bold:true},shapes:[]};}
  function studioViewport(canvas,width,height,padding=Math.max(52,Math.min(canvas.width,canvas.height)*.065)){const scale=Math.min((canvas.width-padding*2)/width,(canvas.height-padding*2)/height);return {scale,x:(canvas.width-width*scale)/2,y:(canvas.height-height*scale)/2,width:width*scale,height:height*scale};}
  function shapePath(c,type,x,y,w,h){c.beginPath();if(type==='circle'){c.ellipse(x,y,w/2,h/2,0,0,Math.PI*2);}else if(type==='star'){for(let i=0;i<10;i++){const r=i%2?w*.22:w*.5,a=-Math.PI/2+i*Math.PI/5,px=x+Math.cos(a)*r,py=y+Math.sin(a)*r*(h/w);i?c.lineTo(px,py):c.moveTo(px,py);}c.closePath();}else if(type==='arrow'){c.moveTo(x-w/2,y-h*.2);c.lineTo(x+w*.08,y-h*.2);c.lineTo(x+w*.08,y-h/2);c.lineTo(x+w/2,y);c.lineTo(x+w*.08,y+h/2);c.lineTo(x+w*.08,y+h*.2);c.lineTo(x-w/2,y+h*.2);c.closePath();}else if(type==='badge'){for(let i=0;i<16;i++){const r=i%2?w*.42:w*.5,a=i*Math.PI/8,px=x+Math.cos(a)*r,py=y+Math.sin(a)*r*(h/w);i?c.lineTo(px,py):c.moveTo(px,py);}c.closePath();}else{roundedPath(c,x-w/2,y-h/2,w,h,Math.min(w,h)*.1);}}
  function drawStudioShape(c,shape,toX,toY,scale){c.save();c.translate(toX(shape.x),toY(shape.y));c.rotate((shape.rotation||0)*Math.PI/180);shapePath(c,shape.type,0,0,shape.width*scale,shape.height*scale);c.fillStyle=shape.color;c.fill();c.restore();}
  function renderStudio(canvas,design,sideName,production=false){
    const side=design.sides[sideName],width=Number(design.width),height=Number(design.height),c=canvas.getContext('2d');c.clearRect(0,0,canvas.width,canvas.height);c.imageSmoothingEnabled=true;c.imageSmoothingQuality='high';const view=production?{scale:canvas.width/width,x:0,y:0,width:canvas.width,height:canvas.height}:studioViewport(canvas,width,height),toX=x=>view.x+x*view.scale,toY=y=>view.y+y*view.scale,ui=Math.max(.8,Math.min(canvas.width,canvas.height)/900);
    if(!production){c.fillStyle='#e7eeee';c.fillRect(0,0,canvas.width,canvas.height);c.fillStyle='#fff';c.fillRect(view.x,view.y,view.width,view.height);c.strokeStyle='#7f9795';c.lineWidth=ui;c.fillStyle='#526565';c.font=`${12*ui}px sans-serif`;c.textAlign='center';for(let inch=0;inch<=Math.floor(width);inch++){const x=toX(inch);c.beginPath();c.moveTo(x,view.y-7*ui);c.lineTo(x,view.y);c.stroke();c.fillText(String(inch),x,view.y-11*ui);}c.textAlign='right';for(let inch=0;inch<=Math.floor(height);inch++){const y=toY(inch);c.beginPath();c.moveTo(view.x-7*ui,y);c.lineTo(view.x,y);c.stroke();c.fillText(String(inch),view.x-11*ui,y+4*ui);}}
    c.save();c.beginPath();c.rect(view.x,view.y,view.width,view.height);c.clip();
    if(studioArtImage&&side.image){const art=side.art,drawWidth=art.width*view.scale,drawHeight=drawWidth*studioArtImage.height/studioArtImage.width;c.save();c.translate(toX(art.x),toY(art.y));c.rotate(art.rotation*Math.PI/180);c.drawImage(studioArtImage,-drawWidth/2,-drawHeight/2,drawWidth,drawHeight);c.restore();}
    for(const shape of side.shapes)drawStudioShape(c,shape,toX,toY,view.scale);
    const text=side.text;if(text.value){c.save();c.translate(toX(text.x),toY(text.y));c.rotate(text.rotation*Math.PI/180);c.fillStyle=text.color;c.textAlign=text.align;c.textBaseline='middle';c.font=`${text.bold?'700':'400'} ${text.points/72*view.scale}px ${text.font}`;c.fillText(text.value,0,0,view.width*.9);c.restore();}
    c.restore();if(!production){c.strokeStyle='#607c79';c.lineWidth=2*ui;c.strokeRect(view.x,view.y,view.width,view.height);c.fillStyle='#263638';c.font=`${12*ui}px sans-serif`;c.textAlign='center';c.fillText(`${width} × ${height} in finished area · artwork clips at edge`,canvas.width/2,canvas.height-12*ui);}
  }
  function studioControls(side){
    if(studioSelection==='text')return `<div class="stack studio-controls">${input('studio_text','Text',side.text.value,'text','maxlength="120" data-studio="text.value"')}${select('studio_font','Font',[['Arial, sans-serif','Arial'],['Impact, sans-serif','Impact'],['Georgia, serif','Georgia'],['"Arial Narrow", Arial, sans-serif','Arial Narrow'],['"Trebuchet MS", sans-serif','Trebuchet'],['"Courier New", monospace','Courier New']],side.text.font)}<div class="fields three">${input('studio_text_points','Size (pt)',side.text.points,'number','min="8" max="300" step="1" data-studio="text.points"')}${input('studio_text_x','X (in)',side.text.x,'number','min="0" step="0.01" data-studio="text.x"')}${input('studio_text_y','Y (in)',side.text.y,'number','min="0" step="0.01" data-studio="text.y"')}</div><div class="fields">${input('studio_text_rotation','Rotation',side.text.rotation,'number','min="-180" max="180" step="1" data-studio="text.rotation"')}${input('studio_text_color','Color',side.text.color,'color','data-studio="text.color"')}</div><div class="row wrap"><button type="button" class="btn light small" data-action="studio-align" data-target="text" data-align="center">Center</button><button type="button" class="btn light small" data-action="studio-toggle-bold">${side.text.bold?'Regular weight':'Bold'}</button></div></div>`;
    if(studioSelection.startsWith('shape:')){const index=Number(studioSelection.split(':')[1]),shape=side.shapes[index];if(!shape)return '<p class="field-hint">Choose a shape below.</p>';return `<div class="stack studio-controls"><strong>${esc(shape.type.replaceAll('_',' '))}</strong><div class="fields">${input('studio_shape_width','Width (in)',shape.width,'number','min="0.1" step="0.01" data-studio="shape.width"')}${input('studio_shape_height','Height (in)',shape.height,'number','min="0.1" step="0.01" data-studio="shape.height"')}</div><div class="fields three">${input('studio_shape_x','X (in)',shape.x,'number','min="0" step="0.01" data-studio="shape.x"')}${input('studio_shape_y','Y (in)',shape.y,'number','min="0" step="0.01" data-studio="shape.y"')}${input('studio_shape_rotation','Rotation',shape.rotation,'number','min="-180" max="180" step="1" data-studio="shape.rotation"')}</div>${input('studio_shape_color','Color',shape.color,'color','data-studio="shape.color"')}<div class="row wrap"><button type="button" class="btn light small" data-action="studio-align" data-target="shape" data-align="center">Center</button><button type="button" class="btn danger small" data-action="studio-delete-shape">Delete shape</button></div></div>`;}
    return `<div class="stack studio-controls"><label class="field"><span>Upload artwork (PNG or JPEG; max 50 MB)</span><input id="studio-upload" type="file" accept="image/png,image/jpeg"></label><div class="fields">${input('studio_art_width','Artwork width (in)',side.art.width,'number','min="0.1" step="0.01" data-studio="art.width"')}${input('studio_art_rotation','Rotation',side.art.rotation,'number','min="-180" max="180" step="1" data-studio="art.rotation"')}</div><div class="fields">${input('studio_art_x','X (in)',side.art.x,'number','min="0" step="0.01" data-studio="art.x"')}${input('studio_art_y','Y (in)',side.art.y,'number','min="0" step="0.01" data-studio="art.y"')}</div><div class="row wrap"><button type="button" class="btn light small" data-action="studio-align" data-target="artwork" data-align="center">Center</button><button type="button" class="btn light small" data-action="studio-fit-art">Fit to area</button><button type="button" class="btn ghost small" data-action="studio-clear-art">Remove</button></div></div>`;
  }
  let studioArtImage=null;
  async function studioView(options={}){
    const existing=options.id?await getDesign(options.id):null,item=project.find(x=>x.key===options.projectKey)||project.find(x=>x.design_id===options.id),p=product(item?.product_id||options.product_id||existing?.product_id||state.selectedProduct)||state.catalog.products[0],width=Math.max(.1,Number(existing?.width||item?.width||p.config.default_width||12)),height=Math.max(.1,Number(existing?.height||item?.height||p.config.default_height||12));
    draft=existing?.studio_version===2?existing:{id:existing?.id||crypto.randomUUID(),studio_version:2,product_id:p.id,projectKey:item?.key||options.projectKey||existing?.projectKey||null,name:existing?.name||publicProductName(p)+' design',width,height,color:options.color||existing?.color||'White',side:'front',sides:{front:newStudioSide(width,height),back:newStudioSide(width,height)}};draft.projectKey=item?.key||options.projectKey||draft.projectKey;draft.side=draft.side||'front';const side=draft.sides[draft.side];studioArtImage=side.image?await loadImage(side.image):null;
    const ratio=width/height,canvasWidth=ratio>=1?1600:Math.max(700,Math.round(1600*ratio)),canvasHeight=ratio>=1?Math.max(700,Math.round(1600/ratio)):1600;
    page('Design studio',`<div class="studio-heading row between wrap mb"><div><p class="eyebrow">TRUE-SIZE ARTBOARD</p><h2>${esc(publicProductName(p))} · ${width} × ${height} in</h2></div><div class="row wrap">${p.config.finished_apparel?select('studio_side','View',[['front','Front'],['back','Back']],draft.side):''}${canvaButton(width,height,publicProductName(p))}<button class="btn primary" data-action="studio-save">Save to project</button></div></div>${canvaGuide(width,height,publicProductName(p))}<div class="studio-layout mt"><section class="panel"><canvas id="studio-canvas" width="${canvasWidth}" height="${canvasHeight}" aria-label="True-size design artboard"></canvas><p class="field-hint">Drag the selected layer on the artboard. Numeric controls use inches; text uses points.</p></section><section class="panel stack"><div class="segmented studio-layer-tabs"><button data-action="studio-select-layer" data-layer="artwork" class="${studioSelection==='artwork'?'active':''}">Artwork</button><button data-action="studio-select-layer" data-layer="text" class="${studioSelection==='text'?'active':''}">Text</button><button data-action="studio-select-layer" data-layer="shapes" class="${studioSelection.startsWith('shape:')?'active':''}">Shapes</button></div><div id="studio-controls">${studioControls(side)}</div><div class="divider"></div><div><h3>Shapes & clipart</h3><div class="shape-library mt-sm">${[['rectangle','Rectangle'],['circle','Circle'],['star','Star'],['arrow','Arrow'],['badge','Burst']].map(([type,label])=>`<button class="shape-button" data-action="studio-add-shape" data-shape="${type}"><span class="shape-swatch ${type}"></span>${label}</button>`).join('')}</div>${side.shapes.length?`<div class="shape-layers mt">${side.shapes.map((shape,index)=>`<button class="btn light small ${studioSelection===`shape:${index}`?'active':''}" data-action="studio-select-layer" data-layer="shape:${index}">${esc(shape.type)} ${index+1}</button>`).join('')}</div>`:''}</div><p class="field-hint">All layers are saved with their dimensions and included in the production layout sent to the shop.</p></section></div>`);
    const canvas=$('#studio-canvas'),redraw=()=>renderStudio(canvas,draft,draft.side);redraw();
    document.querySelectorAll('[data-studio]').forEach(control=>control.addEventListener('input',()=>{const [group,key]=control.dataset.studio.split('.'),target=group==='shape'?side.shapes[Number(studioSelection.split(':')[1])]:side[group];target[key]=['value','color'].includes(key)?control.value:Number(control.value);redraw();}));
    const fontSelect=$('select[name="studio_font"]');if(fontSelect)fontSelect.onchange=()=>{side.text.font=fontSelect.value;redraw();};
    const upload=$('#studio-upload');if(upload)upload.onchange=async event=>{try{const file=event.target.files[0];if(!file)return;if(!['image/png','image/jpeg'].includes(file.type)||file.size>50*1024*1024)throw new Error('Choose a PNG or JPEG image up to 50 MB.');const url=URL.createObjectURL(file);let image;try{image=await loadImage(url);}finally{URL.revokeObjectURL(url);}const normalized=document.createElement('canvas'),scale=Math.min(1,4096/Math.max(image.width,image.height));normalized.width=Math.max(1,Math.round(image.width*scale));normalized.height=Math.max(1,Math.round(image.height*scale));const context=normalized.getContext('2d');context.imageSmoothingEnabled=true;context.imageSmoothingQuality='high';context.drawImage(image,0,0,normalized.width,normalized.height);side.image=normalized.toDataURL('image/png');side.original=file;studioArtImage=await loadImage(side.image);redraw();}catch(error){toast(error.message,true);}};
    const sideSelect=$('select[name="studio_side"]');if(sideSelect)sideSelect.onchange=async()=>{draft.side=sideSelect.value;studioSelection='artwork';await saveDesign(draft);await studioView({id:draft.id,projectKey:draft.projectKey});};
    let dragging=false;canvas.onpointerdown=event=>{dragging=true;canvas.setPointerCapture(event.pointerId);};canvas.onpointerup=()=>dragging=false;canvas.onpointercancel=()=>dragging=false;canvas.onpointermove=event=>{if(!dragging)return;const rect=canvas.getBoundingClientRect(),px=(event.clientX-rect.left)*canvas.width/rect.width,py=(event.clientY-rect.top)*canvas.height/rect.height,view=studioViewport(canvas,width,height),x=clamp((px-view.x)/view.scale,0,width),y=clamp((py-view.y)/view.scale,0,height);if(studioSelection==='text'){side.text.x=x;side.text.y=y;}else if(studioSelection.startsWith('shape:')){const shape=side.shapes[Number(studioSelection.split(':')[1])];if(shape){shape.x=x;shape.y=y;}}else{side.art.x=x;side.art.y=y;}redraw();};
  }
  function roundedPath(c,x,y,w,h,r){r=Math.min(r,w/2,h/2);c.beginPath();c.moveTo(x+r,y);c.arcTo(x+w,y,x+w,y+h,r);c.arcTo(x+w,y+h,x,y+h,r);c.arcTo(x,y+h,x,y,r);c.arcTo(x,y,x+w,y,r);c.closePath();}
  function renderContour(canvas,design,proof=true){
    const c=canvas.getContext('2d'),w=canvas.width,h=canvas.height,s=design.settings,margin=Math.max(18,Math.min(w,h)*.13),border=Math.max(2,Math.min(w,h)*(Number(s.border)||.125)/Math.max(Number(design.width)||3,Number(design.height)||3));
    c.clearRect(0,0,w,h);if(!contourImage)return;
    const layer=document.createElement('canvas');layer.width=w;layer.height=h;const l=layer.getContext('2d'),availableW=w-margin*2-border*2,availableH=h-margin*2-border*2,scale=Math.min(availableW/contourImage.width,availableH/contourImage.height)*(Number(s.scale)||100)/100,iw=contourImage.width*scale,ih=contourImage.height*scale,x=(w-iw)/2,y=(h-ih)/2;
    l.save();if(s.shape==='circle'){l.beginPath();l.ellipse(w/2,h/2,Math.min(iw,w*.7)/2,Math.min(ih,h*.7)/2,0,0,Math.PI*2);l.clip();}else if(s.shape==='rounded'){roundedPath(l,x,y,iw,ih,Math.min(iw,ih)*.12);l.clip();}l.drawImage(contourImage,x,y,iw,ih);l.restore();
    const coloredMask=color=>{const mask=document.createElement('canvas');mask.width=w;mask.height=h;const m=mask.getContext('2d');m.drawImage(layer,0,0);m.globalCompositeOperation='source-in';m.fillStyle=color;m.fillRect(0,0,w,h);return mask;};
    const outline=(mask,radius)=>{const steps=28;for(let i=0;i<steps;i++){const angle=i/steps*Math.PI*2;c.drawImage(mask,Math.cos(angle)*radius,Math.sin(angle)*radius);}};
    if(proof)outline(coloredMask('#d81b60'),border+Math.max(3,Math.min(w,h)*.006));outline(coloredMask(s.border_color||'#ffffff'),border);c.drawImage(layer,0,0);
  }
  function contourCanvas(design,proof,maxPixels){const ratio=Math.max(.12,Math.min(8,(Number(design.width)||3)/(Number(design.height)||3))),canvas=document.createElement('canvas');if(ratio>=1){canvas.width=maxPixels;canvas.height=Math.max(300,Math.round(maxPixels/ratio));}else{canvas.height=maxPixels;canvas.width=Math.max(300,Math.round(maxPixels*ratio));}renderContour(canvas,design,proof);return canvas;}
  const canvasBlob=(canvas,type='image/png')=>new Promise(resolve=>canvas.toBlob(resolve,type));
  function contourDisclaimer(c,w,h,index){
    c.save();c.fillStyle='rgba(255,255,255,.94)';c.fillRect(0,h-132,w,132);c.fillStyle='#263638';c.textAlign='left';c.font=`700 ${Math.max(18,Math.round(w*.026))}px sans-serif`;c.fillText(`Approximate contour preview / Item ${index}`,36,h-96);c.font=`${Math.max(14,Math.round(w*.018))}px sans-serif`;c.fillText('Pink outline is a customer preview only. Final cut path, bleed, and offset may be adjusted by Tampa Signs before production.',36,h-58);c.fillText('Review the final shop proof before production begins.',36,h-28);c.restore();
  }
  async function contourPreviewFromFile(file,item,index){
    if(!file||!['image/png','image/jpeg'].includes(file.type))return [];
    const src=URL.createObjectURL(file);let image;
    try{image=await loadImage(src);}finally{URL.revokeObjectURL(src);}
    const width=Math.max(1,Number(item.width)||3),height=Math.max(1,Number(item.height)||3),ratio=Math.max(.12,Math.min(8,width/height)),maxPixels=1800,canvas=document.createElement('canvas');
    if(ratio>=1){canvas.width=maxPixels;canvas.height=Math.max(520,Math.round(maxPixels/ratio));}else{canvas.height=maxPixels;canvas.width=Math.max(520,Math.round(maxPixels*ratio));}
    const c=canvas.getContext('2d'),w=canvas.width,h=canvas.height,pad=Math.max(32,Math.min(w,h)*.12),footer=140,availableW=w-pad*2,availableH=h-pad*2-footer,scale=Math.min(availableW/image.width,availableH/image.height),iw=image.width*scale,ih=image.height*scale,x=(w-iw)/2,y=pad+(availableH-ih)/2;
    c.fillStyle='#f7faf9';c.fillRect(0,0,w,h);c.strokeStyle='#ccd7d8';c.lineWidth=2;c.strokeRect(pad*.5,pad*.5,w-pad,h-pad-footer*.45);
    const layer=document.createElement('canvas');layer.width=w;layer.height=h;const l=layer.getContext('2d');l.drawImage(image,x,y,iw,ih);
    const mask=document.createElement('canvas');mask.width=w;mask.height=h;const m=mask.getContext('2d');m.drawImage(layer,0,0);m.globalCompositeOperation='source-in';m.fillStyle='#d81b60';m.fillRect(0,0,w,h);
    const radius=Math.max(8,Math.min(w,h)*.018),steps=36;for(let step=0;step<steps;step++){const angle=step/steps*Math.PI*2;c.drawImage(mask,Math.cos(angle)*radius,Math.sin(angle)*radius);}
    c.drawImage(layer,0,0);c.strokeStyle='#d81b60';c.lineWidth=Math.max(4,Math.min(w,h)*.006);c.strokeRect(x-radius,y-radius,iw+radius*2,ih+radius*2);
    c.fillStyle='#263638';c.font=`700 ${Math.max(16,Math.round(w*.018))}px sans-serif`;c.textAlign='center';c.fillText(`${width} x ${height} in finished size`,w/2,h-footer+28);contourDisclaimer(c,w,h,index+1);
    const blob=await canvasBlob(canvas);return blob?[new File([blob],`item-${index+1}-approximate-contour-preview.png`,{type:'image/png'})]:[];
  }
  async function contourFiles(design,index){
    const files=[];if(design.original)files.push(new File([design.original],`item-${index+1}-original-${design.original.name||'artwork.png'}`,{type:design.original.type||'image/png'}));
    contourImage=await loadImage(design.image);const proof=contourCanvas(design,true,1800),production=contourCanvas(design,false,Math.min(4200,Math.max(1200,Math.round(Math.max(Number(design.width)||3,Number(design.height)||3)*300))));
    files.push(new File([await canvasBlob(proof)],`item-${index+1}-customer-contour-proof.png`,{type:'image/png'}));
    files.push(new File([await canvasBlob(production)],`item-${index+1}-production-art-${design.width}x${design.height}in-${design.settings.shape}-cut.png`,{type:'image/png'}));return files;
  }
  let contourImage=null;
  async function contourView(options={}){
    const item=project.find(x=>x.key===options.projectKey)||project.find(x=>x.contour_design_id===options.id),existing=options.id?await getDesign(options.id):null,p=product(item?.product_id||options.product_id||state.selectedProduct);
    draft=existing||{id:crypto.randomUUID(),mode:'contour',product_id:p.id,projectKey:item?.key||options.projectKey,width:Number(item?.width)||3,height:Number(item?.height)||3,image:null,original:null,settings:{shape:'contour',border:.125,border_color:'#ffffff',scale:100}};draft.projectKey=item?.key||options.projectKey||draft.projectKey;draft.settings??={shape:'contour',border:.125,border_color:'#ffffff',scale:100};contourImage=draft.image?await loadImage(draft.image):null;
    const ratio=Math.max(.12,Math.min(8,draft.width/draft.height)),canvasWidth=ratio>=1?900:Math.max(320,Math.round(900*ratio)),canvasHeight=ratio>=1?Math.max(320,Math.round(900/ratio)):900;
    page('Contour-cut proof',`<p class="muted mb">Build a live proof for ${esc(publicProductName(p))}. The pink edge is the cut line; it will not print.</p><div class="studio-layout"><section class="panel"><div class="contour-stage"><canvas id="contour-canvas" width="${canvasWidth}" height="${canvasHeight}" aria-label="Live contour cut proof"></canvas></div><div class="row between wrap mt"><strong>${esc(draft.width)} × ${esc(draft.height)} in finished size</strong><span class="cut-line-key">Pink line = contour cut</span></div></section><section class="panel stack"><h2>Cut setup</h2><label class="field"><span>Artwork (transparent PNG recommended)</span><input id="contour-upload" type="file" accept="image/png,image/jpeg" ${draft.image?'':'required'}></label>${select('contour_shape','Cut shape',[['contour','Contour around artwork'],['rounded','Rounded rectangle'],['circle','Circle / oval']],draft.settings.shape)}<label class="field"><span>White border / cut offset: <strong id="contour-border-value">${draft.settings.border} in</strong></span><input id="contour-border" type="range" min="0.06" max="0.3" step="0.005" value="${draft.settings.border}"></label><label class="field"><span>Border color</span><input id="contour-color" type="color" value="${draft.settings.border_color}"></label><label class="field"><span>Artwork scale</span><input id="contour-scale" type="range" min="55" max="115" step="1" value="${draft.settings.scale}"></label><div class="notice info">Transparent PNG artwork produces the most accurate contour. JPEG artwork is treated as a rectangular image unless you choose circle or rounded rectangle.</div><button class="btn primary" data-action="contour-save" ${draft.image?'':'disabled'}>Save proof to project</button><p class="field-hint">Your original file, live proof and high-resolution transparent production PNG are attached to the order. The shop verifies the final RIP cut path before production.</p></section></div>`);
    const canvas=$('#contour-canvas'),redraw=()=>renderContour(canvas,draft,true);redraw();
    $('#contour-upload').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;if(!['image/png','image/jpeg'].includes(f.type)||f.size>50*1024*1024)throw new Error('Choose a PNG or JPEG image up to 50 MB.');const url=URL.createObjectURL(f);let im;try{im=await loadImage(url);}finally{URL.revokeObjectURL(url);}const normalized=document.createElement('canvas'),scale=Math.min(1,3000/Math.max(im.width,im.height));normalized.width=Math.max(1,Math.round(im.width*scale));normalized.height=Math.max(1,Math.round(im.height*scale));normalized.getContext('2d').drawImage(im,0,0,normalized.width,normalized.height);draft.image=normalized.toDataURL('image/png');draft.original=f;contourImage=await loadImage(draft.image);$('[data-action="contour-save"]').disabled=false;redraw();}catch(error){toast(error.message,true);}};
    $('#contour-border').oninput=e=>{draft.settings.border=Number(e.target.value);$('#contour-border-value').textContent=e.target.value+' in';redraw();};$('#contour-color').oninput=e=>{draft.settings.border_color=e.target.value;redraw();};$('#contour-scale').oninput=e=>{draft.settings.scale=Number(e.target.value);redraw();};$('select[name="contour_shape"]').onchange=e=>{draft.settings.shape=e.target.value;redraw();};
  }
  const usdotFonts={
    montserrat:{family:'Montserrat, Arial, sans-serif',weight:700},
    league_spartan:{family:'"League Spartan", Arial, sans-serif',weight:700},
    archivo_black:{family:'"Archivo Black", Arial, sans-serif',weight:400},
    roboto_condensed:{family:'"Roboto Condensed", Arial, sans-serif',weight:700},
    oswald:{family:'Oswald, Arial, sans-serif',weight:700},
    barlow_condensed:{family:'"Barlow Condensed", Arial, sans-serif',weight:700},
    anton:{family:'Anton, Impact, sans-serif',weight:400},
    bebas_neue:{family:'"Bebas Neue", Impact, sans-serif',weight:400},
    alfa_slab:{family:'"Alfa Slab One", Rockwell, serif',weight:400},
    black_ops:{family:'"Black Ops One", Impact, sans-serif',weight:400},
    bungee:{family:'Bungee, Impact, sans-serif',weight:400},
    orbitron:{family:'Orbitron, Arial, sans-serif',weight:700},
    righteous:{family:'Righteous, Arial, sans-serif',weight:400},
    graduate:{family:'Graduate, Rockwell, serif',weight:400},
    luckiest_guy:{family:'"Luckiest Guy", Impact, sans-serif',weight:400},
    fredoka:{family:'Fredoka, Arial, sans-serif',weight:700},
    lobster:{family:'Lobster, cursive',weight:400},
    pacifico:{family:'Pacifico, cursive',weight:400},
    permanent_marker:{family:'"Permanent Marker", cursive',weight:400},
    playfair:{family:'"Playfair Display", Georgia, serif',weight:700},
    merriweather:{family:'Merriweather, Georgia, serif',weight:700},
    roboto_slab:{family:'"Roboto Slab", Rockwell, serif',weight:700},
    cinzel:{family:'Cinzel, Georgia, serif',weight:700},
    rye:{family:'Rye, Georgia, serif',weight:400},
    courier_prime:{family:'"Courier Prime", "Courier New", monospace',weight:700},
    bold:{family:'Arial, sans-serif',weight:700},
    condensed:{family:'"Arial Narrow", Arial, sans-serif',weight:700},
    industrial:{family:'Impact, "Arial Black", sans-serif',weight:400},
    serif:{family:'Georgia, serif',weight:700},
    rounded:{family:'"Trebuchet MS", Arial, sans-serif',weight:700},
    highway:{family:'"Arial Black", Arial, sans-serif',weight:400},
    stencil:{family:'Impact, "Arial Black", sans-serif',weight:400},
    monospace:{family:'"Courier New", monospace',weight:700},
    modern:{family:'"Century Gothic", Futura, Arial, sans-serif',weight:700},
    slab:{family:'Rockwell, "Courier New", serif',weight:700}
  };
  function fitUsdotText(context,text,maxWidth,size,font){
    let px=Math.max(12,Math.round(size));context.font=`${font.weight} ${px}px ${font.family}`;
    while(px>12&&context.measureText(text).width>maxWidth){px=Math.floor(px*.94);context.font=`${font.weight} ${px}px ${font.family}`;}
    return px;
  }

  async function usdotPrintFile(item,index){
    const d=item.usdot_design,width=Math.max(1,Number(item.width)||18),height=Math.max(1,Number(item.height)||12),dpi=Math.max(72,Math.min(300,4800/Math.max(width,height))),legacyScale=Math.max(.8,Math.min(1.4,Number(d.font_scale)||1)),points=d.font_sizes||{company:56*legacyScale,phone:30*legacyScale,number:72*legacyScale,licenses:30*legacyScale,location:32*legacyScale};
    const canvas=document.createElement('canvas');canvas.width=Math.round(width*dpi);canvas.height=Math.round(height*dpi);
    const c=canvas.getContext('2d'),font=usdotFonts[d.style]||usdotFonts.montserrat,pad=canvas.width*.035;
    try{await document.fonts.load(`${font.weight} 48px ${font.family}`);await document.fonts.ready;}catch{}
    const defaults={company:{x:50,y:16,rotation:0},logo:{x:50,y:20,rotation:0},phone:{x:50,y:33,rotation:0},number:{x:50,y:51,rotation:0},licenses:{x:50,y:69,rotation:0},location:{x:50,y:85,rotation:0}},positions=d.positions||{};
    const pos=key=>({x:Number(positions[key]?.x??defaults[key].x),y:Number(positions[key]?.y??defaults[key].y),rotation:Number(positions[key]?.rotation??0)});
    c.fillStyle=d.text_color||'#111111';c.textAlign='center';c.textBaseline='middle';
    const drawText=(key,text)=>{
      if(!text)return;const p=pos(key),preferred=Math.max(12,Number(points[key]||24)*dpi/72),px=fitUsdotText(c,text,canvas.width-pad*2,preferred,font);
      c.save();c.translate(canvas.width*p.x/100,canvas.height*p.y/100);c.rotate(p.rotation*Math.PI/180);c.font=`${font.weight} ${px}px ${font.family}`;c.fillText(text,0,0,canvas.width-pad*2);c.restore();
    };
    if((d.identity||'text')==='logo'&&d.logo_data_url){
      const logo=await loadImage(d.logo_data_url),p=pos('logo'),targetWidth=canvas.width*Math.max(.1,Math.min(.95,Number(d.logo_width||42)/100)),ratio=logo.height/Math.max(1,logo.width),targetHeight=targetWidth*ratio;
      c.save();c.translate(canvas.width*p.x/100,canvas.height*p.y/100);c.rotate(p.rotation*Math.PI/180);c.drawImage(logo,-targetWidth/2,-targetHeight/2,targetWidth,targetHeight);c.restore();
    }else drawText('company',String(d.company||'').toUpperCase());
    drawText('phone',String(d.phone||'').toUpperCase());
    drawText('number','USDOT '+String(d.number||'').toUpperCase().replace(/^USDOT\s*/,''));
    drawText('licenses',String(d.licenses||'').toUpperCase());
    drawText('location',String(d.location||'').toUpperCase());
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(!blob)throw new Error('Unable to generate the USDOT print file.');
    return new File([blob],`item-${index+1}-usdot-print-ready-${width}x${height}in.png`,{type:'image/png'});
  }

  async function designFiles(uploadedFiles=[]){
    const files=[...await windowUploads.filesFor(project),...await embroidery.filesFor(project)],imageUploads=uploadedFiles.filter(file=>['image/png','image/jpeg'].includes(file.type));let contourUploadIndex=0;
    for(let i=0;i<project.length;i++){
      if(project[i].usdot_design)files.push(await usdotPrintFile(project[i],i));
      if(product(project[i].product_id)?.config.contour_customizer){const source=imageUploads[Math.min(contourUploadIndex,imageUploads.length-1)];contourUploadIndex+=1;if(source)files.push(...await contourPreviewFromFile(source,project[i],i));}
      if(project[i].contour_design_id){const contour=await getDesign(project[i].contour_design_id);if(contour?.image)files.push(...await contourFiles(contour,i));}
      if(!project[i].design_id)continue;
      const d=await getDesign(project[i].design_id);if(!d)throw new Error('A saved design is missing. Reattach artwork before submitting.');
      if(d.studio_version===2){
        for(const [sideName,side] of Object.entries(d.sides)){
          if(side.original){const extension=(side.original.name?.split('.').pop()||side.original.type?.split('/')[1]||'png').replace('jpeg','jpg');files.push(new File([side.original],`item-${i+1}-${sideName}-original.${extension}`,{type:side.original.type||'application/octet-stream'}));}
          if(!side.image&&!side.text?.value&&!side.shapes?.length)continue;
          let originalUrl=null;try{if(side.original){originalUrl=URL.createObjectURL(side.original);studioArtImage=await loadImage(originalUrl);}else studioArtImage=side.image?await loadImage(side.image):null;}finally{if(originalUrl)URL.revokeObjectURL(originalUrl);}
          const width=Math.max(.1,Number(d.width)),height=Math.max(.1,Number(d.height)),dpi=Math.max(72,Math.min(300,4800/Math.max(width,height)));
          const production=document.createElement('canvas');production.width=Math.max(1,Math.round(width*dpi));production.height=Math.max(1,Math.round(height*dpi));renderStudio(production,d,sideName,true);
          const proofRatio=width/height,proof=document.createElement('canvas');if(proofRatio>=1){proof.width=1600;proof.height=Math.max(420,Math.round(1600/proofRatio));}else{proof.height=1600;proof.width=Math.max(420,Math.round(1600*proofRatio));}renderStudio(proof,d,sideName,false);
          files.push(new File([await canvasBlob(proof)],`item-${i+1}-${sideName}-dimensioned-proof-${width}x${height}in.png`,{type:'image/png'}));
          files.push(new File([await canvasBlob(production)],`item-${i+1}-${sideName}-production-${width}x${height}in-${Math.round(dpi)}dpi.png`,{type:'image/png'}));
        }
        continue;
      }
      for(const [side,l] of Object.entries(d.sides)){if(l.original)files.push(new File([l.original],`item-${i+1}-${side}-original.${l.original.type.split('/')[1].replace('jpeg','jpg')}`,{type:l.original.type}));if(l.image||l.text){const canvas=document.createElement('canvas');canvas.width=1400;canvas.height=1400;const c=canvas.getContext('2d');c.scale(2,2);c.fillStyle='white';c.fillRect(0,0,700,700);c.fillStyle='#263638';c.font='14px sans-serif';c.fillText(`Item ${i+1} · ${d.name} · ${side} · Placement reference`,20,30);if(l.image){const im=await loadImage(l.image);c.save();c.translate(l.x,l.y);c.rotate(l.rotation*Math.PI/180);c.drawImage(im,-l.scale/2,-l.scale*im.height/im.width/2,l.scale,l.scale*im.height/im.width);c.restore();}c.fillStyle=l.textColor;c.font=`bold ${l.fontSize*96/72}px ${l.font}`;c.textAlign='center';c.fillText(l.text,l.textX,l.textY,550);files.push(new File([await canvasBlob(canvas)],`item-${i+1}-${side}-placement-reference.png`,{type:'image/png'}));}}
    }
    return files;
  }
  Object.assign(actions,windowUploads.actions,{
    'request-order':add,
    'canva-open':async b=>openCanvaDesign(b.dataset.width,b.dataset.height,b.dataset.label),
    'product-canva':async()=>{await recalculate();const item=state.currentQuoteItems?.[0];if(!item)throw new Error('Complete your options before designing in Canva.');const p=product(item.product_id);if(usesDirectArtwork(p)){toast('For wraps or multiple panes, use Upload Design or Request design help.',true);return;}await openCanvaDesign(item.width,item.height,publicProductName(p));},
    'project-remove':async b=>{project.splice(Number(b.dataset.index),1);persist();await projectView();},
    'embroidery-view':async b=>{const item=project[Number(b.dataset.index)];if(!item?.embroidery_id)throw new Error('The saved embroidery preview is missing. Remove and add the garment again.');showModal('Embroidery preview',`<canvas id="embroidery-modal-canvas" width="800" height="680" class="embroidery-modal-canvas" aria-label="Embroidery preview on garment"></canvas><p class="field-hint mt-sm">Digital representation only. Our shop will digitize your original artwork and provide a proof before production.</p>`,true);await embroidery.show(item);},
    'project-checkout':async()=>{await quoteProject();state.projectCheckout=true;orderModal();window.TampaAnalytics?.track('begin_checkout');await windowUploads.checkoutHint(project);},
    'browse-product':async b=>{state.selectedProduct=Number(b.dataset.id);state.selectedCategory=product(b.dataset.id).config.storefront_categories[0];sessionStorage.setItem('storefront_category',state.selectedCategory);history.pushState(null,'',productPath(product(b.dataset.id)));await calculatorView();},
    'studio-load':async b=>studioView({id:b.dataset.id}),
    'studio-select-layer':async b=>{const side=draft.sides[draft.side];studioSelection=b.dataset.layer==='shapes'?(side.shapes.length?`shape:${side.shapes.length-1}`:'artwork'):b.dataset.layer;await saveDesign(draft);await studioView({id:draft.id,projectKey:draft.projectKey});},
    'studio-add-shape':async b=>{const side=draft.sides[draft.side],size=Math.max(.5,Math.min(draft.width,draft.height)*.25);side.shapes.push({type:b.dataset.shape,x:draft.width/2,y:draft.height/2,width:size,height:size,rotation:0,color:'#16b2b4'});studioSelection=`shape:${side.shapes.length-1}`;await saveDesign(draft);await studioView({id:draft.id,projectKey:draft.projectKey});},
    'studio-delete-shape':async()=>{const side=draft.sides[draft.side],index=Number(studioSelection.split(':')[1]);if(Number.isInteger(index))side.shapes.splice(index,1);studioSelection=side.shapes.length?`shape:${side.shapes.length-1}`:'artwork';await saveDesign(draft);await studioView({id:draft.id,projectKey:draft.projectKey});},
    'studio-align':async b=>{const side=draft.sides[draft.side],target=b.dataset.target==='text'?side.text:b.dataset.target==='shape'?side.shapes[Number(studioSelection.split(':')[1])]:side.art;if(target){target.x=draft.width/2;target.y=draft.height/2;}await saveDesign(draft);await studioView({id:draft.id,projectKey:draft.projectKey});},
    'studio-toggle-bold':async()=>{draft.sides[draft.side].text.bold=!draft.sides[draft.side].text.bold;await saveDesign(draft);await studioView({id:draft.id,projectKey:draft.projectKey});},
    'studio-fit-art':async()=>{const art=draft.sides[draft.side].art;art.x=draft.width/2;art.y=draft.height/2;art.width=draft.width*.9;await saveDesign(draft);await studioView({id:draft.id,projectKey:draft.projectKey});},
    'studio-clear-art':async()=>{const side=draft.sides[draft.side];side.image=null;side.original=null;studioArtImage=null;await saveDesign(draft);await studioView({id:draft.id,projectKey:draft.projectKey});},
    'studio-save':async()=>{await saveDesign(draft);const item=project.find(i=>i.key===draft.projectKey);if(item){item.design_id=draft.id;persist();}toast(item?'Design saved to your project.':'Draft saved in this browser.');if(item){history.pushState(null,'','/project');await projectView();}else await studioView({id:draft.id});},
    'customer-logout':async()=>{await api('/api/customer/logout','POST',{});state.customer=null;await accountView();},
    'customer-order':async b=>{const r=await api(`/api/customer/orders/${b.dataset.id}/open`,'POST',{});location.href=r.portal_url;},
    'customer-reorder':async b=>{if(!confirm('Create a new project from this order using current pricing? Previous artwork will be copied as a reference and a new proof will still be required.'))return;const r=await api(`/api/customer/orders/${b.dataset.id}/reorder`,'POST',{});location.href=r.portal_url;},
    'help-choose':()=>showProductFinder(),
    'sample-kit':()=>sampleKitModal(),
  });
  for(const mode of ['login','register'])forms['customer-'+mode]=async(f,d)=>{const r=await api('/api/customer/'+mode,'POST',d);state.customer=r.customer;await accountView();};
  forms['customer-profile']=async(f,d)=>{await api('/api/customer/profile','PUT',d);toast('Account profile saved.');await accountView();};
  forms['product-finder']=async(f,d)=>{const map={storefront:'Storefront',vehicle:'Vehicles',fleet:'Fleet Services',construction:'Construction signs',event:'Events',apparel:'Apparel',sign:'Signs',sticker:'Stickers'},category=map[d.surface]||'Signs';state.selectedCategory=category;sessionStorage.setItem('storefront_category',category);closeModal();history.pushState(null,'','/');await calculatorView();toast('Starting with '+category+'. You can still switch products or request a custom quote.');};
  forms['sample-kit-request']=async(f,d)=>{const r=await api('/api/custom-requests','POST',{customer_name:d.customer_name,customer_email:d.customer_email,phone:'',project_type:'Material sample kit',notes:'Sample interest: '+d.interest+(d.notes?'\n'+d.notes:''),website:'',dimensions:[]});location.href=r.portal_url;};
  return {count:()=>project.length,setupProduct,shirtItem,designFiles,resumeCanva,clear:()=>{project=[];persist();state.projectCheckout=false;},route:async path=>{if(path==='/products')return allProducts();if(path==='/project')return projectView();if(path==='/account')return accountView();if(path==='/industries')return industriesView();if(path.startsWith('/industries/'))return industryView(path.slice('/industries/'.length));},handles:path=>['/products','/project','/account','/industries'].includes(path)||path.startsWith('/industries/')};
}
