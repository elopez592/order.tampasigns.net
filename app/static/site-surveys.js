// Desktop survey browser uses the same private records and files as the staff app.
export function createSiteSurveys({api, state, esc, staffShell, showModal, actions, forms}) {
  const labels={draft:'Draft',submitted:'Awaiting review',verified:'Verified'};
  const colors={draft:'blue',submitted:'orange',verified:'green'};
  const stamp=value=>value?new Date(value).toLocaleString(undefined,{year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'Not recorded';
  const statusBadge=s=>`<span class="badge ${colors[s]||''}">${esc(labels[s]||s)}</span>`;
  const size=n=>Number(n)>=1024*1024?(Number(n)/(1024*1024)).toFixed(1)+' MB':Math.max(1,Math.round(Number(n)/1024))+' KB';
  let filters={}, current=null, photoIndex=0;
  const listHash=(next=filters)=>{
    const params=new URLSearchParams();
    for(const key of ['q','status','job_id','contact_id','page'])if(next[key]&&next[key]!=='all'&&!(key==='page'&&next[key]==='1'))params.set(key,next[key]);
    return 'surveys'+(params.size?'?'+params:'');
  };
  const navigate=async next=>{
    const hash=listHash(next);
    if(location.hash.slice(1)===hash)return render(hash);
    location.hash=hash;
  };
  const card=s=>{
    const images=s.files.filter(f=>f.mime.startsWith('image/'));
    return `<article class="survey-card panel">
      <a class="survey-cover" href="/staff#survey/${s.id}" aria-label="Open ${esc(s.title)}">
        ${images.length?`<img src="${esc(images[0].thumbnail_url)}" alt="Site photo for ${esc(s.title)}" loading="lazy">`:'<span>No photos attached</span>'}
        <span class="survey-photo-count">${s.photo_count} photo${s.photo_count===1?'':'s'} · ${s.area_count} area${s.area_count===1?'':'s'}</span>
      </a>
      <div class="survey-card-body"><div class="row between wrap"><span class="eyebrow">SURVEY #${s.id}</span>${statusBadge(s.status)}</div>
        <h2><a href="/staff#survey/${s.id}">${esc(s.title)}</a></h2><strong>${esc(s.client_name)}</strong>
        <p class="muted survey-address">${esc(s.address||'Site address not entered')}</p>
        <p class="tiny muted">Recorded by ${esc(s.employee_name)}<br>${esc(stamp(s.created_at))}</p>
        <div class="survey-card-footer"><a class="btn light small" href="/staff#survey/${s.id}">View survey</a>
          ${s.job_id?`<a class="link tiny" href="/staff#job/${s.job_id}">${esc(s.job_number)}</a>`:'<span class="tiny muted">No job linked yet</span>'}</div>
      </div>
    </article>`;
  };

  async function render(hash='surveys') {
    const params=new URLSearchParams(hash.split('?')[1]||'');
    filters={q:params.get('q')||'',status:params.get('status')||'',job_id:params.get('job_id')||'',contact_id:params.get('contact_id')||'',page:String(Math.max(1,Number(params.get('page'))||1))};
    const page=Number(filters.page), query=new URLSearchParams({summary:'true',limit:'12',offset:String((page-1)*12)});
    for(const key of ['q','status','job_id','contact_id'])if(filters[key])query.set(key,filters[key]);
    const data=await api('/api/staff/surveys?'+query), totals=data.totals;
    // A filtered refresh can reduce the page count. Keep the last page reachable.
    if(page>1&&data.total<=data.offset)return navigate({...filters,page:String(Math.max(1,Math.ceil(data.total/12)))});
    current=null;
    staffShell(`<div class="site-surveys"><div class="page-heading"><div><div class="eyebrow">MEASUREMENTS & SITE PHOTOS</div><h1>Site Surveys</h1><p>Find saved site visits, measured areas and photos for every client.</p></div><a class="btn primary" href="/staff/app#survey/new">+ New survey</a></div>
      <div class="kpis"><section class="kpi"><div class="eyebrow">SAVED SURVEYS</div><div class="metric">${totals.surveys}</div><small class="muted">All clients and projects</small></section>
        <section class="kpi"><div class="eyebrow">AWAITING REVIEW</div><div class="metric">${totals.submitted}</div><small class="muted">Submitted by your team</small></section>
        <section class="kpi"><div class="eyebrow">VERIFIED</div><div class="metric">${totals.verified}</div><small class="muted">Measurements reviewed</small></section>
        <section class="kpi last"><div class="eyebrow">SITE PHOTOS</div><div class="metric">${totals.photos}</div><small class="muted">Saved with the surveys</small></section></div>
      <section class="panel survey-filters"><form data-form="surveys-filter"><label class="field survey-search"><span>Search surveys</span><input name="q" maxlength="200" value="${esc(filters.q)}" placeholder="Client, job, address or employee"></label>
        <label class="field"><span>Status</span><select name="status"><option value="">All statuses</option>${Object.entries(labels).map(([key,label])=>`<option value="${key}" ${filters.status===key?'selected':''}>${label}</option>`).join('')}</select></label><button class="btn light">Search</button>
      </form>${filters.job_id||filters.contact_id?'<div class="row wrap mt-sm"><span class="badge blue">'+(filters.job_id?'Surveys for this project':'Surveys for this client')+'</span><a class="link tiny" href="/staff#surveys">View all surveys</a></div>':''}</section>
      <div class="row between wrap survey-results"><strong>${data.total} survey${data.total===1?'':'s'}${filters.q||filters.status?' found':''}</strong><span class="tiny muted">Most recently updated first</span></div>
      ${data.surveys.length?`<div class="survey-grid">${data.surveys.map(card).join('')}</div>`:`<section class="panel survey-empty"><h2>${totals.surveys?'No surveys match these filters.':'Your site surveys will appear here.'}</h2><p class="muted mt-sm">${totals.surveys?'Try another client, job number, address or status.':'Save a site survey to the shop from the staff app to see its measurements and photos here.'}</p>${totals.surveys?'<a class="btn light mt" href="/staff#surveys">Clear filters</a>':''}</section>`}
      ${data.total>12?`<nav class="survey-pagination" aria-label="Survey pages">${page>1?`<a class="btn light small" href="/staff#${esc(listHash({...filters,page:String(page-1)}))}">Previous</a>`:'<span></span>'}<span class="tiny muted">Page ${page} of ${Math.ceil(data.total/12)}</span>${data.offset+data.surveys.length<data.total?`<a class="btn light small" href="/staff#${esc(listHash({...filters,page:String(page+1)}))}">Next</a>`:'<span></span>'}</nav>`:''}</div>`, 'surveys', 'Site Surveys');
    window.scrollTo(0,0);
  }

  const panelLabel=(survey,file)=>survey.measurements.find((m,i)=>(m.panel_key||'area-'+i)===file.panel_key)?.label||(file.panel_key?'Measured area':'General site photo');
  const photoButton=(file,label,cls='')=>`<button class="survey-photo ${cls}" data-action="survey-photo" data-id="${file.id}" aria-label="View photo: ${esc(label)}"><img src="${esc(file.thumbnail_url)}" alt="${esc(label)}" loading="lazy"></button>`;
  async function detail(id) {
    current=await api('/api/staff/surveys/'+id);
    const s=current, pictures=s.files.filter(f=>f.mime.startsWith('image/')), documents=s.files.filter(f=>!f.mime.startsWith('image/'));
    staffShell(`<div class="site-surveys"><a class="link tiny" href="/staff#${esc(listHash())}">← Back to Site Surveys</a>
      <div class="page-heading mt"><div><div class="row wrap mb"><span class="eyebrow">SURVEY #${s.id}</span>${statusBadge(s.status)}</div><h1>${esc(s.title)}</h1><p>${esc(s.client_name)}</p></div><div class="row wrap">${s.job_id?`<a class="btn light" href="/staff#job/${s.job_id}">Open ${esc(s.job_number)}</a>`:''}<a class="btn light" href="/staff/app#survey/${s.id}">${s.status==='draft'?'Open in staff app':'Review in staff app'}</a>${state.user?.role==='admin'?`<button class="btn light" data-action="crm-open" data-id="${s.contact_id}">Open client</button>`:''}</div></div>
      <section class="panel survey-details"><dl><div><dt>Site address</dt><dd>${esc(s.address||'Not entered')}</dd></div><div><dt>On-site contact</dt><dd>${esc(s.site_contact||'Not entered')}</dd></div><div><dt>Recorded by</dt><dd>${esc(s.employee_name)}</dd></div><div><dt>Survey saved</dt><dd>${esc(stamp(s.created_at))}</dd></div><div><dt>Last updated</dt><dd>${esc(stamp(s.updated_at))}</dd></div><div><dt>Related project</dt><dd>${s.job_id?`<a class="link" href="/staff#job/${s.job_id}">${esc(s.job_number)} · ${esc(s.job_title)}</a>`:'No job linked yet'}</dd></div></dl></section>
      ${s.access_notes||s.surface_notes||s.removal_required?`<section class="panel survey-notes"><h2>Site notes</h2>${s.access_notes?`<div><h3>Access & installation</h3><p>${esc(s.access_notes)}</p></div>`:''}${s.surface_notes?`<div><h3>Surface & condition</h3><p>${esc(s.surface_notes)}</p></div>`:''}${s.removal_required?'<div class="notice">Existing material removal required</div>':''}</section>`:''}
      <section class="panel survey-measurements"><div class="row between wrap mb"><h2>Measurements</h2><span class="badge blue">${s.measurements.length} area${s.measurements.length===1?'':'s'}</span></div><div class="survey-area-list">${s.measurements.map((m,index)=>{
        const file=pictures.find(f=>f.panel_key===(m.panel_key||'area-'+index));
        return `<article class="survey-area"><div><span class="eyebrow">AREA ${index+1}</span><h3>${esc(m.label)}</h3><p class="survey-dimensions">${esc(m.width)} × ${esc(m.height)} ${esc(m.unit)} <span>· Qty ${m.quantity}</span></p>${m.unit!=='in'?`<p class="tiny muted">${esc(m.width_inches)} × ${esc(m.height_inches)} in</p>`:''}${m.product_name?`<p class="muted mt-sm">${esc(m.product_name)}</p>`:''}${m.notes?`<p class="survey-area-notes mt-sm">${esc(m.notes)}</p>`:''}</div>${file?photoButton(file,m.label,'survey-panel-photo'):''}</article>`;
      }).join('')||'<p class="muted">No measured areas saved yet.</p>'}</div></section>
      <section class="panel survey-gallery"><div class="row between wrap mb"><h2>Photos & files</h2><span class="badge blue">${s.files.length} saved</span></div>${pictures.length?`<div class="survey-photo-grid">${pictures.map(file=>`<figure>${photoButton(file,panelLabel(s,file))}<figcaption><strong>${esc(panelLabel(s,file))}</strong><span class="tiny muted">${esc(file.filename)} · ${size(file.size)}</span><a class="link tiny" href="${esc(file.download_url)}">Download full photo</a></figcaption></figure>`).join('')}</div>`:''}
        ${documents.length?`<div class="stack-sm ${pictures.length?'mt':''}">${documents.map(file=>`<div class="survey-document"><div><strong>${esc(file.filename)}</strong><p class="tiny muted">PDF · ${size(file.size)}</p></div><div class="row wrap"><a class="btn light small" href="${esc(file.url)}" target="_blank" rel="noopener">Open file</a><a class="link tiny" href="${esc(file.download_url)}">Download</a></div></div>`).join('')}</div>`:''}${!s.files.length?'<p class="muted">No photos or files attached to this saved survey.</p>':''}</section></div>`, 'surveys', 'Site Surveys');
    window.scrollTo(0,0);
  }
  function openPhoto(index) {
    const pictures=current.files.filter(f=>f.mime.startsWith('image/'));
    photoIndex=Math.max(0,Math.min(index,pictures.length-1));
    const file=pictures[photoIndex];if(!file)return;
    const label=panelLabel(current,file);
    showModal(label,`<div class="survey-viewer"><img class="survey-full-photo" src="${esc(file.url)}" alt="${esc(label)}"><p class="tiny muted">${esc(file.filename)} · ${size(file.size)}</p><div class="row between wrap mt"><div class="row"><button class="btn light small" data-action="survey-photo-prev" ${photoIndex===0?'disabled':''}>Previous</button><span class="tiny muted">${photoIndex+1} / ${pictures.length}</span><button class="btn light small" data-action="survey-photo-next" ${photoIndex===pictures.length-1?'disabled':''}>Next</button></div><div class="row wrap"><a class="link tiny" href="${esc(file.url)}" target="_blank" rel="noopener">Open full photo</a><a class="btn primary small" href="${esc(file.download_url)}">Download photo</a></div></div></div>`,true);
  }
  actions['survey-photo']=b=>{if(current)openPhoto(current.files.filter(f=>f.mime.startsWith('image/')).findIndex(f=>f.id===Number(b.dataset.id)));};
  actions['survey-photo-prev']=()=>openPhoto(photoIndex-1);
  actions['survey-photo-next']=()=>openPhoto(photoIndex+1);
  forms['surveys-filter']=(_form,d)=>navigate({...filters,q:d.q||'',status:d.status||'',page:'1'});
  return {render,detail};
}
