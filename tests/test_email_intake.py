from email.message import EmailMessage
import json
import time
import pytest
from app import email_intake as intake
from app.db import transaction, now
from tests.conftest import create_banner

BASE = '/api/admin/email-intake'


def decision(action='new_inquiry', **kwargs):
    return intake.Decision.model_validate(dict(action=action, confidence=.99, title='Window graphics',
        summary='Customer requests graphics.', reason='Customer requesting work', company='Test Co',
        phone='813-555-0100', specifications='Two windows', deadline='', missing=['Dimensions'],
        target_inquiry_id=None, target_job_id=None) | kwargs)


def message(n=1, **kwargs):
    return dict(account='info@example.test', source_id='10:'+str(n), message_id=f'<m{n}@example.test>',
        thread_id='100', sender='client@example.test', sender_name='Client Name', subject='Window graphics',
        body='Can you quote these windows?', received_at=now(), references='', attachments=[]) | kwargs


def seed(app, msg=None, result=None):
    return intake.record_message(app.state.database, msg or message(), result or decision())


def test_intake_auth_and_no_secret_disclosure(env):
    app, admin, employee = env
    assert employee.get(BASE).status_code == 403
    intake.save_secrets(app.state.database, {'api_key':'never-echo-this', 'accounts':{'info@example.test':'never-echo-password'}})
    response = admin.get(BASE)
    assert response.status_code == 200
    assert 'never-echo' not in response.text
    assert response.json()['ai_connected'] is True
    assert oct(intake.secret_path(app.state.database).stat().st_mode & 0o777) == '0o600'


def test_lead_creates_contact_and_inquiry_without_job_or_email(env):
    app, admin, _ = env
    with transaction(app.state.database) as c:
        before_jobs = c.execute('SELECT count(*) FROM jobs').fetchone()[0]
        before_events = c.execute('SELECT count(*) FROM email_events').fetchone()[0] if c.execute("SELECT name FROM sqlite_master WHERE name='email_events'").fetchone() else None
    saved=seed(app)
    assert saved['inquiry_id']
    d=admin.get(BASE+'/inquiries/'+str(saved['inquiry_id'])).json()
    assert d['email']=='client@example.test' and d['job_id'] is None
    assert d['details']['missing']==['Dimensions']
    assert len(d['messages'])==1
    with transaction(app.state.database) as c:
        assert c.execute('SELECT count(*) FROM jobs').fetchone()[0] == before_jobs
        assert c.execute('SELECT auto_reminders FROM crm_contacts WHERE email=?', ('client@example.test',)).fetchone()[0] == 0
        if before_events is not None: assert c.execute('SELECT count(*) FROM email_events').fetchone()[0] == before_events


def test_dedupe_and_followup_and_separate_project(env):
    app, admin, _ = env
    first=seed(app)
    assert seed(app)['duplicate']
    assert seed(app,message(2,source_id='11:1',message_id='<m1@example.test>'))['duplicate']
    second=seed(app,message(2),decision('update'))
    assert first['inquiry_id']==second['inquiry_id']
    third=seed(app,message(3,body='Now can you do two more?'),decision('new_inquiry',target_inquiry_id=first['inquiry_id']))
    assert third['inquiry_id'] != first['inquiry_id']
    assert len(admin.get(BASE).json()['inquiries'])==2


def test_low_confidence_spam_kept_but_certain_spam_skipped(env):
    app, admin, _=env
    assert seed(app,result=decision('ignore',confidence=.6))['inquiry_id']
    assert seed(app,message(2),decision('ignore'))['inquiry_id'] is None
    d=admin.get(BASE).json()
    assert d['inquiries'][0]['status']=='needs_clarification'
    with transaction(app.state.database) as c:
        assert c.execute('SELECT body FROM email_messages WHERE decision=\'ignore\'').fetchone()[0]==''


def test_ai_cannot_link_other_customers_records(env):
    app, admin, _=env
    foreign=seed(app,message(sender='other@example.test'))
    job=create_banner(admin)
    result=seed(app,message(2),decision('update',target_inquiry_id=foreign['inquiry_id'],target_job_id=job))
    data=admin.get(BASE+'/inquiries/'+str(result['inquiry_id'])).json()
    assert result['inquiry_id']!=foreign['inquiry_id'] and data['job_id'] is None
    assert admin.post(BASE+'/inquiries/'+str(result['inquiry_id'])+'/link',json={'job_id':job}).status_code==422


