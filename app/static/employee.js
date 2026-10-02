import {saveDraft, getDraft, listDrafts, deleteDraft} from './employee-drafts.js?v=20260930-2';

const root = document.querySelector('#employee-app');
const dialog = document.querySelector('#employee-dialog');
const state = {user:null, csrf:'', online:navigator.onLine, catalog:null, clients:[], jobs:[], tasks:[], surveys:[],
  route:'home', queue:'mine', job:null, jobTab:'overview', draft:null, estimate:null, price:null, installPrompt:null, urls:[]};
const esc = (v='') => String(v ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = (c=0) => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(c)/100);
const initials = v => String(v || '').split(' ').filter(Boolean).slice(0,2).map(s=>s[0]).join('').toUpperCase();
const owner = () => state.user?.role === 'admin';
const shopName=()=>state.catalog?.shop?.shop_name||document.querySelector('meta[name="shop-name"]')?.content||'Tampa Signs and Stickers';
const shopLogo=()=>document.querySelector('meta[name="shop-logo"]')?.content||'/static/brand/tampa-black.png';
const $ = (selector, context=document) => context.querySelector(selector);
const $$ = (selector, context=document) => [...context.querySelectorAll(selector)];
const stamp = () => new Date().toISOString();
const path = {
 home:'M3 10 12 3l9 7v11h-6v-7H9v7H3z',tasks:'m3 6 2 2 4-4M12 6h9M3 13l2 2 4-4M12 13h9M3 20l2 2 4-4M12 20h9',
 ruler:'m4 16 12-12 4 4-12 12-5 1zM8 13l3 3M12 9l3 3M16 5l3 3',users:'M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8M2 21v-3c0-5 14-5 14 0v3M17 4c5 0 5 7 0 7M20 15c2 0 2 3 2 6',
 file:'M5 2h9l5 5v15H5zM14 2v6h5M8 13h8M8 17h6',plus:'M12 4v16M4 12h16',
 refresh:'M20 7V2l-3 3a9 9 0 1 0 3 11M20 7h-5',arrow:'M5 12h14m-6-6 6 6-6 6',back:'M19 12H5m6-6-6 6 6 6',
 camera:'M3 7h4l2-3h6l2 3h4v14H3zM12 10a4 4 0 1 0 0 8 4 4 0 0 0 0-8',check:'m5 12 4 4L20 5',
 clock:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v6l4 2',upload:'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',
 lock:'M6 10V7a6 6 0 0 1 12 0v3M4 10h16v12H4z',link:'M10 13a4 4 0 0 1 0-6l4-4a4 4 0 0 1 6 6l-3 3M14 11a4 4 0 0 1 0 6l-4 4a4 4 0 0 1-6-6l3-3'
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${path[name] || path.file}"/></svg>`;
const badge = (text, color='') => `<span class="badge ${color}">${esc(text)}</span>`;
const empty = (text, symbol='tasks') => `<div class="empty">${icon(symbol)}<p>${esc(text)}</p></div>`;
const field = (name, label, value='', extra='', type='text') => `<label><span class="label">${esc(label)}</span><input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
const noteField = (name, label, value='') => `<label><span class="label">${esc(label)}</span><textarea name="${name}">${esc(value)}</textarea></label>`;
const select = (name, label, options, value, extra='') => `<label><span class="label">${esc(label)}</span><select name="${name}" ${extra}>${options.map(o=>`<option value="${esc(o.id)}" ${String(o.id)===String(value)?'selected':''}>${esc(o.label)}</option>`).join('')}</select></label>`;
const back = (href, text) => `<a class="back" href="#${href}">${icon('back')}${esc(text)}</a>`;
const product = id => state.catalog?.products.find(p=>p.id===Number(id));
const lineSpecs = line => line.coverage_label||line.vehicle_type_label ? [line.vehicle_type_label,line.coverage_label].filter(Boolean).join(' · ') : line.finished_apparel ? 'Garment sizes / placements in scope' : line.width&&line.height ? `${line.width} × ${line.height} in` : line.unit||'Service';
const clientOptions = current => {
  const options = [{id:'',label:'Select a CRM client'}, ...state.clients.map(c=>({id:c.id,label:c.company ? c.company+' · '+c.name : c.name}))];
  if (current?.contact_id && !options.some(o=>o.id===current.contact_id)) options.push({id:current.contact_id,label:current.client_name || 'Saved survey client'});
  return options;
};
let toastTimer, draftTimer, renderGeneration=0, syncing=false;

function toast(message) {
  const node = $('#employee-toast'); node.textContent=message; node.classList.add('show');
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.remove('show'),5500);
}
function rememberIdentity() {
  localStorage.setItem('tampa_employee_identity', JSON.stringify({...state.user, checked_at:Date.now()}));
}
async function api(url, {method='GET', body, form}={}) {
  const headers={};
  if (method!=='GET') headers['X-CSRF-Token']=state.csrf;
  if (body!==undefined) headers['Content-Type']='application/json';
  let response;
  try {response=await fetch(url,{method,headers,credentials:'same-origin',cache:'no-store',body:form || (body!==undefined?JSON.stringify(body):undefined)});}
  catch {state.online=false; updateConnection();throw new Error('Connection unavailable. Survey drafts remain on this device. Reconnect to sync.');}
  state.online=true;updateConnection();
  let data;
  try {data=await response.json();} catch {throw new Error('The server returned an unexpected response. Try again.');}
  if (!response.ok) {
    if(response.status===401 && !url.includes('/auth/login')) {
      state.user=null;localStorage.removeItem('tampa_employee_identity');loginView('Your staff session expired. Sign in to continue; saved survey drafts are retained.');
    }
    const error=new Error(typeof data.detail==='string'?data.detail:'Check the form fields and try again.');error.status=response.status;throw error;
  }
  return data;
}
function updateConnection() {
  const node=$('#connection-status');
  if(node){node.textContent=state.online?'Connected':'Offline drafts';node.className='badge '+(state.online?'dark':'amber');}
  const bar=$('#offline-bar');if(bar)bar.hidden=state.online;
}
function shell(content, active='home') {
  state.urls.forEach(URL.revokeObjectURL);state.urls=[];
  root.innerHTML=`<header class="top"><div class="top-inner"><a class="wordmark" href="#home">${esc(shopName())}<small>STAFF WORKSPACE</small></a><div class="top-actions"><span id="connection-status" class="badge dark">Connected</span><button class="avatar" data-action="account" aria-label="Account and app settings">${esc(initials(state.user?.name))}</button></div></div></header>
    <div id="offline-bar" class="offline-bar" hidden>Offline · Save survey drafts here. Live prices, sends and task updates require a connection.</div>
    <main class="content">${content}</main><nav class="bottom-nav" aria-label="Employee workspace">${[['home','home','Today'],['tasks','tasks','Queue'],['surveys','ruler','Surveys'],['clients','users','Clients'],['estimates','file','Estimates']].map(([id,ic,label])=>`<a href="#${id}" ${active===id?'aria-current="page"':''} class="${active===id?'active':''}">${icon(ic)}${label}</a>`).join('')}</nav>`;
  updateConnection();
}
function heading(eyebrow,title,subtitle='',action='') {
  return `<div class="heading"><div><p class="eyebrow">${esc(eyebrow)}</p><h1>${esc(title)}</h1>${subtitle?`<p class="muted">${esc(subtitle)}</p>`:''}</div>${action}</div>`;
}
function loginView(message='') {
  root.innerHTML=`<main class="login"><img class="login-brand" src="${esc(shopLogo())}" alt="${esc(shopName())}"><p class="eyebrow">YOUR SHOP, IN YOUR POCKET</p><h1>Ready for the next job.</h1><p class="muted">Your tasks, measurements, clients and estimates. Sign in with your staff account.</p>${message?`<div class="error">${esc(message)}</div>`:''}<form data-form="login">${field('email','Staff email','','required autocomplete="username"','email')}${field('password','Password','','required autocomplete="current-password"','password')}<div data-errors></div><button class="btn primary wide" type="submit">Sign in ${icon('arrow')}</button></form><div class="install-box"><p><strong>Put this app on your home screen</strong><br>iPhone: Safari → Share → Add to Home Screen.<br>Android: Chrome menu → Install app / Add to Home Screen.</p></div></main>`;
}
async function loadData() {
  const results=await Promise.allSettled([
    api('/api/catalog'), api('/api/staff/clients'), api('/api/staff/jobs?active_only=true'),
    api('/api/staff/task-queue?scope=mine'), api('/api/staff/surveys')
  ]);
  if(!state.user) return;
  const keys=['catalog','clients','jobs','tasks','surveys'];
  const inner=['','contacts','jobs','tasks','surveys'];
  results.forEach((r,i)=>{if(r.status==='fulfilled')state[keys[i]]=inner[i]?r.value[inner[i]]:r.value;});
  if(results[0].status==='fulfilled')localStorage.setItem('tampa_employee_public_catalog',JSON.stringify(state.catalog));
  const failed=results.find(r=>r.status==='rejected');if(failed && state.online)toast(failed.reason.message);
}
function taskCard(t) {
  const mine=t.assignee_id===state.user.id, running=t.status==='in_progress';
  const buttons = !t.assignee_id?`<button class="btn primary small" data-action="task" data-id="${t.id}" data-op="claim">${icon('plus')} Accept task</button>`:
    mine || owner()?`${running?`<button class="btn small" data-action="task" data-id="${t.id}" data-op="pause">Pause</button><button class="btn primary small" data-action="task" data-id="${t.id}" data-op="complete">${icon('check')} Finish</button>`:`<button class="btn primary small" data-action="task" data-id="${t.id}" data-op="start" ${t.blocked_reason?'disabled':''}>${icon('clock')} Start</button>`}<button class="btn small" data-action="task-note" data-id="${t.id}" data-op="block">Blocked</button>${mine&&!running?`<button class="btn small" data-action="task" data-id="${t.id}" data-op="release">Release</button>`:''}`:'';
  return `<section class="card task"><div class="row"><a class="job-link grow" href="#job/${t.job_id}">${esc(t.number)} · ${esc(t.customer_name || t.job_title || '')}</a>${badge(running?'In progress':t.status==='blocked'?'Blocked':t.priority==='rush'?'Rush':'To do',running?'teal':t.status==='blocked'?'amber':'')}</div><h3>${esc(t.title)}</h3><p class="meta">${esc(t.department)}${t.assignee?' · '+esc(t.assignee):' · Open to accept'}${t.due_date?' · Due '+esc(t.due_date):''}${t.tracked_minutes?' · '+t.tracked_minutes+' min logged':''}</p>${t.blocked_reason?`<div class="task-note">${icon('lock')} ${esc(t.blocked_reason)}</div>`:''}${t.note?`<div class="task-note">${esc(t.note)}</div>`:''}${buttons?`<div class="task-buttons">${buttons}</div>`:''}</section>`;
}
function jobCard(job) {
  return `<a class="card clickable project" href="#job/${job.id}"><div class="row mb">${badge(job.number,'teal')}${badge(job.stage.replaceAll('_',' '))}${job.priority==='rush'?badge('Rush','amber'):''}</div><div class="project-top"><div><h3>${esc(job.title)}</h3><p class="meta">${esc(job.customer_name)}${job.due_date?' · Due '+esc(job.due_date):''}</p></div><strong class="amount">${money(job.totals.total_cents)}</strong></div><div class="row"><small class="muted grow">${job.tasks_done} / ${job.task_count} tasks complete</small>${icon('arrow')}</div><div class="progress"><span style="width:${job.task_count?Math.round(job.tasks_done/job.task_count*100):0}%"></span></div></a>`;
}
async function homeView() {
  if(state.online)state.jobs=(await api('/api/staff/jobs?active_only=true')).jobs;
  const drafts=await listDrafts(state.user.id), mine=state.tasks;
  const active=state.jobs.filter(j=>j.assignee_id===state.user.id&&j.stage!=='complete');
  const first=mine.find(t=>t.status==='in_progress') || mine.find(t=>!t.blocked_reason);
  const day=new Date().toLocaleDateString('en-US',{weekday:'long',month:'short',day:'numeric'});
  shell(heading(day,`Let’s get to work, ${state.user.name.split(' ')[0]}.`,'Everything you need to keep jobs moving.')+
    `<div class="desktop-grid"><div><section class="hero"><p class="eyebrow">${first?'YOUR NEXT MOVE':'MAKE PROGRESS TODAY'}</p><h2>${esc(first?.title || 'From site visit to estimate.')}</h2><p>${esc(first?first.number+' · '+(first.customer_name || first.job_title):'Capture measurements, photograph the site, and turn the details into a priced project.')}</p><a class="btn" href="#${first?'job/'+first.job_id:'survey/new'}">${first?'Open project':'Start a site survey'} ${icon('arrow')}</a></section><div class="stats"><div class="stat"><strong>${mine.length}</strong><span>In your queue</span></div><div class="stat"><strong>${active.length}</strong><span>Your projects</span></div><div class="stat"><strong>${drafts.filter(d=>d.dirty || d.local_files?.some(f=>!f.id)).length}</strong><span>Drafts to sync</span></div></div><div class="quick-actions"><a class="quick" href="#survey/new"><span class="symbol">${icon('ruler')}</span><span><strong>Site survey</strong><small>Measure & photograph</small></span></a><a class="quick" href="#estimate/new"><span class="symbol">${icon('file')}</span><span><strong>New estimate</strong><small>Use live product rates</small></span></a><a class="quick" href="#client/new"><span class="symbol">${icon('users')}</span><span><strong>Add client</strong><small>Save to your CRM</small></span></a><a class="quick" href="#tasks"><span class="symbol">${icon('tasks')}</span><span><strong>Task queue</strong><small>Accept your next task</small></span></a></div></div><div><div class="section-heading"><h2>Your work queue</h2><a href="#tasks">View queue →</a></div><div class="stack">${mine.slice(0,3).map(taskCard).join('') || empty('No tasks accepted yet. Open the queue to accept a task.')}</div></div></div><div class="section-heading"><h2>Recent projects</h2><a href="#estimates">View all →</a></div><div class="desktop-grid stack">${state.jobs.slice(0,4).map(jobCard).join('')||empty('Your projects will appear here.')}</div>`);
}
async function queueView() {
  const data=await api('/api/staff/task-queue?scope='+state.queue);state.tasks=state.queue==='mine'?data.tasks:state.tasks;
  shell(heading('TAKE OWNERSHIP','Your task queue.','Accept work, log time, and move projects forward.',`<button class="icon-button" data-action="refresh" aria-label="Refresh task queue">${icon('refresh')}</button>`)+
    `<div class="tabs">${[['mine','My queue'],['available','Available'],['all','All tasks']].map(([id,label])=>`<button data-action="queue-filter" data-value="${id}" class="${state.queue===id?'active':''}">${label}</button>`).join('')}</div><div class="stack">${data.tasks.map(taskCard).join('')||empty(state.queue==='mine'?'Your queue is clear. Accept tasks from Available.':'No tasks match this view.')}</div>`,'tasks');
}
async function clientsView() {
  const data=await api('/api/staff/clients');state.clients=data.contacts;
  shell(heading('ONE CONNECTED CRM','Your clients.','Find a client or add one while you’re on site.',`<a class="icon-button" href="#client/new" aria-label="Add client">${icon('plus')}</a>`)+`<input class="search" id="client-search" type="search" placeholder="Search name, company, email or phone" aria-label="Search clients"><div class="stack" id="client-list"></div>`,'clients');renderClientList();
}
function renderClientList(query='') {
  $('#client-list').innerHTML=state.clients.filter(c=>[c.name,c.company,c.email,c.phone].join(' ').toLowerCase().includes(query.toLowerCase())).map(c=>`<a class="card clickable row" href="#client/${c.id}"><span class="letter">${esc(initials(c.company||c.name))}</span><div class="grow"><h3>${esc(c.company||c.name)}</h3><div class="client-contact">${esc(c.company?c.name+' · ':'')}${esc(c.email||c.phone)}</div></div>${icon('arrow')}</a>`).join('')||empty('No clients found.');
}
function clientFormView(current={}) {
  shell(back(current.id?'client/'+current.id:'clients',current.id?'Client details':'Clients')+heading('CRM',current.id?'Update client.':'Add a new client.','Contact details stay connected to surveys and orders.')+
    `<form data-form="client" data-id="${current.id||''}" class="card stack"><div class="form-grid">${field('name','Contact name',current.name||'','required maxlength="120" autocomplete="name"')}${field('company','Company',current.company||'','maxlength="160" autocomplete="organization"')}${field('email','Email',current.email||'','autocomplete="email"','email')}${field('phone','Phone',current.phone||'','maxlength="60" autocomplete="tel"','tel')}<div class="full">${noteField('notes','Client notes',current.notes||'')}</div></div><p class="field-hint">An email is needed to create an order estimate or send proofs.</p><div data-errors></div><button class="btn primary wide" type="submit">${icon('check')} Save client</button></form>`,'clients');
}
async function clientView(id) {
  const client=await api('/api/staff/clients/'+id);
  shell(back('clients','Clients')+heading('CLIENT',client.company||client.name,client.company?client.name:'',`<button class="btn small" data-action="edit-client" data-id="${id}">Edit</button>`)+
    `<section class="card"><div class="stack">${client.email?`<a class="break" href="mailto:${esc(client.email)}">${esc(client.email)}</a>`:''}${client.phone?`<a href="tel:${esc(client.phone.replace(/[^+\d]/g,''))}">${esc(client.phone)}</a>`:''}${client.notes?`<p class="muted break">${esc(client.notes)}</p>`:''}</div></section><div class="quick-actions mt"><button class="quick" data-action="new-survey-client" data-id="${id}"><span class="symbol">${icon('ruler')}</span><strong>New site survey</strong></button><button class="quick" data-action="new-estimate-client" data-id="${id}"><span class="symbol">${icon('file')}</span><strong>New estimate</strong></button></div><div class="section-heading"><h2>Projects & orders</h2></div><div class="stack">${client.jobs.map(j=>`<a class="card clickable row" href="#job/${j.id}"><div class="grow"><h3>${esc(j.title)}</h3><p class="muted">${esc(j.number)} · ${esc(j.state)}</p></div><strong>${money(j.total_cents)}</strong>${icon('arrow')}</a>`).join('')||empty('No projects for this client yet.')}</div>`,'clients');
}
async function surveysView() {
  if(state.online){const data=await api('/api/staff/surveys');state.surveys=data.surveys;}
  const drafts=await listDrafts(state.user.id);
  const local=drafts.filter(d=>d.dirty||d.local_files?.some(f=>!f.id)||!d.id);
  shell(heading('FIELD NOTES, ALL TOGETHER','Site surveys.','Measurements and photos that stay with the job.',`<a class="icon-button" href="#survey/new" aria-label="New site survey">${icon('plus')}</a>`)+
    `${local.length?`<div class="section-heading"><h2>On this device</h2>${badge(local.length+' to sync','amber')}</div><div class="stack">${local.map(d=>`<a class="card clickable row" href="#draft/${d.local_key}"><div class="grow"><h3>${esc(d.title||'Untitled survey')}</h3><p class="muted">${esc(d.client_name||'Choose client')} · ${d.measurements?.length||0} measured areas</p></div>${badge('Device draft','amber')}${icon('arrow')}</a>`).join('')}</div>`:''}<div class="section-heading"><h2>Saved to the shop</h2></div><div class="stack">${state.surveys.map(s=>`<a class="card clickable row" href="#survey/${s.id}"><div class="grow"><h3>${esc(s.title)}</h3><p class="muted">${esc(s.client_name)} · ${s.measurements.length} areas · ${s.files.length} photos / files</p></div>${badge(s.status,s.status==='verified'?'teal':s.status==='submitted'?'amber':'')}${icon('arrow')}</a>`).join('')||empty(state.online?'No saved surveys yet. Start your first site visit.':'Reconnect to see surveys saved to the shop.','ruler')}</div>`,'surveys');
}
function newSurvey(contactId=null,jobId=null) {
  const contact=state.clients.find(c=>c.id===contactId);
  state.draft={local_key:crypto.randomUUID(),client_key:crypto.randomUUID(),user_id:state.user.id,contact_id:contactId,client_name:contact?.company||contact?.name||'',job_id:jobId,title:'',address:'',site_contact:'',access_notes:'',surface_notes:'',removal_required:false,measurements:[newArea()],local_files:[],files:[],version:0,dirty:true,updated_at:stamp()};
  surveyEditor();
}
function newArea(){return {panel_key:crypto.randomUUID(),label:'',width:'',height:'',unit:'in',quantity:1,notes:'',product_id:null};}
function checkPhoto(file) {
  if(!file||!['image/png','image/jpeg'].includes(file.type))throw new Error('Choose a PNG or JPEG panel photo.');
  if(file.size>50*1024*1024)throw new Error('Each panel photo must be no larger than 50 MB.');
}
function previewUrl(photo) {
  if(!photo)return '';
  if(photo.blob){const url=URL.createObjectURL(photo.blob);state.urls.push(url);return url;}
  return photo.url||'';
}
function photoEditor(photo,inputAttrs,removeAttrs) {
  const url=previewUrl(photo);
  return `${url?`<img class="panel-photo-preview" src="${esc(url)}" alt="Panel reference photo"><p class="field-hint">${esc(photo.name||photo.filename||'Panel photo')}</p>`:''}<label class="btn small">${icon('camera')} ${photo?'Replace panel photo':'Add panel photo (optional)'}<input type="file" accept="image/png,image/jpeg" ${inputAttrs}></label><p class="field-hint">Optional reference photo for the client quote.</p>${photo?`<button class="remove" type="button" ${removeAttrs}>Remove photo</button>`:''}`;
}
async function removeSurveyPanelPhoto(key) {
  const d=state.draft,photo=(d.local_files||[]).find(f=>f.panel_key===key)||(d.files||[]).find(f=>f.panel_key===key);
  if(photo?.id)await api(`/api/staff/surveys/${d.id}/files/${photo.id}`,{method:'DELETE'});
  d.local_files=(d.local_files||[]).filter(f=>f.panel_key!==key);d.files=(d.files||[]).filter(f=>f.panel_key!==key);d.dirty=true;
}
function areaHtml(m,index) {
  const products=[{id:'',label:'Choose when estimating'},...(state.catalog?.products||[]).filter(p=>!p.config.finished_apparel).map(p=>({id:p.id,label:p.name}))];
  return `<section class="area" data-area="${index}" data-panel-key="${esc(m.panel_key)}"><div class="area-head"><span class="area-number">AREA ${String(index+1).padStart(2,'0')}</span><button class="remove" type="button" data-action="remove-area" data-id="${index}">Remove</button></div>${field('label','Pane / sign / area label',m.label,'required maxlength="160" placeholder="e.g. Left window, door top glass"')}<div class="dimensions">${field('width','Width',m.width,'required min="0.01" step="any" inputmode="decimal"','number')}${field('height','Height',m.height,'required min="0.01" step="any" inputmode="decimal"','number')}${select('unit','Units',[{id:'in',label:'in'},{id:'ft',label:'ft'},{id:'mm',label:'mm'},{id:'cm',label:'cm'}],m.unit)}</div><div class="form-grid">${field('quantity','Quantity',m.quantity||1,'required min="1" max="100000" step="1" inputmode="numeric"','number')}${select('product_id','Suggested product',products,m.product_id||'')}<div class="full mt">${noteField('notes','Area notes',m.notes||'')}</div></div><div class="panel-photo" data-survey-photo="${esc(m.panel_key)}"></div></section>`;
}
function surveyEditor() {
  const d=state.draft;
  d.measurements.forEach((m,index)=>{m.panel_key ||= 'area-'+index;});
  shell(back('surveys','Site surveys')+heading('SITE VISIT',d.id?'Update survey.':'Capture the details.','Label every pane or area. Keep photos and conditions with the measurements.')+
    `<form data-form="survey"><div id="draft-status" class="draft-status">${icon('check')} ${d.dirty?'Draft saved on this device':'Saved to the shop'}</div><div class="card mb"><div class="form-grid"><div class="full client-picker">${select('contact_id','Client',clientOptions(d),d.contact_id||'','required')}<button type="button" class="btn small" data-action="survey-new-client" ${d.id||d.job_id?'disabled':''}>${icon('plus')} New client</button></div><div class="full">${field('title','Survey / project title',d.title,'required maxlength="180" placeholder="e.g. Storefront window graphics"')}</div><div class="full">${field('address','Site address',d.address,'required maxlength="500" autocomplete="street-address"')}</div><div class="full">${field('site_contact','On-site contact / phone',d.site_contact,'maxlength="300"')}</div><div class="full">${noteField('access_notes','Access & installation notes',d.access_notes)}</div><div class="full">${noteField('surface_notes','Surface / condition notes',d.surface_notes)}</div><label class="check full"><input name="removal_required" type="checkbox" ${d.removal_required?'checked':''}>Existing vinyl / adhesive removal required</label></div></div><div class="section-heading"><h2>Measured areas</h2></div><div class="stack" id="survey-areas">${d.measurements.map(areaHtml).join('')}</div><button class="btn wide mt" type="button" data-action="add-area">${icon('plus')} Add area</button><div class="section-heading"><h2>Site photos & files</h2></div><section class="card"><div class="photo-buttons"><label class="btn">${icon('camera')} Take photo<input id="survey-camera" type="file" accept="image/jpeg,image/png" capture="environment"></label><label class="btn">${icon('upload')} Add photos / PDF<input id="survey-files" type="file" accept="image/jpeg,image/png,application/pdf" multiple></label></div><p class="field-hint">PNG, JPEG or PDF · Up to 50 MB each. Selected photos stay in the device draft until synced.</p><div id="survey-file-list" class="file-list"></div></section><div class="notice mt">Survey measurements are field records. Your owner verifies the sizing against the order and proof before production.</div><div data-errors></div><div class="form-actions"><button class="btn" type="button" data-action="save-device">Save device draft</button><button class="btn primary" type="submit">${icon('upload')} Save to shop</button></div><button class="btn wide mt" type="button" data-action="submit-survey">Submit for review</button></form>`,'surveys');renderSurveyFiles();
}
function collectSurvey() {
  const form=$('form[data-form="survey"]');if(!form||!state.draft)return state.draft;
  const data=new FormData(form), d=state.draft;
  const body = value => JSON.stringify({contact_id:value.contact_id, title:value.title, address:value.address,
    site_contact:value.site_contact,access_notes:value.access_notes,surface_notes:value.surface_notes,
    removal_required:value.removal_required,measurements:(value.measurements||[]).map(m=>({panel_key:m.panel_key,label:m.label,width:m.width,height:m.height,unit:m.unit,quantity:m.quantity,product_id:m.product_id,notes:m.notes}))});
  const before=body(d);
  for(const key of ['title','address','site_contact','access_notes','surface_notes'])d[key]=data.get(key)||'';
  d.contact_id=Number(data.get('contact_id'))||null;
  d.client_name=state.clients.find(c=>c.id===d.contact_id)?.company||state.clients.find(c=>c.id===d.contact_id)?.name||d.client_name;
  d.removal_required=data.get('removal_required')==='on';
  d.measurements=$$('[data-area]',form).map(area=>({panel_key:area.dataset.panelKey,label:$('[name="label"]',area).value,width:$('[name="width"]',area).value,height:$('[name="height"]',area).value,unit:$('[name="unit"]',area).value,quantity:Number($('[name="quantity"]',area).value)||1,product_id:Number($('[name="product_id"]',area).value)||null,notes:$('[name="notes"]',area).value}));
  if(before!==body(d)){d.updated_at=stamp();d.dirty=true;}return d;
}
async function persistSurvey(collect=true) {
  clearTimeout(draftTimer);
  const d=collect?collectSurvey():state.draft;if(!d)return;
  await saveDraft(d);
  const node=$('#draft-status');if(node)node.innerHTML=icon('check')+' Draft saved on this device';
}
function renderSurveyFiles() {
  const d=state.draft,node=$('#survey-file-list');if(!node)return;
  state.urls.forEach(URL.revokeObjectURL);state.urls=[];
  const local=(d.local_files||[]).filter(f=>!f.panel_key), server=(d.files||[]).filter(f=>!f.panel_key&&!local.some(l=>l.id===f.id));
  $$('[data-survey-photo]').forEach(slot=>{
    const key=slot.dataset.surveyPhoto,photo=(d.local_files||[]).find(f=>f.panel_key===key)||(d.files||[]).find(f=>f.panel_key===key);
    const value=photo?{...photo,url:photo.id?`/api/staff/surveys/${d.id}/files/${photo.id}`:''}:null;
    slot.innerHTML=photoEditor(value,`data-survey-photo-input="${esc(key)}"`,`data-action="remove-panel-photo" data-value="${esc(key)}"`);
  });
  node.innerHTML=server.map(f=>`<a class="file-chip" href="/api/staff/surveys/${d.id}/files/${f.id}" target="_blank" rel="noopener">${icon('file')}${esc(f.filename)}</a>`).join('')+local.map((f,i)=>{let image='';if(f.blob?.type.startsWith('image/')){const url=URL.createObjectURL(f.blob);state.urls.push(url);image=`<img src="${url}" alt="Site photo ${i+1}">`;}return `<div class="file-chip">${image}<span>${esc(f.name)}<br>${f.id?'Saved to shop':'Device only'}</span>${!f.id?`<button type="button" data-action="remove-local-file" data-id="${d.local_files.indexOf(f)}" aria-label="Remove ${esc(f.name)}">×</button>`:''}</div>`;}).join('');
}
async function syncSurvey(submit=false) {
  if(syncing)return;
  const form=$('form[data-form="survey"]');if(!form.reportValidity())return;
  syncing=true;
  try {
    await persistSurvey();const d=state.draft;
    if(!state.csrf){
      const session=await api('/api/session');state.csrf=session.csrf;
      if(!session.user || session.user.id!==d.user_id)throw new Error('Sign in with the staff account that owns this device draft before syncing.');
    }
    const server=await api('/api/staff/surveys',{method:'POST',body:d});
    d.id=server.id;d.version=server.version;d.files=server.files;await saveDraft(d);
    for(const f of d.local_files||[])if(!f.id){
      const upload=new FormData();upload.append('file',f.blob,f.name);upload.append('client_key',f.key);upload.append('panel_key',f.panel_key||'');
      const result=await api('/api/staff/surveys/'+d.id+'/files',{method:'POST',form:upload});
      f.id=result.id;await saveDraft(d);
    }
    d.files=(await api('/api/staff/surveys/'+d.id)).files;d.dirty=false;d.updated_at=stamp();await saveDraft(d);
    if(submit) {
      const result=await api('/api/staff/surveys/'+d.id+'/action',{method:'POST',body:{action:'submit',version:d.version}});
      await deleteDraft(d.local_key);state.draft=null;toast('Survey submitted for owner review.');location.hash='survey/'+result.id;
    } else {$('#draft-status').innerHTML=icon('check')+' Saved to the shop';renderSurveyFiles();toast('Measurements and files saved to the shop.');}
  } finally {syncing=false;}
}
async function surveyView(id) {
  const survey=await api('/api/staff/surveys/'+id);
  if(survey.status==='draft' && (survey.created_by===state.user.id || owner())) {
    const local=(await listDrafts(state.user.id)).find(d=>d.id===survey.id);
    state.draft=local?.dirty?local:{...survey,user_id:state.user.id,local_key:local?.local_key||crypto.randomUUID(),local_files:[],dirty:false};
    surveyEditor();return;
  }
  shell(back('surveys','Site surveys')+heading('SURVEY',survey.title,survey.client_name,badge(survey.status,survey.status==='verified'?'teal':'amber'))+
    `<section class="card"><h3>${esc(survey.address)}</h3><p class="muted">${esc(survey.site_contact)}</p>${survey.job_id?`<a class="btn small" href="#job/${survey.job_id}">Open linked project</a>`:''}<p class="muted mt break">${esc(survey.access_notes)}</p><p class="muted break">${esc(survey.surface_notes)}</p>${survey.removal_required?badge('Removal required','amber'):''}</section><div class="section-heading"><h2>Measured areas</h2></div><section class="card">${survey.measurements.map((m,index)=>`<div class="measure-read"><div><strong>${esc(m.label)}</strong><p class="muted">${esc(m.notes)}${m.product_id?' · '+esc(product(m.product_id)?.name||'Selected product'):''}</p>${survey.files.filter(f=>f.panel_key===(m.panel_key||'area-'+index)).map(f=>`<img class="quote-photo" src="/api/staff/surveys/${survey.id}/files/${f.id}" alt="Panel reference photo">`).join('')}</div><span>${esc(m.width)} × ${esc(m.height)} ${esc(m.unit)}<br><small>Qty ${m.quantity}</small></span></div>`).join('')}</section><div class="section-heading"><h2>Photos & files</h2></div><div class="file-list">${survey.files.map(f=>`<a class="file-chip" href="/api/staff/surveys/${survey.id}/files/${f.id}" target="_blank" rel="noopener">${f.mime.startsWith('image/')?`<img src="/api/staff/surveys/${survey.id}/files/${f.id}" alt="${esc(f.filename)}">`:icon('file')}${esc(f.filename)}</a>`).join('')||'<p class="muted">No files attached.</p>'}</div><div class="form-actions">${!survey.job_id?`<button class="btn primary" data-action="survey-estimate" data-id="${id}">${icon('file')} Create estimate</button>`:''}${owner()?`${survey.status==='submitted'?`<button class="btn primary" data-action="verify-survey" data-id="${id}" data-version="${survey.version}">Verify measurements</button>`:''}<button class="btn" data-action="reopen-survey" data-id="${id}" data-version="${survey.version}">Reopen survey</button>`:''}</div>`,'surveys');
}
function itemDefaults(pid) {
  const p=product(pid),c=p?.config||{};
  return {product_id:p?.id||pid,width:String(c.default_width||12),height:String(c.default_height||12),quantity:1,description:'',
    lamination:(c.lamination_options||[]).find(o=>o.default)?.id||c.lamination_options?.[0]?.id||'',material:(c.material_options||[]).find(o=>o.default)?.id||c.material_options?.[0]?.id||'',
    coverage_option:c.coverage_options?.[0]?.id||'',vehicle_type:c.vehicle_type_options?.[0]?.id||'',acrylic_thickness:c.thickness_options?.find(o=>o.default)?.id||c.thickness_options?.[0]?.id||'',acrylic_mounting:c.mounting_options?.find(o=>o.default)?.id||c.mounting_options?.[0]?.id||'',
    installation_requested:false,design_requested:false,shirt_color:Object.keys(c.shirt_colors||{})[0]||'Black',size_quantities:{[c.shirt_sizes?.[0]||'M']:1},print_locations:[c.placement_options?.[0]?.id||'front']};
}
function newEstimate(contactId=null, survey=null) {
  const defaultProduct=state.catalog?.products.find(p=>p.category!=='Custom');
  state.estimate={request_key:crypto.randomUUID(),contact_id:contactId||survey?.contact_id,title:survey?.title||'',notes:survey?['Survey #'+survey.id, survey.address, survey.access_notes, survey.surface_notes,survey.removal_required?'Existing vinyl / adhesive removal required.':''].filter(Boolean).join('\n'):'',survey_id:survey?.id||null,
    items:survey?survey.measurements.map((m,index)=>{const item=itemDefaults(m.product_id||defaultProduct.id),photo=survey.files.find(f=>f.panel_key===(m.panel_key||'area-'+index));return {...item,...(!product(item.product_id)?.config.quantity_only?{width:m.width_inches,height:m.height_inches}:{}),quantity:m.quantity,description:m.label+(m.notes?' · '+m.notes:''),survey_file_id:photo?.id||null,photo:photo?{...photo,url:`/api/staff/surveys/${survey.id}/files/${photo.id}`} :null};}).slice(0,30):[itemDefaults(defaultProduct?.id)]};state.price=null;estimateEditor();
}
function estimateItemHtml(item,index) {
  const p=product(item.product_id),cfg=p?.config||{};
  const productOptions=(state.catalog?.products||[]).filter(p=>p.category!=='Custom').map(p=>({id:p.id,label:p.name}));
  const garmentColors=Object.keys(cfg.shirt_colors||{});
  const optionFields=[['lamination','Lamination',cfg.lamination_options],['material','Material',cfg.material_options],['coverage_option','Wrap coverage',cfg.coverage_options],['vehicle_type','Vehicle / trailer type',cfg.vehicle_type_options],['acrylic_thickness','Thickness',cfg.thickness_options],['acrylic_mounting','Mounting',cfg.mounting_options]];
  return `<section class="area" data-estimate-item="${index}" data-rendered-product="${item.product_id}"><div class="area-head"><span class="area-number">ITEM ${String(index+1).padStart(2,'0')}</span><button type="button" class="remove" data-action="remove-item" data-id="${index}">Remove</button></div>${select('product_id','Product',productOptions,item.product_id,'data-product-select')}
    ${cfg.finished_apparel?`<div class="form-grid mt">${select('shirt_color','Garment color',(garmentColors.length?garmentColors:['Black']).map(x=>({id:x,label:x})),item.shirt_color)}${select('print_location','Placement',cfg.placement_options?.length?cfg.placement_options:[{id:'front',label:'Front'},{id:'back',label:'Back'},{id:'left_chest',label:'Left chest'}],item.print_locations?.[0]||'front')}</div><div class="form-grid mt">${(cfg.shirt_sizes?.length?cfg.shirt_sizes:['M']).map(size=>field('size_'+size,size,item.size_quantities?.[size]||0,'min="0" step="1" inputmode="numeric" data-size="'+esc(size)+'"','number')).join('')}</div><p class="field-hint">Size quantities determine the total. Add another line for a different color or placement.</p>`:
      cfg.quantity_only?`<div class="mt">${field('quantity','Quantity',item.quantity,'required min="1" step="1" inputmode="numeric"','number')}<p class="field-hint">${esc(cfg.quantity_only_note||'Uses the configured product size and pricing.')}</p></div>`:`<div class="dimensions">${field('width','Width (in)',item.width,'required min="0.1" step="any" inputmode="decimal"','number')}${field('height','Height (in)',item.height,'required min="0.1" step="any" inputmode="decimal"','number')}${field('quantity','Qty',item.quantity,'required min="1" step="1" inputmode="numeric"','number')}</div>`}
    <div class="form-grid mt">${optionFields.filter(([, , options])=>options?.length).map(([key,label,options])=>select(key,label,options,item[key])).join('')}<div class="full">${field('description','Line notes / location',item.description||'','maxlength="200"')}</div>${cfg.supports_installation?`<label class="check full"><input name="installation_requested" type="checkbox" ${item.installation_requested?'checked':''}>Include installation estimate (owner reviews site conditions)</label>`:''}${cfg.is_wrap?`<label class="check full"><input name="include_roof_wrap" type="checkbox" ${item.include_roof_wrap?'checked':''}>Include roof wrap</label>`:''}</div><div class="panel-photo" data-estimate-photo="${index}"></div></section>`;
}
function estimateEditor() {
  const e=state.estimate;
  shell(back('estimates','Estimates')+heading('PRODUCT PRICING, CONNECTED','Build an estimate.','Use your saved rates, quantity breaks, materials and finishing.')+
    `<form data-form="estimate"><div class="card form-grid mb"><div class="full">${select('contact_id','CRM client',clientOptions(e),e.contact_id||'','required')}</div><div class="full">${field('title','Project title',e.title,'required maxlength="180"')}</div><div class="full">${noteField('notes','Project / installation notes',e.notes)}</div></div>${e.survey_id?`<div class="notice teal">Measurement dimensions came from survey #${e.survey_id}. Confirm the product and finished print size for every line.</div>`:''}<div class="section-heading"><h2>Products & services</h2><button class="btn small" type="button" data-action="add-item">${icon('plus')} Add item</button></div><div class="stack">${e.items.map(estimateItemHtml).join('')}</div><div data-errors></div><div class="form-actions"><button class="btn primary" type="submit">Calculate estimate</button></div><div id="estimate-price" class="mt"></div></form>`,'estimates');renderEstimatePrice();renderEstimatePhotos();
}
function collectEstimate() {
  const form=$('form[data-form="estimate"]');if(!form)return state.estimate;
  const top=new FormData(form),e=state.estimate;e.contact_id=Number(top.get('contact_id'))||null;e.title=top.get('title')||'';e.notes=top.get('notes')||'';
  e.items=$$('[data-estimate-item]').map((area,index)=>{
    const item={...e.items[index]},pid=Number(area.dataset.renderedProduct||$('[name="product_id"]',area).value),cfg=product(pid)?.config||{};
    item.product_id=pid;
    for(const key of ['width','height','description','lamination','material','coverage_option','vehicle_type','acrylic_thickness','acrylic_mounting'])if($('[name="'+key+'"]',area))item[key]=$('[name="'+key+'"]',area).value;
    item.quantity=Number($('[name="quantity"]',area)?.value || 1);
    item.installation_requested=!!$('[name="installation_requested"]',area)?.checked;item.include_roof_wrap=!!$('[name="include_roof_wrap"]',area)?.checked;
    if(cfg.finished_apparel){item.shirt_color=$('[name="shirt_color"]',area).value;item.print_locations=[$('[name="print_location"]',area).value];item.size_quantities=Object.fromEntries($$('[data-size]',area).map(n=>[n.dataset.size,Number(n.value)||0]));item.quantity=Object.values(item.size_quantities).reduce((sum,q)=>sum+q,0);}
    return item;
  });return e;
}
function estimatePayload() {
  return {...state.estimate,items:state.estimate.items.map(({photo,...item})=>item)};
}
function renderEstimatePhotos() {
  $$('[data-estimate-photo]').forEach(slot=>{
    const index=Number(slot.dataset.estimatePhoto),item=state.estimate.items[index];
    slot.innerHTML=photoEditor(item.photo,`data-estimate-photo-input="${index}"`,`data-action="remove-estimate-photo" data-id="${index}"`);
  });
}
function jobPhotoHtml(job,index) {
  const photo=job.panel_photos?.find(p=>p.line_index===index),editable=!job.archived&&!job.production_started&&job.accepted_version!==job.quote_version;
  return `<div class="panel-photo">${editable?photoEditor(photo?{...photo,url:`/api/quote-photos/${photo.id}`} :null,`data-job-photo-input="${index}"`,`data-action="remove-job-photo" data-id="${photo?.id}"`):photo?`<img class="quote-photo" src="/api/quote-photos/${photo.id}" alt="Panel reference photo"><small class="muted">Panel reference photo</small>`:''}</div>`;
}
async function uploadQuotePhoto(jobId,index,version,photo) {
  const upload=new FormData();upload.append('file',photo.blob,photo.name);upload.append('client_key',photo.key);upload.append('line_index',index);upload.append('version',version);
  return api(`/api/staff/jobs/${jobId}/panel-photos`,{method:'POST',form:upload});
}
function renderEstimatePrice() {
  const node=$('#estimate-price');if(!node)return;const price=state.price;
  node.innerHTML=price?`<section class="card mb">${price.quote.wholesale?`<p class="eyebrow">WHOLESALE · ${esc(price.quote.wholesale.name)}</p>`:''}${price.quote.lines.map(l=>`<div class="quote-line"><div><strong>${esc(l.name)}</strong><small>${esc(lineSpecs(l))} · Qty ${l.quantity}${l.material_label?' · '+esc(l.material_label):''}</small></div><strong>${money(l.sell_cents)}</strong></div>`).join('')}</section>${price.totals.owner_review_required?'<div class="notice">Saved as a draft for owner review of custom scope, installation or tax. Rates come from the current pricing system.</div>':''}<section class="money-summary"><div class="row"><small>Products & services</small><strong>${money(price.totals.subtotal_cents)}</strong></div><div class="row"><small>Sales tax (${esc(price.totals.tax_percent)}%)</small><strong>${money(price.totals.tax_cents)}</strong></div><div class="row total"><span>Estimated total</span><strong>${money(price.totals.total_cents)}</strong></div><small>Includes configured sales tax · Pickup / local scope. Review location-specific tax and delivery with the owner.</small></section><button type="button" class="btn primary wide mt" data-action="save-estimate">${icon('check')} Create order estimate</button>`:'';
}
async function estimatesView() {
  const data=await api('/api/staff/jobs?active_only=true');state.jobs=data.jobs;
  shell(heading('FROM ESTIMATE TO ORDER','Projects & estimates.','Use the same scope, pricing, invoices and proof history.',`<a class="icon-button" href="#estimate/new" aria-label="New estimate">${icon('plus')}</a>`)+`<input class="search" id="estimate-search" type="search" placeholder="Search project, order or customer" aria-label="Search estimates"><div class="stack" id="estimate-list">${state.jobs.map(jobCard).join('')||empty('No order estimates yet.','file')}</div>`,'estimates');
}
async function jobView(id) {
  const job=await api('/api/staff/jobs/'+id);state.job=job;
  const active=state.jobTab;
  let content='';
  if(active==='tasks')content=`<div class="stack">${job.tasks.filter(t=>t.status!=='done').map(t=>taskCard({...t,job_id:job.id,number:job.number,job_title:job.title,customer_name:job.customer_name,priority:job.priority})).join('')||empty('All tasks are complete.')}</div><div class="section-heading"><h2>Completed</h2></div>${job.tasks.filter(t=>t.status==='done').map(t=>`<div class="card row mb">${icon('check')}<div class="grow"><strong>${esc(t.title)}</strong><p class="muted">${esc(t.assignee||'')} · ${t.tracked_minutes} min logged</p></div>${badge('Done','teal')}</div>`).join('')}`;
  else if(active==='proofs')content=`${job.production_started?'<div class="notice">Production has started. Proof revisions require a separate change-order project.</div>':`<form data-form="proof" class="card stack"><h2>Attach & send a proof</h2>${field('label','Proof package label','Complete project proof','required maxlength="180"')}<label><span class="label">PNG, JPEG or PDF</span><input name="file" type="file" accept="image/png,image/jpeg,application/pdf" required></label>${noteField('note','Proof notes')}<label class="check"><input name="covers_all_items" type="checkbox" required>This proof covers every item and shows the finished sizes for this order.</label><p class="field-hint">The client receives the existing portal approval flow and the full artwork / sizing terms.</p><div data-errors></div><button class="btn primary wide" type="submit">${icon('upload')} Upload & send for approval</button></form>`}<div class="section-heading"><h2>Proof history</h2></div><div class="stack">${job.proofs.map(p=>`<section class="card proof-card"><div class="row"><h3 class="grow">${esc(p.label)} · v${p.version}</h3>${badge(p.status.replaceAll('_',' '),p.status==='approved'?'teal':'amber')}</div>${p.mime.startsWith('image/')?`<img class="proof-preview" src="/api/assets/${p.asset_id}" alt="${esc(p.label)}">`:''}<p>${esc(p.note)}</p><a class="btn small" href="/api/assets/${p.asset_id}" target="_blank" rel="noopener">Open proof</a>${p.status==='pending'&&p.id===job.proofs[0].id?` <button class="btn primary small" data-action="resend-proof" data-id="${p.id}">Send again</button>`:''}${p.decisions.map(d=>`<p class="muted mt">${esc(d.signer_name)} · ${esc(d.action.replaceAll('_',' '))}${d.comment?' · '+esc(d.comment):''}</p>`).join('')}</section>`).join('')||empty('No shop proof has been attached yet.','file')}</div>`;
  else {
    const invoices=await api('/api/staff/jobs/'+id+'/invoices');
    content=`<div class="split"><div><section class="card"><h2>Client & scope</h2><p class="muted mt">${esc(job.customer_name)}<br>${esc(job.customer_email)}${job.phone?'<br>'+esc(job.phone):''}</p>${job.notes?`<p class="muted break">${esc(job.notes)}</p>`:''}${job.quote.lines.map((l,index)=>`<div class="quote-line"><div><strong>${esc(l.name)}</strong><small>${esc(l.description)}<br>${esc(lineSpecs(l))} · Qty ${l.quantity}</small>${jobPhotoHtml(job,index)}</div><strong>${money(l.sell_cents)}</strong></div>`).join('')}</section><div class="quick-actions mt"><button class="quick" data-action="job-survey" data-id="${id}"><span class="symbol">${icon('ruler')}</span><strong>Site survey</strong></button><button class="quick" data-action="job-tab" data-value="proofs"><span class="symbol">${icon('file')}</span><strong>Attach proof</strong></button></div></div><div><section class="money-summary"><div class="row"><small>Order total · Tax included</small><strong>${money(job.totals.total_cents)}</strong></div><div class="row"><small>Verified payments</small><strong>${money(job.totals.paid_cents)}</strong></div><div class="row total"><span>Balance</span><strong>${money(job.totals.balance_cents)}</strong></div><div class="row"><small>Deposit remaining</small><strong>${money(job.totals.deposit_remaining_cents)}</strong></div></section><p class="field-hint">${job.accepted_version===job.quote_version?'Customer accepted this quote version.':job.published?'Estimate published; awaiting customer acceptance.':'Draft estimate — not yet sent.'}</p>${!job.charges_verified?'<div class="notice mt">Owner review is required before publishing this estimate. Review tax, delivery and any installation / custom scope in the shop workspace.</div>':''}<div class="form-actions"><a class="btn" href="/api/staff/jobs/${id}/estimate-document" target="_blank" rel="noopener">View estimate</a><button class="btn primary" data-action="send-estimate" ${!job.charges_verified?'disabled':''}>${job.published?'Send estimate again':'Send estimate'}</button></div><button class="btn wide mt" data-action="create-invoice">Create invoice</button><p class="field-hint">A reviewed, accepted quote creates an issued invoice. Otherwise it creates a clearly marked draft. Invoice documents are kept in this system.</p>${invoices.invoices.length?`<div class="section-heading"><h2>Invoices</h2></div><div class="stack">${invoices.invoices.map(i=>`<a class="card clickable row" href="/api/staff/invoices/${i.id}" target="_blank" rel="noopener"><strong class="grow">${esc(i.number)}</strong>${badge(i.status,i.status==='issued'?'teal':'amber')}${icon('arrow')}</a>`).join('')}</div>`:''}</div></div><section class="card mt"><h2>Project notes</h2><form data-form="job-note" class="stack mt">${noteField('message','Add an internal note')}<div data-errors></div><button class="btn" type="submit">Save note</button></form>${job.events.filter(e=>e.action==='shop.message'||e.action==='staff.message').slice(0,5).map(e=>`<p class="muted mt break">${esc(e.actor)} · ${esc(e.details.message||'')}</p>`).join('')}</section>`;
  }
  shell(back('estimates','Projects & estimates')+heading(job.number,job.title,job.customer_name,badge(job.stage.replaceAll('_',' '),'teal'))+`<div class="tabs detail-tabs">${[['overview','Overview'],['tasks','Tasks'],['proofs','Proofs']].map(([id,label])=>`<button data-action="job-tab" data-value="${id}" class="${active===id?'active':''}">${label}</button>`).join('')}</div>${content}`,'estimates');
}
function showDialog(title,body,buttons='') {
  dialog.innerHTML=`<h2>${esc(title)}</h2>${body}${buttons}<button class="btn wide" data-action="close-dialog">Close</button>`;dialog.showModal();
}
async function route() {
  const generation=++renderGeneration;
  if(!state.user){loginView();return;}
  if($('form[data-form="survey"]'))await persistSurvey();
  const hash=location.hash.slice(1)||'home';state.route=hash;
  try {
    if(hash==='home')await homeView();
    else if(hash==='tasks')await queueView();
    else if(hash==='clients')await clientsView();
    else if(hash==='client/new')clientFormView();
    else if(hash.startsWith('client/'))await clientView(Number(hash.split('/')[1]));
    else if(hash==='surveys')await surveysView();
    else if(hash==='survey/new'){if(!state.pendingSurvey)newSurvey();else surveyEditor();state.pendingSurvey=false;}
    else if(hash.startsWith('draft/')){const d=await getDraft(hash.slice(6));if(!d||d.user_id!==state.user.id)throw new Error('Device draft not found for this staff account.');state.draft=d;surveyEditor();}
    else if(hash.startsWith('survey/'))await surveyView(Number(hash.split('/')[1]));
    else if(hash==='estimates')await estimatesView();
    else if(hash==='estimate/new'){if(!state.estimate)newEstimate();else estimateEditor();}
    else if(hash.startsWith('job/'))await jobView(Number(hash.split('/')[1]));
    else await homeView();
  } catch(error) {
    if(generation!==renderGeneration || !state.user)return;
    shell(back('home','Today')+`<div class="error">${esc(error.message)}</div><a class="btn" href="#surveys">Open device survey drafts</a><button class="btn mt" data-action="refresh">Try again</button>`,hash.startsWith('survey')?'surveys':'home');
  }
}
function errorsFor(form,error) {
  const node=$('[data-errors]',form);if(node)node.innerHTML=`<div class="error">${esc(error.message)}</div>`;else toast(error.message);
}
root.addEventListener('submit',async event=>{
  const form=event.target.closest('form[data-form]');if(!form)return;event.preventDefault();
  const button=$('button[type="submit"]',form);if(button)button.disabled=true;
  const data=new FormData(form);const payload=Object.fromEntries(data);
  try {
    if(form.dataset.form==='login') {
      const session=await api('/api/session');state.csrf=session.csrf;
      const auth=await api('/api/auth/login',{method:'POST',body:payload});state.user=auth.user;state.csrf=auth.csrf;rememberIdentity();await loadData();await route();
    } else if(form.dataset.form==='client') {
      const id=form.dataset.id;const result=await api('/api/staff/clients'+(id?'/'+id:''),{method:id?'PATCH':'POST',body:payload});
      state.clients=(await api('/api/staff/clients')).contacts;toast('Client saved to the CRM.');location.hash='client/'+(id||result.id);
    } else if(form.dataset.form==='survey') await syncSurvey();
    else if(form.dataset.form==='estimate') {collectEstimate();state.price=await api('/api/staff/estimates/calculate',{method:'POST',body:estimatePayload()});renderEstimatePrice();$('#estimate-price').scrollIntoView({behavior:'smooth',block:'nearest'});}
    else if(form.dataset.form==='proof') {
      const file=data.get('file');if(file.size>50*1024*1024)throw new Error('Proof files must be no larger than 50 MB.');
      data.set('covers_all_items','true');const result=await api('/api/staff/jobs/'+state.job.id+'/proofs',{method:'POST',form:data});
      toast(result.email_sent?'Proof uploaded and emailed for approval.':'Proof uploaded to the portal. Email was not delivered; use Send again to retry.');await jobView(state.job.id);
    } else if(form.dataset.form==='job-note') {await api('/api/staff/jobs/'+state.job.id+'/message',{method:'POST',body:{message:payload.message,public:false}});toast('Internal project note saved.');await jobView(state.job.id);}
  } catch(error){errorsFor(form,error);} finally {if(button)button.disabled=false;}
});
root.addEventListener('input',event=>{
  if(event.target.id==='client-search')renderClientList(event.target.value);
  if(event.target.id==='estimate-search')$('#estimate-list').innerHTML=state.jobs.filter(j=>[j.title,j.number,j.customer_name].join(' ').toLowerCase().includes(event.target.value.toLowerCase())).map(jobCard).join('')||empty('No matching projects.');
  if(event.target.closest('form[data-form="survey"]') && event.target.type!=='file') {
    collectSurvey();clearTimeout(draftTimer);draftTimer=setTimeout(()=>persistSurvey(false).catch(error=>toast('Device storage could not save this draft: '+error.message)),450);
    if($('#draft-status'))$('#draft-status').textContent='Saving device draft…';
  }
  if(event.target.closest('form[data-form="estimate"]') && event.target.type!=='file'){state.price=null;renderEstimatePrice();}
});
root.addEventListener('change',async event=>{
  try {
    if(event.target.matches('[data-survey-photo-input]')) {
      const file=event.target.files[0];if(!file)return;checkPhoto(file);collectSurvey();
      const key=event.target.dataset.surveyPhotoInput;
      const old=(state.draft.local_files||[]).some(f=>f.panel_key===key)||(state.draft.files||[]).some(f=>f.panel_key===key);
      if(!old&&(state.draft.files?.length||0)+(state.draft.local_files?.filter(f=>!f.id).length||0)>=50)throw new Error('Use up to 50 photos / files per survey.');
      await removeSurveyPanelPhoto(key);state.draft.local_files.push({key:crypto.randomUUID(),panel_key:key,name:file.name,blob:file});
      await persistSurvey(false);renderSurveyFiles();return;
    }
    if(event.target.matches('[data-estimate-photo-input]')) {
      const file=event.target.files[0];if(!file)return;checkPhoto(file);collectEstimate();
      const item=state.estimate.items[Number(event.target.dataset.estimatePhotoInput)];
      item.photo={key:crypto.randomUUID(),name:file.name,blob:file};delete item.survey_file_id;estimateEditor();return;
    }
    if(event.target.matches('[data-job-photo-input]')) {
      const file=event.target.files[0];if(!file)return;checkPhoto(file);
      await uploadQuotePhoto(state.job.id,Number(event.target.dataset.jobPhotoInput),state.job.quote_version,{key:crypto.randomUUID(),name:file.name,blob:file});
      toast('Panel photo saved with the quote.');await jobView(state.job.id);return;
    }
    if(['survey-files','survey-camera'].includes(event.target.id)) {
      collectSurvey();const files=[...event.target.files];
      if(files.some(f=>f.size>50*1024*1024))throw new Error('Each photo or file must be no larger than 50 MB.');
      if(files.some(f=>!['image/png','image/jpeg','application/pdf'].includes(f.type)))throw new Error('Choose PNG, JPEG or PDF files. Convert HEIC photos to JPEG first.');
      if(files.length+(state.draft.files?.length||0)+(state.draft.local_files?.filter(f=>!f.id).length||0)>50)throw new Error('Use up to 50 photos / files per survey.');
      state.draft.local_files.push(...files.map(f=>({key:crypto.randomUUID(),name:f.name,blob:f})));
      await persistSurvey(false);renderSurveyFiles();event.target.value='';
    }
    if(event.target.matches('[data-product-select]')) {
      const area=event.target.closest('[data-estimate-item]'),index=Number(area.dataset.estimateItem),pid=Number(event.target.value);
      collectEstimate();const previous=state.estimate.items[index],item=itemDefaults(pid);
      Object.assign(item,{description:previous.description,photo:previous.photo,survey_file_id:previous.survey_file_id});
      if(!product(pid)?.config.quantity_only&&!product(pid)?.config.finished_apparel){item.width=previous.width;item.height=previous.height;}
      state.estimate.items[index]=item;state.price=null;estimateEditor();
    }
  } catch(error){toast(error.message);}
});
async function action(button) {
  const name=button.dataset.action,id=Number(button.dataset.id),value=button.dataset.value;
  if(name==='close-dialog'){dialog.close();return;}
  if(name==='refresh'){await loadData();await route();return;}
  if(name==='queue-filter'){state.queue=value;await queueView();return;}
  if(name==='task'){await api('/api/staff/tasks/'+id+'/action',{method:'POST',body:{action:button.dataset.op}});toast(button.dataset.op==='claim'?'Task accepted — it’s in your queue.':'Task updated.');await loadData();if(state.route.startsWith('job/'))await jobView(state.job.id);else {state.tasks=(await api('/api/staff/task-queue?scope=mine')).tasks;if(state.route==='tasks')await queueView();else await homeView();}return;}
  if(name==='task-note'){showDialog('What is blocking this task?',`<form data-form="task-block" data-id="${id}">${noteField('note','Reason / next step')}<div data-errors></div><button type="submit" class="btn primary wide">Save blocker</button></form>`);return;}
  if(name==='account'){showDialog('Your staff app',`<p><strong>${esc(state.user.name)}</strong><br>${esc(state.user.email)}<br>${owner()?'Owner / admin':'Employee'}</p><p>iPhone: open this page in Safari, tap Share, then Add to Home Screen.<br>Android: use Chrome’s Install app / Add to Home Screen option.</p><p>Survey drafts stay on this device until you sync them. Return to the app while connected to upload.</p><a class="btn wide" href="/staff" target="_blank" rel="noopener">Open shop workspace</a>`,`${state.installPrompt?'<button class="btn primary wide" data-action="install">Install app</button>':''}<button class="btn wide" data-action="password">Change password</button><button class="btn danger wide" data-action="logout">Sign out</button>`);return;}
  if(name==='install'){await state.installPrompt.prompt();state.installPrompt=null;dialog.close();return;}
  if(name==='logout'){dialog.close();if($('form[data-form="survey"]'))await persistSurvey();await api('/api/auth/logout',{method:'POST',body:{}});localStorage.removeItem('tampa_employee_identity');state.user=null;state.clients=[];state.jobs=[];state.tasks=[];state.surveys=[];state.draft=null;state.estimate=null;loginView();return;}
  if(name==='password'){dialog.close();showDialog('Change your password',`<form data-form="password">${field('current_password','Current password','','required autocomplete="current-password"','password')}${field('new_password','New password','','required minlength="12" maxlength="128" autocomplete="new-password"','password')}<div data-errors></div><button class="btn primary wide" type="submit">Save password</button></form>`);return;}
  if(name==='edit-client'){clientFormView(await api('/api/staff/clients/'+id));return;}
  if(name==='new-survey-client'){newSurvey(id);state.pendingSurvey=true;location.hash='survey/new';return;}
  if(name==='new-estimate-client'){newEstimate(id);location.hash='estimate/new';return;}
  if(name==='survey-new-client'){await persistSurvey();showDialog('Add a client to this survey',`<form data-form="survey-client" class="stack">${field('name','Client name','','required maxlength="120"')}${field('company','Company','','maxlength="160"')}${field('email','Email','','autocomplete="email"','email')}${field('phone','Phone','','autocomplete="tel"','tel')}${noteField('notes','Client notes')}<div data-errors></div><button type="submit" class="btn primary wide">Save client & use in survey</button></form>`);return;}
  if(name==='add-area'||name==='remove-area'){
    collectSurvey();
    if(name==='add-area')state.draft.measurements.push(newArea());
    else {await removeSurveyPanelPhoto(state.draft.measurements[id].panel_key);state.draft.measurements.splice(id,1);}
    state.draft.dirty=true;await persistSurvey(false);surveyEditor();
    if(name==='add-area')$('#survey-areas .area:last-child').scrollIntoView({block:'start'});
    return;
  }
  if(name==='remove-panel-photo'){collectSurvey();await removeSurveyPanelPhoto(value);await persistSurvey(false);renderSurveyFiles();return;}
  if(name==='remove-estimate-photo'){collectEstimate();state.estimate.items[id].photo=null;delete state.estimate.items[id].survey_file_id;estimateEditor();return;}
  if(name==='remove-job-photo'){await api(`/api/staff/jobs/${state.job.id}/panel-photos/${id}`,{method:'DELETE',body:{version:state.job.quote_version}});await jobView(state.job.id);return;}
  if(name==='save-device'){await persistSurvey();toast('Survey draft saved on this phone.');return;}
  if(name==='remove-local-file'){collectSurvey();state.draft.local_files.splice(id,1);state.draft.dirty=true;await persistSurvey(false);renderSurveyFiles();return;}
  if(name==='submit-survey'){await syncSurvey(true);return;}
  if(name==='reopen-survey'){await api('/api/staff/surveys/'+id+'/action',{method:'POST',body:{action:'reopen',version:Number(button.dataset.version)}});await surveyView(id);return;}
  if(name==='verify-survey'){showDialog('Verify project measurements',`<p>Confirm you reviewed every measured area, surface condition and access note, and that finished sizes match the current order scope and proof. Any change to print sizes requires an updated quote and proof.</p>`,`<button class="btn primary wide" data-action="confirm-verify" data-id="${id}" data-version="${button.dataset.version}">Confirm verified measurements</button>`);return;}
  if(name==='confirm-verify'){await api('/api/staff/surveys/'+id+'/action',{method:'POST',body:{action:'verify',version:Number(button.dataset.version),confirm:true}});dialog.close();toast('Survey measurements verified.');await surveyView(id);return;}
  if(name==='survey-estimate'){newEstimate(null,await api('/api/staff/surveys/'+id));location.hash='estimate/new';return;}
  if(name==='add-item'||name==='remove-item'){collectEstimate();if(name==='add-item')state.estimate.items.push(itemDefaults(state.catalog.products[0].id));else state.estimate.items.splice(id,1);state.price=null;estimateEditor();return;}
  if(name==='save-estimate'){if(!state.price)throw new Error('Calculate the current estimate first.');const result=await api('/api/staff/estimates',{method:'POST',body:{...estimatePayload(),fingerprint:state.price.fingerprint}});try{for(const [index,item] of state.estimate.items.entries())if(item.photo?.blob)await uploadQuotePhoto(result.job_id,index,1,item.photo);}catch(error){throw new Error(`Estimate #${result.job_id} is saved. Retry Create order estimate to finish uploading panel photos. ${error.message}`);}state.estimate=null;state.price=null;toast('Order estimate saved with catalog pricing.');state.jobTab='overview';location.hash='job/'+result.job_id;return;}
  if(name==='job-tab'){state.jobTab=value;await jobView(state.job.id);return;}
  if(name==='job-survey'){const contact=state.clients.find(c=>c.email.toLowerCase()===state.job.customer_email.toLowerCase());newSurvey(contact?.id||null,id);state.draft.title=state.job.title+' · Site survey';state.pendingSurvey=true;location.hash='survey/new';return;}
  if(name==='resend-proof'){const result=await api('/api/staff/jobs/'+state.job.id+'/proofs/'+id+'/send',{method:'POST',body:{}});toast(result.email_sent?'Proof email sent.':'Proof remains in the portal. Email delivery failed; retry when connected.');return;}
  if(name==='send-estimate'){showDialog('Send the current estimate',`<p>Confirm the scope, product choices, tax, delivery and total for ${esc(state.job.number)}. The client will receive their private order link to review it.</p>`,`<button class="btn primary wide" data-action="confirm-send-estimate">Confirm & send estimate</button>`);return;}
  if(name==='confirm-send-estimate'){const result=await api('/api/staff/estimates/'+state.job.id+'/send',{method:'POST',body:{version:state.job.quote_version,reviewed:true}});dialog.close();toast(result.email_sent?'Estimate emailed to the client.':'Estimate published in the portal. Email was not delivered.');await jobView(state.job.id);return;}
  if(name==='create-invoice'){const result=await api('/api/staff/jobs/'+state.job.id+'/invoices',{method:'POST',body:{version:state.job.quote_version,confirm:true}});showDialog(result.number,`<p>${result.status==='issued'?'Invoice created for the accepted project scope.':'Draft invoice created. Review charges and obtain customer scope acceptance before issuing.'}</p><a class="btn primary wide" href="/api/staff/invoices/${result.invoice_id}" target="_blank" rel="noopener">Open invoice · Print / Save PDF</a>`);return;}
}
async function handleClick(event) {
  const button=event.target.closest('[data-action]');if(!button)return;
  event.preventDefault();if(button.disabled)return;button.disabled=true;
  try{await action(button);}catch(error){toast(error.message);}finally{button.disabled=false;}
}
root.addEventListener('click',handleClick);dialog.addEventListener('click',handleClick);
dialog.addEventListener('submit',async event=>{
  event.preventDefault();const form=event.target,payload=Object.fromEntries(new FormData(form));
  const button=$('button[type="submit"]',form);button.disabled=true;
  try{
    if(form.dataset.form==='survey-client') {
      const result=await api('/api/staff/clients',{method:'POST',body:payload});
      state.clients.push({...payload,id:result.id});state.draft.contact_id=result.id;state.draft.client_name=payload.company||payload.name;
      if(!state.draft.site_contact)state.draft.site_contact=[payload.name,payload.phone].filter(Boolean).join(' · ');
      state.draft.dirty=true;await persistSurvey(false);dialog.close();surveyEditor();toast('Client added to the CRM and selected for this survey.');return;
    }
    if(form.dataset.form==='password'){const response=await api('/api/auth/password',{method:'POST',body:payload});state.csrf=response.csrf;toast('Password changed.');}
    else if(form.dataset.form==='task-block'){if(!payload.note.trim())throw new Error('Enter the blocker reason.');await api('/api/staff/tasks/'+form.dataset.id+'/action',{method:'POST',body:{action:'block',note:payload.note}});toast('Blocker saved.');}
    dialog.close();await loadData();await route();
  }catch(error){errorsFor(form,error);}finally{button.disabled=false;}
});
window.addEventListener('hashchange',route);
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();state.installPrompt=event;});
window.addEventListener('offline',()=>{state.online=false;updateConnection();});
window.addEventListener('online',async()=>{if(state.user){try{const oldId=state.user.id,session=await api('/api/session');state.csrf=session.csrf;if(session.user){state.user=session.user;rememberIdentity();await loadData();if(oldId!==state.user.id){state.draft=null;state.estimate=null;location.hash='home';await route();toast('Staff sign-in changed. Reopen drafts under their original account.');}else toast('Connected again. Save your device drafts to the shop.');}else {state.user=null;localStorage.removeItem('tampa_employee_identity');loginView('Sign in to sync your saved device drafts.');}}catch(error){toast(error.message);}}});
window.addEventListener('pagehide',()=>{if($('form[data-form="survey"]'))persistSurvey().catch(()=>{});});
async function boot() {
  if('serviceWorker' in navigator)navigator.serviceWorker.register('/staff/sw.js',{scope:'/staff/'}).catch(()=>{});
  try {
    const session=await api('/api/session');state.csrf=session.csrf;state.user=session.user;
    if(state.user){rememberIdentity();await loadData();await route();}else {localStorage.removeItem('tampa_employee_identity');loginView();}
  } catch(error) {
    let identity;try{identity=JSON.parse(localStorage.getItem('tampa_employee_identity')||'null');}catch{}
    if(identity && Date.now()-identity.checked_at<8*3600*1000) {
      state.user=identity;state.online=false;try{state.catalog=JSON.parse(localStorage.getItem('tampa_employee_public_catalog')||'null');}catch{}
      location.hash='surveys';await surveysView();
    } else loginView('Reconnect and sign in to access your employee workspace.');
  }
}
boot();
