"""Payment tests use a fake network gateway and real request/signature validation.
No Stripe account, card, charge or external network is used in this suite.
"""
import copy
import hashlib
import hmac
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from app.checkout import StripeGateway, availability
from app.db import transaction
from .conftest import anonymous, portal, accept, proof, approve, finish, task_action, payment


class FakeGateway(StripeGateway):
    def __init__(self):
        self.ready=True
        self.live=False
        self.webhook_secret='whsec_test_only_not_a_real_secret'
        self.key='sk_test_fake_not_a_real_secret'
        self.sessions={}
        self.creates=[]

    def tax_rate(self, percentage):
        return 'txr_test_only'

    def create_session(self, body, key):
        self.creates.append(copy.deepcopy(body))
        sid='cs_test_'+key.replace('-','')
        self.sessions.setdefault(sid,{'id':sid,'url':'https://checkout.stripe.com/c/pay/'+sid,
                                    'status':'open','payment_status':'unpaid'})
        return self.sessions[sid]

    def retrieve_session(self,sid):
        return copy.deepcopy(self.sessions[sid])


@pytest.fixture
def live_setup(env):
    app,admin,employee=env
    app.state.gateway=FakeGateway()
    s=admin.get('/api/admin/settings').json()
    s.update(rates_live=True,checkout_enabled=True,checkout_tax_reviewed=True,
             checkout_pickup_enabled=True,checkout_pickup_address='TEST ADDRESS - not a real store',
             checkout_pickup_tax_percent='7.5',checkout_shipping_enabled=True,checkout_shipping_price='12')
    response=admin.put('/api/admin/settings',json=s)
    assert response.status_code==200,response.text
    return app,admin,employee


def new_order(app, product_id=1, width=3, height=3, quantity=50, fulfillment='pickup', client=None):
    client=client or anonymous(app)
    items=[{'product_id':product_id,'width':width,'height':height,'quantity':quantity}]
    q=client.post('/api/calculate',json={'items':items}).json()
    body={'items':items,'fingerprint':q['fingerprint'],'request_id':str(uuid.uuid4()),
          'customer_name':'Checkout test','customer_email':'checkout@example.test','title':'Online sticker order',
          'fulfillment':fulfillment,'confirm':True,'total_cents':1}
    result=client.post('/api/orders',json=body)
    if result.status_code==200:
        client.headers['X-CSRF-Token']=result.json()['csrf']
    return client,result,body


def open_session(app,client,jid):
    result=client.post('/api/portal/checkout',json={})
    assert result.status_code==200,result.text
    with transaction(app.state.database) as conn:
        session=dict(conn.execute('SELECT s.* FROM checkout_sessions s JOIN checkout_orders o ON o.id=s.order_id WHERE o.job_id=? ORDER BY s.rowid DESC',(jid,)).fetchone())
    return session


def paid_object(app,session):
    body=json.loads(session['request_body'])
    tax=round(session['merchandise_cents']*.075) if not session['shipping_cents'] else 150
    return {'id':session['stripe_id'],'object':'checkout.session','status':'complete','payment_status':'paid',
            'mode':'payment','livemode':False,'currency':'usd','payment_intent':'pi_'+session['id'],
            'amount_subtotal':session['merchandise_cents'],
            'amount_total':session['merchandise_cents']+session['shipping_cents']+tax,
            'total_details':{'amount_shipping':session['shipping_cents'],'amount_tax':tax,'amount_discount':0},
            'automatic_tax':{'status':'complete'},'client_reference_id':session['order_id'],
            'metadata':{'checkout_id':session['id'],'job_id':body['metadata[job_id]'],'quote_version':str(session['quote_version'])}}


