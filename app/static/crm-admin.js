export function createCrmDashboard({api,staffShell,esc,money,showModal,closeModal,forms,actions,toast}) {
  const labels={new_lead:'New lead',contacted:'Contacted',quote_sent:'Quote sent',awaiting_approval:'Awaiting approval',customer:'Customer',completed:'Completed',lost:'Lost'};
  const number=n=>new Intl.NumberFormat('en-US').format(n||0);
  const localDate=value=>value?new Date(value).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}):'—';
  const statusOptions=value=>Object.entries(labels).map(([v,l])=>`<option value="${v}" ${v===value?'selected':''}>${esc(l)}</option>`).join('');
  let current=null, filters={status:'all',q:''};

  function contactForm(contact={}) {
    const tags=(contact.tags||[]).join(', ');
    return `<form data-form="crm-contact" class="stack">
      <div class="fields">
        <label class="field"><span>Name</span><input name="name" value="${esc(contact.name||'')}" maxlength="120" required></label>
        <label class="field"><span>Company</span><input name="company" value="${esc(contact.company||'')}" maxlength="160"></label>
        <label class="field"><span>Email</span><input name="email" type="email" value="${esc(contact.email||'')}" maxlength="254"></label>
        <label class="field"><span>Phone</span><input name="phone" type="tel" value="${esc(contact.phone||'')}" maxlength="60"></label>
      </div>
      <div class="fields">
        <label class="field"><span>Status</span><select name="status">${statusOptions(contact.status||'new_lead')}</select></label>
        <label class="field"><span>Lead source</span><input name="source" value="${esc(contact.source||'')}" maxlength="120" placeholder="Google, referral, website..."></label>
        <label class="field"><span>Follow-up date</span><input name="follow_up_date" type="date" value="${esc(contact.follow_up_date||'')}"></label>
      </div>
      <label class="field"><span>Tags</span><input name="tags" value="${esc(tags)}" maxlength="500" placeholder="Fleet, Storefront, Contractor, Repeat Customer"></label>
      <label class="check-row"><input type="hidden" name="auto_reminders" value="false"><input type="checkbox" name="auto_reminders" value="true" ${contact.auto_reminders!==false?'checked':''}><span><strong>Automatic project reminders</strong><small>Send conservative quote, proof, and required-deposit reminders when this customer has the next action.</small></span></label>
      <label class="field"><span>Internal notes</span><textarea name="notes" rows="6" maxlength="10000" placeholder="Private notes for your team">${esc(contact.notes||'')}</textarea></label>
      <div class="form-error"></div>
      <div class="modal-footer"><button type="button" class="btn light" data-action="close">Cancel</button><button class="btn primary">Save contact</button></div>
    </form>`;
  }

  async function render(next=filters) {
    filters={...filters,...next};
    const params=new URLSearchParams();
    if(filters.status&&filters.status!=='all')params.set('status',filters.status);
    if(filters.q)params.set('q',filters.q);
    const data=await api('/api/admin/crm'+(params.toString()?'?'+params:''));
    const t=data.totals;
    staffShell(`<div class="page-heading"><div><div class="eyebrow">CUSTOMERS & LEADS</div><h1>CRM</h1><p>Customer details, lead follow-ups and order history in one place.</p></div><div class="row wrap"><button class="btn light" data-action="crm-run-auto">Run reminder check now</button><a class="btn light" href="/api/admin/crm.csv">Export CSV</a><button class="btn primary" data-action="crm-new">+ Add contact</button></div></div>
      <div class="kpis">
        <section class="kpi"><div class="eyebrow">CONTACTS</div><div class="metric">${number(t.contacts)}</div><small class="muted">Customers and leads</small></section>
        <section class="kpi"><div class="eyebrow">ACTIVE LEADS</div><div class="metric">${number(t.leads)}</div><small class="muted">Still in sales follow-up</small></section>
        <section class="kpi"><div class="eyebrow">CUSTOMERS</div><div class="metric">${number(t.customers)}</div><small class="muted">Customer / completed</small></section>
        <section class="kpi last"><div class="eyebrow">FOLLOW-UPS DUE</div><div class="metric">${number(t.follow_ups_due)}</div><small class="muted">Due today or earlier</small></section>
      </div>
      <section class="panel">
        <div class="filter-row">
          <div class="row wrap"><h3>Contacts</h3><span class="badge blue">${number(data.contacts.length)} shown</span></div>
          <form data-form="crm-filter" class="row wrap">
            <div class="search"><span>⌕</span><input name="q" value="${esc(filters.q||'')}" placeholder="Search name, company, email, phone or tag"></div>
            <label class="field compact"><span class="sr-only">Status</span><select name="status"><option value="all">All statuses</option>${statusOptions(filters.status)}</select></label>
            <button class="btn light small">Filter</button>
          </form>
        </div>
        <div class="table-wrap"><table><thead><tr><th>Contact</th><th>Status</th><th>Follow-up</th><th>Jobs</th><th class="right">Quoted</th><th class="right">Paid</th></tr></thead>
          <tbody>${data.contacts.map(c=>`<tr class="clickable-row" data-action="crm-open" data-id="${c.id}">
            <td><strong>${esc(c.company||c.name)}</strong><div class="sub">${c.company?esc(c.name)+' · ':''}${esc(c.email||c.phone||'No contact method')}</div>${c.tags?.length?'<div class="sub">'+c.tags.map(x=>esc(x)).join(' · ')+'</div>':''}</td>
            <td><span class="badge ${['customer','completed'].includes(c.status)?'green':c.status==='lost'?'':'orange'}">${esc(labels[c.status]||c.status)}</span></td>
            <td>${esc(c.follow_up_date||'—')}</td><td>${number(c.order_count)}</td><td class="right money">${money(c.quoted_cents)}</td><td class="right money">${money(c.paid_cents)}</td>
          </tr>`).join('')||'<tr><td colspan="6">No contacts match these filters.</td></tr>'}</tbody>
        </table></div>
      </section>`,'crm','CRM');
  }

  async function open(id) {
    current=await api('/api/admin/crm/'+id);
    const c=current;
    showModal(c.company||c.name,`<div class="stack">
      <div class="row between wrap"><div><div class="eyebrow">${esc(labels[c.status]||c.status)}</div><h2>${esc(c.name)}</h2><p class="muted">${esc(c.email||'')}${c.email&&c.phone?' · ':''}${esc(c.phone||'')}</p></div><div class="row wrap">${c.can_remind?'<button class="btn primary" data-action="crm-remind">Send project reminder</button>':''}<button class="btn light" data-action="crm-edit">Edit contact</button></div></div>
      <div class="kpis crm-mini-kpis"><section class="kpi"><div class="eyebrow">JOBS</div><div class="metric">${number(c.order_count)}</div></section><section class="kpi"><div class="eyebrow">QUOTED</div><div class="metric">${money(c.quoted_cents)}</div></section><section class="kpi"><div class="eyebrow">PAID</div><div class="metric">${money(c.paid_cents)}</div></section><section class="kpi last"><div class="eyebrow">BALANCE</div><div class="metric">${money(c.balance_cents)}</div></section></div>
      <div class="fields"><div><strong>Lead source</strong><p class="muted">${esc(c.source||'Not set')}</p></div><div><strong>Follow-up</strong><p class="muted">${esc(c.follow_up_date||'Not set')}</p></div></div>
      ${c.tags?.length?'<div><strong>Tags</strong><p class="muted">'+c.tags.map(x=>esc(x)).join(' · ')+'</p></div>':''}
      <div><strong>Automatic reminders</strong><p class="muted">${c.auto_reminders?'On — quote, proof, and required-deposit nudges':'Paused for this contact'}</p></div>
      ${c.notes?'<div><strong>Internal notes</strong><p style="white-space:pre-wrap">'+esc(c.notes)+'</p></div>':''}
      ${c.reminders?.length?'<div class="notice info"><strong>Last project reminder</strong><br>'+esc(localDate(c.reminders[0].created_at))+' · '+esc(c.reminders[0].status==='sent'?'Sent to '+c.reminders[0].recipient:'Delivery failed')+'</div>':''}
      <div class="divider"></div><h3>Order & quote history</h3>
      <div class="table-wrap"><table><thead><tr><th>Job</th><th>Date</th><th>Status</th><th class="right">Total</th><th class="right">Paid</th></tr></thead><tbody>
        ${c.jobs.map(j=>`<tr><td><a class="link" href="/staff#job/${j.id}">${esc(j.number)} · ${esc(j.title)}</a></td><td>${esc(localDate(j.created_at))}</td><td>${esc(j.state)}</td><td class="right money">${money(j.total_cents)}</td><td class="right money">${money(j.paid_cents)}</td></tr>`).join('')||'<tr><td colspan="5">No jobs attached yet.</td></tr>'}
      </tbody></table></div>
    </div>`,true);
  }

  actions['crm-new']=()=>{current=null;showModal('Add CRM contact',contactForm(),true);};
  actions['crm-open']=b=>open(Number(b.dataset.id));
  actions['crm-edit']=()=>{if(current)showModal('Edit CRM contact',contactForm(current),true);};
  actions['crm-run-auto']=async()=>{
    const result=await api('/api/admin/crm/reminders/run','POST',{});
    toast(result.sent?result.sent+' automatic reminder'+(result.sent===1?'':'s')+' sent.':result.failed?result.failed+' reminder delivery attempt'+(result.failed===1?'':'s')+' failed.':'No automatic reminders are due right now.',!!result.failed);
    await render();
  };
  actions['crm-remind']=async()=>{
    if(!current)return;
    if(!confirm('Send a friendly “Don’t forget about your project” reminder to '+(current.email||'this contact')+'?'))return;
    const result=await api('/api/admin/crm/'+current.id+'/remind','POST',{});
    toast(result.message||'Project reminder sent.');
    await open(current.id);
  };
  forms['crm-filter']=async(_f,d)=>render({status:d.status||'all',q:d.q||''});
  forms['crm-contact']=async(_f,d)=>{
    const payload={...d,tags:d.tags||'',auto_reminders:d.auto_reminders==='true'};
    const saved=current?await api('/api/admin/crm/'+current.id,'PATCH',payload):await api('/api/admin/crm','POST',payload);
    current=saved;closeModal();toast('CRM contact saved.');await render();
  };
  return {render,open};
}