def test_attachment_private_and_conversion_opens_quote_editor(env):
    app, admin, employee=env
    saved=seed(app,message(attachments=[('artwork.pdf',b'%PDF-1.4\nend')]))
    iid=saved['inquiry_id']
    data=admin.get(BASE+f'/inquiries/{iid}').json()
    aid=data['messages'][0]['attachments'][0]['id']
    assert employee.get(BASE+f'/attachments/{aid}').status_code==403
    attachment=admin.get(BASE+f'/attachments/{aid}')
    assert attachment.content==b'%PDF-1.4\nend' and 'attachment' in attachment.headers['content-disposition']
    response=admin.post(BASE+f'/inquiries/{iid}/convert',json={})
    assert response.status_code==200, response.text
    jid=response.json()['job_id']
    assert admin.post(BASE+f'/inquiries/{iid}/convert',json={}).json()['job_id']==jid
    job=admin.get(f'/api/staff/jobs/{jid}')
    assert job.status_code==200, job.text
    job=job.json()
    assert not job['published'] and job['quote']['lines']==[] and job['tasks']
    assert job['totals']['total_cents']==0 and len(job['assets'])==1
    assert job['email_inquiries'][0]['id']==iid
    assert admin.post(f'/api/staff/jobs/{jid}/publish',json={'reviewed':True,'version':1}).status_code==422
    response=admin.post(f'/api/staff/jobs/{jid}/quote',json={'version':job['quote_version'], 'lines':[{'name':'Window graphics','quantity':1,'sell_total':'200','cost_total':'50','unit':'job','artwork_required':False}]})
    assert response.status_code == 200,response.text
    assert admin.get(f'/api/staff/jobs/{jid}').json()['totals']['total_cents'] == 20000


def test_existing_contact_status_is_preserved(env):
    app, admin, _=env
    c=admin.post('/api/admin/crm',json={'name':'Existing name','email':'client@example.test','status':'customer','phone':'123','notes':'Keep me'}).json()
    seed(app)
    d=admin.get('/api/admin/crm/'+str(c['id'])).json()
    assert d['status']=='customer' and d['name']=='Existing name' and d['notes']=='Keep me'


def test_parse_mime_html_and_filename():
    msg=EmailMessage(); msg['From']='Client <client@example.test>'; msg['Subject']='Cotización'; msg['Message-ID']='<abc@test>'
    msg.set_content('<p>Necesito dos letreros</p><script>doBad()</script>',subtype='html')
    msg.add_attachment(b'art',maintype='application',subtype='octet-stream',filename='../../logo.ai')
    result=intake.parse_message(msg.as_bytes(),'info@example.test','10:1','222')
    assert result['sender']=='client@example.test' and result['thread_id']=='222'
    assert 'Necesito' in result['body'] and 'doBad' not in result['body']
    assert result['attachments'][0][0]=='logo.ai'


class FakeMailbox:
    validity='10'; next_uid=3; folder='All Mail'
    closed=False
    def __init__(self,*args): pass
    def pending(self,last): return [x for x in (1,2) if x>last]
    def fetch(self,uid,account): return message(uid,account=account)
    def history(self,thread): return ['Earlier outgoing quote and incoming requests']
    def close(self): self.closed=True


def configure(app):
    db=app.state.database
    intake.save_secrets(db,{'api_key':'test-only', 'accounts':{'info@example.test':'abcdefghijklmnop'}})
    with transaction(db,True) as c:
        c.execute('INSERT INTO email_accounts(email,enabled,uidvalidity,last_uid,created_at) VALUES(?,1,\'10\',0,?)',('info@example.test',now()))
    return db


def test_cursor_retries_failed_review_no_lost_messages(env):
    app, admin, _=env; db=configure(app)
    def fail(*args): raise RuntimeError('private-secret-must-not-be-logged')
    first=intake.check_mail(db,FakeMailbox,fail)
    assert first['errors']==1
    with transaction(db) as c:
        row=c.execute('SELECT * FROM email_accounts').fetchone()
        assert row['last_uid']==0 and 'private-secret' not in row['error']
    result=intake.check_mail(db,FakeMailbox,lambda *args:decision())
    assert result['reviewed']==2 and result['errors']==0
    with transaction(db) as c:
        assert c.execute('SELECT last_uid FROM email_accounts').fetchone()[0]==2
    assert intake.check_mail(db,FakeMailbox,fail)['reviewed']==0


def test_concurrent_check_lease(env):
    app,_,_=env; db=configure(app)
    with transaction(db,True) as c:
        c.execute('INSERT INTO email_intake_lock VALUES(1,\'other-process\',?)',(time.time()+60,))
    assert intake.check_mail(db,FakeMailbox,lambda *args:decision())=={'busy':True}


def test_connect_mailbox_starts_at_new_mail_and_does_not_echo_secret(env,monkeypatch):
    app, admin, _=env
    intake.save_secrets(app.state.database,{'api_key':'test-only','accounts':{}})
    monkeypatch.setattr(intake,'GmailMailbox',FakeMailbox)
    response=admin.post(BASE+'/accounts',json={'email':'info@example.test','app_password':'abcd efgh ijkl mnop'})
    assert response.status_code==200,response.text
    assert 'abcdefghijklmnop' not in response.text
    with transaction(app.state.database) as c:
        assert c.execute('SELECT last_uid FROM email_accounts').fetchone()[0]==2
    assert admin.post(BASE+'/pause',json={'email':'info@example.test','enabled':False}).status_code==200
    assert intake.check_mail(app.state.database,FakeMailbox,lambda *args:decision())['reviewed']==0


