const promotions = [
  {label:'Sticker packs',title:'Build a sticker pack.',description:'Mix designs, sizes and optional headers in one bundle.',cta:'Build yours',href:'/products/sticker-packs',image:'sticker-packs-custom.webp?v=20261014-2',alt:'Colorful custom sticker pack product scene'},
  {label:'Vehicle wraps',title:'Make your vehicle impossible to miss.',description:'Plan wraps and graphics for service vehicles, fleets and trailers.',cta:'Explore vehicle wraps',href:'/products/vehicle-wraps',image:'vehicle-wraps-custom-v2.webp?v=20261014-3',alt:'Commercial van partial-wrap concept'},
  {label:'Storefront graphics',title:'Turn your storefront into a sign.',description:'Window graphics, dimensional signs and bold first impressions.',cta:'Explore storefront graphics',href:'/products/window-graphics',image:'storefront-graphics-custom-v2.webp?v=20261014-3',alt:'Cafe dimensional signage and window-vinyl concept'},
];

export function catalogPromo() {
  return `<section class="catalog-promo" aria-roledescription="carousel" aria-label="Featured products">
    <div class="catalog-promo-track" tabindex="0" aria-label="Featured products. Swipe or use arrow keys to browse.">
      ${promotions.map((p,index)=>`<article class="catalog-promo-slide" role="group" aria-roledescription="slide" aria-label="${index+1} of ${promotions.length}: ${p.label}">
        <div class="catalog-promo-copy"><div class="eyebrow">${p.label}</div><h2>${p.title}</h2><p>${p.description}</p><a class="btn primary" href="${p.href}">${p.cta} <span aria-hidden="true">→</span></a></div>
        <a class="catalog-promo-art" href="${p.href}" aria-label="${p.cta}"><img src="/static/products/${p.image}" alt="${p.alt}" width="1200" height="480" loading="eager" decoding="async" ${index===0?'fetchpriority="high"':''} draggable="false"></a>
      </article>`).join('')}
    </div>
    <div class="catalog-promo-controls">
      <button type="button" class="catalog-promo-arrow" data-promo-step="-1" aria-label="Previous featured product">‹</button>
      <div class="catalog-promo-dots" role="group" aria-label="Choose a featured product">${promotions.map((p,index)=>`<button type="button" class="catalog-promo-dot" data-promo-index="${index}" aria-label="Show ${p.label.toLowerCase()}" aria-pressed="${index===0}"><span></span></button>`).join('')}</div>
      <span class="catalog-promo-counter" aria-hidden="true">1 / ${promotions.length}</span>
      <button type="button" class="catalog-promo-arrow" data-promo-step="1" aria-label="Next featured product">›</button>
      <button type="button" class="catalog-promo-toggle" aria-label="Pause automatic slides"><span aria-hidden="true">Ⅱ</span></button>
    </div>
    <span class="sr-only catalog-promo-status" role="status" aria-live="polite"></span>
  </section>`;
}

export function mountCatalogPromo(root) {
  if (!root) return () => {};
  const track=root.querySelector('.catalog-promo-track');
  const slides=[...root.querySelectorAll('.catalog-promo-slide')];
  const dots=[...root.querySelectorAll('[data-promo-index]')];
  const toggle=root.querySelector('.catalog-promo-toggle');
  const counter=root.querySelector('.catalog-promo-counter');
  const status=root.querySelector('.catalog-promo-status');
  const motion=window.matchMedia('(prefers-reduced-motion: reduce)');
  const listeners=[];
  let active=0, playing=!motion.matches, hovered=false, focused=false, visible=true;
  let timer=null, scrollTimer=null, disposed=false;
  const listen=(target,event,handler,options)=>{
    target.addEventListener(event,handler,options);
    listeners.push(()=>target.removeEventListener(event,handler,options));
  };
  const clearTimer=()=>{clearTimeout(timer);timer=null;};
  function update() {
    slides.forEach((slide,index)=>{
      slide.inert=index!==active;
      slide.setAttribute('aria-hidden',String(index!==active));
    });
    dots.forEach((dot,index)=>dot.setAttribute('aria-pressed',String(index===active)));
    counter.textContent=`${active+1} / ${slides.length}`;
    toggle.setAttribute('aria-label',playing?'Pause automatic slides':'Play automatic slides');
    toggle.firstElementChild.textContent=playing?'Ⅱ':'▶';
  }
  function schedule() {
    clearTimer();
    if(disposed)return;
    if(!root.isConnected){dispose();return;}
    if(playing&&!hovered&&!focused&&visible&&!document.hidden) {
      timer=setTimeout(()=>show(active+1),7000);
    }
  }
  function pause() {playing=false;update();schedule();}
  function show(index,manual=false) {
    if(manual)playing=false;
    active=(index+slides.length)%slides.length;
    update();
    track.scrollTo({left:active*track.clientWidth,behavior:motion.matches?'instant':'smooth'});
    if(manual)status.textContent=`${promotions[active].label}, ${active+1} of ${slides.length}`;
    schedule();
  }
  listen(root,'click',event=>{
    const dot=event.target.closest('[data-promo-index]');
    const arrow=event.target.closest('[data-promo-step]');
    if(dot){show(Number(dot.dataset.promoIndex),true);return;}
    if(arrow){show(active+Number(arrow.dataset.promoStep),true);return;}
    if(event.target.closest('.catalog-promo-toggle')){playing=!playing;focused=false;update();schedule();}
  });
  listen(root,'keydown',event=>{
    if(event.key==='ArrowRight'||event.key==='ArrowLeft'){
      event.preventDefault();show(active+(event.key==='ArrowRight'?1:-1),true);
    }
  });
  listen(track,'pointerdown',pause,{passive:true});
  listen(track,'wheel',event=>{if(Math.abs(event.deltaX)>0)pause();},{passive:true});
  listen(track,'scroll',()=>{
    clearTimeout(scrollTimer);
    scrollTimer=setTimeout(()=>{
      if(disposed||!track.clientWidth)return;
      active=Math.max(0,Math.min(slides.length-1,Math.round(track.scrollLeft/track.clientWidth)));
      update();
    },150);
  },{passive:true});
  listen(root,'pointerenter',event=>{if(event.pointerType==='mouse'){hovered=true;schedule();}});
  listen(root,'pointerleave',event=>{if(event.pointerType==='mouse'){hovered=false;schedule();}});
  listen(root,'focusin',event=>{
    focused=true;
    // Do not restart autoplay on a keyboard user who is reading a slide.
    if(!event.target.closest('.catalog-promo-toggle'))playing=false;
    update();schedule();
  });
  listen(root,'focusout',event=>{focused=root.contains(event.relatedTarget);schedule();});
  listen(document,'visibilitychange',schedule);
  listen(motion,'change',()=>{if(motion.matches)playing=false;update();schedule();});
  const resize=new ResizeObserver(()=>track.scrollTo({left:active*track.clientWidth,behavior:'instant'}));
  resize.observe(track);
  const intersection=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;schedule();});
  intersection.observe(root);
  const removal=new MutationObserver(()=>{if(!root.isConnected)dispose();});
  removal.observe(root.closest('#app')||root.parentNode,{childList:true,subtree:true});
  function dispose() {
    if(disposed)return;
    disposed=true;clearTimer();clearTimeout(scrollTimer);
    listeners.forEach(remove=>remove());
    resize.disconnect();intersection.disconnect();removal.disconnect();
  }
  update();schedule();
  return dispose;
}
