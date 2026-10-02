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

def test_tier_features_are_enforced_and_update_cached_company(env):
    app,admin,_=env
    info=add_company(admin,'tier-shop','tier.example.test')
    child=tenant(app,'tier.example.test',info)
    assert admin.post('/api/platform/companies/tier-shop/billing',json={'mode':'pilot','plan_id':'studio'}).status_code==200
    assert child.get('/staff/app').status_code==200
    assert child.post('/api/company/billing/simulate',json={'scenario':'active','plan_id':'starter'}).status_code==200
    catalog=child.get('/api/catalog').json()
    assert catalog['entitlements']=={'plan_id':'starter','seats':1,'mobile_app':False,'instant_proofing':False,'product_generators':False}
    assert all(p['config']['instant'] is False and p['config']['self_approve_artwork'] is False for p in catalog['products'])
    for path in ['/staff/app','/staff/manifest.webmanifest','/staff/sw.js','/api/staff/surveys']:
        assert child.get(path).status_code==403,path
    for path in ['/api/orders','/api/portal/artwork-preview/approve','/api/portal/artwork/999/approve','/api/staff/jobs/999/layout']:
        result=child.post(path,json={})
        assert result.status_code==403,(path,result.text)
    # Cached mobile shells cannot use shared staff APIs to keep operating after downgrade.
    assert child.get('/api/staff/jobs',headers={'X-Staff-Mobile':'1'}).status_code==403
    assert child.get('/api/staff/jobs').status_code==200
    product=catalog['products'][0]
    assert child.post('/api/calculate',json={'items':[{'product_id':product['id'],'width':12,'height':12,'quantity':1,'embroidery_preview':{'forged':True}}]}).status_code==403
    assert child.get('/staff/billing').status_code==200
    assert child.get('/api/company/billing').json()['seats']==1
    assert admin.get('/api/catalog').json()['entitlements']['mobile_app'] is True
    for plan,seats in [('studio',10),('business',25)]:
        assert child.post('/api/company/billing/simulate',json={'scenario':'active','plan_id':plan}).status_code==200
        assert child.get('/staff/app').status_code==200
        assert child.get('/api/staff/surveys').status_code==200
        assert child.get('/api/catalog').json()['entitlements']['seats']==seats
        assert child.get('/api/catalog').json()['entitlements']['product_generators'] is (plan=='business')
        generated=child.post('/api/calculate',json={'items':[{'product_id':product['id'],'width':12,'height':12,'quantity':1,'embroidery_preview':{'forged':True}}]})
        layout=child.post('/api/staff/jobs/999/layout',json={})
        if plan=='studio':
            assert generated.status_code==403 and 'Business' in generated.json()['detail']
            assert layout.status_code==403 and 'requires Business.' in layout.json()['detail']
            assert child.get('/api/catalog').json()['entitlements']['instant_proofing'] is True
            assert all(not p['config']['usdot_customizer'] and not p['config']['contour_customizer'] for p in child.get('/api/catalog').json()['products'])
        else:
            assert generated.status_code!=403
            assert layout.status_code==404


def test_tier_seats_cannot_be_increased_by_contract_override(env):
    app,admin,_=env
    info=add_company(admin,'seat-tier','seat-tier.example.test')
    child=tenant(app,'seat-tier.example.test',info)
    admin.post('/api/platform/companies/seat-tier/billing',json={'mode':'pilot','plan_id':'starter'})
    with transaction(app.state.database,True) as conn:
        conn.execute("UPDATE platform_companies SET seats=500 WHERE slug='seat-tier'")
    assert child.get('/api/company/billing').json()['seats']==1
    result=child.post('/api/admin/users',json={'name':'Extra staff','email':'extra@example.test','password':'Temporary-test-123!','role':'employee'})
    assert result.status_code==403,result.text


def test_existing_extra_seat_is_blocked_after_downgrade_and_restored(env):
    app,admin,_=env
    info=add_company(admin,'downgrade','downgrade.example.test')
    child=tenant(app,'downgrade.example.test',info)
    admin.post('/api/platform/companies/downgrade/billing',json={'mode':'pilot','plan_id':'studio'})
    for i in range(3):
        created=child.post('/api/admin/users',json={'name':f'Staff {i}','email':f'staff{i}@example.test','role':'employee'})
        assert created.status_code==200,created.text
    last=created.json()
    extra=tenant(app,'downgrade.example.test',{'owner_email':'staff2@example.test','temporary_password':last['temporary_password']})
    assert extra.get('/api/staff/jobs').status_code==200
    assert child.post('/api/company/billing/simulate',json={'scenario':'active','plan_id':'starter'}).status_code==200
    assert extra.get('/api/staff/jobs').status_code==403
    assert extra.post('/api/jobs/999/artwork',files={'file':('art.png',b'not-image','image/png')}).status_code==403
    assert child.get('/api/admin/company').status_code==200
    assert child.post('/api/company/billing/simulate',json={'scenario':'active','plan_id':'studio'}).status_code==200
    assert extra.get('/api/staff/jobs').status_code==200


def test_existing_starter_plan_migrates_to_one_seat_once(env):
    from app.subscriptions import migrate
    app,_,_=env
    with transaction(app.state.database,True) as conn:
        conn.execute("DELETE FROM subscription_events WHERE id='starter-one-seat-v1'")
        conn.execute("UPDATE subscription_plans SET seats=3 WHERE id='starter'")
    migrate(app)
    with transaction(app.state.database) as conn:
        assert conn.execute("SELECT seats FROM subscription_plans WHERE id='starter'").fetchone()[0]==1
        assert conn.execute("SELECT seats FROM subscription_plans WHERE id='studio'").fetchone()[0]==10
        assert conn.execute("SELECT seats FROM subscription_plans WHERE id='business'").fetchone()[0]==25
    migrate(app)
    with transaction(app.state.database) as conn:
        assert conn.execute("SELECT count(*) FROM subscription_events WHERE id='starter-one-seat-v1'").fetchone()[0]==1
