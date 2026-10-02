import hashlib
import hmac
import json
import time
import pytest
from app.db import transaction
from app.subscriptions import accessible, process_event, SubscriptionGateway
from tests.test_company_platform import add_company, tenant

class FakeBilling(SubscriptionGateway):
    def __init__(self):
        self.key='test-fixture';self.webhook_secret='whsec_fixture';self.live=False
        self.ready=True;self.portal_config='bpc_fixture';self.calls=[];self.current={}
    def call(self,resource,method,params=None,key=None,identifier=None):
        self.calls.append((resource,method,params,key,identifier))
        if resource=='customers': return {'id':'cus_'+key.split('-')[-1]}
        if resource=='prices': return {'id':identifier,'active':True,'currency':'usd','unit_amount':19900,'product':'prod_studio','recurring':{'interval':'month','interval_count':1}}
        if resource=='checkout.sessions': return {'id':'cs_fixture','url':'https://checkout.stripe.com/c/pay/fixture','expires_at':time.time()+86400}
        if resource=='billing_portal.sessions': return {'url':'https://billing.stripe.com/p/session/fixture'}
        raise AssertionError(resource)
    def subscription(self,identifier): return self.current[identifier]

def linked(env):
    app,admin,_=env;app.state.subscription_gateway=FakeBilling()
    info=add_company(admin,'billing-shop','billing.example.test')
    child=tenant(app,'billing.example.test',info)
    with transaction(app.state.database,True) as conn:
        conn.execute("UPDATE subscription_plans SET price_id='price_studio',published=1 WHERE id='studio'")
        conn.execute('UPDATE subscription_settings SET enabled=1')
    assert admin.post('/api/platform/companies/billing-shop/billing',json={'mode':'stripe','plan_id':'studio'}).status_code==200
    return app,admin,child

def subscription(app,status='active',customer='cus_shop'):
    data={'id':'sub_fixture','customer':customer,'status':status,'cancel_at_period_end':False,
          'items':{'data':[{'price':{'id':'price_studio'},'quantity':1,'current_period_end':time.time()+30*86400}]}}
    app.state.subscription_gateway.current['sub_fixture']=data
    return data

def event(kind='customer.subscription.updated',identifier='evt_fixture',obj=None):
    return {'id':identifier,'type':kind,'livemode':False,'data':{'object':obj or {'id':'sub_fixture'}}}

def test_checkout_does_not_grant_access_and_reuses_pending_session(env):
    app,admin,child=linked(env)
    assert child.get('/api/staff/jobs').status_code==403
    result=child.post('/api/company/billing/checkout',json={'plan_id':'studio'})
    assert result.status_code==200,result.text
    assert child.get('/api/staff/jobs').status_code==403
    assert child.post('/api/company/billing/checkout',json={'plan_id':'studio'}).json()==result.json()
    calls=app.state.subscription_gateway.calls
    assert len([c for c in calls if c[0]=='checkout.sessions'])==1
    params=next(c[2] for c in calls if c[0]=='checkout.sessions')
    assert params['mode']=='subscription' and 'payment_method_types' not in params
    assert params['success_url'].startswith('https://billing.example.test/staff/billing')
    assert child.post('/api/company/billing/checkout',json={'plan_id':'business'}).status_code==409
    assert child.get('/staff/billing').status_code==200
    subscription(app)
    process_event(app,event('checkout.session.completed',obj={'id':'cs_fixture','mode':'subscription','subscription':'sub_fixture'}))
    assert child.get('/api/staff/jobs').status_code==200
    assert child.get('/api/company/billing').json()['seats']==10
    assert child.post('/api/company/billing/checkout',json={'plan_id':'studio'}).status_code==409
    assert child.post('/api/company/billing/portal',json={}).status_code==200

