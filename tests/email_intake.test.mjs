import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createEmailIntake} from '../app/static/email-intake.js';

function setup({linked=false}={}) {
  let html='',modal='',closed=false;
  const calls=[],actions={},forms={};
  const esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const data={ai_connected:false,accounts:[],recent:[{sender:'buyer@example.test',subject:'<script>bad()</script>',decision:'new_inquiry',reason:'Wants a quote'}],inquiries:[{id:1,title:'Signs',name:'Client',email:'buyer@example.test',status:'new',message_count:1,updated_at:'2026-11-04T10:00:00Z'}]};
  const inquiry={...data.inquiries[0],job_id:linked?7:null,summary:'Needs <b>signs</b>',details:{missing:['Dimensions'],specifications:'Two signs',deadline:''},messages:[{subject:'Request',sender:'buyer@example.test',received_at:'Today',body:'<img onerror="alert(1)">',attachments:[{id:3,filename:'logo.ai',size:1024}]}],jobs:[{id:7,number:'JOB-0007',title:'Signs'}]};
  const api=async(path,method,body)=>{calls.push({path,method,body});if(path.endsWith('/inquiries/1'))return inquiry;if(path.endsWith('/convert'))return {job_id:7};return data;};
  const ui=createEmailIntake({api,staffShell:s=>html=s,esc,showModal:(_title,s)=>modal=s,closeModal:()=>closed=true,actions,forms,toast:()=>{}});
  return {ui,actions,forms,calls,get html(){return html;},get modal(){return modal;},get closed(){return closed;}};
}

test('setup screen explains automatic intake and escapes email fields',async()=>{
  const t=setup();await t.ui.render();
  assert.match(t.html,/Finish the one-time connections/);
  assert.match(t.html,/INQ-0001/);
  assert.doesNotMatch(t.html,/<script>bad\(\)<\/script>/);
  assert.match(t.html,/&lt;script&gt;/);
});

test('inquiry detail renders escaped original text and attachment download',async()=>{
  const t=setup();await t.ui.open(1);
  assert.match(t.modal,/&lt;img onerror=/);
  assert.doesNotMatch(t.modal,/<img onerror=/);
  assert.match(t.modal,/email-intake\/attachments\/3/);
  assert.match(t.modal,/Create draft quote \/ job/);
  assert.match(t.modal,/Needs &lt;b&gt;signs&lt;\/b&gt;/);
});

test('conversion and linked-job actions close dialog and navigate',async()=>{
  globalThis.location={hash:''};
  const t=setup();await t.ui.open(1);await t.actions['email-convert']();
  assert.equal(location.hash,'job/7');assert.equal(t.closed,true);
  assert.equal(t.calls.at(-1).path,'/api/admin/email-intake/inquiries/1/convert');
  const linked=setup({linked:true});await linked.ui.open(1);
  assert.match(linked.modal,/data-action="email-job"/);
  linked.actions['email-job']();assert.equal(linked.closed,true);
});

test('connection forms collect passwords without putting them in the markup',()=>{
  const t=setup();t.actions['email-connect']();
  assert.match(t.modal,/name="app_password" type="password"/);
  assert.match(t.modal,/autocomplete="off"/);
  t.actions['email-ai']();assert.match(t.modal,/type="password" name="api_key"/);
});
