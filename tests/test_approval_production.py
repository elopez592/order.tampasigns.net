import hashlib
import io
from PIL import Image
from .conftest import create_banner, finalize, portal, accept, proof, approve, finish, payment, task_action, image_bytes
from app.db import transaction


def test_end_to_end_approval_deposit_tasks_and_final_balance(env):
    app,admin,employee=env
    jid=create_banner(admin)
    job=finalize(admin,jid)
    customer=portal(app,admin,jid)
    accept(customer)
    pid=proof(employee,jid)
    job=admin.get(f'/api/staff/jobs/{jid}').json()
    tasks=job['tasks']
    finish(employee,tasks[0]['id'])
    assert task_action(employee,tasks[1]['id'],'start').status_code==409 # purchasing needs deposit
    finish(employee,tasks[2]['id']) # design after quote
    assert task_action(employee,tasks[3]['id'],'start').status_code==409
    result=payment(admin,jid,job['totals']['deposit_cents']/100)
    assert result.status_code==200, result.text
    finish(employee,tasks[1]['id'])
    assert task_action(employee,tasks[3]['id'],'start').status_code==409 # latest proof still pending
    approve(customer,pid)
    assert admin.get(f'/api/staff/jobs/{jid}').json()['stage']=='ready'
    for task in tasks[3:-1]:
        finish(employee,task['id'])
    assert task_action(employee,tasks[-1]['id'],'start').status_code==409
    current=admin.get(f'/api/staff/jobs/{jid}').json()
    assert payment(admin,jid,current['totals']['balance_cents']/100,'TEST-FINAL-2').status_code==200
    finish(employee,tasks[-1]['id'])
    final=customer.get('/api/portal/job').json()
    assert final['stage']=='finished'
    assert final['totals']['balance_cents']==0
    assert 'tasks' not in final and 'task_count' not in final and 'tasks_done' not in final
    assert len(final['proofs'][0]['decisions'])==1


def test_old_proof_cannot_be_approved_and_new_proof_invalidates_gate(env):
    app,admin,employee=env
    jid=create_banner(admin);finalize(admin,jid)
    client=portal(app,admin,jid);accept(client)
    old=proof(admin,jid);new=proof(admin,jid)
    body={'action':'approve','name':'Customer','confirm':True}
    assert client.post(f'/api/portal/proofs/{old}/decision',json=body).status_code==409
    approve(client,new)
    assert client.post(f'/api/portal/proofs/{new}/decision',json=body).status_code==409
    third=proof(admin,jid)
    j=client.get('/api/portal/job').json()
    assert j['proofs'][0]['status']=='pending'
    assert j['proofs'][1]['status']=='approved'
    assert j['proofs'][1]['decisions'][0]['file_hash']==j['proofs'][1]['sha256']


def test_revision_request_requires_new_proof(env):
    app,admin,employee=env
    jid=create_banner(admin);finalize(admin,jid)
    client=portal(app,admin,jid);accept(client)
    pid=proof(admin,jid)
    r=client.post(f'/api/portal/proofs/{pid}/decision',json={'action':'request_changes','name':'Client','comment':'Fix phone number.'})
    assert r.status_code==200
    assert client.post(f'/api/portal/proofs/{pid}/decision',json={'action':'approve','name':'Client','confirm':True}).status_code==409
    assert client.get('/api/portal/job').json()['proofs'][0]['status']=='changes_requested'


def test_payment_reporting_never_marks_paid(env):
    app,admin,employee=env
    jid=create_banner(admin);finalize(admin,jid)
    client=portal(app,admin,jid);accept(client)
    before=client.get('/api/portal/job').json()['totals']
    response=client.post('/api/portal/payment-notice',json={'reference':'CUSTOMER-CLAIM'})
    assert response.status_code==200
    assert client.get('/api/portal/job').json()['totals']==before


def test_payment_idempotency_and_amount_validation(env):
    app,admin,employee=env
    jid=create_banner(admin);job=finalize(admin,jid)
    client=portal(app,admin,jid);accept(client)
    amount=job['totals']['deposit_cents']/100
    first=payment(admin,jid,amount)
    again=payment(admin,jid,amount)
    assert first.status_code==again.status_code==200
    assert again.json()['already_recorded'] is True
    assert payment(admin,jid,amount+1).status_code==409
    assert payment(admin,jid,100000,'TOO-MUCH').status_code==422
    current=admin.get(f'/api/staff/jobs/{jid}').json()
    assert current['totals']['paid_cents']==int(amount*100)
    assert len(current['payments'])==1


def test_quote_revision_revokes_acceptance_and_payment_link(env):
    app,admin,employee=env
    jid=create_banner(admin);finalize(admin,jid)
    client=portal(app,admin,jid);accept(client)
    link=admin.post(f'/api/staff/jobs/{jid}/payment-link',json={'url':'https://connect.intuit.com/test-invoice-not-real','invoice_reference':'TEST-INV','kind':'invoice'})
    assert link.status_code==200,link.text
    job=admin.get(f'/api/staff/jobs/{jid}').json()
    r=admin.post(f'/api/staff/jobs/{jid}/quote',json={'version':job['quote_version'],'shipping':'20','charges_verified':True})
    assert r.status_code==200
    revised=client.get('/api/portal/job').json()
    assert not revised['published']
    assert revised['accepted_version'] is None
    assert revised['payment_url'] is None
    assert revised['quote_version']==job['quote_version']+1
    assert client.post('/api/portal/accept-quote',json={'name':'Client','confirm':True,'version':job['quote_version']}).status_code==409