def test_failed_payments_grace_cancellation_and_reordered_events(env):
    app,_,child=linked(env)
    child.post('/api/company/billing/checkout',json={'plan_id':'studio'})
    subscription(app);process_event(app,event())
    subscription(app,'past_due');process_event(app,event(identifier='evt_failed'))
    assert child.get('/api/staff/jobs').status_code==200
    grace=child.get('/api/company/billing').json()['grace_until']
    process_event(app,event(identifier='evt_failed_again'))
    assert child.get('/api/company/billing').json()['grace_until']==grace
    with transaction(app.state.database,True) as conn: conn.execute("UPDATE platform_companies SET grace_until=? WHERE slug='billing-shop'",(time.time()-1,))
    assert child.get('/api/staff/jobs').status_code==403
    assert child.post('/api/company/billing/portal',json={}).status_code==200
    subscription(app);process_event(app,event(identifier='evt_recovered'))
    assert child.get('/api/staff/jobs').status_code==200
    app.state.subscription_gateway.current['sub_fixture']['cancel_at_period_end']=True
    process_event(app,event(identifier='evt_cancel_later'))
    assert child.get('/api/staff/jobs').status_code==200
    subscription(app,'canceled');process_event(app,event(identifier='evt_cancel_now'))
    assert child.get('/api/staff/jobs').status_code==403
    process_event(app,event('invoice.paid','evt_old_paid',{'parent':{'subscription_details':{'subscription':'sub_fixture'}}}))
    assert child.get('/api/staff/jobs').status_code==403

def test_pilot_testing_is_free_and_recovery_remains_available(env):
    app,admin,employee=env
    info=add_company(admin,'pilot-shop','pilot.example.test');child=tenant(app,'pilot.example.test',info)
    assert admin.post('/api/platform/companies/pilot-shop/billing',json={'mode':'pilot','plan_id':'studio'}).status_code==200
    assert child.get('/api/company/billing').json()['mode']=='pilot'
    assert child.post('/api/company/billing/checkout',json={'plan_id':'studio'}).status_code==409
    for scenario in ['trial','payment_failed','cancel_at_period_end','active']:
        response=child.post('/api/company/billing/simulate',json={'scenario':scenario,'plan_id':'studio'})
        assert response.json()['charged'] is False
        assert child.get('/api/staff/jobs').status_code==200
    for scenario in ['grace_expired','canceled']:
        assert child.post('/api/company/billing/simulate',json={'scenario':scenario}).status_code==200
        assert child.get('/api/staff/jobs').status_code==403
        assert child.get('/api/company/billing').status_code==200
        assert child.get('/staff/billing').status_code==200
        assert child.post('/api/company/billing/simulate',json={'scenario':'active'}).status_code==200
        assert child.get('/api/staff/jobs').status_code==200
    assert employee.get('/api/platform/billing').status_code==403
    assert admin.get('/api/company/billing').json()['mode']=='included'
    assert admin.post('/api/company/billing/checkout',json={'plan_id':'studio'}).status_code==409
    assert child.get('/api/platform/billing').status_code==404

