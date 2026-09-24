/* Optional first-party measurement. No names, email, phone, artwork or form contents. */
(() => {
  'use strict';
  const script=document.currentScript, endpoint=script?.dataset.endpoint||'/api/marketing/event';
  const cookieDomain=location.hostname==='tampasigns.net'||location.hostname.endsWith('.tampasigns.net')?'; Domain=.tampasigns.net':'';
  const secure=location.protocol==='https:'?'; Secure':'';
  const read=name=>document.cookie.split('; ').find(v=>v.startsWith(name+'='))?.slice(name.length+1)||'';
  const write=(name,value,age)=>{document.cookie=name+'='+value+'; Max-Age='+age+'; Path=/; SameSite=Lax'+secure+cookieDomain;};
  const blocked=()=>navigator.doNotTrack==='1'||navigator.globalPrivacyControl===true||read('ts_measure_exclude')==='yes';
  const publicPage=()=>!/^\/(staff|portal|account|studio|api)(\/|$)/.test(location.pathname)&&!location.hash.includes('token=');
  const random=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
  const clean=s=>/^[a-z0-9][a-z0-9_.-]{0,79}$/i.test(s||'')&&!/\d{7}/.test(s)?s.toLowerCase():'';
  let lastPath='', queue=Promise.resolve();
  function attribution(){
    const params=new URLSearchParams(location.search);
    let source=clean(params.get('utm_source')),medium=clean(params.get('utm_medium')),campaign=clean(params.get('utm_campaign'));
    if(!source){
      let host='';try{host=new URL(document.referrer).hostname;}catch{}
      source=/^(www\.)?google\.[a-z.]+$/.test(host)?'google':/(^|\.)bing\.com$/.test(host)?'bing':/(^|\.)instagram\.com$/.test(host)?'instagram':/(^|\.)facebook\.com$/.test(host)?'facebook':host&&!/(^|\.)tampasigns\.net$/.test(host)?'referral':'direct';
      medium=['google','bing'].includes(source)?'organic':['facebook','instagram'].includes(source)?'social':source==='referral'?'referral':'';
    }
    return {source,medium,campaign};
  }
  const entry=attribution();
  function track(event){
    if(blocked()||!publicPage()||read('ts_measure_choice')!=='yes')return;
    let sid=read('ts_measure_sid');if(!/^[a-f0-9]{32}$/.test(sid))sid=random();
    write('ts_measure_sid',sid,1800);
    const data={sid,event_id:random(),event,path:location.pathname,consent:true,...entry};
    queue=queue.catch(()=>{}).then(()=>fetch(endpoint,{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),keepalive:true}).then(r=>{if(r.status===409)write('ts_measure_sid','',0);}).catch(()=>{}));
  }
  function page(){
    if(!publicPage())return;
    const path=location.pathname;
    if(path!==lastPath){lastPath=path;track('page_view');if(path.startsWith('/products/'))track('product_view');}
  }
  function dismiss(){document.getElementById('ts-measure-banner')?.remove();}
  function choose(value){
    write('ts_measure_choice',value,180*86400);dismiss();
    if(value==='yes'&&!blocked()){lastPath='';page();}else write('ts_measure_sid','',0);
  }
  function settings(){
    dismiss();if(!publicPage())return;
    const box=document.createElement('section');box.id='ts-measure-banner';box.setAttribute('aria-label','Optional website measurement');
    const message=document.createElement('p');message.textContent='Help us improve Tampa Signs? Optional first-party measurement links visits, campaign sources and shopping actions across this site and our ordering site. No form contents or artwork are collected. Your choice will not affect ordering.';
    const privacy=document.createElement('a');privacy.href='https://www.tampasigns.net/privacy.html';privacy.textContent='Measurement details';
    const actions=document.createElement('div');actions.className='ts-measure-actions';
    for(const [value,label] of [['yes','Allow measurement'],['no','No thanks']]){const b=document.createElement('button');b.type='button';b.textContent=label;b.disabled=value==='yes'&&blocked();b.onclick=()=>choose(value);actions.append(b);}
    box.append(message,privacy,actions);document.body.append(box);
  }
  function excludeStaff(){write('ts_measure_exclude','yes',365*86400);write('ts_measure_sid','',0);dismiss();}
  window.TampaAnalytics={track,settings,excludeStaff};
  if(!publicPage()){if(location.pathname.startsWith('/staff'))excludeStaff();return;}
  for(const method of ['pushState','replaceState']){const original=history[method];history[method]=function(...args){const result=original.apply(this,args);queueMicrotask(page);return result;};}
  addEventListener('popstate',page);
  document.addEventListener('click',e=>{
    const a=e.target.closest('a');if(a){
      const href=a.getAttribute('href')||'';
      if(href.startsWith('tel:'))track('phone_click');else if(href.startsWith('mailto:'))track('email_click');
      else {try{if(new URL(a.href).hostname==='orders.tampasigns.net'&&location.hostname!=='orders.tampasigns.net')track('start_project');}catch{}}
    }
    const action=e.target.closest('[data-action]')?.dataset.action;
    if(['product-canva','canva-open'].includes(action))track('canva_click');
    if(action==='design-quote')track('design_help_click');
  });
  const start=()=>{
    const button=document.createElement('button');button.type='button';button.id='ts-measure-settings';button.textContent='Privacy choices';button.onclick=settings;document.body.append(button);
    if(!read('ts_measure_choice')&&!blocked())settings();page();
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
