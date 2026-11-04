import {createEmailIntake} from './email-intake.js?v=20261104-2';
import {companyProductImage,companyProjects} from './company-media.js';
import {realWorkPhotosFor,productGalleryMarkup,setupProductPhotoGallery} from './product-photo-gallery.js?v=20261015-taquera-2';
import {surveyReviewFields,reviewedSurveys} from './survey-review.js?v=20261005-1';
import {renderCompany} from './company-admin.js?v=2';
import {belowCheckoutMinimum,minimumCheckoutMessage,submitOrderCheckout} from './order-checkout.js?v=20260930-checkout-3';
import {createMarketingDashboard} from './marketing-admin.js?v=20260924-1';
import {createCrmDashboard} from './crm-admin.js?v=20261104-email-intake';
import {createSiteSurveys} from './site-surveys.js?v=20261007-1';
import {createShop} from './shop.js?v=20261015-taquera-2';
import {createRewards} from './rewards.js?v=20260930-referrals-1';
import {createCheckoutProof,suggestedLines} from './checkout-proof.js?v=20261015-pack-checkout-1';

const state = {calcSequence:0, user:null, customer:null, csrf:'', catalog:null, jobs:[], job:null, jobTab:'overview', boardMode:'board',
  products:[], workflows:[], users:[], product:null, quote:null, selectedProduct:1, tasks:[], queueFilter:'available',
  wholesaleToken:localStorage.getItem('wholesale_token')||'', wholesaleName:localStorage.getItem('wholesale_name')||'', wholesaleEmail:localStorage.getItem('wholesale_email')||'', selectedCategory:sessionStorage.getItem('storefront_category')||'Storefront', reportTrendRange:'month', reportData:null};