def test_signed_webhooks_idempotent_and_cannot_cross_companies(env):
    app,admin,child=linked(env)
    child.post('/api/company/billing/checkout',json={'plan_id':'studio'})
    subscription(app,customer='cus_other');process_event(app,event(identifier='evt_other'))
    assert child.get('/api/staff/jobs').status_code==403
    subscription(app)
    raw=json.dumps(event()).encode();stamp=int(time.time())
    signature=hmac.new(b'whsec_fixture',str(stamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
    from fastapi.testclient import TestClient
    anon=TestClient(app)
    assert anon.post('/api/platform/billing/webhook',content=raw,headers={'Stripe-Signature':f't={stamp},v1={signature}'}).status_code==200
    assert anon.post('/api/platform/billing/webhook',content=raw,headers={'Stripe-Signature':f't={stamp},v1={signature}'}).status_code==200
    assert anon.post('/api/platform/billing/webhook',content=raw,headers={'Stripe-Signature':f't={stamp},v1=invalid'}).status_code==400
    assert child.get('/api/staff/jobs').status_code==200
    with transaction(app.state.database) as conn: assert conn.execute("SELECT count(*) FROM subscription_events WHERE id='evt_fixture'").fetchone()[0]==1
    assert anon.put('/api/platform/billing',json={'enabled':True}).status_code==403
    assert child.post('/api/company/billing/simulate',json={'scenario':'active'}).status_code==403

def test_plan_validation_and_restricted_owner_controls(env):
    app,admin,employee=env;app.state.subscription_gateway=FakeBilling()
    body={'monthly_cents':19900,'seats':10,'published':True,'price_id':'price_studio'}
    assert employee.put('/api/platform/billing/plans/studio',json=body).status_code==403
    assert admin.put('/api/platform/billing/plans/studio',json=body).status_code==200
    assert admin.put('/api/platform/billing/plans/starter',json=body).status_code==422
    assert admin.put('/api/platform/billing',json={'enabled':True}).status_code==422
    assert admin.put('/api/platform/billing',json={'enabled':True,'tax_reviewed':True}).status_code==200
    assert admin.get('/api/platform/billing').json()['enabled'] is True

def test_real_sdk_uses_platform_key_and_server_subscription_price(monkeypatch):
    import requests
    from urllib.parse import parse_qs
    monkeypatch.setenv('STRIPE_SECRET_KEY','root-order-fixture')
    monkeypatch.setenv('PLATFORM_BILLING_SECRET_KEY','rk_test_platform_fixture')
    monkeypatch.setenv('PLATFORM_BILLING_WEBHOOK_SECRET','whsec_fixture')
    calls=[]
    def request(self,method,url,**kwargs):
        calls.append((method,url,kwargs))
        assert self.trust_env is False
        result=requests.Response();result.status_code=200
        result._content=json.dumps({'id':'cs_sdk_fixture','object':'checkout.session','url':'https://checkout.stripe.com/c/pay/sdk'}).encode()
        return result
    monkeypatch.setattr(requests.Session,'request',request)
    gateway=SubscriptionGateway()
    result=gateway.call('checkout.sessions','create',{'mode':'subscription','line_items':[{'price':'price_server','quantity':1}],'customer':'cus_server'},'sdk-idempotency')
    assert result['id']=='cs_sdk_fixture'
    method,url,kwargs=calls[0]
    assert method.lower()=='post' and url=='https://api.stripe.com/v1/checkout/sessions'
    assert kwargs['headers']['Authorization']=='Bearer rk_test_platform_fixture'
    assert kwargs['headers']['Stripe-Version']=='2026-08-26.dahlia'
    assert kwargs['headers']['Idempotency-Key']=='sdk-idempotency'
    params=parse_qs(kwargs['data'])
    assert params['line_items[0][price]']==['price_server']
    assert 'payment_method_types' not in kwargs['data']

def test_historical_prices_and_subscription_owner_are_preserved(env):
    app,_,child=linked(env)
    child.post('/api/company/billing/checkout',json={'plan_id':'studio'})
    subscription(app);process_event(app,event())
    with transaction(app.state.database,True) as conn:
        conn.execute("INSERT INTO subscription_price_history VALUES('price_studio','studio',19900,10)")
        conn.execute("UPDATE subscription_plans SET price_id='price_new_studio',monthly_cents=24900 WHERE id='studio'")
    subscription(app,'past_due');process_event(app,event(identifier='evt_old_price'))
    assert child.get('/api/company/billing').json()['status']=='past_due'
    with transaction(app.state.database) as conn:
        assert conn.execute("SELECT monthly_cents FROM platform_companies WHERE slug='billing-shop'").fetchone()[0]==19900
    # An unrelated second subscription for the same customer cannot replace ownership.
    data=subscription(app);data['id']='sub_other';app.state.subscription_gateway.current['sub_other']=data
    process_event(app,event(identifier='evt_wrong_sub',obj={'id':'sub_other'}))
    with transaction(app.state.database) as conn:
        assert conn.execute("SELECT stripe_subscription FROM platform_companies WHERE slug='billing-shop'").fetchone()[0]=='sub_fixture'