def send_event(app,obj,kind='checkout.session.completed',event_id=None,timestamp=None,signature=None,mode=False):
    event={'id':event_id or 'evt_'+uuid.uuid4().hex,'type':kind,'data':{'object':obj},'livemode':mode,'created':int(time.time())}
    raw=json.dumps(event).encode()
    timestamp=int(time.time()) if timestamp is None else timestamp
    sig=hmac.new(app.state.gateway.webhook_secret.encode(),str(timestamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
    from fastapi.testclient import TestClient
    with TestClient(app) as sender:
        return sender.post('/api/payments/stripe/webhook',content=raw,
              headers={'Content-Type':'application/json','Stripe-Signature':signature or f't={timestamp},v1={sig}'})


def test_customer_api_strips_internal_details(env):
    app,admin,employee=env
    c=portal(app,admin,1)
    j=c.get('/api/portal/job').json()
    for key in ['tasks','tasks_done','task_count','assignee','assignee_id','priority','workflow_id','notes','production_started']:
        assert key not in j
    assert j['stage']=='received'
    text=json.dumps(j)
    for text_ in ['Workflow:', 'Purchasing', 'estimated cost', 'actual material costs', 'gate_reason']:
        assert text_ not in text
    assert all('workflow' not in e['details'] for e in j['events'])
    assert 'tasks' in employee.get('/api/staff/jobs/1').json()


def test_internal_reference_layout_is_not_customer_downloadable(env):
    app,admin,employee=env
    r=admin.post('/api/staff/jobs/1/layout',json={'artwork':{},'publish_as_proof':False})
    assert r.status_code==200
    c=portal(app,admin,1);aid=r.json()['asset_id']
    assert aid not in [a['id'] for a in c.get('/api/portal/job').json()['assets']]
    assert c.get('/api/assets/'+str(aid)).status_code==404
    assert employee.get('/api/assets/'+str(aid)).status_code==200


def test_checkout_disabled_until_connected_and_reviewed(env):
    app,admin,employee=env
    app.state.gateway=FakeGateway()
    c,r,b=new_order(app)
    assert r.status_code==503
    assert not c.get('/api/catalog').json()['checkout']['available']
    assert admin.put('/api/admin/settings',json={'checkout_enabled':True}).status_code==422


@pytest.mark.parametrize('pid,width,height,quantity',[(1,3,3,50),(2,2,2,50),(3,3,3,10),(4,72,36,1),(5,24,18,1)])
def test_standard_products_can_be_purchased(live_setup,pid,width,height,quantity):
    app,admin,employee=live_setup
    c,r,b=new_order(app,pid,width,height,quantity)
    assert r.status_code==200,r.text
    j=c.get('/api/portal/job').json()
    assert j['published'] and j['accepted_version']==j['quote_version']
    assert j['deposit_percent']=='100'
    assert j['totals']['total_cents']>1 # tampered browser total is ignored
    assert j['totals']['paid_cents']==0
    assert j['checkout']['status']=='awaiting_payment'
    assert j['checkout']['can_pay']


def test_standard_order_below_shop_minimum_cannot_checkout(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app,6,24,18,1)
    assert r.status_code==422,r.text
    assert 'Minimum order is $50.00' in r.text


@pytest.mark.parametrize('pid,width,height',[(7,44,92),(8,120,30.5),(4,200,400)])
def test_installation_and_oversize_reject_checkout(live_setup,pid,width,height):
    app,admin,employee=live_setup
    c,r,b=new_order(app,pid,width,height,50 if pid==1 else 1)
    assert r.status_code==422,r.text



def test_vehicle_wrap_print_only_can_checkout_but_installation_requires_quote(live_setup):
    app,admin,employee=live_setup
    client=anonymous(app)
    wrap=next(p for p in client.get('/api/catalog').json()['products'] if p['name']=='Vehicle Wraps')

    print_client,print_response,_=new_order(app,wrap['id'],54,120,1,client=client)
    assert print_response.status_code==200,print_response.text

    client=anonymous(app)
    items=[{'product_id':wrap['id'],'width':54,'height':120,'quantity':1,'installation_requested':True}]
    quote=client.post('/api/calculate',json={'items':items}).json()
    body={'items':items,'fingerprint':quote['fingerprint'],'request_id':str(uuid.uuid4()),
          'customer_name':'Wrap install test','customer_email':'wrap@example.test','title':'Vehicle wrap install',
          'fulfillment':'pickup','confirm':True}
    response=client.post('/api/orders',json=body)
    assert response.status_code==422,response.text


def test_checkout_confirmation_and_csrf_required(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app)
    b.update(request_id=str(uuid.uuid4()),confirm=False)
    assert c.post('/api/orders',json=b).status_code==422
    c.headers.pop('X-CSRF-Token')
    assert c.post('/api/orders',json=b).status_code==403


def test_saved_order_is_idempotent_and_price_locked(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app);jid=r.json()['job_id']
    again=c.post('/api/orders',json=b)
    assert again.status_code==200,again.text
    assert again.json()['job_id']==jid
    c.headers['X-CSRF-Token']=again.json()['csrf']
    j=admin.get(f'/api/staff/jobs/{jid}').json()
    assert admin.post(f'/api/staff/jobs/{jid}/quote',json={'version':j['quote_version'],'charges_verified':True}).status_code==409
    assert payment(admin,jid,1).status_code==409
    other=anonymous(app)
    assert other.post('/api/orders',json=b).status_code==409


def test_stale_price_rejected_at_order_creation(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app)
    p=admin.get('/api/admin/products').json()['products'][0]
    p['config']['sell_per_sqft']='99';p.update(active=True,public=True)
    assert admin.put('/api/admin/products/1',json=p).status_code==200
    b['request_id']=str(uuid.uuid4())
    assert c.post('/api/orders',json=b).status_code==409


def test_payment_session_reused_and_no_card_fields_returned(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app);jid=r.json()['job_id']
    s=open_session(app,c,jid)
    second=c.post('/api/portal/checkout',json={})
    assert second.status_code==200
    assert len(app.state.gateway.creates)==1
    body=app.state.gateway.creates[0]
    assert body['line_items[0][price_data][unit_amount]']==str(s['merchandise_cents'])
    assert body['line_items[0][tax_rates][0]']=='txr_test_only'
    assert 'sk_' not in second.text
    assert c.get('/api/portal/job?payment=received').json()['totals']['paid_cents']==0


def test_valid_signed_payment_counts_once_but_proof_still_required(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app,4,72,36,1);jid=r.json()['job_id'];s=open_session(app,c,jid)
    obj=paid_object(app,s)
    ev='evt_stable_test'
    response=send_event(app,obj,event_id=ev)
    assert response.status_code==200,response.text
    assert send_event(app,obj,event_id=ev).json()['duplicate']
    assert send_event(app,obj).status_code==200
    j=admin.get(f'/api/staff/jobs/{jid}').json()
    assert j['totals']['paid_cents']==obj['amount_total']
    assert len(j['payments'])==1
    assert j['checkout']['status']=='paid'
    assert c.post('/api/portal/checkout',json={}).status_code==409
    tasks=j['tasks']
    for t in tasks[:3]:finish(employee,t['id'])
    assert task_action(employee,tasks[3]['id'],'start').status_code==409
    assert c.get('/api/portal/job').json()['stage']=='received'
    approve(c,proof(employee,jid))
    assert task_action(employee,tasks[3]['id'],'start').status_code==200
    assert c.get('/api/portal/job').json()['stage']=='production'


@pytest.mark.parametrize('mode', ['invalid_signature','stale_signature','wrong_mode','wrong_amount','wrong_job','wrong_currency','unpaid'])
def test_invalid_payment_cannot_clear_balance(live_setup,mode):
    app,admin,employee=live_setup
    c,r,b=new_order(app);jid=r.json()['job_id'];s=open_session(app,c,jid);obj=paid_object(app,s)
    kwargs={}
    if mode=='invalid_signature':kwargs['signature']='t=123,v1=bad'
    if mode=='stale_signature':kwargs['timestamp']=int(time.time())-600
    if mode=='wrong_mode':kwargs['mode']=True
    if mode=='wrong_amount':obj['amount_total']=1
    if mode=='wrong_job':obj['metadata']['job_id']='999'
    if mode=='wrong_currency':obj['currency']='eur'
    if mode=='unpaid':obj['payment_status']='unpaid'
    response=send_event(app,obj,**kwargs)
    assert response.status_code in (200,400)
    assert c.get('/api/portal/job').json()['totals']['paid_cents']==0


def test_shipping_uses_stripe_tax_and_reconciles_address(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app,fulfillment='shipping');jid=r.json()['job_id'];s=open_session(app,c,jid)
    assert c.get('/api/portal/job').json()['checkout']['tax_pending']
    body=json.loads(s['request_body'])
    assert body['automatic_tax[enabled]']=='true'
    assert body['shipping_address_collection[allowed_countries][0]']=='US'
    obj=paid_object(app,s)
    obj['collected_information']={'shipping_details':{'name':'Test Person','address':{'line1':'Synthetic address'}}}
    assert send_event(app,obj).status_code==200
    j=c.get('/api/portal/job').json()
    assert j['totals']['tax_cents']==150
    assert not j['checkout']['tax_pending']
    assert 'Synthetic address' not in json.dumps(j)
    assert 'Synthetic address' in admin.get(f'/api/staff/jobs/{jid}').text


def test_refunds_and_disputes_update_received_amount(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app);jid=r.json()['job_id'];s=open_session(app,c,jid);obj=paid_object(app,s)
    assert send_event(app,obj).status_code==200
    assert send_event(app,{'payment_intent':obj['payment_intent'],'amount_refunded':500},'charge.refunded').status_code==200
    j=c.get('/api/portal/job').json()
    assert j['totals']['paid_cents']==obj['amount_total']-500
    assert j['checkout']['status']=='partly_refunded'
    assert send_event(app,{'payment_intent':obj['payment_intent'],'status':'needs_response'},'charge.dispute.created').status_code==200
    assert c.get('/api/portal/job').json()['totals']['paid_cents']==0
    assert send_event(app,{'payment_intent':obj['payment_intent'],'status':'won'},'charge.dispute.closed').status_code==200
    assert c.get('/api/portal/job').json()['totals']['paid_cents']==obj['amount_total']-500


def test_early_refund_cannot_be_lost_by_later_paid_event(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app);jid=r.json()['job_id'];s=open_session(app,c,jid);obj=paid_object(app,s)
    assert send_event(app,{'payment_intent':obj['payment_intent'],'amount_refunded':obj['amount_total']},'charge.refunded').status_code==200
    assert send_event(app,obj).status_code==200
    j=c.get('/api/portal/job').json()
    assert j['totals']['paid_cents']==0 and j['checkout']['status']=='refunded'


def test_server_checks_provider_before_replacing_expired_session(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app);jid=r.json()['job_id'];s=open_session(app,c,jid)
    app.state.gateway.sessions[s['stripe_id']]['status']='expired'
    r=c.post('/api/portal/checkout',json={})
    assert r.status_code==200,r.text
    assert len(app.state.gateway.creates)==2


def test_unpaid_return_cannot_fake_receipt_and_paid_retry_reconciles(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app);jid=r.json()['job_id'];s=open_session(app,c,jid)
    assert c.get('/api/portal/job?payment=received&paid=true').json()['totals']['paid_cents']==0
    app.state.gateway.sessions[s['stripe_id']]=paid_object(app,s)
    r=c.post('/api/portal/checkout',json={})
    assert r.status_code==200 and r.json()['paid']
    assert c.get('/api/portal/job').json()['checkout']['status']=='paid'


def test_customer_approval_of_generated_proof_still_downloads(live_setup):
    app,admin,employee=live_setup
    c,r,b=new_order(app);jid=r.json()['job_id']
    from .conftest import image_bytes
    aid=c.post(f'/api/jobs/{jid}/artwork',files={'file':('test.png',image_bytes(),'image/png')}).json()['asset_id']
    proof_r=employee.post(f'/api/staff/jobs/{jid}/layout',json={'artwork':{'0':aid},'publish_as_proof':True})
    assert proof_r.status_code==200
    assert c.get('/api/assets/'+str(proof_r.json()['asset_id'])).status_code==200



def custom_paid_object(session):
    body=json.loads(session['request_body'])
    return {'id':session['stripe_id'],'object':'checkout.session','status':'complete','payment_status':'paid',
            'mode':'payment','livemode':False,'currency':'usd','payment_intent':'pi_custom_'+session['id'],
            'amount_subtotal':session['amount_cents'],'amount_total':session['amount_cents'],
            'total_details':{'amount_shipping':0,'amount_tax':0,'amount_discount':0},
            'client_reference_id':'custom-'+str(session['job_id']),
            'metadata':{'custom_checkout_id':session['id'],'job_id':str(session['job_id']),
                        'quote_version':str(session['quote_version']),'payment_kind':session['payment_kind']}}


def test_custom_quote_unlocks_deposit_or_total_after_acceptance(live_setup):
    app,admin,employee=live_setup
    from .conftest import create_banner, finalize
    jid=create_banner(admin)
    finalize(admin,jid)
    c=portal(app,admin,jid)
    before=c.get('/api/portal/job').json()
    assert not before['custom_checkout']['available']
    accept(c)
    job=c.get('/api/portal/job').json()
    assert job['custom_checkout']['available']
    assert job['custom_checkout']['can_pay_deposit']
    assert job['custom_checkout']['can_pay_total']
    assert job['custom_checkout']['deposit_cents']==job['totals']['deposit_remaining_cents']
    response=c.post('/api/portal/custom-checkout',json={'payment_kind':'deposit'})
    assert response.status_code==200,response.text
    with transaction(app.state.database) as conn:
        session=dict(conn.execute(
            'SELECT * FROM custom_checkout_sessions WHERE job_id=? ORDER BY rowid DESC LIMIT 1',(jid,)
        ).fetchone())
    assert session['amount_cents']==job['totals']['deposit_remaining_cents']
    body=json.loads(session['request_body'])
    assert body['line_items[0][price_data][unit_amount]']==str(session['amount_cents'])
    assert body['metadata[payment_kind]']=='deposit'


def test_custom_stripe_deposit_then_balance(live_setup):
    app,admin,employee=live_setup
    from .conftest import create_banner, finalize
    jid=create_banner(admin)
    finalize(admin,jid)
    c=portal(app,admin,jid)
    accept(c)
    initial=c.get('/api/portal/job').json()
    deposit=initial['totals']['deposit_remaining_cents']

    first=c.post('/api/portal/custom-checkout',json={'payment_kind':'deposit'})
    assert first.status_code==200,first.text
    with transaction(app.state.database) as conn:
        session=dict(conn.execute(
            'SELECT * FROM custom_checkout_sessions WHERE job_id=? ORDER BY rowid DESC LIMIT 1',(jid,)
        ).fetchone())
    assert send_event(app,custom_paid_object(session)).status_code==200
    after=c.get('/api/portal/job').json()
    assert after['totals']['paid_cents']==deposit
    assert after['totals']['balance_cents']==initial['totals']['total_cents']-deposit
    assert after['custom_checkout']['can_pay_total']
    assert not after['custom_checkout']['can_pay_deposit']

    second=c.post('/api/portal/custom-checkout',json={'payment_kind':'total'})
    assert second.status_code==200,second.text
    with transaction(app.state.database) as conn:
        balance_session=dict(conn.execute(
            'SELECT * FROM custom_checkout_sessions WHERE job_id=? ORDER BY rowid DESC LIMIT 1',(jid,)
        ).fetchone())
    assert balance_session['amount_cents']==after['totals']['balance_cents']
    assert send_event(app,custom_paid_object(balance_session)).status_code==200
    paid=c.get('/api/portal/job').json()
    assert paid['totals']['balance_cents']==0
    assert paid['custom_checkout']['status']=='paid'


def test_custom_checkout_rejects_unaccepted_or_tampered_payment(live_setup):
    app,admin,employee=live_setup
    from .conftest import create_banner, finalize
    jid=create_banner(admin)
    finalize(admin,jid)
    c=portal(app,admin,jid)
    assert c.post('/api/portal/custom-checkout',json={'payment_kind':'total'}).status_code==409
    accept(c)
    assert c.post('/api/portal/custom-checkout',json={'payment_kind':'other'}).status_code==422
    assert c.post('/api/portal/custom-checkout',json={'payment_kind':'total'}).status_code==200
    with transaction(app.state.database) as conn:
        session=dict(conn.execute(
            'SELECT * FROM custom_checkout_sessions WHERE job_id=? ORDER BY rowid DESC LIMIT 1',(jid,)
        ).fetchone())
    obj=custom_paid_object(session)
    obj['amount_total']-=1
    assert send_event(app,obj).status_code==200
    job=c.get('/api/portal/job').json()
    assert job['totals']['paid_cents']==0
    assert job['custom_checkout']['status']=='payment_review'
