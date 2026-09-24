"""Requests use pytest's isolated temporary database, never production."""
import uuid
from fastapi.testclient import TestClient
from app.marketing import INDEXNOW_KEY
from app.db import transaction
from .conftest import anonymous, payment, finalize, portal, accept


def event(sid=None, **extra):
    return {'sid':sid or uuid.uuid4().hex,'event_id':uuid.uuid4().hex,'event':'page_view','path':'/','consent':True,'source':'google','medium':'organic',**extra}


def send(client,data,origin='https://www.tampasigns.net',**headers):
    return client.post('/api/marketing/event',json=data,headers={'Origin':origin,**headers})


def test_event_privacy_permissions_and_security(env):
    app,admin,employee=env
    with TestClient(app) as client:
        e=event()
        assert send(client,e).status_code==204
        assert send(client,e).status_code==204
        assert send(client,event(),origin='https://evil.example').status_code==403
        assert send(client,event(event='purchase',amount=999999)).status_code==400
        assert send(client,event(path='/portal')).status_code==400
        assert send(client,event(path='/?email=private@example.test')).status_code==400
        assert send(client,event(customer_email='private@example.test')).status_code==400
        assert send(client,event(consent=False)).status_code==400
        assert send(client,event(),DNT='1').status_code==204
        assert send(client,event(),**{'Sec-GPC':'1'}).status_code==204
        assert client.get('/api/admin/marketing').status_code==401
        assert client.get('/api/admin/marketing.csv').status_code==401
        assert client.post('/api/requests',json={}).status_code==403
        assert client.options('/api/marketing/event',headers={'Origin':'https://www.tampasigns.net'}).headers['access-control-allow-origin']=='https://www.tampasigns.net'
        assert client.get('/'+INDEXNOW_KEY+'.txt').text==INDEXNOW_KEY
    assert employee.get('/api/admin/marketing').status_code==403
    assert employee.get('/api/admin/marketing.csv').status_code==403
    r=admin.get('/api/admin/marketing').json()
    assert r['totals']['sessions']==1 and r['totals']['page_view']==1
    assert admin.get('/api/admin/marketing?start=bad').status_code==400
    assert admin.get('/api/admin/marketing?site=bad').status_code==400


def test_cross_site_attribution_and_verified_payment(env):
    app,admin,_=env
    client=anonymous(app);sid=uuid.uuid4().hex
    assert send(client,event(sid,source='instagram',medium='social',campaign='fall-signs')).status_code==204
    assert send(client,event(sid,event='add_to_cart',path='/products'),origin='http://testserver').status_code==204
    client.cookies.set('ts_measure_sid',sid);client.cookies.set('ts_measure_choice','yes')
    items=[{'product_id':1,'width':3,'height':3,'quantity':100}]
    q=client.post('/api/calculate',json={'items':items}).json()
    r=client.post('/api/requests',json={'title':'Attribution test','customer_name':'Private Name','customer_email':'private@example.test','items':items,'fingerprint':q['fingerprint']})
    assert r.status_code==200,r.text
    job=r.json()['job_id'];report=admin.get('/api/admin/marketing?site=main').json()
    assert report['totals']['submitted_requests']==1
    assert report['totals']['attributed_requests']==1
    assert report['totals']['conversion_rate']==100
    row=report['requests'][0]
    assert row['source']=='instagram' and row['campaign']=='fall-signs'
    assert 'Private Name' not in str(report) and 'private@example.test' not in str(report)
    assert report['totals']['collected_cents']==0
    finalize(admin,job)
    accept(portal(app,admin,job))
    pay=payment(admin,job,'25.00','MARKETING-TEST')
    assert pay.status_code==200,pay.text
    r=admin.get('/api/admin/marketing?site=main').json()
    assert r['totals']['collected_cents']==2500 and r['totals']['paid_jobs']==1
    assert 'instagram' in admin.get('/api/admin/marketing.csv').text
    with transaction(app.state.database) as conn:
        payment_id=conn.execute('SELECT id FROM payments WHERE job_id=?',(job,)).fetchone()['id']
    assert admin.post(f'/api/staff/payments/{payment_id}/void',json={'reason':'Test correction'}).status_code==200
    assert admin.get('/api/admin/marketing?site=main').json()['totals']['collected_cents']==0


def test_no_consent_keeps_request_unattributed(env):
    app,admin,_=env;client=anonymous(app);sid=uuid.uuid4().hex
    send(client,event(sid));client.cookies.set('ts_measure_sid',sid);client.cookies.set('ts_measure_choice','no')
    items=[{'product_id':1,'width':3,'height':3,'quantity':100}]
    q=client.post('/api/calculate',json={'items':items}).json()
    r=client.post('/api/requests',json={'title':'No consent','customer_name':'Private','customer_email':'no@example.test','items':items,'fingerprint':q['fingerprint']})
    assert r.status_code==200,r.text
    data=admin.get('/api/admin/marketing?site=unattributed').json()
    assert any(row['id']==r.json()['job_id'] for row in data['requests'])
    assert data['totals']['attributed_requests']==0


def test_optional_attribution_failure_does_not_break_orders(env,monkeypatch):
    app,admin,_=env;client=anonymous(app)
    def unavailable(_value):raise ValueError('Simulated analytics failure')
    monkeypatch.setattr('app.marketing.token_hash',unavailable)
    items=[{'product_id':1,'width':3,'height':3,'quantity':100}]
    q=client.post('/api/calculate',json={'items':items}).json()
    r=client.post('/api/requests',json={'title':'Safe request','customer_name':'Private','customer_email':'safe@example.test','items':items,'fingerprint':q['fingerprint']})
    assert r.status_code==200,r.text