let shop=null, rewardsUi=null, checkoutProof=null;
const incomingReferral=new URLSearchParams(location.search).get('ref');
if(incomingReferral&&/^TS[1-9][0-9]*-[A-F0-9]{8}$/i.test(incomingReferral)){
  localStorage.setItem('tampa_referral_code',incomingReferral.toUpperCase());
}
const referralCode=()=>localStorage.getItem('tampa_referral_code')||'';
const app = document.querySelector('#app');
const modal = document.querySelector('#modal');
const $ = (q, root=document) => root.querySelector(q);
const all = (q, root=document) => [...root.querySelectorAll(q)];
const esc = (v='') => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = (c=0) => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(c)/100);
const num = v => new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(Number(v));
const date = value => value ? new Date(value).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}) : 'Not set';
const initials = name => (name||'?').split(' ').filter(Boolean).slice(0,2).map(x=>x[0]).join('').toUpperCase();
const owner = () => state.user?.role === 'admin';
const titleCase = text => String(text).replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
const paths = {
 grid:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
 tasks:'m3 6 2 2 4-4 M12 6h9 M3 13l2 2 4-4 M12 13h9 M3 20l2 2 4-4 M12 20h9',
 box:'m3 7 9-4 9 4-9 4z M3 7v10l9 4 9-4V7 M12 11v10',
 flow:'M5 3h5v5H5z M14 16h5v5h-5z M7 8v10h7 M10 5h7v11',
 settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2',
 users:'M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M2 21v-3c0-5 14-5 14 0v3 M17 4c5 0 5 7 0 7 M20 15c2 0 2 3 2 6',
 arrow:'M5 12h14 m-6-6 6 6-6 6', plus:'M12 4v16 M4 12h16', check:'m5 12 4 4L20 5',
 clock:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v6l4 2',lock:'M6 10V7a6 6 0 0 1 12 0v3 M4 10h16v12H4z M12 15v3',
 search:'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14 m5 12 6 6', file:'M5 2h9l5 5v15H5z M14 2v6h5 M8 13h8 M8 17h6',
 refresh:'M20 7V2l-3 3a9 9 0 1 0 3 11 M20 7h-5', link:'M10 13a4 4 0 0 1 0-6l4-4a4 4 0 0 1 6 6l-3 3 M14 11a4 4 0 0 1 0 6l-4 4a4 4 0 0 1-6-6l3-3',
 edit:'m4 16 12-12 4 4-12 12-5 1z M14 6l4 4', logout:'M9 3H3v18h6 M9 12h12 m-5-5 5 5-5 5',
  print:'M6 8V2h12v6 M6 17H3V8h18v9h-3 M6 13h12v9H6z', image:'M3 3h18v18H3z M3 17l5-6 5 5 4-4 4 5 M7 7h1',
  chart:'M4 20V10h4v10 M10 20V4h4v16 M16 20v-7h4v7 M3 20h18',
 credit:'M3 5h18v14H3z M3 10h18 M6 15h5', chevron:'m9 5 7 7-7 7', mail:'M3 5h18v14H3z M3 5l9 8 9-8',
 sticker:'M7 3h7l7 7-11 11-7-7V7z M8 8h.01', label:'M4 5h16v14H4z M7 9h10 M7 13h7', magnet:'M5 4v9a7 7 0 0 0 14 0V4h-4v9a3 3 0 0 1-6 0V4z', banner:'M4 4h16v12H4z M7 20v-4 M17 20v-4 M7 8h10', sign:'M5 4h14v11H5z M12 15v6 M8 21h8', yard:'M5 4h14v10H5z M9 14v7 M15 14v7', window:'M4 3h16v18H4z M12 3v18 M4 12h16', acrylic:'M6 3h12l3 3v15H6L3 18V6z M8 8h8 M8 12h8', vehicle:'M3 14l2-5h14l2 5v5h-2a2 2 0 0 1-4 0H9a2 2 0 0 1-4 0H3z M7 14h10 M7 10l2-4h6l2 4',
};
const icon = (name,cls='') => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]||paths.box}"/></svg>`;
const publicProductName = p => { const n=String(p?.name||''),key=n.trim().toLowerCase(); if(key==='partial vehicle wraps')return 'Vehicle Wraps'; if(key==='trailer / food truck wraps')return 'Trailer / Food Truck Wraps'; if(key==='fleet window tinting')return 'Vehicle Window Tinting'; if(key==='storefront window tinting')return 'Storefront Window Tinting'; if(key==='acrylic signs')return 'Acrylic Signs'; if(key==='illuminated sign faces'||key==='acrylic sign face replacement')return 'Illuminated Sign Faces'; if(/roll-up|retractable/i.test(n))return 'Roll-up banners'; if(/label/i.test(n))return 'Labels'; if(/magnet/i.test(n))return 'Magnets'; if(/banner/i.test(n))return 'Banners'; if(/yard sign/i.test(n))return 'Yard signs'; if(/ACM/i.test(n))return 'ACM signs'; if(/perforated|window/i.test(n))return 'Window graphics'; if(/wrap/i.test(n))return 'Vehicle Wraps'; return n.replace(/\s*-\s*single sided/ig,'').replace(/^Roll\s*\/\s*sheet\s+/i,''); };
const productSlug = p => {let name=String(p?.name||'').trim().toLowerCase();if(name==='partial vehicle wraps')name='vehicle wraps';return name.replaceAll('&',' and ').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');};
const productPath = p => '/products/'+productSlug(p);
function setPublicSeo(product=null){
  const shopName=state.catalog?.shop?.shop_name||'Tampa Signs and Stickers';
  const name=product?publicProductName(product):'',description=product?.config?.description||state.catalog?.shop?.storefront_description||('Order custom signs, stickers, vehicle wraps, window graphics, banners and apparel from '+shopName+'.'),url=location.origin+(product?productPath(product):location.pathname==='/products'?'/products':'/');
  document.title=product?name+' | '+shopName:location.pathname==='/products'?'Custom Signs, Wraps, Decals and Apparel | '+shopName:shopName+' | '+(state.catalog?.shop?.storefront_heading||'Custom Signs, Wraps and Printing');
  let meta=document.querySelector('meta[name="description"]');if(!meta){meta=document.createElement('meta');meta.name='description';document.head.appendChild(meta);}meta.content=description;
  let canonical=document.querySelector('link[rel="canonical"]');if(!canonical){canonical=document.createElement('link');canonical.rel='canonical';document.head.appendChild(canonical);}canonical.href=url;
  for(const [property,value] of [['og:title',document.title],['og:description',description],['og:url',url]]){let node=document.querySelector(`meta[property="${property}"]`);if(!node){node=document.createElement('meta');node.setAttribute('property',property);document.head.appendChild(node);}node.content=value;}
}
const storefrontProductsFor = (products,category) => { const inCategory=products.filter(p=>(p.config.storefront_categories||[]).includes(category)),hasCoverageWrap=inCategory.some(p=>String(p.name||'').trim().toLowerCase()==='partial vehicle wraps'); return inCategory.filter(p=>!(hasCoverageWrap&&String(p.name||'').trim().toLowerCase()==='vehicle wraps')); };
const storefrontProductGroup = (product,category) => {
  const name=String(product?.name||'').toLowerCase();
  if(category==='Storefront'){
    if(name==='window graphics')return 'Window Graphics';
    if(name==='storefront window tinting')return 'Window Tinting';
    if(['banners','roll-up banners','a-frame inserts','foam boards'].includes(name))return 'Displays';
    return 'Storefront Signs';
  }
  if(category==='Vehicles'){
    if(name.includes('wrap'))return 'Wraps & Graphics';
    if(name==='fleet window tinting')return 'Vehicle Tinting';
    return 'Decals & Identification';
  }
  if(category==='Fleet Services'){
    if(name.includes('wrap'))return 'Fleet Wraps';
    if(name==='fleet window tinting')return 'Vehicle Tinting';
    return 'Fleet Identification';
  }
  if(category==='Construction & Site Signs')return name==='banners'?'Site Banners':'Rigid & Site Signs';
  if(category==='Events')return name==='custom t-shirts'?'Event Apparel':'Displays';
  return '';
};
const storefrontProductRail = (products,category,selectedId) => {
  if(!['Storefront','Vehicles','Fleet Services','Construction & Site Signs','Events'].includes(category))return products.map(p=>`<a href="${productPath(p)}" class="product-option ${p.id===selectedId?'active':''}" data-action="choose-product" data-id="${p.id}">${productIcon(p)}<span>${esc(publicProductName(p))}</span></a>`).join('');
  const groups=[];
  for(const product of products){const label=storefrontProductGroup(product,category);let group=groups.find(g=>g.label===label);if(!group){group={label,products:[]};groups.push(group);}group.products.push(product);}
  return groups.map(group=>`<div class="product-group-label">${esc(group.label)}</div>${group.products.map(p=>`<a href="${productPath(p)}" class="product-option ${p.id===selectedId?'active':''}" data-action="choose-product" data-id="${p.id}">${productIcon(p)}<span>${esc(publicProductName(p))}</span></a>`).join('')}`).join('');
};
const productIconName = p => { const n=(String(p?.name||'')+' '+String(p?.category||'')).toLowerCase(); if(n.includes('dtf')||n.includes('embroider')||n.includes('polo')||n.includes('hat'))return 'box'; if(n.includes('label'))return 'label'; if(n.includes('magnet'))return 'magnet'; if(n.includes('banner'))return 'banner'; if(n.includes('yard'))return 'yard'; if(n.includes('perforated')||n.includes('window'))return 'window'; if(n.includes('acrylic'))return 'acrylic'; if(n.includes('vehicle')||n.includes('wrap'))return 'vehicle'; if(n.includes('acm')||n.includes('sign'))return 'sign'; return 'sticker'; };
const productIcon = p => `<span class="product-symbol">${icon(productIconName(p),'product-icon')}</span>`;
const productImageKind = p => { const n=(String(p?.name||'')+' '+String(p?.category||'')).toLowerCase(); if(p?.config?.is_wrap||n.includes('wrap'))return 'wrap'; if(n.includes('sublimation')||n.includes('apparel')||n.includes('embroider')||n.includes('hat')||n.includes('polo')||n.includes('t-shirt')||n.includes('shirt')||n.includes('dtf'))return 'apparel'; if(n.includes('banner')||n.includes('roll-up'))return 'banner'; if(n.includes('window')||n.includes('tint')||n.includes('perforated'))return 'window'; if(n.includes('acrylic'))return 'acrylic'; if(n.includes('acm')||n.includes('yard sign')||n.includes('sign')||n.includes('foam board')||n.includes('a-frame'))return 'sign'; if(n.includes('magnet'))return 'magnet'; if(n.includes('label'))return 'label'; if(n.includes('business card')||n.includes('flyer'))return 'print'; return 'sticker'; };
const specialtyProductIllustration = p => {
  const name=String(p?.name||'').toLowerCase();
  let drawing='';
  if(name.includes('table cover')||name.includes('table runner'))drawing='<path d="M45 90 L240 90 L270 125 L20 125 Z" fill="#ddd"/><path d="M20 125 L270 125 L260 215 L30 215 Z" fill="currentColor"/><path d="M75 125 L215 125 L210 200 L80 200 Z" fill="#181818"/><path d="M135 150 L145 132 L152 151 L173 153 L157 166 L161 188 L144 176 L126 188 L130 166 L115 153 Z" fill="#fff"/>';
  else if(name.includes('backdrop')||name.includes('tent'))drawing='<path d="M30 230 L30 45 L270 45 L270 230 M15 230 L45 230 M255 230 L285 230" stroke="#222" stroke-width="8" fill="none"/><path d="M37 55 L263 55 L263 215 L37 215 Z" fill="currentColor"/><path d="M75 90 L225 90 M75 135 L225 135 M75 180 L225 180" stroke="#fff" stroke-width="15" stroke-dasharray="15 25"/>';
  else if(name.includes('feather flag'))drawing='<path d="M145 230 L145 40 Q225 30 225 90 L225 175 Q200 185 145 180" fill="currentColor" stroke="#222" stroke-width="5"/><path d="M115 235 L175 235" stroke="#222" stroke-width="8"/>';
  else if(p.category==='Promotional Products')drawing=name.includes('pen')?'<path d="M55 190 L215 55" stroke="#222" stroke-width="22" stroke-linecap="round"/><path d="M70 178 L195 74" stroke="currentColor" stroke-width="14"/><path d="M205 48 L235 72 L203 100" fill="none" stroke="#aaa" stroke-width="7"/>':'<rect x="38" y="85" width="224" height="108" rx="14" fill="#222"/><circle cx="60" cy="110" r="6" fill="#eee"/><path d="M92 118 L235 118 M92 155 L205 155" stroke="currentColor" stroke-width="9"/>';
  return drawing?`<div class="specialty-product-example" style="padding:24px;background:#f4f3ef;color:var(--accent);text-align:center;border-radius:12px" role="img" aria-label="Illustration of ${esc(publicProductName(p))}"><svg viewBox="0 0 300 260" style="display:block;max-height:230px;width:100%" aria-hidden="true">${drawing}</svg><span style="font-size:10px;color:#444">PRODUCT ILLUSTRATION</span></div>`:'';
};
const productImage = (p,size='detail') => { const media=companyProductImage(state.catalog?.company_media,p);if(media)return `<div class="company-product-image company-product-image-${esc(size)}"><img src="${esc(media.image)}" alt="${esc(String(media.alt||'').trim()||('Custom '+publicProductName(p)+' example from '+shopName()))}" loading="lazy" decoding="async"><span class="example-caption">PRODUCT MOCKUP</span></div>`;if(state.catalog?.company_media?.products)return '';const illustration=specialtyProductIllustration(p);if(illustration)return illustration;const kind=productImageKind(p); return kind?`<div class="product-example product-example-${esc(kind)} product-example-${esc(size)} produxç_w¶‰žËkºwµç\][™È[Ý\ˆ˜[[˜ÙKÜ˜Âˆ[ÙH^[Y[IÏ]ˆÛ\ÜÏH››ÝXÙH[™›È]\›Ý™HHÝ\œ™[][ÝHÈ[›ØÚÈ^[Y[Ü[ÛœËÙ]‰ÎÂ‚ˆÛÛœÝ›Ú™XÝ]Z[ÏX]Z[ÈÛ\ÜÏHœÜ[[[Ü™KY]Z[È‚ˆÝ[[X\žOÜ[Ý›Û™Ï“[Ü™H›Ú™XÝ]Z[ÏÜÝ›Û™ÏÛX[•\]\Ë›ÛÙˆ\ÝÜžKØÚY[[™ËTˆÝ]\È[™Y\ÜØYÙ\ÏÜÛX[ÜÜ[Ü[ˆÛ\ÜÏH™]Z[ËXÚ]œ›Ûˆ¸£!ÜÜ[ÜÝ[[X\žO‚ˆ]ˆÛ\ÜÏHœÜ[[[Ü™KYÜšY‚ˆ	Ü›ÛÙ’\ÝÜžJ‹œ›ÛÙœÊ_BˆÙXÝ[ÛˆÛ\ÜÏHœ[™[ÈÛ\ÜÏH›Xˆ“Ü™\ˆ\]\ÏÚÏ‰Ù]™[ÕšY]Ê‹™]™[ËœÛXÙJLŠJ_OÜÙXÝ[Û‚ˆÙXÝ[ÛˆÛ\ÜÏHœ[™[Ï”ØÚY[HH™^Ý\ÚÏÛ\ÜÏH™šY[Z[]\ÛH”™\]Y\ÝHÚ]HÝ\™^KÛÛœÝ[][Û‹[œÝ[][ÛˆÚ[™ÝËÜˆXÚÝ\ÛÛÜ™[˜][Û‹Ü]ÛˆÛ\ÜÏH˜ˆYÚ]ˆ]KXXÝ[ÛHœÜ[X\Ú[Y[”™\]Y\ÝH[YOØ]ÛÜÙXÝ[Û‚ˆÙXÝ[ÛˆÛ\ÜÏHœ[™[Ï”Ú\™XX›H›Ø‹\Ý]\ÈTÚÏÛ\ÜÏH™šY[Z[]\ÛHÜ™X]\ÈH[Z]YÝ]\È[šÈÚ]Ý]][ÝK\ÛÜšË›ÛÙ‹^[Y[ÜˆÝ\ÝÛY\ˆ]Z[ËÜ]ÛˆÛ\ÜÏH˜ˆYÚ]ˆ]KXXÝ[ÛHœÜ[\Ý]\Ë\\ˆ”ÚÝÈÝ]\ÈTØ]ÛÜÙXÝ[Û‚ˆÙXÝ[ÛˆÛ\ÜÏHœ[™[ÈÛ\ÜÏH›Xˆ“Y\ÜØYÙHHÚÜÚÏ›Ü›H]KY›Ü›OHœÜ[[Y\ÜØYÙHˆÛ\ÜÏHœÝXÚÈX™[Û\ÜÏH™šY[Ü[–[Ý\ˆY\ÜØYÙOÜÜ[^\™XH˜[YOH›Y\ÜØYÙHˆ™\]Z\™YX^[™ÝHŒÌˆXÙZÛ\H”]Y\Ý[ÛˆX›Ý]\È›Ú™XÝ‹‹ˆÝ^\™XOÛX™[]ˆÛ\ÜÏH™›Ü›KY\œ›ÜˆÙ]]ÛˆÛ\ÜÏH˜ˆYÚ”Ù[™Y\ÜØYÙH	ÚXÛÛŠ	ÛXZ[	Ë	ÚXÛÛ‹\ÛIÊ_OØ]ÛÙ›Ü›OÜÙXÝ[Û‚ˆÛ\ÜÏH[žH]]YÜ[\š]˜]K[›ÝH’ÙY\[Ý\ˆš]˜]H›Ú™XÝÙ[\ˆ[šÈÙXÝ\™Kˆ][˜ÛY\È][ÝH[™›ÛÙˆXØÙ\ÜËÜ‚ˆÙ]‚ˆÙ]Z[Ï˜Â‚ˆ\š[›™\’S\X›XÒXY\Š
JØXZ[ˆÛ\ÜÏHœÜ[\YÙH‚ˆÙXÝ[ÛˆÛ\ÜÏHœÜ[Z\›È‚ˆ]ˆÛ\ÜÏHœ›ÝÈ™]ÙY[ˆ]]ˆÛ\ÜÏH™^YXœ›ÝÈ”“Ò‘PÕÑS•TˆÈ	Ù\ØÊ‹›[X™\Š_OÙ]O‰Ù\ØÊ‹]J_OÚOÛ\ÜÏH›]]Y]\ÛH‰Ù\ØÊ‹˜Ý\ÝÛY\—Û˜[YJ_H0­È	Ù\ØÊÝ\ÝÛY\”ÝYÙ\ÖÚ‹œÝYÙW_	ÓÜ™\ˆ™XÙZ]™Y	Ê_OÜÙ]]ÛˆÛ\ÜÏH˜ˆYÚÛX[ˆ]KXXÝ[ÛHœÜ[\™Yœ™\Ú‰ÚXÛÛŠ	Ü™Yœ™\Ú	Ë	ÚXÛÛ‹\ÛIÊ_H™Yœ™\ÚØ]ÛÙ]‚ˆÛÛ\ÜÏH˜Ý\ÝÛY\‹\›ÙÜ™\ÜÈˆ\šXK[X™[H“Ü™\ˆ›ÙÜ™\ÜÈ‰ÖÖÉÜ™XÙZ]™Y	Ë	ÓÜ™\ˆ™XÙZ]™Y	×KÉÜ›ÙXÝ[Û‰Ë	Ò[ˆ›ÙXÝ[Û‰×KÉÙš[š\ÚY	Ë	Ñš[š\ÚY	×WK›X\

ÚÙ^KX™[KJOO˜HÛ\ÜÏH‰ÚOZ[™^ÉØXÝ]™IÎ‰ÉßHˆ	ÚOOOZ[™^ÉØ\šXKXÝ\œ™[HœÝ\‰Î‰ÉßOÜ[‰ÚO[™^ÚXÛÛŠ	ØÚXÚÉË	ÚXÛÛ‹\ÛIÊNšJÌ_OÜÜ[Ý›Û™Ï‰ÛX™[OÜÝ›Û™ÏÛO˜
Kš›Ú[Š	ÉÊ_OÛÛ‚ˆÜÙXÝ[Û‚ˆ	Ü›Ú™XÝÙ[\“Ý™\šY]Ê‹XØÙ\Y
_IÚ‹š[›ÚXÙ\ÏË›[™ÝØÙXÝ[ÛˆÛ\ÜÏHœ[™[XˆÏ’[›ÚXÙ\ÏÚÏ]ˆÛ\ÜÏHœÝXÚÈ]‰Ú‹š[›ÚXÙ\Ë›X\
OO˜HÛ\ÜÏH˜ˆYÚˆ™YH‹Ø\KÚ[›ÚXÙ\ËÉÚKšYHˆ\™Ù]H—Ø›[šÈˆ™[H››ÛÜ[™\ˆ•šY]È[›ÚXÙH	Ù\ØÊK›[X™\Š_H0­È][ÝH‰ÚKœ][ÝWÝ™\œÚ[ÛŸOØO˜
Kš›Ú[Š	ÉÊ_OÙ]ÜÙXÝ[Û˜‰ÉßIÚ‹œÚ]WÜÝ\™^OËœÝ]\ÏOOIÜ™\]Y\ÝY	ÏÉÏ]ˆÛ\ÜÏH››ÝXÙHXˆ”Ú]HÝ\™^H™\]Y\ÝYˆHÚÜÚ[ÛÛ™š\›HH^˜H™YH[™\Ú[Y[ˆš[[™È\ÈÛˆÛ[[YX\Ý\™[Y[È\™H™\šYšYYÙ]‰Î‰ÉßBˆ	Ü™]\›š[™ÏOOIÜ™XÙZ]™Y	É‰˜ÛÏËœÝ]\ÏOOIØ]ØZ][™×Ü^[Y[	ÏÉÏ]ˆÛ\ÜÏH››ÝXÙH[™›ÈXˆ•ÙH\™HÛÛ™š\›Z[™È[Ý\ˆ^[Y[ˆX\ÙHÈ›Ý^HYØZ[ˆÚ[HÛÛ™š\›X][Ûˆ\È[™[™ËÙ]‰Î‰ÉßBˆ	Ü™]\›š[™ÏOOIØØ[˜Ù[Y	ÏÉÏ]ˆÛ\ÜÏH››ÝXÙHXˆÚXÚÛÝ]Ø\ÈØ[˜Ù[Yˆ[Ý\ˆ›Ú™XÝ\ÈØ]™YÈ[ÝHØ[ˆ™\Ý[YH^[Y[™[ÝËÙ]‰Î‰ÉßBˆ]ˆÛ\ÜÏHœÜ[YÜšY‚ˆ]ˆÛ\ÜÏHœÝXÚÈ‚ˆÙXÝ[ÛˆÛ\ÜÏHœ[™[Ü[\š[X\žK\[™[ˆYHœÜ[\][ÝH]ˆÛ\ÜÏHœ[™[ZXY\ˆ]]ˆÛ\ÜÏH™^YXœ›ÝÈ‰ØÛÏÉÖSÕTˆÔ‘T‰Î‰ÖSÕTˆUSÕIßOÙ]ˆÛ\ÜÏH›]\ÛH‰ØÛÏÉÔ›Ú™XÝ]Z[ÉÎš‹œX›\ÚYÉÔ™]šY]È[Ý\ˆ][ÝIÎ‰ÕÙH]™H[Ý\ˆ™\]Y\Ý	ßOÚÙ]‰Ø˜YÙJXØÙ\YÉÐÛÛ™š\›YY	Îš‹œX›\ÚYÉÔ™]šY]È][ÝIÎ‰Ô][ÝH™\]Y\ÝY	ËXØÙ\YÉÙÜ™Y[‰Î‰ÛÜ˜[™ÙIÊ_OÙ]‰ÈZ‹œX›\ÚYÉÏ]ˆÛ\ÜÏH››ÝXÙH[™›ÈXˆ“Ý\ˆX[H\È™]šY]Ú[™È[Ý\ˆ›Ú™XÝ[™Ú[X›\Ú[Ý\ˆ][ÝH\™KÙ]‰Î‰ÉßIÜ][ÝUX›JŠ_IÚ‹˜Y\ÝY[Û›ÝOÉÏÛ\ÜÏH[žH]]Y™]Ü˜\]‰ÊÙ\ØÊ‹˜Y\ÝY[Û›ÝJJÉÏÜ‰Î‰ÉßIÚ‹œX›\ÚY	‰ˆXXØÙ\YÉÏ]ÛˆÛ\ÜÏH˜ˆš[X\žH]ˆ]KXXÝ[ÛH˜XØÙ\\][ÝH”™]šY]È	ˆXØÙ\][ÝOØ]Û‰Î‰ÉßOÜÙXÝ[Û‚ˆÙXÝ[ÛˆÛ\ÜÏHœ[™[Ü[\š[X\žK\[™[ˆYHœÜ[\›ÛÙˆ]ˆÛ\ÜÏH™^YXœ›ÝÈXˆ”“ÓÑÙ]ˆÛ\ÜÏH›Xˆ–[Ý\ˆ›Ú™XÝ›ÛÙÚÛ\ÜÏH›]]Y[žHXˆÚXÚÈ\ÛÜšËÜ[[™Ë[Y[œÚ[ÛœÈ[™XÙ[Y[ˆ›ÙXÝ[Ûˆ›ÛÝÜÈ[Ý\ˆ\›Ý˜[Ü‰Ü›ÛÙØ\™
‹œ›ÛÙœÖÌKXØÙ\Y‹š›Ø—Ý\›\Ê_IÊ‹œ›ÛÙœÖÌOË˜\›Ý™YÙš[\ß×JK›X\
š[OO˜HÛ\ÜÏH™š[K\›ÝÈˆ™YH‹Ø\KØ\ÜÙ]ËÉÙš[K˜\ÜÙ]ÚYHˆ\™Ù]H—Ø›[šÈˆ™[H››ÛÜ[™\ˆ‰Ù\ØÊš[K™š[[˜[YJ_H0­È\›Ý™YÛÝ\˜ÙH8¡¥ÏØO˜
Kš›Ú[Š	ÉÊ_IÜÙ[\›Ý˜[›Þ
‹XØÙ\Y
_OHÛ\ÜÏH›[šÈ[žH]ˆ™YH‹Ý\›\Èˆ\™Ù]H—Ø›[šÈˆ™[H››ÛÜ[™\ˆ\ÛÜšÈ	ˆÚ^š[™È\›\È8¡¥ÏØOÜÙXÝ[Û‚ˆ	ØXØÙ\Ð\ÛÜšÏØÙXÝ[ÛˆÛ\ÜÏHœ[™[]ˆÛ\ÜÏHœ[™[ZXY\ˆ]]ˆÛ\ÜÏH™^YXœ›ÝÈ‘’STÏÙ]Ï–[Ý\ˆ\ÛÜšÏÚÏÙ]]ÛˆÛ\ÜÏH˜ˆYÚÛX[ˆ]KXXÝ[ÛHœÜ[X\ÛÜšÈ‰ÚXÛÛŠ	Ü\ÉË	ÚXÛÛ‹\ÛIÊ_H\ØY\ÛÜšÏØ]ÛÙ]‰Ø\ÜÙ]\Ý
‹˜\ÜÙ]Ë™š[\ŠOO˜KšÚ[™OOIØ\ÛÜšÉÊJ_OÜÙXÝ[Û˜‰ÉßBˆ	Ü›Ú™XÝ]Z[ßBˆÙ]‚ˆ\ÚYHÛ\ÜÏHœÝXÚÈ‚ˆÙXÝ[ÛˆÛ\ÜÏHœ[™[Ü[\^[Y[XØ\™ˆYHœÜ[\^[Y[]ˆÛ\ÜÏH™^YXœ›ÝÈ‰ØÛÏË^Ü[™[™ÏÉÓÔ‘Tˆ
ÈSU‘T–K‘Q“Ô‘HV	Î‰ÔVSQS•	ßOÙ]]ˆÛ\ÜÏH›Y]šXÈ\™ÙH]\ÛH‰ÈZ‹œX›\ÚY	‰š‹Ý[ËÝ[ØÙ[ÏOOLÉÔ][ÝH[™[™ÉÎ›[Û™^J‹Ý[ËÝ[ØÙ[Ê_OÙ]‰ØÛÏË^Ü[™[™ÏÉÏÛ\ÜÏH™šY[Z[]\ÛH•^\ÈØ[Ý[]Y›Üˆ[Ý\ˆÚ\[™ÈY™\ÜÈ]ÚXÚÛÝ]Ü‰Î‰ÉßIØÝ\ÝÛY\•Ý[ÊŠ_IØÛÏÉÏÛ\ÜÏH[žH]]Y]‰ÊÊÛË™[š[Y[OOIÜXÚÝ\	ÏÉÓØØ[XÚÝ\ˆ	ÊÙ\ØÊÛËœXÚÝ\ØY™\ÜÊN‰ÕTÈÚ\[™ÉÊJÉÏÜ‰Î‰ÉßIÜ^[Y[OÜÙXÝ[Û‚ˆ	Ü™]Ø\™ÕZKœÜ[›Þ
Ý]KœÜ[™]Ø\™Ê_Bˆ	Ú‹œ^[Y[Ë›[™ÝØÙXÝ[ÛˆÛ\ÜÏHœ[™[ÈÛ\ÜÏH›Xˆ”^[Y[ÏÚÏ‰Ü^[Y[X›J‹YJ_OÜÙXÝ[Û˜‰ÉßBˆ	Ú‹œÝYÙOOOIÙš[š\ÚY	ÏØÙXÝ[ÛˆÛ\ÜÏHœ[™[Ï”˜]H[Ý\ˆÛÛ\]Y›Ú™XÝÚÏÛ\ÜÏH™šY[Z[]\ÛH–[Ý\ˆ™]šY]ÈÚ[™HX\šÙY\È™\šYšYYÜ›Ü›H]KY›Ü›OHœÜ[\™]šY]ÈˆÛ\ÜÏHœÝXÚÈ]‰ÜÙ[XÝ
	Ü˜][™ÉË	Ô˜][™ÉËÖÉÍIË	ÍH8 %^Ù[[	×KÉÍ	Ë	Í8 %™\žHÛÛÙ	×KÉÌÉË	ÌÈ8 %ÛÛÙ	×KÉÌ‰Ë	Ìˆ8 %˜Z\‰×KÉÌIË	ÌH8 %ÛÜ‰×WK	ÍIÊ_OX™[Û\ÜÏH™šY[Ü[”™]šY]È
Ü[Û˜[
OÜÜ[^\™XH˜[YOH˜ÛÛ[Y[ˆX^[™ÝHŒLŒˆXÙZÛ\H•Ú]ÚÝ[]\™HÝ\ÝÛY\œÈÛ›ÝÏÈÝ^\™XOÛX™[]ˆÛ\ÜÏH™›Ü›KY\œ›ÜˆÙ]]ÛˆÛ\ÜÏH˜ˆš[X\žHÚYH”ÝX›Z]™]šY]ÏØ]ÛÙ›Ü›OÜÙXÝ[Û˜‰ÉßBˆØ\ÚYO‚ˆÙ]‚ˆÛXZ[˜ÂŸB™[˜Ý[ÛˆÝ\ÝÛY\•Ý[ÊŠ^ØÛÛœÝZ‹Ý[ÎÜ™]\›ˆ]ˆÛ\ÜÏH›]]ˆÛ\ÜÏH›[™K]Ý[Ü[”›ÙXÝÈ	ˆÙ\šXÙ\ÏÜÜ[Ý›Û™Ï‰Û[Û™^J›Y\˜Ú[™\ÙWØÙ[ÊÊœ™]Ø\™×Ù\ØÛÝ[ØÙ[ß
J_OÜÝ›Û™ÏÙ]‰Ýœ™]Ø\™×Ù\ØÛÝ[ØÙ[ÏÉÏ]ˆÛ\ÜÏH›[™K]Ý[Ü[Ü™Y]È	ˆÚ[ÏÜÜ[Ý›Û™Ï¸¢$‰ÊÛ[Û™^Jœ™]Ø\™×Ù\ØÛÝ[ØÙ[ÊJÉÏÜÝ›Û™ÏÙ]‰Î‰ÉßO]ˆÛ\ÜÏH›[™K]Ý[Ü[”Ú\[™ÏÜÜ[Ý›Û™Ï‰Û[Û™^JœÚ\[™×ØÙ[Ê_OÜÝ›Û™ÏÙ]]ˆÛ\ÜÏH›[™K]Ý[Ü[•^ÜÜ[Ý›Û™Ï‰Ú‹˜ÚXÚÛÝ]Ë^Ü[™[™ÏÉÐ]ÚXÚÛÝ]	Î›[Û™^J^ØÙ[Ê_OÜÝ›Û™ÏÙ]]ˆÛ\ÜÏH›[™K]Ý[Ü[”^[Y[™XÙZ]™YÜÜ[Ý›Û™Ï‰Û[Û™^JœZYØÙ[Ê_OÜÝ›Û™ÏÙ]]ˆÛ\ÜÏH›[™K]Ý[Ü˜[™Ü[˜[[˜ÙOÜÜ[Ý›Û™Ï‰Û[Û™^J˜˜[[˜ÙWØÙ[Ê_IÚ‹˜ÚXÚÛÝ]Ë^Ü[™[™ÏÉÈ
È^	Î‰ÉßOÜÝ›Û™ÏÙ]Ù]˜ßB‚‹ÊˆX[ÙÈZ[\œÈ
‹Â™[˜Ý[Ûˆ][ÝT™]š\Ú[Û”›ÝÊ[™O^ßKÛÝ\˜ÙR[™^IÉÊ^ÂˆÛÛœÝ]O[[™Kœ]X[]OÏÌK[š][[™K[š]	ÙXXÚ	ËÚY[[™KÚYÏÉÉËZYÚ[[™KšZYÚÏÉÉÎÂˆÛÛœÝ\ÛÜšÏ[[™K˜\ÛÜš×Ü™\]Z\™YOO][™Yš[™YÈH[[™K˜\ÛÜš×Ü™\]Z\™YŠ[[™K˜\ÛÜš×Ý\ØYÙ\ØX›Y	‰ÚYOOIÉÉ‰šZYÚOOIÉÊNÂˆ™]\›ˆ]ˆÛ\ÜÏHœ][ÝK\™]š\Ú[Û‹[[™Hˆ]K\][ÝK\™]š\Ú[Û‹[[™H]K\ÛÝ\˜ÙKZ[™^H‰ÜÛÝ\˜ÙR[™^H‚ˆ]ˆÛ\ÜÏHœ][ÝK\™]š\Ú[Û‹[XZ[ˆ‚ˆ[œ]]K\™]š\Ú[Û‹[˜[YH˜[YOH‰Ù\ØÊ[™K›˜[Y_	Ó™]ÈÙ\šXÙIÊ_HˆXÙZÛ\H”›ÙXÝÜˆÙ\šXÙHˆ\šXK[X™[H”›ÙXÝÜˆÙ\šXÙHˆ™\]Z\™YX^[™ÝHŒLŒ‚ˆ[œ]]K\™]š\Ú[Û‹Y\ØÜš\[Ûˆ˜[YOH‰Ù\ØÊ[™K™\ØÜš\[ÛŸ	ÉÊ_HˆXÙZÛ\H‘\ØÜš\[ÛˆÈØÛÜHˆ\šXK[X™[H‘\ØÜš\[ÛˆÜˆØÛÜHˆX^[™ÝH‰Û[™KœÝXÚÙ\—ÜXÚÏÎLH‚ˆ[œ]]K\™]š\Ú[Û‹\]X[]H\OH›[X™\ˆˆZ[H‹ŒHˆÝ\H‹ŒHˆ˜[YOH‰Ù\ØÊ]J_Hˆ\šXK[X™[H”]X[]Hˆ™\]Z\™Y‚ˆ[œ]]K\™]š\Ú[Û‹][š]˜[YOH‰Ù\ØÊ[š]
_HˆXÙZÛ\H•[š]ˆ\šXK[X™[H•[š]ˆX^[™ÝHˆ™\]Z\™Y‚ˆ[œ]]K\™]š\Ú[Û‹]ÚY\OH›[X™\ˆˆZ[H‹ŒHˆÝ\H‹ŒHˆ˜[YOH‰Ù\ØÊÚY
_HˆXÙZÛ\H•È
[ŠHˆ\šXK[X™[H•ÚY[˜Ú\È‚ˆ[œ]]K\™]š\Ú[Û‹ZZYÚ\OH›[X™\ˆˆZ[H‹ŒHˆÝ\H‹ŒHˆ˜[YOH‰Ù\ØÊZYÚ
_HˆXÙZÛ\H’
[ŠHˆ\šXK[X™[H’ZYÚ[˜Ú\È‚ˆ[œ]]K\™]š\Ú[Û‹\šXÙH\OH›[X™\ˆˆZ[HŒˆÝ\H‹ŒHˆ˜[YOH‰Ù\ØÊ
[™KœÙ[ØÙ[ß
KÌL
_HˆXÙZÛ\H”šXÙH	ˆ\šXK[X™[HÝ\ÝÛY\ˆ[™HšXÙHˆ™\]Z\™Y‚ˆ[œ]]K\™]š\Ú[Û‹XÛÜÝ\OH›[X™\ˆˆZ[HŒˆÝ\H‹ŒHˆ˜[YOH‰Ù\ØÊ
[™K˜ÛÜÝØÙ[ß
KÌL
_HˆXÙZÛ\HÛÜÝ	ˆ\šXK[X™[H’[\›˜[\Ý[X]YÛÜÝˆ™\]Z\™Y‚ˆÙ]‚ˆ]ˆÛ\ÜÏHœ›ÝÈ™]ÙY[ˆÜ˜\][ÝK\™]š\Ú[Û‹]ÛÛÈX™[Û\ÜÏH˜ÚXÚÈ[žH[œ]]K\™]š\Ú[Û‹X\ÛÜšÈ\OH˜ÚXÚØ›Þˆ	Ø\ÛÜšÏÉØÚXÚÙY	Î‰ÉßOˆ\ÛÜšÈÈ›ÛÙˆ™\]Z\™YÛX™[]ˆÛ\ÜÏHœ›ÝÈ]Ûˆ\OH˜]ÛˆˆÛ\ÜÏH˜ˆÚÜÝÛX[ˆ]KXXÝ[ÛHœ][ÝK[[™K]\ˆ\šXK[X™[H“[Ý™H[™H\¸¡¤OØ]Û]Ûˆ\OH˜]ÛˆˆÛ\ÜÏH˜ˆÚÜÝÛX[ˆ]KXXÝ[ÛHœ][ÝK[[™KYÝÛˆˆ\šXK[X™[H“[Ý™H[™HÝÛˆ¸¡¤ÏØ]Û]Ûˆ\OH˜]ÛˆˆÛ\ÜÏH˜ˆ[™Ù\ˆÛX[ˆ]KXXÝ[ÛHœ™[[Ý™K\][ÝK[[™H”™[[Ý™OØ]ÛÙ]Ù]‚ˆÙ]˜ÂŸB™[˜Ý[ÛˆÛ›[™TšXÙPÛÜœ™XÝ[Û“[Ù[

^ÂˆÛÛœÝ\Ý]Kš›ØŽÂˆÚÝÓ[Ù[
	ÐÛÜœ™XÝ[œZYÛ›[™HšXÙIË›Ü›H]KY›Ü›OH›Û›[™K\šXÙKXÛÜœ™XÝ[ÛˆˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›È‰Ù\ØÊ‹›[X™\Š_Nˆ	Û[J‹œ][ÝK›[™\ÖÌKœ]X[]J_H0åÈ	Ù\ØÊ‹œ][ÝK›[™\ÖÌKÚY
_H0åÈ	Ù\ØÊ‹œ][ÝK›[™\ÖÌKšZYÚ
_H	Ù\ØÊ‹œ][ÝK›[™\ÖÌK›˜[YJ_KˆÝ\œ™[›ÙXÝšXÙNˆ	Û[Û™^J‹œ][ÝKœÝXÝ[ØÙ[Ê_KˆHÛ^[Y[[šÈÚ[™HÛÜÙYˆHÝ\ÝÛY\ˆÚ[™XÙZ]™HHÝÙ\ˆ][ÝH[™]\ÝXØÙ\]™Y›Ü™H^Z[™ËÙ]‰Ú[œ]
	Û™]×ÜšXÙIË	ÐÛÜœ™XÝY›ÙXÝšXÙH
	
IË	ÉË	Û[X™\‰Ë	ÛZ[HŒÍHˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_OX™[Û\ÜÏH™šY[Ü[”™X\ÛÛˆÚÝÛˆÛˆHÝ\ÝÛY\ˆ][ÝOÜÜ[^\™XH˜[YOHœ™X\ÛÛˆˆX^[™ÝHŒLˆ™\]Z\™YXÙZÛ\HÛÜœ™XÝYÝXÚÙ\ˆšXÚ[™ÈÝ^\™XOÛX™[‰ØÚXÚØ›Þ
	ØÛÛ™š\›IË	ÒH™]šY]ÙYH™]ÈšXÙH[™Ø[È[XZ[\ÈÛÜœ™XÝY][ÝHÈHÝ\ÝÛY\‹‰Ê_IÙ›Ü›Q›ÛÝ\Š	ÔØ]™HÛÜœ™XÝ[Ûˆ[™[XZ[Ý\ÝÛY\‰Ê_OÙ›Ü›O˜YJNÂŸB™[˜Ý[ÛˆY]][ÝS[Ù[

^ØÛÛœÝ\Ý]Kš›ØŽÜÚÝÓ[Ù[
	ÑY]][ÝH[™\È	ˆš[˜[Ú\™Ù\ÉË›Ü›H]KY›Ü›OH™Y]\][ÝHˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›È‘Y]^\Ý[™È›ÙXÝÈÜˆYÛ™K[Ù™ˆÙ\šXÙ\È\™XÝHÈ\È][ÝKˆØ]š[™ÈÜ™X]\ÈH™]È][ÝH™\œÚ[Û‹ÛX\œÈÝ\ÝÛY\ˆXØÙ\[˜ÙH[™™[[Ý™\ÈH™]š[Ý\È^[Y[[šËÙ]]ˆÛ\ÜÏHœ[™[ZXY\ˆ]Ï”›ÙXÝÈ	ˆÙ\šXÙ\ÏÚÏÛ\ÜÏH™šY[Z[]\ÛH“[™HšXÙ\È\™HÝ\ÝÛY\ˆÝ[È›Üˆ][™Kˆ[\›˜[ÛÜÝ\È\ÙYÛ›H›ÜˆHX\™Ú[ˆ\Ý[X]KˆX]™HÚY[™ZYÚ›[šÈ›ÜˆÙ\šXÙ\ÈÝXÚ\È\ÚYÛ‹[œÝ[][Û‹™[[Ý˜[Üˆ\›Z][™[™ËÜÙ]]Ûˆ\OH˜]ÛˆˆÛ\ÜÏH˜ˆYÚÛX[ˆ]KXXÝ[ÛH˜Y\][ÝK\Ù\šXÙH‰ÚXÛÛŠ	Ü\ÉË	ÚXÛÛ‹\ÛIÊ_HY›ÙXÝÈÙ\šXÙOØ]ÛÙ]]ˆYHœ][ÝK\™]š\Ú[Û‹[[™\È‰Ú‹œ][ÝK›[™\Ë›X\

[™KJOOœ][ÝT™]š\Ú[Û”›ÝÊ[™KJJKš›Ú[Š	ÉÊ_OÙ]]ˆÛ\ÜÏH™]šY\ˆÙ]Ï”][ÝK[]™[Ú\™Ù\ÏÚÏ]ˆÛ\ÜÏH™šY[È‰Ú[œ]
	Ù^˜WÜšXÙIË	ÓYØXÞHY][Û˜[Ù\šXÙ\ÈY\ÝY[
	
IË‹™^˜WÜšXÙWØÙ[ËÌL	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒH‰Ê_IÚ[œ]
	Ù^˜WØÛÜÝ	Ë	ÓYØXÞHY][Û˜[ÛÜÝY\ÝY[
	
IË‹™^˜WØÛÜÝØÙ[ËÌL	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒH‰Ê_IÚ[œ]
	ÜšXÙWÛÝ™\œšYIË	ÐYÜ™YYY\˜Ú[™\ÙH
ÈÙ\šXÙ\ÈšXÙHÝ™\œšYH
	
IË‹œšXÙWÛÝ™\œšYWØÙ[ÏOO[[ÉÉÎš‹œšXÙWÛÝ™\œšYWØÙ[ËÌL	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒH‰Ê_IÚ[œ]
	Ù\ÜÚ]Ü\˜Ù[	Ë	Ô™\]Z\™Y\ÜÚ]	IË‹™\ÜÚ]Ü\˜Ù[	Û[X™\‰Ë	ÛZ[HŒˆX^HŒLˆÝ\H‹ŒH‰Ê_IÚ[œ]
	ÜÚ\[™ÉË	ÐÝ\ÝÛY\ˆ[]™\žHÈÚ\[™ÈÚ\™ÙH
	
IË‹Ý[ËœÚ\[™×ØÙ[ËÌL	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒH‰Ê_IÚ[œ]
	Ý^	Ë	Õ™\šYšYYØ[\È^[[Ý[
	
IË‹Ý[Ë^ØÙ[ËÌL	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒH‰Ê_OÙ]Û\ÜÏH™šY[Z[‘›Üˆ™]ÈÛÜšË\ÙHÙ\\˜]H][ÝH[™\ÈX›Ý™H[œÝXYÙˆHYØXÞHY\ÝY[šY[ËˆHYÜ™YY\šXÙHÝ™\œšYH™\XÙ\ÈH›ÙXÝÜÙ\šXÙHÝXÝ[]›ÝÚ\[™ÈÜˆ^ÜX™[Û\ÜÏH™šY[Ü[Ý\ÝÛY\‹]š\ÚX›H][ÝH›ÝOÜÜ[^\™XH˜[YOH˜Y\ÝY[Û›ÝHˆX^[™ÝHŒŒ‰Ù\ØÊ‹˜Y\ÝY[Û›ÝJ_OÝ^\™XOÛX™[‰ØÚXÚØ›Þ
	ØÚ\™Ù\×Ý™\šYšYY	Ë	ÒHÚXÚÙYHØÛÜK›ÙXÝÜÙ\šXÙHšXÙ\Ë\Ý[X]YÛÜÝË^™X]Y[[™[]™\žHÚ\™Ù\È›Üˆ\È›Ø‹‰Ë‹˜Ú\™Ù\×Ý™\šYšYY
_IÙ›Ü›Q›ÛÝ\Š	ÔØ]™H™]š\ÙY][ÝIÊ_OÙ›Ü›O˜YJNßB™[˜Ý[ÛˆØÚY[S[Ù[

^ØÛÛœÝ\Ý]Kš›ØŽÜÚÝÓ[Ù[
	ÔØÚY[H	ˆ\ÜÚYÛˆ\È›Ø‰Ë›Ü›H]KY›Ü›OHœØÚY[HˆÛ\ÜÏHœÝXÚÈ‰Ú[œ]
	ÙYWÙ]IË	ÑYH]IË‹™YWÙ]_	ÉË	Ù]IÊ_IÜÙ[XÝ
	Ø\ÜÚYÛ™YWÚY	Ë	Ò›ØˆÝÛ™\‰ËÖÌ	Õ[˜\ÜÚYÛ™Y	×K‹‹œÝ]K\Ù\œË™š[\ŠOOK˜XÝ]™JK›X\
OO–ÝKšYK›˜[YWJWK‹˜\ÜÚYÛ™YWÚY
_IÜÙ[XÝ
	Üš[Üš]IË	Ôš[Üš]IËÖÉÛ›Ü›X[	Ë	Ó›Ü›X[	×KÉÜ\Ú	Ë	Ô\Ú	×WK‹œš[Üš]J_IÙ›Ü›Q›ÛÝ\Š
_OÙ›Ü›O˜
NßB™[˜Ý[Ûˆ›ÛÙ•\ØY[Ù[

^ÜÚÝÓ[Ù[
	ÔX›\ÚHÛÛ\]H›ÛÙˆXÚØYÙIË›Ü›H]KY›Ü›OH\ØY\›ÛÙˆˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH’[˜ÛYH]™\žH][H[ˆH›Ø‹ˆ›Üˆ][\H[™[Ë\ØYÛ™HÛÛXš[™Y[XYÙHÜˆH][K\YÙH‹ˆH™]È™\œÚ[Ûˆ™\XÙ\ÈHÝ\œ™[›ÛÙˆ›Üˆ\›Ý˜[]™\Ù\™\ÈX\›Y\ˆXÚ\Ú[ÛœËÙ]‰Ú[œ]
	ÛX™[	Ë	Ô›ÛÙˆ]IË	ÐÛÛ\]H›Øˆ›ÛÙ‰Ë	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒN‰Ê_OX™[Û\ÜÏH™šY[Ü[”‘Ë”QÈÜˆˆÈX^[][HLPÜÜ[[œ]\OH™š[Hˆ˜[YOH™š[HˆXØÙ\H‹œ™ËšœËšœYËœˆˆ™\]Z\™YÛX™[X™[Û\ÜÏH™šY[Ü[Ý\ÝÛY\‹]š\ÚX›H›ÛÙˆ›Ý\ÏÜÜ[^\™XH˜[YOH››ÝHˆX^[™ÝHŒÌÝ^\™XOÛX™[‰ØÚXÚØ›Þ
	ØÛÝ™\œ×Ø[Ú][\ÉË	Õ\È›ÛÙˆXÚØYÙHÛÝ™\œÈ[›ÙXÝÈ[™[™[È[ˆH›Ø‹‰Ê_OÛ\ÜÏH™šY[Z[”œÈ\™HÝÛ›ØY[Û›KˆÛY[È]\Ý™]šY]È]™\žHYÙH™Y›Ü™H\›Ýš[™ËÜ‰Ù›Ü›Q›ÛÝ\Š	ÔX›\Ú›ÛÙˆ™\œÚ[Û‰Ê_OÙ›Ü›O˜
NßB™[˜Ý[Ûˆ\ÛÜšÓ[Ù[
Ü[Y˜[ÙJ^ØÛÛœÝ›Ø\Ü[ÜÝ]KœÜ[›ØŽœÝ]Kš›ØŽÜÚÝÓ[Ù[
	Õ\ØY\ÛÜšÈÜˆH™Y™\™[˜ÙIË›Ü›H]KY›Ü›OH˜\ÛÜšÈˆ]KZ›Ø‹ZYH‰Ú›Ø‹šYHˆ]K\Ü[H‰ÜÜ[HˆÛ\ÜÏHœÝXÚÈX™[Û\ÜÏH™šY[Ü[”‘Ë”QÈÜˆˆÈX^[][HLPÜÜ[[œ]\OH™š[Hˆ˜[YOH™š[HˆXØÙ\H‹œ™ËšœËšœYËœˆˆ™\]Z\™YÛX™[Û\ÜÏH™šY[Z[\ÛÜšÈ\ÈHÛÝ\˜ÙKÜ™Y™\™[˜ÙHš[K›Ý[ˆ\›Ý™Y›ÛÙ‹ˆ[XYÙ\È\™H›Ü›X[^™YÈ‘È›ÜˆØY™H\Ü^KˆˆÜšYÚ[˜[È\™HÝÜ™Y›ÜˆÝÛ›ØYÜ‰Ù›Ü›Q›ÛÝ\Š	Õ\ØYš[IÊ_OÙ›Ü›O˜
NßB™[˜Ý[Ûˆ^[Ý][Ù[

^ØÛÛœÝ\Ý]Kš›Ø‹\Z‹˜\ÜÙ]Ë™š[\ŠOO˜K›Z[YOOOIÚ[XYÙKÜ™ÉÉ‰˜KšÚ[™OOIØ\ÛÜšÉÊKš[X›OZ‹œ][ÝK›[™\Ë›X\

JOOŠÛ_JJK™š[\ŠOž›˜\ÛÜš×Ü™\]Z\™YOOY˜[ÙI‰ˆ^›˜\ÛÜš×Ý\ØYÙ\ØX›Y	‰ž›ÚYOOIÉÉ‰ž›šZYÚOOIÉÊNÚYŠ\š[X›K›[™Ý
]›ÝÈ™]È\œ›ÜŠ	Õ\È][ÝH\È›È›ÙXÝ[™\È]™\]Z\™H[ˆ\ÛÜšÈ^[Ý]‰ÊNÜÚÝÓ[Ù[
	ÑÙ[™\˜]HH[Y[œÚ[Û™Y[™[^[Ý]	Ë›Ü›H]KY›Ü›OH›^[Ý]ˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›È”Ù\šXÙK[Û›H][ÝH[™\È\™H^ÛYYˆXXÚš[X›H[™[\Ù\È]ÈØ]™YÚY[™ZYÚ]Û™H™[]]™HØØ[KÙ]‰Üš[X›K›X\

Û_JOOœÙ[XÝ
	Ø\ÉÊÚK
™\ØÜš\[ÛŸ›˜[YJJÉÈÈ	ÊÛÚY
ÉÈˆ	ÊÛšZYÚ
ÉÈ‰ËÖÉÉË	Ð›[šÈYX\Ý\™[Y[[\]I×K‹‹˜\›X\
OO–ØKšYK™š[[˜[YWJWK	ÉÊJKš›Ú[Š	ÉÊ_IÜÙ[XÝ
	Ùš]	Ë	Ð\ÛÜšÈš][™ÉËÖÉØÛÛZ[‰Ë	Ñš]ÚÛH\ÛÜšÈ
X^HX]™HX\™Ú[œÊI×KÉØÛÝ™\‰Ë	Ñš[[™[
X^HÜ›Ü\ÛÜšÊI×WK	ØÛÛZ[‰Ê_IØÚXÚØ›Þ
	ÜX›\ÚØ\×Ü›ÛÙ‰Ë	ÔX›\Ú\ÈHÛÛ\]H›ÛÙˆ›ÜˆÝ\ÝÛY\ˆ\›Ý˜[
\ÛÜšÈ]\Ý™H\ÜÚYÛ™YÈ]™\žHš[X›H›ÙXÝ
K‰Ê_OÛ\ÜÏH™šY[Z[“X]™HH›Þ[˜ÚXÚÙYÈÜ™X]HH™Y™\™[˜ÙH^[Ý]Û›Kˆ\ØY[XYÙH\ÛÜšÈš\œÝÈ\ÜÚYÛˆ]Èš[X›H›ÙXÝËÜ‰Ù›Ü›Q›ÛÝ\Š	ÑÙ[™\˜]H^[Ý]	Ê_OÙ›Ü›O˜
NßB™[˜Ý[Ûˆ^[Y[[šÓ[Ù[

^ØÛÛœÝ\Ý]Kš›ØŽÜÚÝÓ[Ù[
	Ð]XÚH]ZXÚÐ›ÛÚÜÈ^[Y[\Ý[˜][Û‰Ë›Ü›H]KY›Ü›OHœ^[Y[[[šÈˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›ÈÜ™X]HH[›ÚXÙH[ˆ]ZXÚÐ›ÛÚÜË[ˆ\ÝH]ÈÝ\ÝÛY\‹Y˜XÚ[™ÈÛ›[™H^[Y[[šÈ\™KˆÛÛ™š\›H]H[›ÚXÙHÝ\ÝÛY\ˆ[™[[Ý[X]Ú\ÈXØÙ\Y][ÝKÙ]‰ÜÙ[XÝ
	ÚÚ[™	Ë	Ó[šÈ\IËÖÉÚ[›ÚXÙIË	Ò[›ÚXÙK\ÜXÚYšXÈÛ›[™H^[Y[YÙH
™XÛÛ[Y[™Y
I×KÉÜ^[Y[Û[šÉË	ÔÝ[™[Û™H]ZXÚÐ›ÛÚÜÈ^[Y[[šÉ×WK‹œ^[Y[ÚÚ[™
_IÚ[œ]
	Ú[›ÚXÙWÜ™Y™\™[˜ÙIË	Ô]ZXÚÐ›ÛÚÜÈ[›ÚXÙHÈ[šÈ™Y™\™[˜ÙIË‹š[›ÚXÙWÜ™Y™\™[˜ÙK	Ý^	Ë	Ü™\]Z\™Y	Ê_IÚ[œ]
	Ý\›	Ë	ÐÝ\ÝÛY\‹Y˜XÚ[™ÈÈ]ZXÚÐ›ÛÚÜÈÈ[Z][šÉË‹œ^[Y[Ý\›	ÉË	Ý\›	Ë	Ü™\]Z\™Y	Ê_OÛ\ÜÏH™šY[Z[HÝ[™[Û™H^[Y[[šÈ\È›Ý\]Z]˜[[È^Z[™È[ˆ^\Ý[™È[›ÚXÙKˆ\È\˜[Y]\ÈHT“ÜÝ]Ø[››Ý™\šYžH]È[›ÚXÙHÜˆ[[Ý[Ú]Ý][ˆTHÛÛ›™XÝ[Û‹Ü‰Ù›Ü›Q›ÛÝ\Š	ÔØ]™H^[Y[[šÉÊ_OÙ›Ü›O˜
NßB™[˜Ý[Ûˆ™\šYžT^[Y[[Ù[

^ØÛÛœÝ\Ý]Kš›ØŽÜÚÝÓ[Ù[
	Ô™XÛÜ™H^[Y[™\šYšYY[ˆ]ZXÚÐ›ÛÚÜÉË›Ü›H]KY›Ü›OH™\šYžK\^[Y[ˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH•\È™XÛÜ™È[ˆ[™XYH™XÙZ]™Y^[Y[ˆ]Ù\È›ÝÚ\™ÙHHØ\™[š]X]HH^[Y[ÜˆÜ™X]H[ˆ[žH[ˆ]ZXÚÐ›ÛÚÜËÙ]]ˆÛ\ÜÏH™šY[È‰Ú[œ]
	Ø[[Ý[	Ë	Ð[[Ý[™XÙZ]™Y
	
IË
‹Ý[Ë™\ÜÚ]Ü™[XZ[š[™×ØÙ[ß‹Ý[Ë˜˜[[˜ÙWØÙ[ÊKÌL	Û[X™\‰ËZ[HŒŒHˆX^H‰Ú‹Ý[Ë˜˜[[˜ÙWØÙ[ËÌLHˆÝ\H‹ŒHˆ™\]Z\™Y
_IÚ[œ]
	Ü™Y™\™[˜ÙIË	Õ[š\]YH]ZXÚÐ›ÛÚÜÈ˜[œØXÝ[Ûˆ™Y™\™[˜ÙIË	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒŒ‰Ê_OÙ]X™[Û\ÜÏH™šY[Ü[’[\›˜[™\šYšXØ][Ûˆ›ÝOÜÜ[^\™XH˜[YOH››ÝHˆX^[™ÝHŒLÝ^\™XOÛX™[‰ØÚXÚØ›Þ
	Ý™\šYšYYÚ[—Ü]ZXÚØ›ÛÚÜÉË	ÒH™\šYšYYHXÝX[˜[œØXÝ[Ûˆ[™[[Ý[[ˆ]ZXÚÐ›ÛÚÜËˆ\È™Y™\™[˜ÙH\È›Ý[™XYH™Y[ˆ™XÛÜ™Y‰Ê_IÙ›Ü›Q›ÛÝ\Š	Ô™XÛÜ™™\šYšYY^[Y[	Ê_OÙ›Ü›O˜
NßB™[˜Ý[ÛˆY]›ÙXÝ[Ù[
Y[[
^ÂˆÛÛœÝÜšYÚ[˜[\Ý]Kœ›ÙXÝË™š[™
OœšYOOZY
NÂˆÛÛœÝ[ÜšYÚ[˜[ÜÝXÝ\™YÛÛ™JÜšYÚ[˜[
NžÛ˜[YN‰Ó™]ÈÝ\ÝÛH›ÙXÝ	ËØ]YÛÜžN‰ÔÚYÛœÉËÛÜšÙ›Ý×ÚYŒËXÝ]™NŒKX›XÎŒKÛÛ™šYÎœÝXÝ\™YÛÛ™JÝ]Kœ›ÙXÝÖÌOË˜ÛÛ™šYßßJ_NÂˆÝ]K™Y]›ÙXÝ\ÂˆÛÛœÝÏ\˜ÛÛ™šYÎÂˆÚÝÓ[Ù[
ÜšYÚ[˜[ÉÑY]	ÊÜ›˜[YN‰ÐYH›ÙXÝ	Ë›Ü›H]KY›Ü›OHœ›ÙXÝˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH™šY[È‰Ú[œ]
	Û˜[YIË	Ô›ÙXÝ˜[YIË›˜[YK	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒLŒ‰Ê_IÚ[œ]
	ØØ]YÛÜžIË	ÐØ]YÛÜžIË˜Ø]YÛÜžK	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒ‰Ê_IÜÙ[XÝ
	ÝÛÜšÙ›Ý×ÚY	Ë	ÑY˜][ÛÜšÙ›ÝÉËÝ]KÛÜšÙ›ÝÜË›X\
ÏO–ÝËšYË›˜[YWJKÛÜšÙ›Ý×ÚY
_IÜÙ[XÝ
	Ý[š]	Ë	ÐÝ\ÝÛY\ˆ]X[]HÝ[IËÖÉÜYXÙIË	ÔYXÙ\ÈÈÝXÚÙ\œÈÈX™[É×KÉÜÜY	Ë	Ô[™[ÈÈÜ]X\™KY›ÛÝ›ÙXÝÉ×WKË[š]
_OÙ]X™[Û\ÜÏH™šY[Ü[Ý\ÝÛY\‹Y˜XÚ[™È\ØÜš\[ÛˆÈ[˜ÛYYÙ\šXÙ\ÏÜÜ[^\™XH˜[YOH™\ØÜš\[ÛˆˆX^[™ÝHÌ‰Ù\ØÊË™\ØÜš\[ÛŠ_OÝ^\™XOÛX™[Ï”šXÙH[™ÛÜÝ[œ]ÏÚÏ]ˆÛ\ÜÏH™šY[È™YH‰Ú[œ]
	ÜÙ[Ü\—ÜÜY	Ë	ÔÙ[[™È˜]HÈÜH
	
IËËœÙ[Ü\—ÜÜY	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ØÛÜÝÜ\—ÜÜY	Ë	ÓX]\šX[È[™YÛÜÝ\ˆÜH
	
IËË˜ÛÜÝÜ\—ÜÜY	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÛZ[š[][WÜšXÙIË	Ô›ÙXÝ[™HZ[š[][H
	
IËË›Z[š[][WÜšXÙK	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÜÙ]\ÜšXÙIË	ÔÙ]\Ù[[™ÈšXÙH
	
IËËœÙ]\ÜšXÙK	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÜÙ]\ØÛÜÝ	Ë	ÔÙ]\ÛÜÝ
	
IËËœÙ]\ØÛÜÝ	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÝØ\ÝWÜ\˜Ù[	Ë	ÓX]\šX[Ø\ÝH	IËËØ\ÝWÜ\˜Ù[	Û[X™\‰Ë	ÛZ[HŒˆX^HŒŒˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÛX›Ü—ÛZ[]\×Ü\—Ý[š]	Ë	ÐY][Û˜[X›ÜˆZ[]\È\ˆYXÙKÜ[™[	ËË›X›Ü—ÛZ[]\×Ü\—Ý[š]	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_OÙ]Û\ÜÏH™šY[Z[‘È›ÝYX›Üˆ\™HYˆ]\È[™XYH[™Y[ÈHÜ]X\™KY›ÛÝ˜]KˆÛÜÝÈ™XÙZ]™HHÚÜ	ÜÈÛÛ™šYÝ\™YY™™\‹ˆÝ\ÝÛY\ˆÙ[[™ÈšXÙH\È›ÝXÝYžHH\™Ù][X\™Ú[ˆ›ÛÜ‹Ü‰ØËœÝXÚÙ\—ÜXÚÏØÏ”ÝXÚÙ\ˆXÚÈY][ÛœÏÚÏ]ˆÛ\ÜÏH™šY[È™YH‰Ú[œ]
	ÜXÚ×ÚXY\—ÍÜšXÙIË	Ò[˜ÛYYØ\™ÝØÚÈXY\ˆÈXÚÈ
	
IËËœXÚ×ÚXY\—ÍÜšXÙOÏÉÌKL	Ë	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÜXÚ×Ù\ÚYÛ—ÜšXÙIË	Ð\ÛÜšÈÜ™X][ÛˆÈY™™\™[ÝXÚÙ\ˆ\ÚYÛˆ
	
IËËœXÚ×Ù\ÚYÛ—ÜšXÙOÏÉÌKŒ	Ë	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÜXÚ×ÜXÚØYÚ[™×ÜšXÙIË	ÔXÚØYÚ[™È	ˆ\ÜÙ[X›HÈXÚÈ
	
IËËœXÚ×ÜXÚØYÚ[™×ÜšXÙOÏÉÌKŒ	Ë	Û[X™\‰Ë	ÛZ[HŒˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_OÙ]Û\ÜÏH™šY[Z[”ÝXÚÙ\ˆ\ÚYÛœÈ\ÙHHÝ\œ™[YKXÝ]ÝXÚÙ\œÈ˜]\ËÚ^™\È[™]X[]Hœ™XZÜËˆ]™\žHXÚÈ[˜ÛY\ÈHØ\™ÝØÚÈXY\‹˜YÈ[™\ÜÙ[X›KˆÝ\ÝÛH\ÛÜšÈ\ÈÜ[Û˜[ÈXÚØYÙHÚ^™HX^H˜\žKÜ˜‰ÉßOÏ”Ú^™\È[™]X[]Y\ÏÚÏ]ˆÛ\ÜÏH™šY[È™YH‰Ú[œ]
	ÛZ[—ÝÚY	Ë	ÓZ[š[][HÚY
[ŠIËË›Z[—ÝÚYŒK	Û[X™\‰Ë	ÛZ[H‹ŒHˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÛZ[—ÚZYÚ	Ë	ÓZ[š[][HZYÚ
[ŠIËË›Z[—ÚZYÚŒK	Û[X™\‰Ë	ÛZ[H‹ŒHˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÙY˜][ÝÚY	Ë	ÑY˜][ÚY
[ŠIËË™Y˜][ÝÚY	Û[X™\‰Ë	ÛZ[H‹ŒHˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÙY˜][ÚZYÚ	Ë	ÑY˜][ZYÚ
[ŠIËË™Y˜][ÚZYÚ	Û[X™\‰Ë	ÛZ[H‹ŒHˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÛX^ÝÚY	Ë	Ó\™Ù\Ý]]Ë\][ÝHÚY
[ŠIËË›X^ÝÚY	Û[X™\‰Ë	ÛZ[H‹ŒHˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÛX^ÚZYÚ	Ë	Ó\™Ù\Ý]]Ë\][ÝHZYÚ
[ŠIËË›X^ÚZYÚ	Û[X™\‰Ë	ÛZ[H‹ŒHˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_IÚ[œ]
	ÛX^Ü]X[]IË	ÓX^[][H]X[]IËË›X^Ü]X[]K	Û[X™\‰Ë	ÛZ[HŒHˆÝ\HŒHˆ™\]Z\™Y	Ê_OÙ]X™[Û\ÜÏH™šY[Ü[‘Ü˜YX]Y]X[]H˜[™ÈÈÝ\ˆ][\Y\ˆ
Û™H\ˆ[™JOÜÜ[^\™XH˜[YOHY\œÈˆ™\]Z\™Y‰Ù\ØÊ
ËY\œßÞÙœ›ÛNŒK][\Y\Ž‰ÌIßWJK›X\
O™œ›ÛJÉÎ‰ÊÝ›][\Y\ŠKš›Ú[Š	×‰ÊJ_OÝ^\™XOÛX™[Û\ÜÏH™šY[Z[‘^[\NˆNŒK[ˆLŒŽHÛˆH™^[™Kˆ[š]ÈKNNH\ÙHH[˜]NÈ[š]ÈLÛØ\™Ù]HÝÙ\ˆ˜]KˆX\›Y\ˆ[š]È\™H›Ý™\šXÙYÛÈÝ[ÈÈ›Ý˜[]HY\ˆ›Ý[™\žKÜ]ˆÛ\ÜÏHœÝXÚË\ÛH‰ØÚXÚØ›Þ
	ØXÝ]™IË	Ô›ÙXÝ\ÈXÝ]™IËH\˜XÝ]™J_IØÚXÚØ›Þ
	ÜX›XÉË	ÔÚÝÈ[ˆHÝ\ÝÛY\ˆØ[Ý[]Ü‰ËH\œX›XÊ_IØÚXÚØ›Þ
	Ú[œÝ[	Ë	Ð[ÝÈÛ›[™H\˜Ú\ÙHÚ][ˆHÚ^™H[Z]È
›È[œÝ[][ÛŠIËËš[œÝ[
_IØÚXÚØ›Þ
	ÜÝ\Ü×Û][\WÙ[Y[œÚ[ÛœÉË	Ð[ÝÈ][\H[™[ÈÚ[™ÝÈ[Y[œÚ[ÛœÈ[ˆHÝ\ÝÛY\ˆØ[Ý[]Ü‰ËHXËœÝ\Ü×Û][\WÙ[Y[œÚ[ÛœÊ_IØÚXÚØ›Þ
	ÜÙ[—Ø\›Ý™WØ\ÛÜšÉË	ÐÝ\ÝÛY\ˆX^H\›Ý™HZ\ˆ\ØYYš[\™XYH\ÛÜšÉËHXËœÙ[—Ø\›Ý™WØ\ÛÜšÊ_IØÚXÚØ›Þ
	Ü™\]Z\™\×Ú[œÝ[][Û‰Ë	Ô™\]Z\™\È[œÝ[][ÛˆH[Ø^\È™\]Y\ÝH][ÝIËËœ™\]Z\™\×Ú[œÝ[][ÛŠ_IØÚXÚØ›Þ
	Ú\×ÝÜ˜\	Ë	ÕÜ˜\›ÙXÝH[Ø^\È™\]Y\ÝH][ÝIËËš\×ÝÜ˜\
_OÙ]‰Ù›Ü›Q›ÛÝ\ŠÜšYÚ[˜[ÉÔØ]™H›ÙXÝ™\œÚ[Û‰Î‰ÐÜ™X]H›ÙXÝ	Ê_OÙ›Ü›O˜YJNÂŸB™[˜Ý[ÛˆÛÜšÙ›ÝÔ›ÝÊÝ\[™^
^Ü™]\›ˆ]ˆÛ\ÜÏHÛÜšÙ›ÝËYY]\›ÝÈˆ]K\Ý\Ü[ˆÛ\ÜÏH[žH]]Y‰Ú[™^
Ì_OÜÜ[[œ]]K\Ý\]]H˜[YOH‰Ù\ØÊÝ\]J_Hˆ\šXK[X™[H•\ÚÈ]Hˆ™\]Z\™Y[œ]]K\Ý\Y\\Y[˜[YOH‰Ù\ØÊÝ\™\\Y[
_Hˆ\šXK[X™[H‘\\Y[ˆ™\]Z\™YÙ[XÝ]K\Ý\YØ]H\šXK[X™[H‘Ø]H‰ÖÉÛ›Û™IË	Ü][ÝIË	Ù\ÜÚ]	Ë	Ü›ÙXÝ[Û‰Ë	Ù[]™\žI×K›X\
ÏO˜Ü[Ûˆ	ÜÝ\™Ø]OOOYÏÉÜÙ[XÝY	Î‰ÉßO‰ÙßOÛÜ[Û˜
Kš›Ú[Š	ÉÊ_OÜÙ[XÝ[œ]]K\Ý\Y\È˜[YOH‰Ù\ØÊÝ\™\[™×ÛÛ‹š›Ú[Š	Ë	ÊJ_Hˆ\šXK[X™[H”™\™\]Z\Ú]HÝ\[X™\œÈ]Ûˆ\OH˜]ÛˆˆÛ\ÜÏH˜ÛÜÙKXˆˆ]KXXÝ[ÛHœ™[[Ý™K\Ý\ˆ\šXK[X™[H”™[[Ý™HÝ\‰[Y\ÎÏØ]ÛÙ]˜ßB™[˜Ý[ÛˆÛÜšÙ›ÝÓ[Ù[
Y[[
^ØÛÛœÝ^\Ý[™Ï\Ý]KÛÜšÙ›ÝÜË™š[™
ÏOËšYOOZY
NÜÝ]K™Y]ÛÜšÙ›ÝÏY^\Ý[™ÏÜÝXÝ\™YÛÛ™J^\Ý[™ÊNžÛ˜[YN‰Ó™]È›ÙXÝ[ÛˆÛÜšÙ›ÝÉËÝ\ÎœÝXÝ\™YÛÛ™JÝ]KÛÜšÙ›ÝÜÖÌKœÝ\Ê_NØÛÛœÝÏ\Ý]K™Y]ÛÜšÙ›ÝÎÜÚÝÓ[Ù[
^\Ý[™ÏÉÑY]ÛÜšÙ›ÝÉÎ‰ÐÜ™X]HÛÜšÙ›ÝÉË›Ü›H]KY›Ü›OHÛÜšÙ›ÝÈˆÛ\ÜÏHœÝXÚÈ‰Ú[œ]
	Û˜[YIË	ÕÛÜšÙ›ÝÈ˜[YIËË›˜[YK	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒLŒ‰Ê_O]ˆÛ\ÜÏH››ÝXÙH[™›È”™\™\]Z\Ú]\È\ÙHX\›Y\ˆÝ\[X™\œËÙ\\˜]YžHÛÛ[X\ËˆH›[šÈ\Ý[ÝÜÈ\˜[[ÛÜšËˆ[˜ÛYHH›ÙXÝ[ÛˆØ]H[™[™Ú]H[]™\žHØ]KˆY\Ý™\™\]Z\Ú]H[X™\œÈY\ˆ™[[Ýš[™ÈÝ\ËÙ]]]ˆÛ\ÜÏHÛÜšÙ›ÝËYY]\›ÝÈÛÜšÙ›ÝËYY]ZXYÜ[ˆÏÜÜ[Ü[•TÒÏÜÜ[Ü[‘TT•QS•ÜÜ[Ü[‘ÐUOÜÜ[Ü[“‘QQÏÜÜ[Ü[ÜÜ[Ù]]ˆYHÛÜšÙ›ÝË\›ÝÜÈ‰ÝËœÝ\Ë›X\
ÛÜšÙ›ÝÔ›ÝÊKš›Ú[Š	ÉÊ_OÙ]Ù]]Ûˆ\OH˜]ÛˆˆÛ\ÜÏH˜ˆYÚˆ]KXXÝ[ÛH˜Y\Ý\‰ÚXÛÛŠ	Ü\ÉË	ÚXÛÛ‹\ÛIÊ_HYÝ\Ø]Û‰Ù›Ü›Q›ÛÝ\Š^\Ý[™ÏÉÔØ]™H™]ÈÛÜšÙ›ÝÈ™\œÚ[Û‰Î‰ÐÜ™X]HÛÜšÙ›ÝÉÊ_OÙ›Ü›O˜YJNßB™[˜Ý[Ûˆ\›Ý˜[[Ù[
XÝ[ÛŠ^ØÛÛœÝ\Ý]KœÜ[›ØŽÜÚÝÓ[Ù[
XÝ[ÛOOIØ\›Ý™IÏÉÐ\›Ý™H\ÛÜšÈ	ˆXØÙ\\›\ÉÎ‰Ô™\]Y\ÝH›ÛÙˆ™]š\Ú[Û‰Ë›Ü›H]KY›Ü›OHœ›ÛÙ‹YXÚ\Ú[Ûˆˆ]KYXÚ\Ú[ÛH‰ØXÝ[ÛŸHˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH	ØXÝ[ÛOOIØ\›Ý™IÏÉÚ[™›ÉÎ‰ÉßH‰ØXÝ[ÛOOIØ\›Ý™IÏÉÖ[ÝH\™H\›Ýš[™È›ÛÙˆXÚØYÙH™\œÚ[Ûˆ	ÊÚ‹œ›ÛÙœÖÌK™\œÚ[ÛŠÉËˆ™]šY]ÈH^XÝš[K]™\žH[™[[™[[Y[œÚ[ÛœÈ™Y›Ü™HÛÛ[Z[™Ë‰Î‰ÕHÝ\œ™[›ÛÙˆÚ[™HX\šÙYÚ[™Ù\È™\]Y\ÝYˆH\ÚYÛ™\ˆ]\ÝX›\ÚH™]È™\œÚ[Ûˆ™Y›Ü™H]Ø[ˆ™H\›Ý™Y‰ßOÙ]‰Ú[œ]
	Û˜[YIË	Ö[Ý\ˆ[˜[YIË	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒLŒ‰Ê_OX™[Û\ÜÏH™šY[Ü[‰ØXÝ[ÛOOIØ\›Ý™IÏÉÓÜ[Û˜[ÛÛ[Y[ÉÎ‰Ñ\ØÜšX™HHÚ[™Ù\È™YYY	ßOÜÜ[^\™XH˜[YOH˜ÛÛ[Y[ˆX^[™ÝHŒÌˆ	ØXÝ[ÛOOIØ\›Ý™IÏÉÉÎ‰Ü™\]Z\™Y	ßOÝ^\™XOÛX™[‰ØXÝ[ÛOOIØ\›Ý™IÏØ\›Ý˜[YÜ™Y[Y[
‹š›Ø—Ý\›\Ë‹˜\›Ý˜[ÜÝ][Y[
N‰ÉßIÙ›Ü›Q›ÛÝ\ŠXÝ[ÛOOIØ\›Ý™IÏÉÐ\›Ý™H\ÛÜšÈ	ˆXØÙ\\›\ÉÎ‰ÔÙ[™Ú[™ÙH™\]Y\Ý	Ê_OÙ›Ü›O˜
NßB˜\Þ[˜È[˜Ý[Ûˆ™Yœ™\ÚY\•\ÚÊ
^ÚYŠØØ][Û‹š\ÚœÝ\ÕÚ]
	ÈÚ›Ø‹ÉÊJX]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NÙ[ÙH]ØZ]ØY]Y]YJ
NßB™[˜Ý[ÛˆÝ\ÝÛQ[Y[œÚ[Û”›ÝÊ[™^
^Ü™]\›ˆ]ˆÛ\ÜÏH™[Y[œÚ[Û‹\›ÝÈˆ]KXÝ\ÝÛKY[Y[œÚ[Û]ˆÛ\ÜÏH™šY[È›Ý\ˆ‰Ú[œ]
	ØÝ\ÝÛWÛX™[ÉÊÚ[™^	ÓX™[È\™XIË	ÉË	Ý^	Ë	ÛX^[™ÝHŒLŒˆXÙZÛ\H‘š]™\ˆÚYK[™[K‹‹ˆ‰Ê_IÚ[œ]
	ØÝ\ÝÛWÝÚYÉÊÚ[™^	ÕÚY
[ŠIË	ÉË	Û[X™\‰Ë	ÛZ[H‹ŒHˆX^HŒLˆÝ\H‹ŒH‰Ê_IÚ[œ]
	ØÝ\ÝÛWÚZYÚÉÊÚ[™^	ÒZYÚ
[ŠIË	ÉË	Û[X™\‰Ë	ÛZ[H‹ŒHˆX^HŒLˆÝ\H‹ŒH‰Ê_IÚ[œ]
	ØÝ\ÝÛWÜ]WÉÊÚ[™^	Ô]IËK	Û[X™\‰Ë	ÛZ[HŒHˆX^HŒLˆÝ\HŒH‰Ê_OÙ]]Ûˆ\OH˜]ÛˆˆÛ\ÜÏH˜ˆYÚÛX[ˆ]KXXÝ[ÛHœ™[[Ý™KXÝ\ÝÛKY[Y[œÚ[Ûˆ”™[[Ý™OØ]ÛÙ]˜ßB‚™[˜Ý[ÛˆÚÛ\Ø[QY]ÜŠÛY[[[
^ÂˆÛÛœÝ›ÙXÝÏ\Ý]KÚÛ\Ø[PYZ[Ëœ›ÙXÝß×KÝ™\œšY\Ï[™]ÈX\

ÛY[Ëœ›ÙXÝÙ\ØÛÝ[ß×JK›X\
O–ÔÝš[™Êœ›ÙXÝÚY
K™\ØÛÝ[Ü\˜Ù[JJNÂˆÝ]K™Y]ÚÛ\Ø[OXÛY[ÂˆÚÝÓ[Ù[
ÛY[ÉÑY]ÚÛ\Ø[HÛY[	Î‰ÐYÚÛ\Ø[HÛY[	Ë›Ü›H]KY›Ü›OHÚÛ\Ø[KXÛY[ˆÛ\ÜÏHœÝXÚÈ‚ˆ]ˆÛ\ÜÏH››ÝXÙH[™›È•ÚÛ\Ø[HÛY[ÈÚYÛˆ[ˆÚ]HØ]™Y\Ù\›˜[YH[™\ÜÝÛÜ™ˆZ\ˆ™YÛÝX]YšXÚ[™ÈÝ^\ÈXÝ]™HÛˆ]]šXÙH›Üˆ\ÈÌ^\Ëˆ›ÙXÝ\ÜXÚYšXÈ\ØÛÝ[ÈÝ™\œšYHHY˜][\ØÛÝ[Ù]‚ˆ]ˆÛ\ÜÏH™šY[È‰Ú[œ]
	Û˜[YIË	ÐÛY[ÈÛÛ\[žH˜[YIËÛY[Ë›˜[Y_	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒLŒ‰Ê_IÚ[œ]
	Ý\Ù\›˜[YIË	Õ\Ù\›˜[YIËÛY[Ë\Ù\›˜[Y_	ÉË	Ý^	Ë	Ü™\]Z\™YZ[›[™ÝHŒÈˆX^[™ÝHŒˆ]]ØÛÛ\]OH›Ù™ˆ‰Ê_IÚ[œ]
	Ù[XZ[	Ë	ÕÚÛ\Ø[HÛÛXÝ[XZ[	ËÛY[Ë™[XZ[	ÉË	Ù[XZ[	Ë	Ü™\]Z\™YX^[™ÝHŒM‰Ê_IÚ[œ]
	Ù\ØÛÝ[Ü\˜Ù[	Ë	ÑY˜][\ØÛÝ[	IËÛY[Ë™\ØÛÝ[Ü\˜Ù[	Û[X™\‰Ë	ÛZ[HŒˆX^HŽLˆÝ\H‹ŒHˆ™\]Z\™Y	Ê_OÙ]‚ˆ	ØÛY[ØÚXÚØ›Þ
	ØXÝ]™IË	ÕÚÛ\Ø[HšXÚ[™ÈXÝ]™IËHXÛY[˜XÝ]™JN‰ÉßBˆ]Ï”›ÙXÝ\ÜXÚYšXÈ\ØÛÝ[ÈÜ[ˆÛ\ÜÏH›]]Y[žHŠÜ[Û˜[
OÜÜ[ÚÏ]ˆÛ\ÜÏHœÝXÚË\ÛH]\ÛH‰Ü›ÙXÝË›X\
O˜]ˆÛ\ÜÏHœ›ÝÈ™]ÙY[ˆÜ[‰Ù\ØÊ›˜[YJ_OÜÜ[[œ]]K]ÚÛ\Ø[K\›ÙXÝH‰ÜšYHˆ\OH›[X™\ˆˆZ[HŒˆX^HŽLˆÝ\H‹ŒHˆXÙZÛ\H•\ÙHY˜][ˆ˜[YOH‰Ù\ØÊÝ™\œšY\Ë™Ù]
Ýš[™ÊšY
J_	ÉÊ_HˆÝ[OH›X^]ÚYŒLŒÙ]˜
Kš›Ú[Š	ÉÊ_OÙ]Ù]‚ˆ	ØÛY[ØÚXÚØ›Þ
	Ü™\Ù]Ü\ÜÝÛÜ™	Ë	ÑÙ[™\˜]HH™]ÈÚÛ\Ø[H\ÜÝÛÜ™	Ë˜[ÙJN‰ÉßBˆ	Ù›Ü›Q›ÛÝ\ŠÛY[ÉÔØ]™HÚÛ\Ø[H›Ùš[IÎ‰ÐÜ™X]HÚÛ\Ø[HÛY[	Ê_OÙ›Ü›O˜YJNÂŸB™[˜Ý[ÛˆÚÝÕÚÛ\Ø[PÜ™Y[X[Ê\Ù\›˜[YK\ÜÝÛÜ™
^ÂˆÚÝÓ[Ù[
	ÔØ]™HÚÛ\Ø[HÙÚ[‰Ë]ˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH•H[\Ü˜\žH\ÜÝÛÜ™\È\Ü^YYÛ›HÛ˜ÙKˆÙ[™H\Ù\›˜[YH[™\ÜÝÛÜ™ÙXÝ\™[HÈH\›Ý™YÚÛ\Ø[HÛY[Ù]‰Ú[œ]
	ÜØ]™YÝ\Ù\›˜[YIË	Õ\Ù\›˜[YIË\Ù\›˜[YK	Ý^	Ë	Ü™XYÛ›IÊ_IÚ[œ]
	ÜØ]™YÜ\ÜÝÛÜ™	Ë	Õ[\Ü˜\žH\ÜÝÛÜ™	Ë\ÜÝÛÜ™	Ý^	Ë	Ü™XYÛ›IÊ_O]ÛˆÛ\ÜÏH˜ˆš[X\žHˆ]KXXÝ[ÛH˜ÛÜÙH”Ø]™YÙXÝ\™[OØ]ÛÙ]˜
NÂŸB‚‹Êˆ]™\žH]]][™ÈXÝ[ÛˆØ[ÈH˜XÚÙ[™ÈHÓH\È™]™\ˆHšXÙH]]Üš]Kˆ
‹Â˜ÛÛœÝXÝ[ÛœÈHÂˆ	ÛÝÛ™\‹\™[X\ÙK\™]Ø\™ÉÎ˜\Þ[˜Ê
OOžØ]ØZ]\JØ\KØYZ[‹Ü™]Ø\™ËÚ›ØœËÉÜÝ]Kš›Ø‹šYKÜ™[X\ÙX	ÔÔÕ	ËØÛÛ™š\›NY_JNÝØ\Ý
	Õ[\ÙY˜[[˜ÙH™]\›™YÈHÛY[‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ	ÜÜ[X\›Ý™K\™]šY]ÜÉÎŠ
OOœÜ[\ØY\›Ý˜[

Kˆ	ØÛÛ\]K\Ú]K\Ý\™^IÎ˜ÛÛ\]TÚ]TÝ\™^S[Ù[ˆ	Ý\ÙÝ\™\Ù][^[Ý]	ÎŠ
OOžÜ™\Ù]\ÙÝÜÚ][ÛœÊ
NÜ™XØ[Ý[]J
NßKˆ	Ý\ÙÝY›Û	Î˜OžÂˆÛÛœÝ›Ü›OI
	ÈØØ[Ý[]Ü‰ÊK›Û]\ÙÝ›Û
‹™]\Ù]™›Û
NÚYŠY›Ü›J\™]\›ŽÂˆ›Ü›K™[[Y[Ë\ÙÝÜÝ[K˜[YOY›ÛšYÂˆÛÛœÝÝ\œ™[I
	Ë\ÙÝY›ÛXÝ\œ™[	ÊKØ[\OI
	Ë\ÙÝY›ÛXÝ\œ™[\Ø[\IÊNÂˆYŠÝ\œ™[
^ØÝ\œ™[^ÛÛ[Y›Û›˜[YNØÝ\œ™[˜Û\ÜÓ˜[YOIÝ\ÙÝY›ÛXÝ\œ™[\ÙÝY›ÛIÊÙ›ÛšYßBˆYŠØ[\J^ÜØ[\K˜Û\ÜÓ˜[YOIÝ\ÙÝY›ÛXÝ\œ™[\Ø[\H\ÙÝY›ÛIÊÙ›ÛšYßBˆ‹˜ÛÜÙ\Ý
	Ù]Z[ÉÊOËœ™[[Ý™P]šX]J	ÛÜ[‰ÊNÝ\]U\ÙÝ™]šY]Ê
NÜ™XØ[Ý[]J
NÂˆKˆ	ÛÛ›[™K\^IÎ˜\Þ[˜Ê
OOžØÛÛœÝX]ØZ]\J	ËØ\KÜÜ[ØÚXÚÛÝ]	Ë	ÔÔÕ	ËßJNÛØØ][Û‹š™Y\‹\›ßKˆ	ØÝ\ÝÛK\^IÎŠ
OOžØÛÛœÝÏ\Ý]KœÜ[›Ø‹˜Ý\ÝÛWØÚXÚÛÝ]Ü[ÛœÏV×NÚYŠÏË˜Ø[—Ü^WÙ\ÜÚ]	‰˜Ë™\ÜÚ]ØÙ[ÏË˜˜[[˜ÙWØÙ[Ê[Ü[ÛœËœ\Ú
ÉÙ\ÜÚ]	Ë	Ô™\]Z\™Y\ÜÚ]H	ÊÛ[Û™^JË™\ÜÚ]ØÙ[ÊWJNÚYŠÏË˜Ø[—Ü^WÝÝ[
[Ü[ÛœËœ\Ú
ÉÝÝ[	Ë	Ô^H™[XZ[š[™È˜[[˜ÙHH	ÊÛ[Û™^JË˜˜[[˜ÙWØÙ[ÊWJNÚYŠ[Ü[ÛœË›[™Ý
]›ÝÈ™]È\œ›ÜŠ	Ó›ÈØ\™^[Y[\ÈÝ\œ™[HYK‰ÊNÜÚÝÓ[Ù[
	Ð\›Ý™H	ˆ^IË›Ü›H]KY›Ü›OH˜Ý\ÝÛK\^[Y[ˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›È–[Ý\ˆÝ\œ™[][ÝH\È\›Ý™YˆÚÛÜÙHÝÈ]XÚ[ÝHØ[È^H›ÝËˆ[ÝHÚ[ÛÛ\]H^[Y[ÛˆÝš\IÜÈÙXÝ\™HÚXÚÛÝ]YÙKÙ]‰ÜÙ[XÝ
	Ü^[Y[ÚÚ[™	Ë	Ô^[Y[[[Ý[	ËÜ[ÛœËÜ[ÛœÖÌVÌJ_OÛ\ÜÏH™šY[Z[H\ÜÚ]™YXÙ\ÈH™[XZ[š[™È˜[[˜ÙKˆ^Z[™ÈHÝ[ÛX\œÈHÝ\œ™[˜[[˜ÙKˆ\ÛÜšÈ\›Ý˜[™[XZ[œÈHÙ\\˜]H›ÙXÝ[ÛˆÝ\Ü‰Ù›Ü›Q›ÛÝ\Š	ÐÛÛ[YHÈÙXÝ\™H^[Y[	Ê_OÙ›Ü›O˜
NßKˆÛÜÙNŠ
OO˜ÛÜÙS[Ù[

Kˆ™Yœ™\ÚŠ
OOœ›Ý]J
Kˆ	Ù[XZ[]\Ý	Î˜\Þ[˜Ê
OOžØÛÛœÝX]ØZ]\J	ËØ\KØYZ[‹Ù[XZ[]\Ý	Ë	ÔÔÕ	ËßJNÝØ\Ý
	Õ\Ý[XZ[Ù[È	ÊÜ‹œ™XÚ\Y[
ÉË‰ÊNØ]ØZ]ØYÙ][™ÜÊ
NßKˆ	ÝÚÛ\Ø[K[ÙÚ[‰ÎŠ
OOœÚÝÓ[Ù[
	ÕÚÛ\Ø[HÚYÛˆ[‰Ë›Ü›H]KY›Ü›OHÚÛ\Ø[K[ÙÚ[ˆˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›È”ÚYÛˆ[ˆÛ˜ÙHÈ\ÙH[Ý\ˆ™YÛÝX]YÚÛ\Ø[HšXÚ[™Ëˆ\È]šXÙHØ[ˆÝ^HÚYÛ™Y[ˆ›Üˆ\ÈÌ^\ËÙ]‰Ú[œ]
	Ý\Ù\›˜[YIË	Õ\Ù\›˜[YIË	ÉË	Ý^	Ë	Ü™\]Z\™YZ[›[™ÝHŒÈˆX^[™ÝHŒˆ]]ØÛÛ\]OH\Ù\›˜[YH‰Ê_IÚ[œ]
	Ü\ÜÝÛÜ™	Ë	Ô\ÜÝÛÜ™	Ë	ÉË	Ü\ÜÝÛÜ™	Ë	Ü™\]Z\™YZ[›[™ÝHŒLˆˆX^[™ÝHŒLŽˆ]]ØÛÛ\]OH˜Ý\œ™[\\ÜÝÛÜ™‰Ê_IÙ›Ü›Q›ÛÝ\Š	ÔÚYÛˆ[‰Ê_OÙ›Ü›O˜
Kˆ	ÝÚÛ\Ø[KXÛX\‰Î˜\Þ[˜Ê
OOžÜÝ]KÚÛ\Ø[UÚÙ[IÉÎÜÝ]KÚÛ\Ø[S˜[YOIÉÎÜÝ]KÚÛ\Ø[Q[XZ[IÉÎÛØØ[ÝÜ˜YÙKœ™[[Ý™R][J	ÝÚÛ\Ø[WÝÚÙ[‰ÊNÛØØ[ÝÜ˜YÙKœ™[[Ý™R][J	ÝÚÛ\Ø[WÛ˜[YIÊNÛØØ[ÝÜ˜YÙKœ™[[Ý™R][J	ÝÚÛ\Ø[WÙ[XZ[	ÊNÝØ\Ý
	ÕÚÛ\Ø[HšXÚ[™ÈÚYÛ™YÝ]‰ÊNØ]ØZ]Ø[Ý[]Ü•šY]Ê
NßKˆ	Û™]Ë]ÚÛ\Ø[IÎŠ
OOÚÛ\Ø[QY]ÜŠ
Kˆ	ÙY]]ÚÛ\Ø[IÎ˜OÚÛ\Ø[QY]ÜŠ
Ý]KÚÛ\Ø[PYZ[Ë˜ÛY[ß×JK™š[™
OžšYOOS[X™\Š‹™]\Ù]šY
JJKˆ	ÜÜ[\™Yœ™\Ú	ÎŠ
OO›ØYÜ[

Kˆ	ÜÜ[\Ý]\Ë\\‰Î˜\Þ[˜Ê
OOžØÛÛœÝX]ØZ]\J	ËØ\KÜÜ[ÜÝ]\Ë[[šÉË	ÔÔÕ	ËßJNÜÚÝÓ[Ù[
	ÔÚ\™XX›H›ØˆÝ]\ÉË]ˆÛ\ÜÏHœÝ]\Ë\\‹]Ü˜\[YÈÜ˜ÏH‰Ù\ØÊ‹œ\—Ý\›
_Hˆ[H”TˆÛÙH›Üˆ[Z]Y›ØˆÝ]\ÈÛ\ÜÏH™šY[Z[[ž[Û™HÚ]\ÈTˆØ[ˆÙYHÛ›HH›Øˆ[X™\ˆ[™ÛØ\œÙH›ÙXÝ[ÛˆÝ]\ËÜX™[Û\ÜÏH™šY[Ü[”Ý]\È[šÏÜÜ[[œ]˜[YOH‰Ù\ØÊ‹œÝ]\×Ý\›
_Hˆ™XYÛ›OÛX™[Ù]˜
NßKˆ	ÜÜ[X\Ú[Y[	ÎŠ
OOœÚÝÓ[Ù[
	Ô™\]Y\ÝØÚY[[™ÉË›Ü›H]KY›Ü›OHœÜ[X\Ú[Y[ˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›ÈÚÛÜÙHH™Y™\œ™Y]H[™[YHÚ[™ÝËˆ\È\ÈH™\]Y\Ý›ÝHÛÛ™š\›YY\Ú[Y[ÈHÚÜÚ[›ÛÝÈ\Ú]]˜Z[Xš[]KˆÚ]HÝ\™^\È]™H[ˆ^˜H™YKÛÛ™š\›YY™Y›Ü™HØÚY[[™Ë[™Ûš[[™È[[YX\Ý\™[Y[È\™H™\šYšYYÙ]‰ÜÙ[XÝ
	ÚÚ[™	Ë	ÕÚ]È[ÝH™YYÉËÖÉÜÚ]WÜÝ\™^IË	ÔÚ]HÝ\™^HÈYX\Ý\™[Y[É×KÉØÛÛœÝ[][Û‰Ë	Ô›Ú™XÝÛÛœÝ[][Û‰×KÉÚ[œÝ[][Û‰Ë	Ò[œÝ[][ÛˆØÚY[[™É×KÉÜXÚÝ\	Ë	ÔXÚÝ\ÛÛÜ™[˜][Û‰×WK	ÜÚ]WÜÝ\™^IÊ_O]ˆÛ\ÜÏH™šY[È‰Ú[œ]
	Ü™\]Y\ÝYÙ]IË	Ô™Y™\œ™Y]IË	ÉË	Ù]IË	Ü™\]Z\™Y	Ê_IÜÙ[XÝ
	ÝÚ[™ÝÉË	Ô™Y™\œ™Y[YIËÖÉÓ[Ü›š[™ÉË	Ó[Ü›š[™É×KÉÐY\››ÛÛ‰Ë	ÐY\››ÛÛ‰×KÉÐ[žH[YIË	Ð[žH[YI×WK	Ó[Ü›š[™ÉÊ_OÙ]‰Ú[œ]
	ÛØØ][Û‰Ë	ÓØØ][ÛˆÈY™\ÜÈ
Yˆ\XØX›JIË	ÉË	Ý^	Ë	ÛX^[™ÝHL‰Ê_OX™[Û\ÜÏH™šY[Ü[”ØÚY[[™È›Ý\ÏÜÜ[^\™XH˜[YOH››ÝHˆX^[™ÝHŒŒÝ^\™XOÛX™[]ˆÛ\ÜÏH™›Ü›KY\œ›ÜˆÙ]‰Ù›Ü›Q›ÛÝ\Š	ÔÙ[™ØÚY[[™È™\]Y\Ý	Ê_OÙ›Ü›O˜
Kˆš[Š
OOÚ[™ÝËœš[

Kˆ	ØÚÛÜÙKXØ]YÛÜžIÎ˜\Þ[˜ÈOžÜÝ]KœÙ[XÝYØ]YÛÜžOX‹™]\Ù]˜Ø]YÛÜžNÜÙ\ÜÚ[Û”ÝÜ˜YÙKœÙ]][J	ÜÝÜ™Yœ›ÛØØ]YÛÜžIËÝ]KœÙ[XÝYØ]YÛÜžJNÜÝ]KœÙ[XÝY›ÙXÝ[[Ú\ÝÜžKœ\ÚÝ]J[	ÉË	ËÉÊNØ]ØZ]Ø[Ý[]Ü•šY]Ê
NßKˆ	ØÚÛÜÙK\›ÙXÝ	Î˜\Þ[˜ÈOžÜÝ]KœÙ[XÝY›ÙXÝS[X™\Š‹™]\Ù]šY
NØÛÛœÝ›ÙXÝ\Ý]K˜Ø][ÙËœ›ÙXÝË™š[™
OœšYOO\Ý]KœÙ[XÝY›ÙXÝ
NÚ\ÝÜžKœ\ÚÝ]J[	ÉË›ÙXÝ]
›ÙXÝ
JNØ]ØZ]Ø[Ý[]Ü•šY]Ê
NßKˆ]X[]N˜\Þ[˜ÈOžÉ
	ÈØØ[Ý[]Ü‰ÊK™[[Y[Ëœ]X[]K˜[YOX‹™]\Ù]˜[YNØ]ØZ]™XØ[Ý[]J
NßKˆ	Ü™\]Y\Ý[Ü™\‰ÎŠ
OOžØÛÛœÝ›Ü›OI
	ÈØØ[Ý[]Ü‰ÊNÚYŠ›Ü›I‰ˆY›Ü›Kœ™\Ü˜[Y]J
J\™]\›ŽÛÜ™\“[Ù[

NßKˆ	Ù\ÚYÛ‹\][ÝIÎŠ
OOœÚÝÓ[Ù[
	Ó™YY\ÚYÛÉË›Ü›H]KY›Ü›OH™\ÚYÛ‹\][ÝHˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›È•[\ÈÚ][ÝH™YY\ÚYÛ™YˆÙx &[™]šY]ÈHØÛÜH[™][ÝHH\ÚYÛˆÙ\šXÙH™Y›Ü™H›ÙXÝ[Û‹Ù]]ˆÛ\ÜÏH™šY[È‰Ú[œ]
	ØÝ\ÝÛY\—Û˜[YIË	Ö[Ý\ˆ˜[YIË	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒLŒ‰Ê_IÚ[œ]
	ØÝ\ÝÛY\—Ù[XZ[	Ë	Ñ[XZ[	Ë	ÉË	Ù[XZ[	Ë	Ü™\]Z\™YX^[™ÝHŒM‰Ê_IÚ[œ]
	ÜÛ™IË	ÔÛ™H
Ü[Û˜[
IË	ÉË	Ý[	Ê_IÚ[œ]
	Ý]IË	Ô›Ú™XÝÈ›ÙXÝ	Ë	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒN‰Ê_OÙ]X™[Û\ÜÏH™šY[Ü[‘\ÚYÛˆœšYYÜÜ[^\™XH˜[YOH››Ý\Èˆ™\]Z\™YX^[™ÝHLˆXÙZÛ\H•Ú]\™HÙH\ÚYÛš[™ÏÈ[˜ÛYHÛÜ™[™ËÛÛÜœËÝ[KÚ^™KXY[™K[™Ú\™H]Ú[™H\ÙYˆÝ^\™XOÛX™[X™[Û\ÜÏH™šY[Ü[“ÙÛÜËÚÙ]Ú\ÈÜˆ™Y™\™[˜ÙHš[\È
Ü[Û˜[
OÜÜ[[œ]˜[YOH˜\ÛÜšÈˆ\OH™š[HˆXØÙ\H‹œ™ËšœËšœYËœˆˆ][\OÛX™[Û\ÜÏH™šY[Z[]XÚ][\H™Y™\™[˜ÙHš[\Ë\ÈLPˆXXÚÜX™[Û\ÜÏHœÜ‹[Û›H“X]™H›[šÏ[œ]˜[YOHÙXœÚ]HˆXš[™^H‹LHˆ]]ØÛÛ\]OH›Ù™ˆÛX™[‰Ù›Ü›Q›ÛÝ\Š	Ô™\]Y\Ý\ÚYÛˆ][ÝIÊ_OÙ›Ü›O˜YJKˆ	ØY]Ü˜\Y[Y[œÚ[Û‰Î˜OžØÛÛœÝÙ™Ï\Ý]K˜Ø][ÙËœ›ÙXÝË™š[™
OœšYOO\Ý]KœÙ[XÝY›ÙXÝ
K˜ÛÛ™šYËÛÝ[X[
	ÖÙ]K]Ü˜\Y[Y[œÚ[Û—IÊK›[™ÝÚYŠÛÝ[LŒ
]›ÝÈ™]È\œ›ÜŠ	ÓX^[][HŒÚ^™H›ÝÜË‰ÊNÉ
	ÈÝÜ˜\Y[Y[œÚ[ÛœÉÊKš[œÙ\Y˜XÙ[S
	Ø™Y›Ü™Y[™	ËÜ˜\[Y[œÚ[Û”›ÝÊÙ™ËÛÝ[	ÉË	ÉËJJNÜ™XØ[Ý[]J
NßKˆ	Ü™[[Ý™K]Ü˜\Y[Y[œÚ[Û‰Î˜OžÚYŠ[
	ÖÙ]K]Ü˜\Y[Y[œÚ[Û—IÊK›[™ÝLJ\™]\›ŽØ‹˜ÛÜÙ\Ý
	ÖÙ]K]Ü˜\Y[Y[œÚ[Û—IÊKœ™[[Ý™J
NÜ™XØ[Ý[]J
NßKˆ	ØYXÝ\ÝÛKY[Y[œÚ[Û‰ÎŠ
OOžØÛÛœÝ›ÞI
	ÈØÝ\ÝÛKY[Y[œÚ[ÛœÉÊKÛÝ[X[
	ÖÙ]KXÝ\ÝÛKY[Y[œÚ[Û—IË›Þ
K›[™ÝÚYŠÛÝ[LŒ
]›ÝÈ™]È\œ›ÜŠ	ÓX^[][HŒÜ[Û˜[[Y[œÚ[Ûˆ›ÝÜË‰ÊNØ›Þš[œÙ\Y˜XÙ[S
	Ø™Y›Ü™Y[™	ËÝ\ÝÛQ[Y[œÚ[Û”›ÝÊÛÝ[
JNßKˆ	Ü™[[Ý™KXÝ\ÝÛKY[Y[œÚ[Û‰Î˜O˜‹˜ÛÜÙ\Ý
	ÖÙ]KXÝ\ÝÛKY[Y[œÚ[Û—IÊKœ™[[Ý™J
Kˆ	ØÝ\ÝÛK\][ÝIÎŠ
OOœÚÝÓ[Ù[
	Ô™\]Y\ÝHÝ\ÝÛH][ÝIË›Ü›H]KY›Ü›OH˜Ý\ÝÛK\][ÝHˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›È•\ÙH\È›ÜˆÜXÚX[H˜XœšXØ][Û‹ÓÈÜˆ\Ù\‹XÝ]ÛÜšË[Y[œÚ[Û˜[ÚYÛœË›Y]Ü˜\XÜË[ÈÜ™\œËÝ\ÝÛHX]\šX[ËÜˆ[ž][™È›Ý\ÝY[ˆHÝ[™\™›ÙXÝËÙ]]ˆÛ\ÜÏH™šY[È‰Ú[œ]
	ØÝ\ÝÛY\—Û˜[YIË	Ö[Ý\ˆ˜[YIË	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒLŒ‰Ê_IÚ[œ]
	ØÝ\ÝÛY\—Ù[XZ[	Ë	Ñ[XZ[	Ë	ÉË	Ù[XZ[	Ë	Ü™\]Z\™YX^[™ÝHŒM‰Ê_IÚ[œ]
	ÜÛ™IË	ÔÛ™H
Ü[Û˜[
IË	ÉË	Ý[	Ê_IÜÙ[XÝ
	Ü›Ú™XÝÝ\IË	Ô›Ú™XÝ\IËÖÉÐÝ\ÝÛH˜XœšXØ]YÚYÛ‰Ë	ÐÝ\ÝÛH˜XœšXØ]YÚYÛ‰×KÉÐÓÈÈ›Ý]YÚYÛ‰Ë	ÐÓÈÈ›Ý]YÚYÛ‰×KÉÓ\Ù\‹XÝ]XÜž[XÉË	Ó\Ù\‹XÝ]XÜž[XÉ×KÉÑ[Y[œÚ[Û˜[]\š[™ÉË	Ñ[Y[œÚ[Û˜[]\š[™É×KÉÑ›Y]È][\H™ZXÛ\ÉË	Ñ›Y]È][\H™ZXÛ\É×KÉÐ[ÈÜ™\‰Ë	Ð[ÈÜ™\‰×KÉÓÝ\ˆÝ\ÝÛH›Ú™XÝ	Ë	ÓÝ\ˆÝ\ÝÛH›Ú™XÝ	×WK	ÐÝ\ÝÛH˜XœšXØ]YÚYÛ‰Ê_OÙ]]ˆÛ\ÜÏH™šY[È‰Ú[œ]
	Ü]X[]IË	Ô]X[]HÈ\›Þ[X]HØÛÜIË	ÉË	Ý^	Ë	ÛX^[™ÝHŒLŒ‰Ê_IÚ[œ]
	Ý™ZXÛWØÛÝ[	Ë	Ñ›Y]™ZXÛHÛÝ[
Yˆ\XØX›JIË	ÉË	Ý^	Ë	ÛX^[™ÝHŒLŒ‰Ê_OÙ]]]ˆÛ\ÜÏHœ›ÝÈ™]ÙY[ˆXˆ]Ï‘[Y[œÚ[ÛœÈÜ[ˆÛ\ÜÏH›]]Y[žHŠÜ[Û˜[
OÜÜ[ÚÏÛ\ÜÏH™šY[Z[Y\ÈX[žH[™]šYX[[™[ËYXÙ\ËÜˆ™ZXÛH\™X\È\È[ÝHÛ›ÝËÜÙ]]Ûˆ\OH˜]ÛˆˆÛ\ÜÏH˜ˆYÚÛX[ˆ]KXXÝ[ÛH˜YXÝ\ÝÛKY[Y[œÚ[Ûˆ‰ÚXÛÛŠ	Ü\ÉË	ÚXÛÛ‹\ÛIÊ_HY[Y[œÚ[ÛœÏØ]ÛÙ]]ˆYH˜Ý\ÝÛKY[Y[œÚ[ÛœÈˆÛ\ÜÏHœÝXÚË\ÛHÙ]Ù]X™[Û\ÜÏH™šY[Ü[•[\ÈX›Ý]H›Ú™XÝÜÜ[^\™XH˜[YOH››Ý\Èˆ™\]Z\™YX^[™ÝHLˆXÙZÛ\H“X]\šX[š[š\ÚXY[™K[œÝ[][Ûˆ™YYË™ZXÛH\\ËÜˆ[ž][™È[ÙH][È\È][ÝH]ˆÝ^\™XOÛX™[X™[Û\ÜÏH™šY[Ü[”™Y™\™[˜ÙHš[\ÈÜˆ\ÛÜšÈ
Ü[Û˜[
OÜÜ[[œ]˜[YOH˜\ÛÜšÈˆ\OH™š[HˆXØÙ\H‹œ™ËšœËšœYËœˆˆ][\OÛX™[Û\ÜÏH™šY[Z[–[ÝHØ[ˆ]XÚ][\Hš[\Ë\ÈLPˆXXÚÜX™[Û\ÜÏHœÜ‹[Û›H“X]™H›[šÏ[œ]˜[YOHÙXœÚ]HˆXš[™^H‹LHˆ]]ØÛÛ\]OH›Ù™ˆÛX™[‰Ù›Ü›Q›ÛÝ\Š	Ô™\]Y\ÝÝ\ÝÛH][ÝIÊ_OÙ›Ü›O˜YJKˆ	Ø›Ø\™[[ÙIÎ˜OžÜÝ]K˜›Ø\™[ÙOX‹™]\Ù]˜[YNØ[
	ÖÙ]KXXÝ[ÛH˜›Ø\™[[ÙH—IÊK™›Ü‘XXÚ
Ož˜Û\ÜÓ\ÝÙÙÛJ	ØXÝ]™IËOOXŠJNÜ™[™\›Ø\™

NßKˆ	Ü]Y]YKYš[\‰Î˜OžÜÝ]Kœ]Y]YQš[\X‹™]\Ù]˜[YNØ[
	ÖÙ]KXXÝ[ÛHœ]Y]YKYš[\ˆ—IÊK™›Ü‘XXÚ
Ož˜Û\ÜÓ\ÝÙÙÛJ	ØXÝ]™IËOOXŠJNÜ™[™\”]Y]YJ
NßKˆ	Ü™\Ü]™[™\˜[™ÙIÎ˜OžÚYŠ\™\Ü™[™Ü[ÛœÖØ‹™]\Ù]˜[YW_\Ý]Kœ™\Ü]J\™]\›ŽÜÝ]Kœ™\Ü™[™˜[™ÙOX‹™]\Ù]˜[YNØÛÛœÝ[™[I
	Ëœ™\Ü]™[™ÉÊNÚYŠ\[™[
\™]\›ŽØ[
	ÖÙ]KXXÝ[ÛHœ™\Ü]™[™\˜[™ÙH—IË[™[
K™›Ü‘XXÚ
]ÛOžØÛÛœÝÙ[XÝYX]Û‹™]\Ù]˜[YOOO\Ý]Kœ™\Ü™[™˜[™ÙNØ]Û‹˜Û\ÜÓ\ÝÙÙÛJ	ØXÝ]™IËÙ[XÝY
NØ]Û‹œÙ]]šX]J	Ø\šXK\™\ÜÙY	ËÝš[™ÊÙ[XÝY
JNßJNÉ
	ÈÜ™\Ü]™[™XÚ\	Ë[™[
Kš[›™\’S\™\Ü™[™ÛÛ[
Ý]Kœ™\Ü]JNßKˆ	Ú›Ø‹]X‰Î˜OžÜÝ]Kš›Ø•XX‹™]\Ù]˜[YNÜ™[™\’›ØŠ
NßKˆ	Ü™]\›‹\]›Ü›IÎ˜\Þ[˜Ê
OOžØÛÛœÝ\Ý[˜][Û\Ý]K\Ù\‹œÝ\ÜÜ™]\›ŽØ]ØZ]\J	ËØ\KØ]]ÛÙÛÝ]	Ë	ÔÔÕ	ÊNÛØØ][Û‹š™YY\Ý[˜][ÛŽßKˆÙÛÝ]˜\Þ[˜Ê
OOžØÛÛœÝX]ØZ]\J	ËØ\KØ]]ÛÙÛÝ]	Ë	ÔÔÕ	ÊNÜÝ]K˜ÜÜ™\‹˜ÜÜ™ŽÜÝ]K\Ù\[[ÛØØ][Û‹š™YIËÜÝY™‰ÎßKˆ\ÜÝÛÜ™Š
OOœÚÝÓ[Ù[
	ÐÚ[™ÙH[Ý\ˆ\ÜÝÛÜ™	Ë›Ü›H]KY›Ü›OHœ\ÜÝÛÜ™ˆÛ\ÜÏHœÝXÚÈ‰Ú[œ]
	ØÝ\œ™[Ü\ÜÝÛÜ™	Ë	ÐÝ\œ™[\ÜÝÛÜ™	Ë	ÉË	Ü\ÜÝÛÜ™	Ë	Ü™\]Z\™Y]]ØÛÛ\]OH˜Ý\œ™[\\ÜÝÛÜ™‰Ê_IÚ[œ]
	Û™]×Ü\ÜÝÛÜ™	Ë	Ó™]È\ÜÝÛÜ™
L‹LLŽÚ\˜XÝ\œÊIË	ÉË	Ü\ÜÝÛÜ™	Ë	Ü™\]Z\™YZ[›[™ÝHŒLˆˆX^[™ÝHŒLŽˆ]]ØÛÛ\]OH›™]Ë\\ÜÝÛÜ™‰Ê_IÚ[œ]
	ØÛÛ™š\›WÜ\ÜÝÛÜ™	Ë	Ô™\X]™]È\ÜÝÛÜ™	Ë	ÉË	Ü\ÜÝÛÜ™	Ë	Ü™\]Z\™YZ[›[™ÝHŒLˆˆ]]ØÛÛ\]OH›™]Ë\\ÜÝÛÜ™‰Ê_IÙ›Ü›Q›ÛÝ\Š	Õ\]H\ÜÝÛÜ™	Ê_OÙ›Ü›O˜
Kˆ	ØÛZ[KZ›Ø‰Î˜\Þ[˜Ê
OOžØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKØÛZ[X	ÔÔÕ	ÊNÝØ\Ý
	Ò›Øˆ\ÜÚYÛ™YÈ[ÝK‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ	ÜÚ\™KZ›Ø‰ÎŠ
OOœÚÝÓ[Ù[
	ÐÜ™X]HÜˆ™\XÙHHÛY[[šÉË]ˆÛ\ÜÏHœÝXÚÈÛ\ÜÏH›]]Y•\ÈÜ™X]\ÈHš]˜]KMY^H[šÈ›Üˆ\È›Ø‹ˆ[ž[Û™HÚ]H[šÈØ[ˆšY]ÈH›Øˆ[™ÝX›Z]Ý\ÝÛY\ˆ\›Ý˜[ËÜ]ˆÛ\ÜÏH››ÝXÙH[žHX\›Y\ˆ[šÈ[™Ý\ÝÛY\ˆÙ\ÜÚ[Ûˆ›Üˆ\È›ØˆÚ[ÝÜÛÜšÚ[™ËˆÙ[™H™]È[šÈÈ[Ý\ˆÛY[Ù]]ÛˆÛ\ÜÏH˜ˆš[X\žHˆ]KXXÝ[ÛH˜ÛÛ™š\›K\Ú\™HÜ™X]Hš]˜]HÛY[[šÏØ]ÛÙ]˜
Kˆ	ØÛÛ™š\›K\Ú\™IÎ˜\Þ[˜Ê
OOžØÛÛœÝ\Ý]Kš›Ø‹X]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÚ‹šYKÜÚ\™X	ÔÔÕ	ÊNÜÝ]K›\ÝÚ\™O\‹œÜ[Ý\›ÜÚÝÓ[Ù[
	Ö[Ý\ˆš]˜]HÛY[[šÉË]ˆÛ\ÜÏHœÝXÚÈÛ\ÜÏH›]]Y•˜[Y›ÜˆM^\ËˆÚ\™HÛ›HÚ]HÝ\ÝÛY\ˆ]]Üš^™YÈ\›Ý™H\È›Ø‹Ü[œ]YHœÚ\™K[[šÈˆ˜[YOH‰Ù\ØÊ‹œÜ[Ý\›
_Hˆ™XYÛ›H\šXK[X™[H”š]˜]HÛY[[šÈ]ˆÛ\ÜÏHœ›ÝÈÜ˜\]ÛˆÛ\ÜÏH˜ˆš[X\žHˆ]KXXÝ[ÛH˜ÛÜK\Ú\™HÛÜH[šÏØ]ÛHÛ\ÜÏH˜ˆYÚˆ™YH‰Ù\ØÊ‹œÜ[Ý\›
_Hˆ\™Ù]H—Ø›[šÈˆ™[H››ÛÜ[™\ˆ›Ü™Y™\œ™\ˆ”™]šY]ÈÝ\ÝÛY\ˆÜ[	ÚXÛÛŠ	Ø\œ›ÝÉË	ÚXÛÛ‹\ÛIÊ_OØOHÛ\ÜÏH˜ˆYÚˆ™YH›XZ[Î‰Ù\ØÊ‹˜Ý\ÝÛY\—Ù[XZ[
_OÜÝXš™XÝIÙ[˜ÛÙUT’PÛÛ\Û™[
‹›[X™\ŠÉÈH[Ý\ˆ›Ú™XÝ][ÝH[™›ÛÙ‰Ê_I˜›ÙOIÙ[˜ÛÙUT’PÛÛ\Û™[
	ÔX\ÙH\ÙH\Èš]˜]H[šÈÈ™]šY]È[Ý\ˆ›Ø‹\›Ý™HHÝ\œ™[][ÝH[™›ÛÙ‹[™XØÙ\ÜÈ[Ý\ˆ^[Y[[šÎ——‰ÊÜ‹œÜ[Ý\›
É×—•\È[šÈ^\™\È[ˆM^\ËˆX\ÙHÙY\]š]˜]K‰Ê_H“Ü[ˆ[XZ[˜YØOÙ]Û\ÜÏH™šY[Z[ÛÜKÜÚ\™H[™Ü[š[™È[Ý\ˆ[XZ[\XØ][Ûˆ\™HÝ\ÜYˆHÙ\™\ˆÙ\È›ÝÙ[™[ˆ[XZ[]]ÛX]XØ[KÜÙ]˜
NßKˆ	ØÛÜK\Ú\™IÎ˜\Þ[˜Ê
OOžÝž^Ø]ØZ]˜]šYØ]Ü‹˜Û\›Ø\™Üš]U^
Ý]K›\ÝÚ\™JNÝØ\Ý
	Ôš]˜]H[šÈÛÜYY‰ÊNßXØ]ÚÉ
	ÈÜÚ\™K[[šÉÊKœÙ[XÝ

NÝØ\Ý
	ÔÙ[XÝ[™ÛÜHHYÚYÚY[šË‰ÊNß_Kˆ	ØØ[˜Ù[Z›Ø‰ÎŠ
OOœÚÝÓ[Ù[
	ÐØ[˜Ù[\È›ØÉË›Ü›H]KY›Ü›OH˜Ø[˜Ù[Z›ØˆˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH•\È™[[Ý™\ÈH›Øˆœ›ÛHHXÝ]™H]Y]YH]™\Ù\™\È]È][ÝKš[\Ë^[Y[È[™]Y]\ÝÜžKˆ]Ù\È›Ý\ÜÝYHH™Y[™Ù]X™[Û\ÜÏH™šY[Ü[”™X\ÛÛˆ›ÜˆØ[˜Ù[][ÛÜÜ[^\™XH˜[YOHœ™X\ÛÛˆˆ™\]Z\™YX^[™ÝHŒLÝ^\™XOÛX™[‰Ù›Ü›Q›ÛÝ\Š	ÐØ[˜Ù[›Ø‰Ê_OÙ›Ü›O˜
Kˆ	Ù[XZ[\›ÛÙ‹X\›Ý˜[	Î˜OžØÛÛœÝ\Ý]Kš›Ø‹œ›ÛÙœÖÌNÚYŠ\šYOOS[X™\Š‹™]\Ù]šY
J]›ÝÈ™]È\œ›ÜŠ	Ô™[ØYHÝ\œ™[›ÛÙ‹‰ÊNÜÚÝÓ[Ù[
	Ô™XÛÜ™\›Ý˜[™XÙZ]™YžH[XZ[	Ë›Ü›H]KY›Ü›OH™[XZ[\›ÛÙ‹X\›Ý˜[ˆ]KZYH‰ÜšYHˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›È”›ÛÙˆ™\œÚ[Ûˆ	Ü™\œÚ[ÛŸNˆ	Ù\ØÊ›X™[
_KˆÜ[ˆH^XÝ›ÛÙˆš[H[™™\šYžH]HÛY[	ÜÈ[XZ[\›Ý™\È\È™\œÚ[Ûˆ[™]È[ØÛÜKÙ]HÛ\ÜÏH˜ˆYÚˆ™YH‹Ø\KØ\ÜÙ]ËÉÜ˜\ÜÙ]ÚYHˆ\™Ù]H—Ø›[šÈˆ™[H››ÛÜ[™\ˆ“Ü[ˆ›ÛÙˆš[OØO‰Ú[œ]
	Û˜[YIË	ÐÝ\ÝÛY\ˆ˜[YIË	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒLŒ‰Ê_IÚ[œ]
	Ø\›Ý™YØ]	Ë	Ð\›Ý˜[[XZ[]H[™[YIË	ÉË	Ù]][YK[ØØ[	Ë	Ü™\]Z\™Y	Ê_OX™[Û\ÜÏH™šY[Ü[‘[XZ[™Y™\™[˜ÙH
ÝXš™XÝÙ[™\ˆÜˆY\ÜØYÙHQ
OÜÜ[^\™XH˜[YOH™[XZ[Ü™Y™\™[˜ÙHˆ™\]Z\™YX^[™ÝHŒLÝ^\™XOÛX™[‰ØÚXÚØ›Þ
	ØÛÛ™š\›IË	ÒH™\šYšYYHÝ\ÝÛY\ˆ\›Ý™Y\È^XÝ›ÛÙˆ[™Ü™\ˆØÛÜHžH[XZ[‰Ê_OÛ\ÜÏH™šY[Z[•\È™XÛÜ™È[Ý\ˆ™\šYšXØ][ÛŽÈ]Ù\È›ÝÛZ[HHÝ\ÝÛY\ˆXØÙ\Y\›\È[ˆHÜ[Ü‰Ù›Ü›Q›ÛÝ\Š	Ô™XÛÜ™[XZ[\›Ý˜[	Ê_OÙ›Ü›O˜
NßKˆ	ÜÙ[™\›ÛÙ‰Î˜\Þ[˜ÈOžØÛÛœÝX]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÜ›ÛÙœËÉØ‹™]\Ù]šYKÜÙ[™	ÔÔÕ	ËßJNÝØ\Ý
‹™[XZ[ÜÙ[ÉÔ›ÛÙˆ\›Ý˜[[XZ[Ù[‰Î‰Ô›ÛÙˆ[šÈØ]™Y][XZ[[]™\žH˜Z[YˆÚXÚÈ[XZ[Ý]\È[ˆÚÜÙ][™ÜË‰Ë\‹™[XZ[ÜÙ[
NØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ	ÜÙ[‹X\›Ý™KX\ÛÜšÉÎ˜OœÚÝÓ[Ù[
	Ð\›Ý™H\ÛÜšÈ	ˆXØÙ\\›\ÉË›Ü›H]KY›Ü›OHœÙ[‹X\›Ý™KX\ÛÜšÈˆ]KZYH‰Ø‹™]\Ù]šYHˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›È•\ÙH\ÈÛ›HÚ[ˆ[Ý\ˆ\ØYYš[H\È[H\ÚYÛ™Y[™™XYHÈš[\ÈÝ\YYˆ	Ù\ØÊÚÜ˜[YJ
J_HÚ[\ÙH\È^XÝš[H\ÈH\›Ý™Y›ÛÙ‹Ù]‰Ú[œ]
	Û˜[YIË	Ö[Ý\ˆ[˜[YIË	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒLŒ‰Ê_IØ\›Ý˜[YÜ™Y[Y[
Ý]KœÜ[›Ø‹š›Ø—Ý\›\ËÝ]KœÜ[›Ø‹˜\›Ý˜[ÜÝ][Y[
_IÙ›Ü›Q›ÛÝ\Š	Ð\›Ý™H\ÛÜšÈ	ˆXØÙ\\›\ÉÊ_OÙ›Ü›O˜
Kˆ	ÙY]\][ÝIÎŠ
OO™Y]][ÝS[Ù[

Kˆ	ÛÛ›[™K\šXÙKXÛÜœ™XÝ[Û‰ÎŠ
OO›Û›[™TšXÙPÛÜœ™XÝ[Û“[Ù[

Kˆ	ÜX›\Ú\][ÝIÎŠ
OOœÚÝÓ[Ù[
	ÔX›\Ú\È™]šY]ÙY][ÝIË›Ü›H]KY›Ü›OHœX›\ÚˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH•HÛY[Ú[ÙYH™\œÚ[Ûˆ	ÜÝ]Kš›Ø‹œ][ÝWÝ™\œÚ[ÛŸH›Üˆ	Û[Û™^JÝ]Kš›Ø‹Ý[ËÝ[ØÙ[Ê_KˆX›\Ú[™ÈÙ\È›ÝÜ™X]HH]ZXÚÐ›ÛÚÜÈ[›ÚXÙKÙ]‰ØÚXÚØ›Þ
	Ü™]šY]ÙY	Ë	ÒH™]šY]ÙYH[Y[œÚ[ÛœË[˜ÛYYÙ\šXÙ\ËX]\šX[ÛÜÝËX›Ü‹^\Ë[]™\žH[™š[˜[šXÙKˆH][ÝH\È™XYH›ÜˆHÛY[‰Ê_IÙ›Ü›Q›ÛÝ\Š	ÔX›\ÚÝ\ÝÛY\ˆ][ÝIÊ_OÙ›Ü›O˜
Kˆ	ÜØÚY[KZ›Ø‰ÎŠ
OOœØÚY[S[Ù[

Kˆ\ÚÎ˜\Þ[˜ÈOžØ]ØZ]\JØ\KÜÝY™‹Ý\ÚÜËÉØ‹™]\Ù]šYKØXÝ[Û˜	ÔÔÕ	ËØXÝ[ÛŽ˜‹™]\Ù]˜[Y_JNÝØ\Ý
	Õ\ÚÈ\]Y‰ÊNØ]ØZ]™Yœ™\ÚY\•\ÚÊ
NßKˆ	Ø›ØÚË]\ÚÉÎ˜OœÚÝÓ[Ù[
	Ñ›YÈH›ØÚÙY\ÚÉË›Ü›H]KY›Ü›OH˜›ØÚË]\ÚÈˆ]KZYH‰Ø‹™]\Ù]šYHˆÛ\ÜÏHœÝXÚÈX™[Û\ÜÏH™šY[Ü[•Ú]\È™]™[[™È\È\ÚÈœ›ÛH[Ýš[™ÏÏÜÜ[^\™XH˜[YOH››ÝHˆ™\]Z\™YX^[™ÝHŒŒˆXÙZÛ\H•ØZ][™ÈÛˆX]\šX[Z\ÜÚ[™È\ÛÜšËXXÚ[™H\ÜÝYK‹‹ˆÝ^\™XOÛX™[‰Ù›Ü›Q›ÛÝ\Š	ÓX\šÈ›ØÚÙY	Ê_OÙ›Ü›O˜
Kˆ	ØY]\ÚÉÎŠ
OOœÚÝÓ[Ù[
	ÐYH›Ø‹\ÜXÚYšXÈ\ÚÉË›Ü›H]KY›Ü›OH˜Y]\ÚÈˆÛ\ÜÏHœÝXÚÈ‰Ú[œ]
	Ý]IË	Õ\ÚÈ˜[YIË	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒLŒ‰Ê_IÚ[œ]
	Ù\\Y[	Ë	Ñ\\Y[	Ë	Ô›ÙXÝ[Û‰Ë	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒ‰Ê_IÜÙ[XÝ
	ÙØ]IË	Ð\›Ý˜[È^[Y[Ø]IËÖÉÛ›Û™IË	Ó›Û™HH[ZÙHÛÜšÉ×KÉÜ][ÝIË	ÐXØÙ\Y][ÝI×KÉÙ\ÜÚ]	Ë	ÐXØÙ\Y][ÝH
È\ÜÚ]	×KÉÜ›ÙXÝ[Û‰Ë	Ô][ÝH
È\›Ý™Y›ÛÙˆ
È\ÜÚ]	×KÉÙ[]™\žIË	Ô›ÙXÝ[ÛˆÚXÚÜÈ
ÈZY˜[[˜ÙI×WK	Ü›ÙXÝ[Û‰Ê_OX™[Û\ÜÏH™šY[Ü[”™\™\]Z\Ú]\È
Ù[XÝ[žHX\›Y\ˆ\ÚÜÈ™\]Z\™Y
OÜÜ[Ù[XÝ˜[YOH™\[™[˜ÚY\Èˆ][\HÚ^™OHH‰ÜÝ]Kš›Ø‹\ÚÜË›X\
O˜Ü[Ûˆ˜[YOH‰ÝšYH‰ÝœÜÚ][ÛŸKˆ	Ù\ØÊ]J_OÛÜ[Û˜
Kš›Ú[Š	ÉÊ_OÜÙ[XÝÛX™[Û\ÜÏH™šY[Z[•\ÈYÈH\ÚÈÈ\È›ØˆÛ›Kˆ\]HÛÜšÙ›ÝÈ[\]\È›Üˆ]\™H›ØœËˆÝ\ÝÛZ^™HÚXÚÛ\ÝÈ™Y›Ü™H›ÙXÝ[ÛˆÝ\ËÜ‰Ù›Ü›Q›ÛÝ\Š	ÐY\ÚÉÊ_OÙ›Ü›O˜
Kˆ	Ý\ØYX\ÛÜšÉÎŠ
OO˜\ÛÜšÓ[Ù[
˜[ÙJKˆ	ÜÜ[X\ÛÜšÉÎŠ
OO˜\ÛÜšÓ[Ù[
YJKˆ	Ý\ØY\›ÛÙ‰ÎŠ
OOœ›ÛÙ•\ØY[Ù[

Kˆ^[Ý]Š
OO›^[Ý][Ù[

Kˆ	Ü^[Y[[[šÉÎŠ
OOœ^[Y[[šÓ[Ù[

Kˆ	Ý™\šYžK\^[Y[	ÎŠ
OO™\šYžT^[Y[[Ù[

Kˆ	Ý›ÚY\^[Y[	Î˜OœÚÝÓ[Ù[
	ÐÛÜœ™XÝH^[Y[™XÛÜ™	Ë›Ü›H]KY›Ü›OH›ÚY\^[Y[ˆ]KZYH‰Ø‹™]\Ù]šYHˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH•\ÈÛ›H™]™\œÙ\ÈHØØ[™\šYšXØ][Ûˆ™XÛÜ™ˆ]Ù\È›Ý™Y[™[Û™^HÜˆÚ[™ÙH]ZXÚÐ›ÛÚÜËˆ™XÛÛ˜Ú[HHXØÛÝ[[™È˜[œØXÝ[ÛˆÙ\\˜][KÙ]X™[Û\ÜÏH™šY[Ü[”™X\ÛÛˆ›ÜˆÛÜœ™XÝ[™ÈH™XÛÜ™ÜÜ[^\™XH˜[YOHœ™X\ÛÛˆˆ™\]Z\™YX^[™ÝHŒLÝ^\™XOÛX™[‰Ù›Ü›Q›ÛÝ\Š	Õ›ÚYØØ[™XÛÜ™	Ê_OÙ›Ü›O˜
Kˆ	ØY[[™IÎŠ
OOžÚYŠ[
	ÖÙ]K\][ÝK[[™WIÊK›[™ÝLÌ
]›ÝÈ™]È\œ›ÜŠ	ÓX^[][HÌ›ÙXÝ[™\Ë‰ÊNÉ
	ÈÜ][ÝK[[™\ÉÊKš[œÙ\Y˜XÙ[S
	Ø™Y›Ü™Y[™	Ë][ÝQY]›ÝÊ[
	ÖÙ]K\][ÝK[[™WIÊK›[™Ý
JNßKˆ	Ü™[[Ý™K[[™IÎ˜OžÚYŠ[
	ÖÙ]K\][ÝK[[™WIÊK›[™ÝOOLJ]›ÝÈ™]È\œ›ÜŠ	ÒÙY\]X\ÝÛ™H›ÙXÝ[™K‰ÊNØ‹˜ÛÜÙ\Ý
	ÖÙ]K\][ÝK[[™WIÊKœ™[[Ý™J
NßKˆ	ØY\][ÝK\Ù\šXÙIÎŠ
OOžÚYŠ[
	ÖÙ]K\][ÝK\™]š\Ú[Û‹[[™WIÊK›[™ÝLÌ
]›ÝÈ™]È\œ›ÜŠ	ÓX^[][HÌ][ÝH[™\Ë‰ÊNÉ
	ÈÜ][ÝK\™]š\Ú[Û‹[[™\ÉÊKš[œÙ\Y˜XÙ[S
	Ø™Y›Ü™Y[™	Ë][ÝT™]š\Ú[Û”›ÝÊßK	ÉÊJNßKˆ	Ü™[[Ý™K\][ÝK[[™IÎ˜OžÚYŠ[
	ÖÙ]K\][ÝK\™]š\Ú[Û‹[[™WIÊK›[™ÝOOLJ]›ÝÈ™]È\œ›ÜŠ	ÒÙY\]X\ÝÛ™H][ÝH[™K‰ÊNØ‹˜ÛÜÙ\Ý
	ÖÙ]K\][ÝK\™]š\Ú[Û‹[[™WIÊKœ™[[Ý™J
NßKˆ	Ü][ÝK[[™K]\	Î˜OžØÛÛœÝ›ÝÏX‹˜ÛÜÙ\Ý
	ÖÙ]K\][ÝK\™]š\Ú[Û‹[[™WIÊK™]\›ÝËœ™]š[Ý\Ñ[[Y[ÚX›[™ÎÚYŠ™]Š\›ÝËœ\™[›ÙKš[œÙ\™Y›Ü™J›ÝË™]ŠNßKˆ	Ü][ÝK[[™KYÝÛ‰Î˜OžØÛÛœÝ›ÝÏX‹˜ÛÜÙ\Ý
	ÖÙ]K\][ÝK\™]š\Ú[Û‹[[™WIÊK™^\›ÝË›™^[[Y[ÚX›[™ÎÚYŠ™^
\›ÝËœ\™[›ÙKš[œÙ\™Y›Ü™J™^›ÝÊNßKˆ	ÙY]\›ÙXÝ	Î˜O™Y]›ÙXÝ[Ù[
[X™\Š‹™]\Ù]šY
JKˆ	Û™]Ë\›ÙXÝ	ÎŠ
OO™Y]›ÙXÝ[Ù[

Kˆ	ÙY]]ÛÜšÙ›ÝÉÎ˜OÛÜšÙ›ÝÓ[Ù[
[X™\Š‹™]\Ù]šY
JKˆ	Û™]Ë]ÛÜšÙ›ÝÉÎŠ
OOÛÜšÙ›ÝÓ[Ù[

Kˆ	ØY\Ý\	ÎŠ
OOžØÛÛœÝÛÝ[X[
	ÖÙ]K\Ý\IÊK›[™ÝÚYŠÛÝ[M
]›ÝÈ™]È\œ›ÜŠ	ÓX^[][HÝ\Ë‰ÊNÉ
	ÈÝÛÜšÙ›ÝË\›ÝÜÉÊKš[œÙ\Y˜XÙ[S
	Ø™Y›Ü™Y[™	ËÛÜšÙ›ÝÔ›ÝÊÝ]N‰Ó™]È\ÚÉË\\Y[‰Ô›ÙXÝ[Û‰ËØ]N‰Ù[]™\žIË\[™×ÛÛŽ˜ÛÝ[ÖØÛÝ[N–×_KÛÝ[
JNßKˆ	Ü™[[Ý™K\Ý\	Î˜OžØ‹˜ÛÜÙ\Ý
	ÖÙ]K\Ý\IÊKœ™[[Ý™J
NØ[
	ÖÙ]K\Ý\IÊK™›Ü‘XXÚ

›ÝËJOOœ›ÝË™š\œÝ[[Y[Ú[^ÛÛ[ZJÌJNßKˆ	Û™]Ë]\Ù\‰ÎŠ
OOœÚÝÓ[Ù[
	Ò[š]HHX[[X]IË›Ü›H]KY›Ü›OH›™]Ë]\Ù\ˆˆÛ\ÜÏHœÝXÚÈ‰Ú[œ]
	Û˜[YIË	Ñ[˜[YIË	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒLŒ‰Ê_IÚ[œ]
	Ù[XZ[	Ë	Ñ[XZ[	Ë	ÉË	Ù[XZ[	Ë	Ü™\]Z\™Y	Ê_IÜÙ[XÝ
	Ü›ÛIË	ÐXØÙ\ÜÈ]™[	ËÖÉÙ[\ÞYYIË	Ñ[\ÞYYHH›ØœË\ÚYÛˆ[™›ÙXÝ[Û‰×KÉØYZ[‰Ë	ÓÝÛ™\‹ØYZ[ˆHšXÚ[™Ë[ÜH[™^[Y[É×WK	Ù[\ÞYYIÊ_OÛ\ÜÏH™šY[Z[H˜[™ÛH\ÜÝÛÜ™\È\Ü^YYÛ˜ÙHY\ˆÜ™X][Û‹ˆÚ\™H]ÙXÝ\™[NÈ\È[ÝÙ\È›ÝÙ[™[š]][Ûˆ[XZ[ËÜ‰Ù›Ü›Q›ÛÝ\Š	ÐÜ™X]HX[[X]IÊ_OÙ›Ü›O˜
Kˆ	Ü™\Ù]]\Ù\‰Î˜OœÚÝÓ[Ù[
	Ô™\Ù]\ÈX[[X]H\ÜÝÛÜ™ÉË]ˆÛ\ÜÏHœÝXÚÈÛ\ÜÏH›]]Y[^\Ý[™ÈÙ\ÜÚ[ÛœÈ›Üˆ\ÈX[[X]HÚ[™HÚYÛ™YÝ]ˆH™]È˜[™ÛH\ÜÝÛÜ™Ú[™HÚÝÛˆÛ˜ÙKÜ]ÛˆÛ\ÜÏH˜ˆš[X\žHˆ]KXXÝ[ÛH˜ÛÛ™š\›K\™\Ù]]\Ù\ˆˆ]KZYH‰Ø‹™]\Ù]šYH”™\Ù]\ÜÝÛÜ™Ø]ÛÙ]˜
Kˆ	ØÛÛ™š\›K\™\Ù]]\Ù\‰Î˜\Þ[˜ÈOžØÛÛœÝX]ØZ]\JØ\KØYZ[‹Ý\Ù\œËÉØ‹™]\Ù]šYX	ÔUÒ	ËÜ™\Ù]Ü\ÜÝÛÜ™Y_JNÜÚÝÐÜ™Y[X[Ê‹[\Ü˜\žWÜ\ÜÝÛÜ™
NØ]ØZ]ØYX[J
NßKˆ	ÝÙÙÛK]\Ù\‰Î˜\Þ[˜ÈOžØ]ØZ]\JØ\KØYZ[‹Ý\Ù\œËÉØ‹™]\Ù]šYX	ÔUÒ	ËØXÝ]™N˜‹™]\Ù]˜[YOOOIÝYIßJNÝØ\Ý
	ÐXØÛÝ[XØÙ\ÜÈ\]Y‰ÊNØ]ØZ]ØYX[J
NßKˆ	ØXØÙ\\][ÝIÎŠ
OOœÚÝÓ[Ù[
	ÐXØÙ\[Ý\ˆ›Ú™XÝ][ÝIË›Ü›H]KY›Ü›OH˜XØÙ\\][ÝHˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›È”][ÝH™\œÚ[Ûˆ	ÜÝ]KœÜ[›Ø‹œ][ÝWÝ™\œÚ[ÛŸHÈÝ[	Û[Û™^JÝ]KœÜ[›Ø‹Ý[ËÝ[ØÙ[Ê_HÈ	ÜÝ]KœÜ[›Ø‹˜ÚXÚÛÝ]ÉÔ^[Y[™\]Z\™Y	ÊÛ[Û™^JÝ]KœÜ[›Ø‹Ý[ËÝ[ØÙ[ÊN‰Ô™\]Z\™Y\ÜÚ]	ÊÛ[Û™^JÝ]KœÜ[›Ø‹Ý[Ë™\ÜÚ]ØÙ[Ê_KÙ]‰Ú[œ]
	Û˜[YIË	Ö[Ý\ˆ[˜[YIË	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒLŒ‰Ê_IØÚXÚØ›Þ
	ØÛÛ™š\›IË	ÒH™\šYšYYH›ÙXÝË[Y[œÚ[ÛœËÝ\YYYX\Ý\™[Y[ËØÛÜKÚ\™Ù\È[™Ý[ˆHXØÙ\\È][ÝH[™H\ÛÜšËÚ^š[™È	ˆ›ÙXÝ[Ûˆ\›\Ë‰ÊJÝ\›\Ñ]Z[ÊÝ]KœÜ[›Ø‹š›Ø—Ý\›\Ê_OÛ\ÜÏH™šY[Z[\ÛÜšÈ\›Ý˜[\ÈHÙ\\˜]HÝ\ˆ	ÜÝ]KœÜ[›Ø‹˜ÚXÚÛÝ]ÉÔ›ÙXÝ[Ûˆ™YÚ[œÈÛ›HY\ˆH™\]Z\™Y\›Ý˜[È[™^[Y[\™H™\šYšYY‰Î‰Ô›ÙXÝ[Ûˆ™YÚ[œÈÛ›HY\ˆH™\]Z\™Y\›Ý˜[È[™\ÜÚ]\™H™\šYšYY‰ßOÜ‰Ù›Ü›Q›ÛÝ\Š	ÐXØÙ\][ÝIÊ_OÙ›Ü›O˜
Kˆ	Ø\›Ý™K\›ÛÙ‰ÎŠ
OO˜\›Ý˜[[Ù[
	Ø\›Ý™IÊKˆ	Ü™\]Y\ÝXÚ[™Ù\ÉÎŠ
OO˜\›Ý˜[[Ù[
	Ü™\]Y\ÝØÚ[™Ù\ÉÊKˆ	Ü^[Y[[›ÝXÙIÎŠ
OOœÚÝÓ[Ù[
	Ó]HÚÜÛ›ÝÈ[ÝHZY	Ë›Ü›H]KY›Ü›OHœ^[Y[[›ÝXÙHˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH[™›È•HÚÜÚ[™\šYžH[Ý\ˆ˜[œØXÝ[Ûˆ[ˆ]ZXÚÐ›ÛÚÜËˆ™\Ü[™È]\™HÙ\È›ÝÚ[™ÙH[Ý\ˆ˜[[˜ÙH[[]\È™\šYšYYÙ]‰Ú[œ]
	Ü™Y™\™[˜ÙIË	Ô^[Y[™Y™\™[˜ÙHÈ™XÙZ\Y[YšY\‰Ë	ÉË	Ý^	Ë	Ü™\]Z\™YX^[™ÝHŒŒ‰Ê_IÙ›Ü›Q›ÛÝ\Š	ÔÙ[™^[Y[›ÝXÙIÊ_OÙ›Ü›O˜
KŸNÂ™[˜Ý[ÛˆÚÝÐÜ™Y[X[Ê\ÜÝÛÜ™
^ÜÚÝÓ[Ù[
	ÔØ]™HH™]ÈXØÛÝ[\ÜÝÛÜ™	Ë]ˆÛ\ÜÏHœÝXÚÈ]ˆÛ\ÜÏH››ÝXÙH•\È\ÜÝÛÜ™\È\Ü^YYÛ›HÛ˜ÙKˆÚ\™H]ÙXÝ\™[K[ˆ]™HHX[[X]HÚ[™ÙH]Y\ˆÚYÛš[™È[‹Ù][œ]˜[YOH‰Ù\ØÊ\ÜÝÛÜ™
_Hˆ™XYÛ›H\šXK[X™[H•[\Ü˜\žH\ÜÝÛÜ™Û\ÜÏH›]]Y[žH•HÙ\™\ˆÝÜ™\ÈH\ÜÝÛÜ™\Ú›Ý\È™XYX›H\ÜÝÛÜ™Ü]ÛˆÛ\ÜÏH˜ˆš[X\žHˆ]KXXÝ[ÛH˜ÛÜÙH”Ø]™YÙXÝ\™[OØ]ÛÙ]˜
NßB‚˜ÛÛœÝ›Ü›\ÈHÂˆ	ØÛÛ\]K\Ú]K\Ý\™^IÎ˜\Þ[˜Ê‹
OOžØÛÛœÝ›Ø’YS[X™\Š‹™]\Ù]š›Ø’Y
NØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÚ›Ø’YKÜÚ]K\Ý\™^KØÛÛ\]X	ÔÔÕ	ËÛ›ÝN™››ÝKÛÛ™š\›NˆHY˜ÛÛ™š\›K][ÝWÝ™\œÚ[ÛŽ“[X™\Š‹™]\Ù]œ][ÝU™\œÚ[ÛŠK™]šY]ÙYÜÝ\™^\Îœ™]šY]ÙYÝ\™^\ÊŠ_JNØÛÜÙS[Ù[

NÝØ\Ý
	ÔÚ]HÝ\™^H™\šYšYY[™ÛÛ\]Y‰ÊNØ]ØZ]ØY›ØŠ›Ø’Y
NßKˆ	ÜÜ[]\ØYX\›Ý˜[	Î˜\Þ[˜Ê‹
OOžØÛÛœÝÙ[XÝYX[
	ÖÙ]K\Ü[\›ÛÙ‹Yš[WN˜ÚXÚÙY	ËŠK›X\
[œ]O“[X™\Š[œ]™]\Ù]œÜ[›ÛÙ‘š[JJNØÛÛœÝš[\Ï\Ù[XÝY›X\
YOžØÛÛœÝ\ÜÙ]\Ý]KœÜ[›Ø‹˜\ÜÙ]Ë™š[™
][OOš][KšYOOZY
NÜ™]\›ˆØ\ÜÙ]ÚYšYÚLMŽ˜\ÜÙ]œÚLM‹[™WÚ[™XÙ\Î˜[
Ù]K\Ü[\›ÛÙ‹X\ÜÙ]H‰ÚYH—N˜ÚXÚÙYŠK›X\
[œ]O“[X™\Š[œ]™]\Ù]œÜ[›ÛÙ“[™JJ_NßJNØ]ØZ]\J	ËØ\KÜÜ[Ø\ÛÜšË\™]šY]ËØ\›Ý™IË	ÔÔÕ	ËÛ˜[YN™›˜[YKÛÛ™š\›NˆHY˜ÛÛ™š\›K\›\×Ý™\œÚ[ÛŽœÝ]KœÜ[›Ø‹š›Ø—Ý\›\Ë™\œÚ[Û‹][ÝWÝ™\œÚ[ÛŽœÝ]KœÜ[›Ø‹œ][ÝWÝ™\œÚ[Û‹š[\ßJNØÛÜÙS[Ù[

NÝØ\Ý
	Ö[Ý\ˆ\ØY™]šY]ÜÈ\™H\›Ý™Y›Üˆš[‰ÊNØ]ØZ]ØYÜ[

NßKˆÙÚ[Ž˜\Þ[˜Ê‹
OOžØÛÛœÝX]ØZ]\J	ËØ\KØ]]ÛÙÚ[‰Ë	ÔÔÕ	Ë
NÜÝ]K\Ù\\‹\Ù\ŽÜÝ]K˜ÜÜ™\‹˜ÜÜ™ŽØ]ØZ]›Ý]J
NßKˆ	Ü™\ÜYš[\‰Î˜\Þ[˜Ê‹
OO›ØY™\ÜÊÜÝ\™œÝ\[™™™[™JKˆØ[Ý[]ÜŽ˜\Þ[˜Ê
OOžØ]ØZ]™XØ[Ý[]J
NßKˆ	ÝÚÛ\Ø[K[ÙÚ[‰Î˜\Þ[˜Ê‹
OOžØÛÛœÝX]ØZ]\J	ËØ\KÝÚÛ\Ø[KØXÝ]˜]IË	ÔÔÕ	ËÝ\Ù\›˜[YN™\Ù\›˜[YK\ÜÝÛÜ™™œ\ÜÝÛÜ™JNÜÝ]KÚÛ\Ø[UÚÙ[\‹ÚÙ[ŽÜÝ]KÚÛ\Ø[S˜[YO\‹˜ÛY[›˜[YNÜÝ]KÚÛ\Ø[Q[XZ[\‹˜ÛY[™[XZ[ÛØØ[ÝÜ˜YÙKœÙ]][J	ÝÚÛ\Ø[WÝÚÙ[‰Ë‹ÚÙ[ŠNÛØØ[ÝÜ˜YÙKœÙ]][J	ÝÚÛ\Ø[WÛ˜[YIË‹˜ÛY[›˜[YJNÛØØ[ÝÜ˜YÙKœÙ]][J	ÝÚÛ\Ø[WÙ[XZ[	Ë‹˜ÛY[™[XZ[
NØÛÜÙS[Ù[

NÝØ\Ý
	ÕÚÛ\Ø[HšXÚ[™È\YY‰ÊNØ]ØZ]Ø[Ý[]Ü•šY]Ê
NßKˆ	ÝÚÛ\Ø[KXÛY[	Î˜\Þ[˜Ê‹
OOžØÛÛœÝ›ÙXÝÙ\ØÛÝ[Ï^ßNØ[
	ÖÙ]K]ÚÛ\Ø[K\›ÙXÝIËŠK™›Ü‘XXÚ
OžÚYŠ˜[YHOOIÉÊ\›ÙXÝÙ\ØÛÝ[ÖÞ™]\Ù]ÚÛ\Ø[T›ÙXÝO^˜[YNßJNØÛÛœÝ^[ØY^Û˜[YN™›˜[YK\Ù\›˜[YN™\Ù\›˜[YK[XZ[™™[XZ[\ØÛÝ[Ü\˜Ù[™™\ØÛÝ[Ü\˜Ù[›ÙXÝÙ\ØÛÝ[ËXÝ]™NœÝ]K™Y]ÚÛ\Ø[OÈHY˜XÝ]™NYK™\Ù]Ü\ÜÝÛÜ™ˆHYœ™\Ù]Ü\ÜÝÛÜ™NØÛÛœÝ\Ý]K™Y]ÚÛ\Ø[OØ]ØZ]\J	ËØ\KØYZ[‹ÝÚÛ\Ø[KÉÊÜÝ]K™Y]ÚÛ\Ø[KšY	ÔU	Ë^[ØY
N˜]ØZ]\J	ËØ\KØYZ[‹ÝÚÛ\Ø[IË	ÔÔÕ	Ë^[ØY
NØÛÜÙS[Ù[

NØ]ØZ]ØYÙ][™ÜÊ
NÚYŠ‹[\Ü˜\žWÜ\ÜÝÛÜ™
\ÚÝÕÚÛ\Ø[PÜ™Y[X[Ê‹\Ù\›˜[Y_\Ù\›˜[YK‹[\Ü˜\žWÜ\ÜÝÛÜ™
NÙ[ÙHØ\Ý
	ÕÚÛ\Ø[HšXÚ[™È\]Y‰ÊNßKˆ	Ù\ÚYÛ‹\][ÝIÎ˜\Þ[˜Ê‹
OOžÂˆÛÛœÝš[\ÏVË‹‹™‹™[[Y[Ë˜\ÛÜšË™š[\×NÙ[]H˜\ÛÜšÎÂˆYŠš[\ËœÛÛYJš[OO™š[KœÚ^™OL
ŒL
ŒL
J]›ÝÈ™]È\œ›ÜŠ	ÑXXÚ™Y™\™[˜ÙHš[H]\Ý™HLPˆÜˆÛX[\‹‰ÊNÂˆÛÛœÝX]ØZ]\J	ËØ\KØÝ\ÝÛK\™\]Y\ÝÉË	ÔÔÕ	ËØÝ\ÝÛY\—Û˜[YN™˜Ý\ÝÛY\—Û˜[YKÝ\ÝÛY\—Ù[XZ[™˜Ý\ÝÛY\—Ù[XZ[Û™N™œÛ™K›Ú™XÝÝ\N‰Ñ\ÚYÛˆÙ\šXÙ\È8 %	ÊÙ]K›Ý\Î™››Ý\ËÙXœÚ]N™ÙXœÚ]_	ÉË[Y[œÚ[ÛœÎ–×K™Y™\œ˜[ØÛÙNœ™Y™\œ˜[ÛÙJ
_JNÂˆÛÛœÝÚÙ[[™]ÈT“
‹œÜ[Ý\›
Kš\ÚœÛXÙJÊNØÛÛœÝX]ØZ]\J	ËØ\KÜÜ[Ù^Ú[™ÙIË	ÔÔÕ	ËÝÚÙ[ŸJNÜÝ]K˜ÜÜ™^˜ÜÜ™ŽÂˆ]\ØY\œ›ÜIÉÎÂˆ›ÜŠÛÛœÝš[HÙˆš[\Ê^Ýž^ØÛÛœÝ™[™]È›Ü›Q]J
NÙ™˜\[™
	Ùš[IËš[JNØ]ØZ]\JØ\KÚ›ØœËÉÜ‹š›Ø—ÚYKØ\ÛÜšØ	ÔÔÕ	Ë™
NßXØ]Ú
J^Ý\ØY\œ›ÜYK›Y\ÜØYÙNØœ™XZÎß_BˆÛÜÙS[Ù[

NÚ\ÝÜžKœ\ÚÝ]J[	ÉË	ËÜÜ[	ÊNØ]ØZ]ØYÜ[

NÂˆÚÝÓ[Ù[
	Ñ\ÚYÛˆ™\]Y\Ý™XÙZ]™Y	Ë]ˆÛ\ÜÏHœÝXÚÈÏ‰Ù\ØÊ‹›[X™\Š_OÚÏÛ\ÜÏH›]]Y•Ùx &[™]šY]ÈH\ÚYÛˆØÛÜH[™™\\™HH][ÝKÜ‰Ý\ØY\œ›ÜÉÏ]ˆÛ\ÜÏH››ÝXÙH–[Ý\ˆ™\]Y\Ý\ÈØ]™Y]H™Y™\™[˜ÙHš[HY›Ý\ØYˆ	ÊÙ\ØÊ\ØY\œ›ÜŠJÉËˆ[ÝHØ[ˆ\ØY]œ›ÛHH›Ú™XÝYÙKÙ]‰Î‰ÉßO]ÛˆÛ\ÜÏH˜ˆš[X\žHÚYHˆ]KXXÝ[ÛH˜ÛÜÙH“Ü[ˆ^H™\]Y\ÝØ]ÛÙ]˜
NÂˆKˆ	ØØ[˜Ù[Z›Ø‰Î˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKØØ[˜Ù[	ÔÔÕ	ËÜ™X\ÛÛŽ™œ™X\ÛÛŸJNØÛÜÙS[Ù[

NÝØ\Ý
	Ò›ØˆØ[˜Ù[Y[™™[[Ý™Yœ›ÛHHXÝ]™H]Y]YK‰ÊNÛØØ][Û‹š\ÚIÙ\Ú›Ø\™	ÎßKˆ	ÜÙ[‹X\›Ý™KX\ÛÜšÉÎ˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÜ[Ø\ÛÜšËÉÙ‹™]\Ù]šYKØ\›Ý™X	ÔÔÕ	ËÛ˜[YN™›˜[YKÛÛ™š\›NˆHY˜ÛÛ™š\›K\›\×Ý™\œÚ[ÛŽœÝ]KœÜ[›Ø‹š›Ø—Ý\›\Ë™\œÚ[ÛŸJNØÛÜÙS[Ù[

NÝØ\Ý
	Ð\ÛÜšÈ\›Ý™Y›Üˆš[‰ÊNØ]ØZ]ØYÜ[

NßKˆ	ÜX›XË[Ü™\‰Î˜\Þ[˜Ê‹
OOžÂˆÛÛœÝ^O\Ý]K˜Ø[^I‰ˆYœÚ]WÜÝ\™^WÜ™\]Y\ÝYÂˆÛÛœÝ™]šY]ÏXÚXÚÛÝ]›ÛÙ‹œÝX›Z\ÜÚ[ÛŠ‹^JKš[\Ï\™]šY]Ë™š[\ÎÂˆ[]H˜\ÛÜšÎÂˆYŠš[\ËœÛÛYJ][OOš][K™š[KœÚ^™OL
ŒL
ŒL
J]›ÝÈ™]È\œ›ÜŠ	ÑXXÚ\ÛÜšÈš[H]\Ý™HLPˆÜˆÛX[\‹‰ÊNÂˆÛÛœÝÛÜ™\Žœ‹›Ø›[KÚXÚÛÝ]\ÛÜšÐ\›Ý™Y^[Y[˜Z[YOX]ØZ]ÝX›Z]Ü™\ÚXÚÛÝ]
Ø\KÙ]ÜÜ™Ž˜[YOOžÜÝ]K˜ÜÜ™]˜[YNßK^K][ÝNœÝ]Kœ][ÝK™]šY]Ë^[ØYžË‹‹™ÛÛ™š\›NˆHY˜ÛÛ™š\›K\›\×Ý™\œÚ[ÛŽœÝ]K˜Ø][ÙËš›Ø—Ý\›\Ë™\œÚ[Û‹Ú]WÜÝ\™^WÜ™\]Y\ÝYˆHYœÚ]WÜÝ\™^WÜ™\]Y\ÝY\ÚÜ™\]Y\ÝYˆHYœ\ÚÜ™\]Y\ÝY™\]Y\ÝÚYœÝ]K›Ü™\”™\]Y\ÝY][\ÎœÝ]K˜Ý\œ™[][ÝR][\Ëš[™Ù\œš[œÝ]Kœ][ÝK™š[™Ù\œš[ÚÛ\Ø[WÝÚÙ[ŽœÝ]KÚÛ\Ø[UÚÙ[‹™Y™\œ˜[ØÛÙNœ™Y™\œ˜[ÛÙJ
__JNÂˆYŠÝ]Kœ›Ú™XÝÚXÚÛÝ]	‰ˆ\›Ø›[J\ÚÜ˜ÛX\Š
NÂˆÚXÚÛÝ]›ÛÙ‹˜ÛX\Š
NØÛÜÙS[Ù[

NÚ\ÝÜžKœ\ÚÝ]J[	ÉË	ËÜÜ[	ÊNÂˆYŠÚXÚÛÝ]Ë\›
^ÛØØ][Û‹š™YXÚXÚÛÝ]\›Ü™]\›ŽßBˆ]ØZ]ØYÜ[

NÂˆÚÝÓ[Ù[
	Ö[Ý\ˆÜ™\ˆ\ÈØ]™Y	Ë]ˆÛ\ÜÏHœÝXÚÈÏ‰Ù\ØÊ‹›[X™\Š_OÚÏÛ\ÜÏH›]]Y‰Ø\ÛÜšÐ\›Ý™YÉÖ[Ý\ˆ\ÛÜšÈ\›Ý˜[[™XØÙ\Y\›\È\™HØ]™YÚ]\ÈÜ™\‹‰Î‰Ö[Ý\ˆ›Ú™XÝ\ÈØ]™YˆÚXÚÈ[Ý\ˆš]˜]HÜ™\ˆYÙH›ÜˆH™^Ý\‰ßOÜX™[Û\ÜÏH™šY[Ü[”š]˜]H›Ú™XÝ[šÏÜÜ[[œ]˜[YOH‰Ù\ØÊ‹œÜ[Ý\›
_Hˆ™XYÛ›OÛX™[‰Ü›Ø›[OÉÏ]ˆÛ\ÜÏH››ÝXÙH‰ÊÙ\ØÊ›Ø›[JJÉÈ[Ý\ˆš[\È[™›Ú™XÝ™[XZ[ˆØ]™Y[ˆ\Èœ›ÝÜÙ\‹Ù]‰Î‰ÉßIØ^I‰œ^[Y[˜Z[YÉÏ]ÛˆÛ\ÜÏH˜ˆš[X\žHÚYHˆ]KXXÝ[ÛH›Û›[™K\^H”™]žHÙXÝ\™H^[Y[	ÊÚXÛÛŠ	Ø\œ›ÝÉÊJÉÏØ]Û‰Î‰Ï]ÛˆÛ\ÜÏH˜ˆš[X\žHÚYHˆ]KXXÝ[ÛH˜ÛÜÙH“Ü[ˆ^HÜ™\Ø]Û‰ßOÙ]˜
NÂˆKˆ	ØÝ\ÝÛK\][ÝIÎ˜\Þ[˜Ê‹
OOžÂˆÛÛœÝš[\ÏVË‹‹™‹™[[Y[Ë˜\ÛÜšË™š[\×NÙ[]H˜\ÛÜšÎÂˆYŠš[\ËœÛÛYJš[OO™š[KœÚ^™OL
ŒL
ŒL
J]›ÝÈ™]È\œ›ÜŠ	ÑXXÚ\ÛÜšÈš[H]\Ý™HLPˆÜˆÛX[\‹‰ÊNÂˆÛÛœÝ[Y[œÚ[ÛœÏX[
	ÖÙ]KXÝ\ÝÛKY[Y[œÚ[Û—IËŠK›X\
›ÝÏOžØÛÛœÝšY[ÏX[
	Ú[œ]	Ë›ÝÊNÜ™]\›ˆÛX™[™šY[ÖÌK˜[YKÚY™šY[ÖÌWK˜[YKZYÚ™šY[ÖÌ—K˜[YK]X[]N™šY[ÖÌ×K˜[Y_NßJK™š[\ŠOžÚYšZYÚ
NÂˆÛÛœÝX]ØZ]\J	ËØ\KØÝ\ÝÛK\™\]Y\ÝÉË	ÔÔÕ	ËË‹‹™[Y[œÚ[ÛœË™Y™\œ˜[ØÛÙNœ™Y™\œ˜[ÛÙJ
_JNÂˆÛÛœÝÚÙ[[™]ÈT“
‹œÜ[Ý\›
Kš\ÚœÛXÙJÊNØÛÛœÝX]ØZ]\J	ËØ\KÜÜ[Ù^Ú[™ÙIË	ÔÔÕ	ËÝÚÙ[ŸJNÜÝ]K˜ÜÜ™^˜ÜÜ™ŽÂˆ]\ØY\œ›ÜIÉÎÂˆ›ÜŠÛÛœÝš[HÙˆš[\Ê^Ýž^ØÛÛœÝ™[™]È›Ü›Q]J
NÙ™˜\[™
	Ùš[IËš[JNØ]ØZ]\JØ\KÚ›ØœËÉÜ‹š›Ø—ÚYKØ\ÛÜšØ	ÔÔÕ	Ë™
NßXØ]Ú
J^Ý\ØY\œ›ÜYK›Y\ÜØYÙNØœ™XZÎß_BˆÛÜÙS[Ù[

NÚ\ÝÜžKœ\ÚÝ]J[	ÉË	ËÜÜ[	ÊNØ]ØZ]ØYÜ[

NÂˆÚÝÓ[Ù[
	ÐÝ\ÝÛH][ÝH™\]Y\Ý™XÙZ]™Y	Ë]ˆÛ\ÜÏHœÝXÚÈÏ‰Ù\ØÊ‹›[X™\Š_OÚÏÛ\ÜÏH›]]Y•ÙH]™H[Ý\ˆ›Ú™XÝ]Z[È[™Ú[™]šY]È[H›ÜˆHÝ\ÝÛH][ÝKÜ‰Ý\ØY\œ›ÜÉÏ]ˆÛ\ÜÏH››ÝXÙH–[Ý\ˆ™\]Y\Ý\ÈØ]™Y]Hš[HØ\È›Ý\ØYYˆ	ÊÙ\ØÊ\ØY\œ›ÜŠJÉËˆ[ÝHØ[ˆ\ØY]œ›ÛH[Ý\ˆÜ™\ˆYÙKÙ]‰Î‰ÉßO]ÛˆÛ\ÜÏH˜ˆš[X\žHÚYHˆ]KXXÝ[ÛH˜ÛÜÙH“Ü[ˆ^H™\]Y\ÝØ]ÛÙ]˜
NÂˆKˆ	Û™]ËZ›Ø‰Î˜\Þ[˜Ê‹
OOžØÛÛœÝ][\ÏX[
	ÖÙ]K\][ÝK[[™WIËŠK›X\
›ÝÏOŠÜ›ÙXÝÚY“[X™\Š	
	ÖÙ]K[[™K\›ÙXÝIË›ÝÊK˜[YJK\ØÜš\[ÛŽ‰
	ÖÙ]K[[™KY\ØÜš\[Û—IË›ÝÊK˜[YKÚY‰
	ÖÙ]K[[™K]ÚYIË›ÝÊK˜[YKZYÚ‰
	ÖÙ]K[[™KZZYÚIË›ÝÊK˜[YK]X[]N‰
	ÖÙ]K[[™K\]X[]WIË›ÝÊK˜[Y_JJNØÛÛœÝX]ØZ]\J	ËØ\KÜÝY™‹Ú›ØœÉË	ÔÔÕ	ËË‹‹™ÛÜšÙ›Ý×ÚY“[X™\ŠÛÜšÙ›Ý×ÚY
K][\ßJNÝØ\Ý
	Ò›Ø‹][ÝH[™›ÙXÝ[ÛˆÚXÚÛ\ÝÜ™X]Y‰ÊNÛØØ][Û‹š\ÚIÚ›Ø‹ÉÊÜ‹š›Ø—ÚYßKˆ	ÛÛ›[™K\šXÙKXÛÜœ™XÝ[Û‰Î˜\Þ[˜Ê‹
OOžØÛÛœÝX]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÛÛ›[™K\šXÙKXÛÜœ™XÝ[Û˜	ÔÔÕ	ËÝ™\œÚ[ÛŽœÝ]Kš›Ø‹œ][ÝWÝ™\œÚ[Û‹™]×ÜšXÙN™›™]×ÜšXÙK™X\ÛÛŽ™œ™X\ÛÛ‹ÛÛ™š\›NˆHY˜ÛÛ™š\›_JNØÛÜÙS[Ù[

NÝØ\Ý
‹˜Ý\ÝÛY\—Û›ÝYšYYÉÐÛÜœ™XÝY][ÝH[XZ[YÈÝ\ÝÛY\‹‰Î‰ÔšXÙHÛÜœ™XÝYˆ[XZ[Ø\È›Ý[]™\™YÈÚ\™HH\]YÜ[[šÈÚ]HÝ\ÝÛY\‹‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ	ÙY]\][ÝIÎ˜\Þ[˜Ê‹
OOžØÛÛœÝ[™\ÏX[
	ÖÙ]K\][ÝK\™]š\Ú[Û‹[[™WIËŠK›X\
›ÝÏOŠÜÛÝ\˜ÙWÚ[™^œ›ÝË™]\Ù]œÛÝ\˜ÙR[™^OOIÉÏÛ[“[X™\Š›ÝË™]\Ù]œÛÝ\˜ÙR[™^
K˜[YN‰
	ÖÙ]K\™]š\Ú[Û‹[˜[YWIË›ÝÊK˜[YK\ØÜš\[ÛŽ‰
	ÖÙ]K\™]š\Ú[Û‹Y\ØÜš\[Û—IË›ÝÊK˜[YK]X[]N‰
	ÖÙ]K\™]š\Ú[Û‹\]X[]WIË›ÝÊK˜[YK[š]‰
	ÖÙ]K\™]š\Ú[Û‹][š]IË›ÝÊK˜[YKÚY‰
	ÖÙ]K\™]š\Ú[Û‹]ÚYIË›ÝÊK˜[YKZYÚ‰
	ÖÙ]K\™]š\Ú[Û‹ZZYÚIË›ÝÊK˜[YKÙ[ÝÝ[‰
	ÖÙ]K\™]š\Ú[Û‹\šXÙWIË›ÝÊK˜[YKÛÜÝÝÝ[‰
	ÖÙ]K\™]š\Ú[Û‹XÛÜÝIË›ÝÊK˜[YK\ÛÜš×Ü™\]Z\™Y‰
	ÖÙ]K\™]š\Ú[Û‹X\ÛÜš×IË›ÝÊK˜ÚXÚÙYJJNØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÜ][ÝX	ÔÔÕ	ËË‹‹™[™\Ë™\œÚ[ÛŽœÝ]Kš›Ø‹œ][ÝWÝ™\œÚ[Û‹Ú\™Ù\×Ý™\šYšYYˆHY˜Ú\™Ù\×Ý™\šYšYYJNØÛÜÙS[Ù[

NÝØ\Ý
	Ó™]È][ÝH™\œÚ[ÛˆØ]™YˆX›\ÚÚ[ˆ™]šY]ÙY‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆX›\Ú˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÜX›\Ú	ÔÔÕ	ËÜ™]šY]ÙYˆHYœ™]šY]ÙY™\œÚ[ÛŽœÝ]Kš›Ø‹œ][ÝWÝ™\œÚ[ÛŸJNØÛÜÙS[Ù[

NÝØ\Ý
	Ô][ÝHX›\ÚYÈHÝ\ÝÛY\ˆÜ[‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆØÚY[N˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÛY]X	ÔUÒ	ËË‹‹™\ÜÚYÛ™YWÚY“[X™\Š˜\ÜÚYÛ™YWÚY
_[JNØÛÜÙS[Ù[

NÝØ\Ý
	ÔØÚY[H\]Y‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ	Ø›ØÚË]\ÚÉÎ˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÝY™‹Ý\ÚÜËÉÙ‹™]\Ù]šYKØXÝ[Û˜	ÔÔÕ	ËØXÝ[ÛŽ‰Ø›ØÚÉË›ÝN™››Ý_JNØÛÜÙS[Ù[

NØ]ØZ]™Yœ™\ÚY\•\ÚÊ
NßKˆ	ØY]\ÚÉÎ˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÝ\ÚÜØ	ÔÔÕ	ËÝ]N™]K\\Y[™™\\Y[Ø]N™™Ø]K\[™[˜ÚY\Î–Ë‹‹™‹™[[Y[Ë™\[™[˜ÚY\ËœÙ[XÝYÜ[Ûœ×K›X\
ÏO“[X™\ŠË˜[YJJ_JNØÛÜÙS[Ù[

NØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ\ÛÜšÎ˜\Þ[˜ÊŠOOžØ]ØZ]\JØ\KÚ›ØœËÉÙ‹™]\Ù]š›Ø’YKØ\ÛÜšØ	ÔÔÕ	Ë™]È›Ü›Q]JŠJNØÛÜÙS[Ù[

NÝØ\Ý
	Ð\ÛÜšÈ\ØYY‰ÊNÚYŠ‹™]\Ù]œÜ[OOIÝYIÊX]ØZ]ØYÜ[

NÙ[ÙH]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ	Ù[XZ[\›ÛÙ‹X\›Ý˜[	Î˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÜ›ÛÙœËÉÙ‹™]\Ù]šYKÙ[XZ[X\›Ý˜[	ÔÔÕ	ËÛ˜[YN™›˜[YK\›Ý™YØ]™˜\›Ý™YØ][XZ[Ü™Y™\™[˜ÙN™™[XZ[Ü™Y™\™[˜ÙKÛÛ™š\›NˆHY˜ÛÛ™š\›_JNØÛÜÙS[Ù[

NÝØ\Ý
	Ñ[XZ[\›Ý˜[™XÛÜ™Y‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ	Ý\ØY\›ÛÙ‰Î˜\Þ[˜ÊŠOOžØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÜ›ÛÙœØ	ÔÔÕ	Ë™]È›Ü›Q]JŠJNØÛÜÙS[Ù[

NÝØ\Ý
	Ó™]È›ÛÙˆ™\œÚ[Ûˆ\È™XYH›Üˆ™]šY]Ë‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ^[Ý]˜\Þ[˜Ê‹
OOžØÛÛœÝ\ÛÜšÏ^ßNÓØš™XÝ™[šY\Ê
K™š[\Š
ÚË—JOOšËœÝ\ÕÚ]
	Ø\ÉÊI‰ŠK™›Ü‘XXÚ

ÚË—JOO˜\ÛÜšÖÚËœÛXÙJ
WOS[X™\ŠŠJNØÛÛœÝX]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÛ^[Ý]	ÔÔÕ	ËØ\ÛÜšËš]™™š]X›\ÚØ\×Ü›ÛÙŽˆHYœX›\ÚØ\×Ü›ÛÙŸJNØÛÜÙS[Ù[

NØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NÜÚÝÓ[Ù[
œX›\ÚØ\×Ü›ÛÙÉÐÛÛ\]H›ÛÙˆÙ[™\˜]Y	Î‰Ô™Y™\™[˜ÙH^[Ý]Ù[™\˜]Y	Ë]ˆÛ\ÜÏHœÝXÚÈÛ\ÜÏH›]]Y‰ÙœX›\ÚØ\×Ü›ÛÙÉÕH™]È›ÛÙˆ\È›ÝÈ]˜Z[X›H[ˆHÝ\ÝÛY\ˆÜ[›Üˆ\›Ý˜[‰Î‰Õ\È\ÈH™Y™\™[˜ÙH[\]K›Ý[ˆ\›Ý˜[Y[YÚX›H›ÛÙ‹‰ßOÜHÛ\ÜÏH˜ˆš[X\žHˆ™YH‹Ø\KØ\ÜÙ]ËÉÜ‹˜\ÜÙ]ÚYHˆ\™Ù]H—Ø›[šÈˆ™[H››ÛÜ[™\ˆ“Ü[ˆ[Y[œÚ[Û™Y^[Ý]	ÚXÛÛŠ	Ø\œ›ÝÉÊ_OØOÛ\ÜÏH™šY[Z[”™]šY]ÈÛ›Kˆ›È›YY[\Ú^™Hš[ØØ[KPÐÈÝ]]Üˆ’TØÝ]]\È[˜ÛYYÜÙ]˜
NßKˆ	Ü^[Y[[[šÉÎ˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÜ^[Y[[[šØ	ÔÔÕ	Ë
NØÛÜÙS[Ù[

NÝØ\Ý
	Ô]ZXÚÐ›ÛÚÜÈ[šÈ]XÚY‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ	Ý™\šYžK\^[Y[	Î˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÜ^[Y[Ø	ÔÔÕ	ËË‹‹™™\šYšYYÚ[—Ü]ZXÚØ›ÛÚÜÎˆHY™\šYšYYÚ[—Ü]ZXÚØ›ÛÚÜßJNØÛÜÙS[Ù[

NÝØ\Ý
	Ô^[Y[™XÛÜ™Y[™›ÙXÝ[ÛˆÚXÚÜÈ\]Y‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ	Ý›ÚY\^[Y[	Î˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÝY™‹Ü^[Y[ËÉÙ‹™]\Ù]šYKÝ›ÚY	ÔÔÕ	Ë
NØÛÜÙS[Ù[

NÝØ\Ý
	ÓØØ[™\šYšXØ][Ûˆ™XÛÜ™›ÚYYˆ]ZXÚÐ›ÛÚÜÈØ\È›ÝÚ[™ÙY‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ	ÜÝY™‹[Y\ÜØYÙIÎ˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÝY™‹Ú›ØœËÉÜÝ]Kš›Ø‹šYKÛY\ÜØYÙX	ÔÔÕ	ËÛY\ÜØYÙN™›Y\ÜØYÙKX›XÎˆHYœX›XßJNÝØ\Ý
	Ò›Øˆ\]HØ]™Y‰ÊNØ]ØZ]ØY›ØŠÝ]Kš›Ø‹šY
NßKˆ›ÙXÝ˜\Þ[˜Ê‹
OOžØÛÛœÝ\Ý]K™Y]›ÙXÝØÛÛœÝÛÛ™šYÏ^Ë‹‹œ˜ÛÛ™šYßNÙ›ÜŠÛÛœÝÙ^HÙˆÉÝ[š]	Ë	Ù\ØÜš\[Û‰Ë	ÜÙ[Ü\—ÜÜY	Ë	ØÛÜÝÜ\—ÜÜY	Ë	ÛZ[š[][WÜšXÙIË	ÜÙ]\ÜšXÙIË	ÜÙ]\ØÛÜÝ	Ë	ÝØ\ÝWÜ\˜Ù[	Ë	ÛX›Ü—ÛZ[]\×Ü\—Ý[š]	Ë	ÛZ[—ÝÚY	Ë	ÛZ[—ÚZYÚ	Ë	ÙY˜][ÝÚY	Ë	ÙY˜][ÚZYÚ	Ë	ÛX^ÝÚY	Ë	ÛX^ÚZYÚ	Ë	ÛX^Ü]X[]I×JXÛÛ™šYÖÚÙ^WOYÚÙ^WNÙ›ÜŠÛÛœÝÙ^HÙˆÉÜXÚ×ÚXY\—ÍÜšXÙIË	ÜXÚ×ÜXÚØYÚ[™×ÜšXÙIË	ÜXÚ×Ù\ÚYÛ—ÜšXÙI×JZYŠÚÙ^WHOO][™Yš[™Y
XÛÛ™šYÖÚÙ^WOYÚÙ^WNØÛÛ™šYËš[œÝ[HHYš[œÝ[ØÛÛ™šYËœÝ\Ü×Û][\WÙ[Y[œÚ[ÛœÏHHYœÝ\Ü×Û][\WÙ[Y[œÚ[ÛœÎØÛÛ™šYËœÙ[—Ø\›Ý™WØ\ÛÜšÏHHYœÙ[—Ø\›Ý™WØ\ÛÜšÎØÛÛ™šYËœ™\]Z\™\×Ú[œÝ[][ÛHHYœ™\]Z\™\×Ú[œÝ[][ÛŽØÛÛ™šYËš\×ÝÜ˜\HHYš\×ÝÜ˜\ØÛÛ™šYËY\œÏYY\œËœÜ]
	×‰ÊK›X\
Ožš[J
JK™š[\Š›ÛÛX[ŠK›X\
[™OOžØÛÛœÝÙœ›ÛK][\Y\—O[[™KœÜ]
	Î‰ÊNÚYŠYœ›Û_[][\Y\Š]›ÝÈ™]È\œ›ÜŠ	ÑXXÚ]X[]H˜[™]\Ý\ÙHÝ\›][\Y\‹‰ÊNÜ™]\›ˆÙœ›ÛN“[X™\Šœ›ÛJK][\Y\Ž›][\Y\‹š[J
_NßJNØÛÛœÝ›ÙO^Û˜[YN™›˜[YKØ]YÛÜžN™˜Ø]YÛÜžKÛÜšÙ›Ý×ÚY“[X™\ŠÛÜšÙ›Ý×ÚY
KXÝ]™NˆHY˜XÝ]™KX›XÎˆHYœX›XËÛÛ™šYË™\œÚ[ÛŽœ™\œÚ[ÛŸNØ]ØZ]\J	ËØ\KØYZ[‹Ü›ÙXÝÉÊÊšYÉËÉÊÜšY‰ÉÊKšYÉÔU	Î‰ÔÔÕ	Ë›ÙJNÜÝ]K˜Ø][ÙÏX]ØZ]\J	ËØ\KØØ][ÙÉÊNØÛÜÙS[Ù[

NÝØ\Ý
	Ô›ÙXÝØ]™Yˆ^\Ý[™È›ØœÈ™[XZ[ˆ[˜Ú[™ÙY‰ÊNØ]ØZ]ØY›ÙXÝÊ
NßKˆÛÜšÙ›ÝÎ˜\Þ[˜Ê‹
OOžØÛÛœÝÏ\Ý]K™Y]ÛÜšÙ›ÝËÝ\ÏX[
	ÖÙ]K\Ý\IËŠK›X\
›ÝÏOŠÝ]N‰
	ÖÙ]K\Ý\]]WIË›ÝÊK˜[YK\\Y[‰
	ÖÙ]K\Ý\Y\\Y[IË›ÝÊK˜[YKØ]N‰
	ÖÙ]K\Ý\YØ]WIË›ÝÊK˜[YK\[™×ÛÛŽ‰
	ÖÙ]K\Ý\Y\×IË›ÝÊK˜[YKœÜ]
	Ë	ÊK›X\
O‹š[J
JK™š[\Š›ÛÛX[ŠK›X\
[X™\Š_JJNØ]ØZ]\J	ËØ\KØYZ[‹ÝÛÜšÙ›ÝÜÉÊÊËšYÉËÉÊÝËšY‰ÉÊKËšYÉÔU	Î‰ÔÔÕ	ËÛ˜[YN™›˜[YKÝ\Ë™\œÚ[ÛŽË™\œÚ[ÛŸJNØÛÜÙS[Ù[

NÝØ\Ý
	ÕÛÜšÙ›ÝÈØ]™Y›Üˆ™]È›ØœË‰ÊNØ]ØZ]ØYÛÜšÙ›ÝÜÊ
NßKˆÙ][™ÜÎ˜\Þ[˜Ê‹
OOžØ]ØZ]\J	ËØ\KØYZ[‹ÜÙ][™ÜÉË	ÔU	ËË‹‹™˜]\×Û]™NˆHYœ˜]\×Û]™KÚXÚÛÝ]Ù[˜X›YˆHY˜ÚXÚÛÝ]Ù[˜X›YÚXÚÛÝ]Ý^Ü™]šY]ÙYˆHY˜ÚXÚÛÝ]Ý^Ü™]šY]ÙYÚXÚÛÝ]ÜXÚÝ\Ù[˜X›YˆHY˜ÚXÚÛÝ]ÜXÚÝ\Ù[˜X›YÚXÚÛÝ]ÜÚ\[™×Ù[˜X›YˆHY˜ÚXÚÛÝ]ÜÚ\[™×Ù[˜X›YJNÜÝ]K˜Ø][ÙÏX]ØZ]\J	ËØ\KØØ][ÙÉÊNÝØ\Ý
	ÔÚÜY˜][ÈØ]™Y‰ÊNØ]ØZ]ØYÙ][™ÜÊ
NßKˆ	Û™]Ë]\Ù\‰Î˜\Þ[˜Ê‹
OOžØÛÛœÝX]ØZ]\J	ËØ\KØYZ[‹Ý\Ù\œÉË	ÔÔÕ	Ë
NÜÚÝÐÜ™Y[X[Ê‹[\Ü˜\žWÜ\ÜÝÛÜ™
NØ]ØZ]ØYX[J
NßKˆ\ÜÝÛÜ™˜\Þ[˜Ê‹
OOžÚYŠ›™]×Ü\ÜÝÛÜ™OOY˜ÛÛ™š\›WÜ\ÜÝÛÜ™
]›ÝÈ™]È\œ›ÜŠ	ÕH™]È\ÜÝÛÜ™ÈÈ›ÝX]Ú‰ÊNØÛÛœÝX]ØZ]\J	ËØ\KØ]]Ü\ÜÝÛÜ™	Ë	ÔÔÕ	ËØÝ\œ™[Ü\ÜÝÛÜ™™˜Ý\œ™[Ü\ÜÝÛÜ™™]×Ü\ÜÝÛÜ™™›™]×Ü\ÜÝÛÜ™JNÜÝ]K˜ÜÜ™\‹˜ÜÜ™ŽØÛÜÙS[Ù[

NÝØ\Ý
	Ô\ÜÝÛÜ™Ú[™ÙYˆÝ\ˆÙ\ÜÚ[ÛœÈÙ\™HÚYÛ™YÝ]‰ÊNßKˆ	ØXØÙ\\][ÝIÎ˜\Þ[˜Ê‹
OOžØ]ØZ]\J	ËØ\KÜÜ[ØXØÙ\\][ÝIË	ÔÔÕ	ËÛ˜[YN™›˜[YKÛÛ™š\›NˆHY˜ÛÛ™š\›K\›\×Ý™\œÚ[ÛŽœÝ]KœÜ[›Ø‹š›Ø—Ý\›\Ë™\œÚ[Û‹™\œÚ[ÛŽœÝ]KœÜ[›Ø‹œ][ÝWÝ™\œÚ[ÛŸJNØÛÜÙS[Ù[

NÝØ\Ý
	Ô][ÝHXØÙ\Y‰ÊNØ]ØZ]ØYÜ[

NßKˆ	ØÝ\ÝÛK\^[Y[	Î˜\Þ[˜Ê‹
OOžØÛÛœÝX]ØZ]\J	ËØ\KÜÜ[ØÝ\ÝÛKXÚXÚÛÝ]	Ë	ÔÔÕ	ËÜ^[Y[ÚÚ[™™œ^[Y[ÚÚ[™JNÚYŠ‹œZY
^ØÛÜÙS[Ù[

NÝØ\Ý
	Ô^[Y[™XÙZ]™Y‰ÊNØ]ØZ]ØYÜ[

NÜ™]\›Žß[ØØ][Û‹š™Y\‹\›ßKˆ	Ü›ÛÙ‹YXÚ\Ú[Û‰Î˜\Þ[˜Ê‹
OOžØ]ØZ]\JØ\KÜÜ[Ü›ÛÙœËÉÜÝ]KœÜ[›Ø‹œ›ÛÙœÖÌKšYKÙXÚ\Ú[Û˜	ÔÔÕ	ËØXÝ[ÛŽ™‹™]\Ù]™XÚ\Ú[Û‹˜[YN™›˜[YKÛÛ[Y[™˜ÛÛ[Y[ÛÛ™š\›NˆHY˜ÛÛ™š\›K\›\×Ý™\œÚ[ÛŽœÝ]KœÜ[›Ø‹š›Ø—Ý\›\Ë™\œÚ[ÛŸJNØÛÜÙS[Ù[

NÝØ\Ý
‹™]\Ù]™XÚ\Ú[ÛOOIØ\›Ý™IÏÉÔ›ÛÙˆ\›Ý˜[™XÛÜ™Y‰Î‰ÐÚ[™Ù\ÈÙ[ÈH\ÚYÛ™\‹‰ÊNØ]ØZ]ØYÜ[

NßKˆ	ÜÜ[[Y\ÜØYÙIÎ˜\Þ[˜Ê‹
OOžØ]ØZ]\J	ËØ\KÜÜ[ÛY\ÜØYÙIË	ÔÔÕ	ËÛY\ÜØYÙN™›Y\ÜØYÙ_JNÝØ\Ý
	ÓY\ÜØYÙHØ]™YÈ[Ý\ˆ›Ø‹‰ÊNØ]ØZ]ØYÜ[

NßKˆ	ÜÜ[X\Ú[Y[	Î˜\Þ[˜Ê‹
OOžØ]ØZ]\J	ËØ\KÜÜ[Ø\Ú[Y[\™\]Y\Ý	Ë	ÔÔÕ	Ë
NØÛÜÙS[Ù[

NÝØ\Ý
	ÔØÚY[[™È™\]Y\ÝÙ[ˆHÚÜÚ[ÛÛ™š\›H]˜Z[Xš[]K‰ÊNØ]ØZ]ØYÜ[

NßKˆ	ÜÜ[\™]šY]ÉÎ˜\Þ[˜Ê‹
OOžØ]ØZ]\J	ËØ\KÜÜ[Ü™]šY]ÉË	ÔÔÕ	Ë
NÝØ\Ý
	Õ[šÈ[ÝKˆ[Ý\ˆ™\šYšYY™]šY]ÈØ\ÈØ]™Y‰ÊNØ]ØZ]ØYÜ[

NßKˆ	Ü^[Y[[›ÝXÙIÎ˜\Þ[˜Ê‹
OOžØÛÛœÝX]ØZ]\J	ËØ\KÜÜ[Ü^[Y[[›ÝXÙIË	ÔÔÕ	Ë
NØÛÜÙS[Ù[

NÝØ\Ý
‹›Y\ÜØYÙJNØ]ØZ]ØYÜ[

NßKŸNÂ‚˜ÛÛœÝX\šÙ][™Ñ\Ú›Ø\™XÜ™X]SX\šÙ][™Ñ\Ú›Ø\™
Ø\KÝY™”Ú[\ØË[Û™^K›Ü›\ËØ\ÝJNÂ˜ÛÛœÝ[XZ[[ZÙOXÜ™X]Q[XZ[[ZÙJØ\KÝY™”Ú[\ØËÚÝÓ[Ù[ÛÜÙS[Ù[›Ü›\ËXÝ[ÛœËØ\ÝJNÂ˜ÛÛœÝÜ›Q\Ú›Ø\™XÜ™X]PÜ›Q\Ú›Ø\™
Ø\KÝY™”Ú[\ØË[Û™^KÚÝÓ[Ù[ÛÜÙS[Ù[›Ü›\ËXÝ[ÛœËØ\ÝJNÂ˜ÛÛœÝÝ\™^\Ñ\Ú›Ø\™XÜ™X]TÚ]TÝ\™^\ÊØ\KÝ]K\ØËÝY™”Ú[ÚÝÓ[Ù[XÝ[ÛœË›Ü›\ßJNÂ˜ÚXÚÛÝ]›ÛÙXÜ™X]PÚXÚÛÝ]›ÛÙŠÜÝ]K\ØËÚÜŠ
OOœÚÜØ\ÝJNÂœ™]Ø\™ÕZOXÜ™X]T™]Ø\™ÊØ\KÝ]K\ØË[Û™^K]KÚÝÓ[Ù[ÛÜÙS[Ù[Ø\ÝÝY™”Ú[[œ]Ù[XÝÚXÚØ›Þ›Ü›Q›ÛÝ\‹XÝ[ÛœË›Ü›\ËØYÜ[JNÂœÚÜXÜ™X]TÚÜ
Ü™]Ø\™ÐXØÛÝ[›ÞØ[]Oœ™]Ø\™ÕZK˜XØÛÝ[›Þ
Ø[]
KÝ]K\\K\ØË[Û™^K[œ]Ù[XÝ›Ü›Q›ÛÝ\‹ÚÝÓ[Ù[ÛÜÙS[Ù[Ø\ÝX›XÒXY\‹X›XÔ›ÙXÝ˜[YK›ÙXÝ]Ù]X›XÔÙ[ËÝÜ™Yœ›Û›ÙXÝÑ›Ü‹›ÙXÝXÛÛ‹›ÙXÝ[XYÙK™X[ÛÜšÑØ[\žKØ[Ý[]Ü•šY]Ë™XØ[Ý[]KÝ\œ™[][\ËÜ™\“[Ù[XÝ[ÛœË›Ü›\ßJNÂ‚™ØÝ[Y[˜Y]™[\Ý[™\Š	ØÛXÚÉË\Þ[˜È]™[OžÂˆÛÛœÝ]ÛY]™[\™Ù]˜ÛÜÙ\Ý
	ÖÙ]KXXÝ[Û—IÊNÚYŠX]ÛŸ]Û‹™\ØX›Y
\™]\›ŽÂˆÛÛœÝ[™\XXÝ[ÛœÖØ]Û‹™]\Ù]˜XÝ[Û—NÚYŠZ[™\Š\™]\›ŽÂˆ]™[œ™]™[Y˜][

NØ]Û‹™\ØX›Y]YNÂˆž^Ø]ØZ][™\Š]ÛŠNßXØ]Ú
\œ›ÜŠ^ÝØ\Ý
\œ›Ü‹›Y\ÜØYÙKYJNßBˆš[˜[^Ø]Û‹™\ØX›YY˜[ÙNßBŸJNÂ™ØÝ[Y[˜Y]™[\Ý[™\Š	ÜÝX›Z]	Ë\Þ[˜È]™[OžÂˆÛÛœÝ›Ü›OY]™[\™Ù]˜ÛÜÙ\Ý
	Ù›Ü›VÙ]KY›Ü›WIÊNÚYŠY›Ü›J\™]\›ŽÂˆ]™[œ™]™[Y˜][

NØÛÛœÝ[™\Y›Ü›\ÖÙ›Ü›K™]\Ù]™›Ü›WNÚYŠZ[™\Š\™]\›ŽÂˆÛÛœÝ]ÛI
	Ø]Û–Ý\OHœÝX›Z]—K]ÛŽ››Ý
Ý\WJIË›Ü›JK\œ›Ü›ÞI
	Ë™›Ü›KY\œ›Ü‰Ë›Ü›JNÂˆYŠ\œ›Ü›Þ
Y\œ›Ü›Þ^ÛÛ[IÉÎÚYŠ]ÛŠX]Û‹™\ØX›Y]YNÂˆž^Ø]ØZ][™\Š›Ü›KØš™XÝ™œ›ÛQ[šY\Ê™]È›Ü›Q]J›Ü›JJJNßBˆØ]Ú
\œ›ÜŠ^ÚYŠ\œ›Ü›Þ
Y\œ›Ü›Þ^ÛÛ[Y\œ›Ü‹›Y\ÜØYÙNÙ[ÙHØ\Ý
\œ›Ü‹›Y\ÜØYÙKYJNßBˆš[˜[^ÚYŠ]ÛŠX]Û‹™\ØX›YY˜[ÙNßBŸJNÂ™ØÝ[Y[˜Y]™[\Ý[™\Š	Ú[œ]	Ë]™[OžÂˆYŠ]™[\™Ù]˜ÛÜÙ\Ý
	ÈØØ[Ý[]Ü‰ÊJ^ØÛX\•[Y[Ý]
Ý]K˜Ø[Õ[Y\ŠNÚYŠ	
	ÈØÛÛ[YKX‰ÊJI
	ÈØÛÛ[YKX‰ÊK™\ØX›Y]YNÜÝ]K˜Ø[Õ[Y\\Ù][Y[Ý]


OOœ™XØ[Ý[]J
KL
NßBˆYŠ]™[\™Ù]šYOOIÚ›Ø‹\ÙX\˜Ú	Ê\™[™\›Ø\™

NÂˆYŠ]™[\™Ù]˜ÛÜÙ\Ý
	Ë\ÙÝXÛÛ™šYÉÊJ]\]U\ÙÝ™]šY]Ê
NÂˆYŠ]™[\™Ù]˜ÛÜÙ\Ý
	ÈØØ[Ý[]Ü‰ÊI‰–ÉÝÚY	Ë	ÚZYÚ	×Kš[˜ÛY\Ê]™[\™Ù]›˜[YJJ]\]U\ÙÝ™]šY]Ê
NÂŸJNÂ™ØÝ[Y[˜Y]™[\Ý[™\Š	ØÚ[™ÙIË]™[OžÂˆYŠ]™[\™Ù]šYOOIÝ\ÙÝ[ÙÛËYš[IÊ^ÛØY\ÙÝÙÛÊ]™[\™Ù]™š[\ÏË–ÌJK[Š

OOœ™XØ[Ý[]J
JK˜Ø]Ú
OOØ\Ý
K›Y\ÜØYÙKYJJNÜ™]\›ŽßBˆYŠ]™[\™Ù]›˜[YOOOIÝ\ÙÝÚY[]IÊ^Ý\]U\ÙÝ™]šY]Ê
NÜ™XØ[Ý[]J
NßBˆYŠ]™[\™Ù]›˜[YOOOIØÛÝ™\˜YÙWÛÜ[Û‰Ê^Ø[
	Ë˜ÛÝ™\˜YÙKXØ\™	ÊK™›Ü‘XXÚ
Ø\™O˜Ø\™˜Û\ÜÓ\ÝÙÙÛJ	ÜÙ[XÝY	ËØ\™˜ÛÛZ[œÊ]™[\™Ù]
JJNÝ\]PÛÝ™\˜YÙUš\ÝX[Ê
NÜ™XØ[Ý[]J
NßBˆYŠ]™[\™Ù]›˜[YOOOIÝ™ZXÛWÝ\IÉ‰™]™[\™Ù]˜ÛÜÙ\Ý
	ÈØØ[Ý[]Ü‰ÊJ^Ý\]PÛÝ™\˜YÙUš\ÝX[Ê
NÜ™XØ[Ý[]J
NßBˆYŠ]™[\™Ù]›X]Ú\Ê	ÖÙ]K[[™K\›ÙXÝIÊJ^ØÛÛœÝ›ÝÏY]™[\™Ù]˜ÛÜÙ\Ý
	ÖÙ]K\][ÝK[[™WIÊK\Ý]Kœ›ÙXÝË™š[™
OœšYOOS[X™\Š]™[\™Ù]˜[YJJNØÛÛœÝÏI
	ÖÙ]K[[™K]ÚYIË›ÝÊKI
	ÖÙ]K[[™KZZYÚIË›ÝÊKOI
	ÖÙ]K[[™K\]X[]WIË›ÝÊNÝË˜[YO\˜ÛÛ™šYË™Y˜][ÝÚYÝË›Z[\˜ÛÛ™šYË›Z[—ÝÚYŒNÚ˜[YO\˜ÛÛ™šYË™Y˜][ÚZYÚÚ›Z[\˜ÛÛ™šYË›Z[—ÚZYÚŒNÜK˜[YOLNÜK›Z[LNßBˆYŠ]™[\™Ù]›˜[YOOOIÜÚ^™WÜ™\Ù]	É‰™]™[\™Ù]˜ÛÜÙ\Ý
	ÈØØ[Ý[]Ü‰ÊJ^ØÛÛœÝ›Ü›OI
	ÈØØ[Ý[]Ü‰ÊNÚYŠ]™[\™Ù]˜[YHOOIØÝ\ÝÛIÊ^ØÛÛœÝ\ÏY]™[\™Ù]˜[YKœÜ]
	ß	ÊNÙ›Ü›K™[[Y[ËÚY˜[YO\\ÖÌNÙ›Ü›K™[[Y[ËšZYÚ˜[YO\\ÖÌWNßY›Ü›K™[[Y[ËÚYœ™XYÛ›OY]™[\™Ù]˜[YHOOIØÝ\ÝÛIÎÙ›Ü›K™[[Y[ËšZYÚœ™XYÛ›OY]™[\™Ù]˜[YHOOIØÝ\ÝÛIÎÝ\]U\ÙÝ™]šY]Ê
NÜ™XØ[Ý[]J
NßBˆYŠ]™[\™Ù]›˜[YOOOIÜXÙ[Y[	É‰™]™[\™Ù]˜ÛÜÙ\Ý
	ÈØØ[Ý[]Ü‰ÊJ^ØÛÛœÝ›Ü›OI
	ÈØØ[Ý[]Ü‰ÊK›ÙXÝ\Ý]K˜Ø][ÙËœ›ÙXÝË™š[™
OœšYOO\Ý]KœÙ[XÝY›ÙXÝ
KÚÚXÙOJ›ÙXÝË˜ÛÛ™šYËœXÙ[Y[ÛÜ[Ûœß×JK™š[™
OžšYOOY]™[\™Ù]˜[YJNÚYŠÚÚXÙJ^Ù›Ü›K™[[Y[ËÚY˜[YOXÚÚXÙKÚYÙ›Ü›K™[[Y[ËšZYÚ˜[YOXÚÚXÙKšZYÚßY›Ü›K™[[Y[ËÚYœ™XYÛ›OY]™[\™Ù]˜[YHOOIØÝ\ÝÛIÎÙ›Ü›K™[[Y[ËšZYÚœ™XYÛ›OY]™[\™Ù]˜[YHOOIØÝ\ÝÛIÎÜ™XØ[Ý[]J
NßBˆYŠ]™[\™Ù]›˜[YOOOIÝ\ÙÝÜÝ[Iß]™[\™Ù]›˜[YOËœÝ\ÕÚ]
	Ý\ÙÝÉÊI‰™]™[\™Ù]›˜[YK™[™ÕÚ]
	×ÜÚ[ÉÊJ]\]U\ÙÝ™]šY]Ê
NÂŸJNÂ›]\ÙÝ˜[œÙ›Ü›O[[Â™ØÝ[Y[˜Y]™[\Ý[™\Š	ÜÚ[\™ÝÛ‰Ë]™[OžÂˆÛÛœÝ][OY]™[\™Ù]˜ÛÜÙ\Ý
	ÖÙ]K]\ÙÝZÙ^WIÊK™]šY]ÏZ][OË˜ÛÜÙ\Ý
	ÈÝ\ÙÝ\™]šY]ÉÊNÚYŠZ][_\™]šY]ß][KšY[Š\™]\›ŽÂˆÛÛœÝ[ÙOY]™[\™Ù]˜ÛÜÙ\Ý
	ÖÙ]K]\ÙÝ]˜[œÙ›Ü›WIÊOË™]\Ù]\ÙÝ˜[œÙ›Ü›_	Û[Ý™IËÙ^OZ][K™]\Ù]\ÙÝÙ^K›Ü›OI
	ÈØØ[Ý[]Ü‰ÊK]\ÙÝÜÚ][ÛŠÙ^JNÂˆ\ÙÝÙ[XÝYÙ^OZÙ^NÝ\]U\ÙÝ™]šY]Ê
NÙ]™[œ™]™[Y˜][

NÚ][KœÙ]Ú[\Ø\\™OËŠ]™[œÚ[\’Y
NÂˆÛÛœÝ›Ý[™ÏZ][K™Ù]›Ý[™[™ÐÛY[™XÝ

KÙ[\–X›Ý[™Ë›Y
Ø›Ý[™ËÚYÌ‹Ù[\–OX›Ý[™ËÜ
Ø›Ý[™ËšZYÚÌŽÂˆÛÛœÝšY[˜[YO]\ÙÝÚ^™QšY[
Ù^JKšY[YšY[˜[YOÙ›Ü›OË™[[Y[ÖÙšY[˜[YWN›[Âˆ\ÙÝ˜[œÙ›Ü›O^Âˆ[ÙKÙ^K][K™]šY]ËÚ[\’Y™]™[œÚ[\’YÝ\ÛY[™]™[˜ÛY[Ý\ÛY[N™]™[˜ÛY[KˆÝ\“[X™\Šž
KÝ\N“[X™\ŠžJKÝ\›Ý][ÛŽ“[X™\Šœ›Ý][ÛŸ
KÙ[\–Ù[\–KˆÝ\[™ÛN“X]˜][ŒŠ]™[˜ÛY[KXÙ[\–K]™[˜ÛY[XÙ[\–
JŒNÓX]”KˆÝ\\Ý[˜ÙN“X]›X^
X]š\Ý
]™[˜ÛY[XÙ[\–]™[˜ÛY[KXÙ[\–JJKˆšY[Ý\Ú^™N“[X™\ŠšY[Ë˜[YJ_
Ù^OOOIÛÙÛÉÏÍŽŒÌŠBˆNÂŸJNÂ™ØÝ[Y[˜Y]™[\Ý[™\Š	ÜÚ[\›[Ý™IË]™[OžÂˆYŠ]\ÙÝ˜[œÙ›Ü›J\™]\›ŽÂˆÛÛœÝ]\ÙÝ˜[œÙ›Ü›K]œ™]šY]Ë™Ù]›Ý[™[™ÐÛY[™XÝ

K˜[œÙ›Ü›O]\ÙÝÜÚ][ÛŠšÙ^JNÂˆYŠ›[ÙOOOIÛ[Ý™IÊ^Âˆ˜[œÙ›Ü›KžSX]›X^
X]›Z[ŠLœÝ\
Ê]™[˜ÛY[]œÝ\ÛY[
KÜÚY
ŒL
JNÂˆ˜[œÙ›Ü›KžOSX]›X^
X]›Z[ŠLœÝ\JÊ]™[˜ÛY[K]œÝ\ÛY[JKÜšZYÚ
ŒL
JNÂˆY[ÙHYŠ›[ÙOOOIÜ™\Ú^™IÉ‰™šY[
^ÂˆÛÛœÝ\Ý[˜ÙOSX]›X^
X]š\Ý
]™[˜ÛY[]˜Ù[\–]™[˜ÛY[K]˜Ù[\–JJK˜][ÏY\Ý[˜ÙKÝœÝ\\Ý[˜ÙNÂˆÛÛœÝZ[]šÙ^OOOIÛÙÛÉÏÌLŽX^]šÙ^OOOIÛÙÛÉÏÎMNŒÌÂˆ™šY[˜[YOSX]œ›Ý[™
X]›X^
Z[‹X]›Z[ŠX^œÝ\Ú^™Jœ˜][ÊJJNÂˆY[ÙHYŠ›[ÙOOOIÜ›Ý]IÊ^ÂˆÛÛœÝ[™ÛOSX]˜][ŒŠ]™[˜ÛY[K]˜Ù[\–K]™[˜ÛY[]˜Ù[\–
JŒNÓX]”NÂˆ]›Ý][Û]œÝ\›Ý][ÛŠÊ[™ÛK]œÝ\[™ÛJNÜ›Ý][ÛJ
›Ý][ÛŠÌN
ILÍŒ
ÌÍŒ
ILÍŒLNÂˆYŠ]™[œÚYÙ^J\›Ý][ÛSX]œ›Ý[™
›Ý][Û‹ÌMJJŒMNÂˆ˜[œÙ›Ü›Kœ›Ý][ÛS[X™\Š›Ý][Û‹Ñš^Y
JJNÂˆBˆ\]U\ÙÝ™]šY]Ê
NÂŸJNÂ™[˜Ý[Ûˆš[š\Ú\ÙÝ˜[œÙ›Ü›J
^ÂˆYŠ]\ÙÝ˜[œÙ›Ü›J\™]\›ŽÝ\ÙÝ˜[œÙ›Ü›Kš][Kœ™[X\ÙTÚ[\Ø\\™OËŠ\ÙÝ˜[œÙ›Ü›KœÚ[\’Y
NÝ\ÙÝ˜[œÙ›Ü›O[[Ü™XØ[Ý[]J
NÂŸB™ØÝ[Y[˜Y]™[\Ý[™\Š	ÜÚ[\\	Ëš[š\Ú\ÙÝ˜[œÙ›Ü›JNÂ™ØÝ[Y[˜Y]™[\Ý[™\Š	ÜÚ[\˜Ø[˜Ù[	Ëš[š\Ú\ÙÝ˜[œÙ›Ü›JNÂÚ[™ÝË˜Y]™[\Ý[™\Š	Ú\ÚÚ[™ÙIË

OOœ›Ý]J
K˜Ø]Ú
OOØ\Ý
K›Y\ÜØYÙKYJJJNÂÚ[™ÝË˜Y]™[\Ý[™\Š	ÜÜÝ]IË

OOœ›Ý]J
K˜Ø]Ú
OOØ\Ý
K›Y\ÜØYÙKYJJJNÂ˜\Þ[˜È[˜Ý[Ûˆ›ÛÝ

^Âˆž^Û]ÏX]ØZ]\J	ËØ\KÜÙ\ÜÚ[Û‰ÊNÜÝ]K˜ÜÜ™\Ë˜ÜÜ™ŽÂˆYŠØØ][Û‹œ]˜[YOOOIËÜÝY™‰É‰›ØØ][Û‹š\ÚœÝ\ÕÚ]
	ÈÜÝ\ÜIÊJ^ÂˆÛÛœÝÚÙ[[™]ÈT“ÙX\˜Ú\˜[\ÊØØ][Û‹š\ÚœÛXÙJJJK™Ù]
	ÜÝ\Ü	ÊNÚ\ÝÜžKœ™\XÙTÝ]J[	ÉË	ËÜÝY™‰ÊNÂˆÛÛœÝ™\Ý[X]ØZ]\J	ËØ\KØ]]Ü]›Ü›K\Ý\Ü	Ë	ÔÔÕ	ËÝÚÙ[ŸJNÜÝ]K˜ÜÜ™\™\Ý[˜ÜÜ™ŽÜÏX]ØZ]\J	ËØ\KÜÙ\ÜÚ[Û‰ÊNÂˆBˆÝ]K\Ù\\Ë\Ù\ŽÚYŠË\Ù\Š]Ú[™ÝË•[\P[˜[]XÜÏË™^ÛYTÝY™Š
NÜÝ]K˜Ø][ÙÏX]ØZ]\J	ËØ\KØØ][ÙÉÊNØÛÛœÝÝ\ÝÛY\X]ØZ]\J	ËØ\KØÝ\ÝÛY\‰ÊNÜÝ]K˜Ý\ÝÛY\XÝ\ÝÛY\‹˜Ý\ÝÛY\ŽØ]ØZ]›Ý]J
NßBˆØ]Ú
\œ›ÜŠ^Ø\š[›™\’SX]ˆÛ\ÜÏHš[š]X[[ØY[™ÈO•[˜X›HÈÜ[ˆHÛÜšÜÜXÙOÚOÛ\ÜÏH›]]Y‰Ù\ØÊ\œ›Ü‹›Y\ÜØYÙJ_OÜHÛ\ÜÏH˜ˆš[X\žHˆ™YH‹È•žHYØZ[ØOÙ]˜ßBŸB˜›ÛÝ

NÂ