/* Apply published company identity to customer and staff surfaces. */
(async()=>{
  try {
    const response=await fetch('/api/brand',{credentials:'same-origin'});if(!response.ok)return;
    const brand=await response.json();
    const apply=()=>{
      if(brand.custom)document.querySelectorAll('.wordmark').forEach(node=>{if(node.textContent.includes('TAMPA')){node.replaceChildren(document.createTextNode(brand.shop_name));const label=document.createElement('small');label.textContent='STAFF WORKSPACE';node.append(label);}});
      document.querySelectorAll('img[src*="/static/brand/tampa-"]').forEach(image=>{
        if(brand.brand_logo){const url='/brand/images/'+brand.brand_logo;if(!image.src.endsWith(url))image.src=url;}
        else if(brand.custom && !image.src.includes('/brand/app-icon.png'))image.src='/brand/app-icon.png';
        image.alt=brand.shop_name;
      });
      const title=document.title.replaceAll('Tampa Signs and Stickers',brand.shop_name).replaceAll('Tampa Signs Staff',brand.shop_name+' Staff').replaceAll('Tampa Signs · Staff',brand.shop_name+' · Staff');if(title!==document.title)document.title=title;
      document.querySelectorAll('.brand').forEach(node=>node.setAttribute('aria-label',brand.shop_name+' home'));
      const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let node;
      while((node=walker.nextNode())){
        if(['SCRIPT','STYLE','TEXTAREA'].includes(node.parentElement?.tagName))continue;
        if(brand.custom){for(const text of ['BOTH TAMPA SIGNS WEBSITES','TAMPA SIGNS REWARDS'])if(node.nodeValue.includes(text))node.nodeValue=node.nodeValue.replace(text,brand.shop_name.toUpperCase()+(text.includes('REWARDS')?' REWARDS':' WEBSITE'));}
        if(node.nodeValue.trim()==='Tampa Signs and Stickers' && brand.shop_name!=='Tampa Signs and Stickers')node.nodeValue=node.nodeValue.replace('Tampa Signs and Stickers',brand.shop_name);
      }
    };
    apply();let queued=false;
    new MutationObserver(()=>{if(!queued){queued=true;requestAnimationFrame(()=>{queued=false;apply();});}}).observe(document.body,{childList:true,subtree:true});
  }catch{}
})();