def test_crm_email_link_and_javascript_escape_boundaries(env):
    _, admin, _=env
    assert 'Email inquiries' in admin.get('/static/crm-admin.js').text
    js=admin.get('/static/email-intake.js').text
    assert 'esc(m.body)' in js and 'esc(m.subject' in js


def test_review_api_contract_and_schema(monkeypatch):
    captured={}
    class FakeClient:
        def __init__(self,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def post(self,url,headers,json):
            import httpx
            captured.update(url=url,headers=headers,payload=json)
            return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':decision().model_dump_json()}]}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(intake.httpx,'Client',FakeClient)
    result=intake.review(message(),{'jobs':[]},'test-secret')
    assert result.action=='new_inquiry'
    assert captured['payload']['store'] is False
    assert captured['payload']['text']['format']['strict'] is True
    assert captured['payload']['text']['format']['schema']['additionalProperties'] is False
    assert captured['payload']['model']=='gpt-4.1-mini'


def test_gmail_adapter_reads_all_mail_without_marking_seen(monkeypatch):
    calls=[]
    msg=EmailMessage(); msg['From']='Client <client@example.test>'; msg['Message-ID']='<live@test>'; msg.set_content('Need stickers')
    class FakeImap:
        def __init__(self,*args,**kwargs): pass
        def login(self,*args): calls.append(('login',))
        def list(self): return 'OK',[b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"']
        def select(self,folder,readonly): calls.append(('select',folder,readonly)); return 'OK',[b'2']
        def response(self,key): return key,[b'10' if key=='UIDVALIDITY' else b'3']
        def uid(self,*args):
            calls.append(args)
            if args[0]=='SEARCH': return 'OK',[b'1 2']
            return 'OK',[(b'1 (X-GM-THRID 123 BODY[] {100}',msg.as_bytes()),b')']
        def logout(self): calls.append(('logout',))
    monkeypatch.setattr(intake.imaplib,'IMAP4_SSL',FakeImap)
    box=intake.GmailMailbox('info@example.test','test')
    assert box.pending(1)==[2]
    assert box.fetch(2,'info@example.test')['thread_id']=='123'
    box.close()
    assert ('select','"[Gmail]/All Mail"',True) in calls
    assert any(call[0]=='FETCH' and 'BODY.PEEK[]' in call[2] for call in calls)


def test_invalid_sender_retained_without_borrowing_another_contact(env):
    app,admin,_=env
    msg=EmailMessage(); msg['From']='bad sender'; msg['Subject']='Need signs'; msg.set_content('Need a quote')
    parsed=intake.parse_message(msg.as_bytes(),'info@example.test','10:99','999')
    assert parsed['sender']==''
    assert intake.context_for(app.state.database,parsed)['jobs']==[]
    iid=seed(app,parsed)['inquiry_id']
    assert admin.get(BASE+f'/inquiries/{iid}').json()['status']=='needs_clarification'
    assert admin.post(BASE+f'/inquiries/{iid}/convert',json={}).status_code==422


def test_cross_company_inquiries_and_credentials_are_isolated(env):
    from tests.test_company_platform import add_company,tenant
    app,admin,_=env
    iid=seed(app)['inquiry_id']
    intake.save_secrets(app.state.database,{'api_key':'root-secret','accounts':{}})
    credentials=add_company(admin,'inbox-shop','inbox.example.test')
    other=tenant(app,'inbox.example.test',credentials)
    data=other.get(BASE)
    assert data.status_code==200 and data.json()['ai_connected'] is False
    assert data.json()['inquiries']==[]
    assert other.get(BASE+f'/inquiries/{iid}').status_code==404


def test_job_followups_link_to_correct_sender_only(env):
    app,admin,_=env
    jid=create_banner(admin)
    msg=message(sender='customer@example.test')
    iid=seed(app,msg,decision('update',target_job_id=jid))['inquiry_id']
    assert admin.get(BASE+f'/inquiries/{iid}').json()['job_id']==jid
    assert admin.get(f'/api/staff/jobs/{jid}').json()['email_inquiries'][0]['id']==iid


def test_uidvalidity_change_is_visible_and_does_not_advance_cursor(env):
    app,admin,_=env; db=configure(app)
    class ResetMailbox(FakeMailbox): validity='99'
    result=intake.check_mail(db,ResetMailbox,lambda *args:decision())
    assert result['errors']==1
    data=admin.get(BASE).json()['accounts'][0]
    assert data['last_uid']==0 and 'numbering changed' in data['error']