def test_blank_layout_is_not_approval_eligible(env):
    app,admin,employee=env
    jid=create_banner(admin)
    result=admin.post(f'/api/staff/jobs/{jid}/layout',json={'artwork':{},'publish_as_proof':False})
    assert result.status_code==200,result.text
    image=admin.get('/api/assets/'+str(result.json()['asset_id']))
    assert Image.open(io.BytesIO(image.content)).width>500
    j=admin.get(f'/api/staff/jobs/{jid}').json()
    assert j['proofs']==[]
    assert j['assets'][0]['kind']=='layout'
    assert admin.post(f'/api/staff/jobs/{jid}/layout',json={'artwork':{},'publish_as_proof':True}).status_code==422


def test_generated_complete_layout_and_cross_job_asset_restriction(env):
    app,admin,employee=env
    jid=create_banner(admin)
    aid=admin.post(f'/api/jobs/{jid}/artwork',files={'file':('source.png',image_bytes(),'image/png')}).json()['asset_id']
    result=admin.post(f'/api/staff/jobs/{jid}/layout',json={'artwork':{'0':aid},'publish_as_proof':True,'fit':'contain'})
    assert result.status_code==200,result.text
    job=admin.get(f'/api/staff/jobs/{jid}').json()
    assert job['proofs'][0]['status']=='pending'
    assert job['proofs'][0]['specs'][0]['width']=='72'
    other=create_banner(admin)
    assert admin.post(f'/api/staff/jobs/{other}/layout',json={'artwork':{'0':aid},'publish_as_proof':True}).status_code==422


def test_proof_and_financial_revisions_are_blocked_after_production_starts(env):
    app,admin,employee=env
    jid=create_banner(admin);job=finalize(admin,jid)
    client=portal(app,admin,jid);accept(client)
    approve(client,proof(admin,jid))
    payment(admin,jid,job['totals']['deposit_cents']/100)
    tasks=job['tasks']
    for t in tasks[:3]:finish(employee,t['id'])
    assert task_action(employee,tasks[3]['id'],'start').status_code==200
    response=admin.post(f'/api/staff/jobs/{jid}/proofs',files={'file':('new.png',image_bytes(),'image/png')},data={'covers_all_items':'true'})
    assert response.status_code==409
    response=admin.post(f'/api/staff/jobs/{jid}/quote',json={'version':job['quote_version'],'charges_verified':True})
    assert response.status_code==409


def test_task_state_machine_does_not_skip_start_or_double_start(env):
    app,admin,employee=env
    task_id=admin.get('/api/staff/jobs/1').json()['tasks'][0]['id']
    assert task_action(employee,task_id,'complete').status_code==409
    assert task_action(employee,task_id,'start').status_code==200
    assert task_action(employee,task_id,'start').status_code==409
    assert task_action(employee,task_id,'pause').status_code==200
    assert task_action(employee,task_id,'start').status_code==200
    assert task_action(employee,task_id,'complete').status_code==200
    assert task_action(employee,task_id,'start').status_code==409


def test_file_integrity_is_checked_at_approval(env):
    app,admin,employee=env
    jid=create_banner(admin);finalize(admin,jid)
    client=portal(app,admin,jid);accept(client)
    pid=proof(admin,jid)
    with transaction(app.state.database) as conn:
        stored=conn.execute('SELECT a.stored_name FROM assets a JOIN proofs p ON p.asset_id=a.id WHERE p.id=?',(pid,)).fetchone()[0]
    (app.state.uploads/stored).write_bytes(b'tampered')
    response=client.post(f'/api/portal/proofs/{pid}/decision',json={'action':'approve','name':'Client','confirm':True})
    assert response.status_code==409


def test_payment_correction_is_local_only_and_restores_balance(env):
    app,admin,employee=env
    jid=create_banner(admin);job=finalize(admin,jid)
    client=portal(app,admin,jid);accept(client)
    response=payment(admin,jid,job['totals']['deposit_cents']/100)
    assert response.status_code==200
    pid=response.json()['payment_id']
    assert admin.post(f'/api/staff/payments/{pid}/void',json={'reason':'Duplicate bookkeeping entry; corrected in QuickBooks separately.'}).status_code==200
    current=client.get('/api/portal/job').json()
    assert current['totals']['paid_cents']==0
    assert current['payments'][0]['voided_at']


def test_private_staff_message_not_visible_to_customer(env):
    app,admin,employee=env
    client=portal(app,admin,1)
    assert admin.post('/api/staff/jobs/1/message',json={'message':'CONFIDENTIAL INTERNAL NOTE','public':False}).status_code==200
    assert 'CONFIDENTIAL INTERNAL NOTE' not in client.get('/api/portal/job').text


def test_missing_proof_file_blocks_approval_cleanly(env):
    app,admin,employee=env
    jid=create_banner(admin);finalize(admin,jid)
    client=portal(app,admin,jid);accept(client)
    pid=proof(admin,jid)
    with transaction(app.state.database) as conn:
        stored=conn.execute('SELECT a.stored_name FROM assets a JOIN proofs p ON p.asset_id=a.id WHERE p.id=?',(pid,)).fetchone()[0]
    (app.state.uploads/stored).unlink()
    response=client.post(f'/api/portal/proofs/{pid}/decision',json={'action':'approve','name':'Client','confirm':True})
    assert response.status_code==409
    assert 'unavailable' in response.json()['detail']
