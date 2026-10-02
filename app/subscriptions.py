"""Platform subscriptions; company order-payment credentials are never used here."""
from . import entitlements
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from fastapi import Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from .db import transaction, audit, now
from .checkout import StripeGateway, API_VERSION

EVENTS = ['checkout.session.completed', 'checkout.session.async_payment_succeeded',
          'customer.subscription.created', 'customer.subscription.updated',
          'customer.subscription.deleted', 'customer.subscription.paused',
          'customer.subscription.resumed', 'invoice.paid', 'invoice.payment_failed',
          'invoice.payment_action_required', 'charge.dispute.created', 'charge.refunded']
SCHEMA = '''CREATE TABLE IF NOT EXISTS subscription_plans (
 id TEXT PRIMARY KEY,name TEXT NOT NULL,monthly_cents INTEGER NOT NULL,seats INTEGER NOT NULL,
 price_id TEXT NOT NULL DEFAULT '',product_id TEXT NOT NULL DEFAULT '',published INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS subscription_price_history (price_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL,monthly_cents INTEGER NOT NULL,seats INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS subscription_events (id TEXT PRIMARY KEY,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS subscription_settings (id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS subscription_checkout (slug TEXT PRIMARY KEY,plan_id TEXT NOT NULL,session_id TEXT NOT NULL,url TEXT NOT NULL,expires_at REAL NOT NULL);
INSERT OR IGNORE INTO subscription_settings VALUES(1,0);'''
COLUMNS = {'billing_mode':"TEXT NOT NULL DEFAULT 'manual'",'plan_id':"TEXT NOT NULL DEFAULT ''",
 'stripe_customer':"TEXT NOT NULL DEFAULT ''",'stripe_subscription':"TEXT NOT NULL DEFAULT ''",
 'subscription_status':"TEXT NOT NULL DEFAULT ''",'paid_through':"REAL NOT NULL DEFAULT 0",
 'grace_until':"REAL NOT NULL DEFAULT 0",'cancel_at_period_end':"INTEGER NOT NULL DEFAULT 0",
 'billing_alert':"TEXT NOT NULL DEFAULT ''"}
DEFAULT_PLANS = [('starter','Starter',9900,1),('studio','Studio',19900,10),('business','Business',39900,25)]

class SubscriptionGateway(StripeGateway):
    def __init__(self):
        self.key=os.getenv('PLATFORM_BILLING_SECRET_KEY','') or (os.getenv('STRIPE_SECRET_KEY','') if os.getenv('PLATFORM_BILLING_USE_SHOP_ACCOUNT')=='1' else '')
        self.webhook_secret=os.getenv('PLATFORM_BILLING_WEBHOOK_SECRET','')
        self.live=self.key.startswith(('sk_live_','rk_live_'))
        self.ready=bool(self.key.startswith(('sk_live_','rk_live_','sk_test_','rk_test_')) and self.webhook_secret.startswith('whsec_'))
        self.portal_config=os.getenv('PLATFORM_BILLING_PORTAL_CONFIG','')
    def call(self,resource,method,params=None,key=None,identifier=None):
        if not self.ready: raise HTTPException(503,'Platform billing is not connected yet. Pilot testing is available.')
        from stripe import StripeClient, StripeError, RequestsClient
        import requests
        session=requests.Session();session.trust_env=False
        client=StripeClient(self.key,stripe_version=API_VERSION,max_network_retries=2,http_client=RequestsClient(timeout=25,session=session))
        service=client.v1
        for part in resource.split('.'): service=getattr(service,part)
        try:
            kwargs={'params':params or {}}
            if key: kwargs['options']={'idempotency_key':key}
            result=getattr(service,method)(identifier,**kwargs) if identifier else getattr(service,method)(**kwargs)
            return result.to_dict()
        except StripeError:
            raise HTTPException(502,'Stripe billing could not complete this request. Retry shortly.')
        finally: session.close()
    def subscription(self,identifier):
        return self.call('subscriptions','retrieve',identifier=identifier)

def migrate(app):
    with transaction(app.state.database,True) as conn:
        conn.executescript(SCHEMA)
        existing={r['name'] for r in conn.execute('PRAGMA table_info(platform_companies)')}
        for name,definition in COLUMNS.items():
            if name not in existing: conn.execute(f'ALTER TABLE platform_companies ADD COLUMN {name} {definition}')
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS billing_customer_unique ON platform_companies(stripe_customer) WHERE stripe_customer<>''")
        for values in DEFAULT_PLANS:
            conn.execute('INSERT OR IGNORE INTO subscription_plans(id,name,monthly_cents,seats) VALUES(?,?,?,?)',values)
        if not conn.execute("SELECT 1 FROM subscription_events WHERE id='starter-one-seat-v1'").fetchone():
            conn.execute("UPDATE subscription_plans SET seats=1 WHERE id='starter'")
            conn.execute("INSERT INTO subscription_events VALUES('starter-one-seat-v1',?)", (now(),))
        for identifier,name,amount,seats in DEFAULT_PLANS:
            price=os.getenv('PLATFORM_BILLING_PRICE_'+identifier.upper(),'')
            product=os.getenv('PLATFORM_BILLING_PRODUCT_'+identifier.upper(),'')
            if price and product:
                conn.execute("UPDATE subscription_plans SET price_id=?,product_id=? WHERE id=? AND price_id=''",(price,product,identifier))
        conn.execute("INSERT OR IGNORE INTO subscription_price_history SELECT price_id,id,monthly_cents,seats FROM subscription_plans WHERE price_id<>''")
        # One-time pilot enrollment, preserving deliberate future billing changes.
        if not conn.execute("SELECT 1 FROM subscription_events WHERE id='mirakol-pilot-v1'").fetchone():
            conn.execute("UPDATE platform_companies SET billing_mode='pilot',plan_id='studio',subscription_status='active',monthly_cents=0,setup_cents=0 WHERE slug='mirakol' AND hostname='mirakol.tampasigns.net' AND name='Mirakol Customs'")
            conn.execute("INSERT INTO subscription_events VALUES('mirakol-pilot-v1',?)",(now(),))
    app.state.subscription_gateway=SubscriptionGateway()
    app.state.subscription_lock=threading.RLock()

def accessible(row,clock=None):
    clock=time.time() if clock is None else clock
    if row['status'] in ('suspended','closed'): return False
    mode=row.get('billing_mode','manual')
    if mode=='manual':
        from datetime import date
        return not (row['status']=='trial' and row['trial_ends'] and date.today()>date.fromisoformat(row['trial_ends']))
    state=row['subscription_status']
    if mode=='pilot': return state in ('active','trialing') or (state=='past_due' and row['grace_until']>clock)
    if state in ('active','trialing'): return row['paid_through']+7*86400>clock
    return state=='past_due' and row['grace_until']>clock

def plans(app):
    with transaction(app.state.database) as conn:
        from .entitlements import PLAN_FEATURES
        return [dict(r) | {'features':PLAN_FEATURES.get(r['id'], {})} for r in conn.execute('SELECT * FROM subscription_plans ORDER BY monthly_cents')]

def connection(app):
    gateway=app.state.subscription_gateway
    with transaction(app.state.database) as conn: enabled=bool(conn.execute('SELECT enabled FROM subscription_settings WHERE id=1').fetchone()[0])
    return {'connected':gateway.ready,'live':gateway.live,'enabled':enabled,
            'portal_ready':bool(gateway.portal_config),'webhook_url':app.state.public_url+'/api/platform/billing/webhook'}

def reconcile(app,subscription):
    customer=subscription.get('customer');customer=customer.get('id') if isinstance(customer,dict) else customer
    with transaction(app.state.database) as conn:
        known=conn.execute('SELECT billing_mode FROM platform_companies WHERE stripe_customer=?',(customer,)).fetchone()
    if not known or known['billing_mode']!='stripe': return False
    identifier=subscription.get('id','')
    items=subscription.get('items',{}).get('data',[])
    if len(items)!=1 or items[0].get('quantity',1)!=1: raise HTTPException(409,'Subscription needs platform-owner review.')
    price=items[0].get('price',{}).get('id')
    with transaction(app.state.database,True) as conn:
        row=conn.execute('SELECT * FROM platform_companies WHERE stripe_customer=?',(customer,)).fetchone()
        plan=conn.execute('SELECT * FROM subscription_plans WHERE price_id=?',(price,)).fetchone()
        if not plan: plan=conn.execute('SELECT plan_id AS id,monthly_cents,seats FROM subscription_price_history WHERE price_id=?',(price,)).fetchone()
        if not row or row['billing_mode']!='stripe' or not plan: return False
        pending=conn.execute('SELECT * FROM subscription_checkout WHERE slug=?',(row['slug'],)).fetchone()
        if row['stripe_subscription'] and row['stripe_subscription']!=identifier: return False
        if not row['stripe_subscription'] and (not pending or pending['plan_id']!=plan['id']): return False
        status=subscription['status']
        end=float(subscription.get('trial_end') or items[0].get('current_period_end') or subscription.get('current_period_end') or 0)
        grace=(row['grace_until'] or time.time()+7*86400) if status=='past_due' else 0
        conn.execute('UPDATE platform_companies SET stripe_subscription=?,subscription_status=?,plan_id=?,seats=?,monthly_cents=?,paid_through=?,grace_until=?,cancel_at_period_end=?,revision=revision+1,updated_at=? WHERE slug=?',
          (identifier,status,plan['id'],plan['seats'],plan['monthly_cents'],end,grace,int(bool(subscription.get('cancel_at_period_end'))),now(),row['slug']))
        audit(conn,None,'Stripe','platform.subscription_updated',{'slug':row['slug'],'status':status,'plan':plan['id']})
    return True

def process_event(app,event):
    with app.state.subscription_lock:
        with transaction(app.state.database) as conn:
            if conn.execute('SELECT 1 FROM subscription_events WHERE id=?',(event['id'],)).fetchone(): return
        obj=event['data']['object'];kind=event['type'];sid=None
        if kind.startswith('customer.subscription.'): sid=obj['id']
        elif kind.startswith('checkout.session.'):
            with transaction(app.state.database) as conn:
                pending=conn.execute('SELECT 1 FROM subscription_checkout WHERE session_id=?',(obj['id'],)).fetchone()
            if pending and obj.get('mode')=='subscription': sid=obj.get('subscription')
        elif kind.startswith('invoice.'):
            sid=obj.get('parent',{}).get('subscription_details',{}).get('subscription') or obj.get('subscription')
        if isinstance(sid,dict): sid=sid.get('id')
        if sid:
            # Retrieve current provider state so delayed/reordered events cannot reactivate cancellation.
            reconcile(app,app.state.subscription_gateway.subscription(sid))
        if kind in ('charge.dispute.created','charge.refunded'):
            charge=obj if kind=='charge.refunded' else app.state.subscription_gateway.call('charges','retrieve',identifier=obj['charge'])
            with transaction(app.state.database,True) as conn:
                conn.execute("UPDATE platform_companies SET billing_alert='A subscription payment requires review in Stripe.' WHERE stripe_customer=?",(charge.get('customer',''),))
        with transaction(app.state.database,True) as conn:
            conn.execute('INSERT OR IGNORE INTO subscription_events VALUES(?,?)',(event['id'],now()))

def checkout(app,slug,plan_id):
    with app.state.subscription_lock:
        with transaction(app.state.database) as conn:
            row=dict(conn.execute('SELECT * FROM platform_companies WHERE slug=?',(slug,)).fetchone())
            plan=conn.execute('SELECT * FROM subscription_plans WHERE id=? AND published=1',(plan_id,)).fetchone()
            pending=conn.execute('SELECT * FROM subscription_checkout WHERE slug=?',(slug,)).fetchone()
        if row['billing_mode']!='stripe': raise HTTPException(409,'This company has free pilot or manually managed access.')
        if not plan or not plan['price_id'] or not connection(app)['enabled']: raise HTTPException(409,'This subscription plan is not open for checkout.')
        if row['stripe_subscription']:
            reconcile(app,app.state.subscription_gateway.subscription(row['stripe_subscription']))
            with transaction(app.state.database) as conn: current=conn.execute('SELECT subscription_status FROM platform_companies WHERE slug=?',(slug,)).fetchone()[0]
            if current not in ('canceled','incomplete_expired'): raise HTTPException(409,'Manage your existing subscription in Billing instead of creating another.')
            with transaction(app.state.database,True) as conn: conn.execute("UPDATE platform_companies SET stripe_subscription='' WHERE slug=?",(slug,))
        if pending and pending['expires_at']>time.time():
            if pending['plan_id']!=plan_id: raise HTTPException(409,'Finish or cancel the open checkout before changing plans.')
            return {'url':pending['url']}
        with transaction(app.state.database.parent/'companies'/slug/'signshop.sqlite3') as conn:
            if conn.execute('SELECT count(*) FROM users WHERE active=1').fetchone()[0]>plan['seats']: raise HTTPException(409,'Choose a plan with enough seats for your current staff.')
        gateway=app.state.subscription_gateway
        if not row['stripe_customer']:
            customer=gateway.call('customers','create',{'name':row['name'],'email':row['owner_email']},'platform-customer-'+slug)
            with transaction(app.state.database,True) as conn: conn.execute('UPDATE platform_companies SET stripe_customer=? WHERE slug=?',(customer['id'],slug))
            row['stripe_customer']=customer['id']
        key='platform-checkout-'+slug+'-'+plan_id+'-'+str(int(time.time()//1800))
        label=hashlib.sha256(key.encode()).hexdigest()[:8].translate(str.maketrans('0123456789','abcdefghij'))
        url='https://'+row['hostname']+'/staff/billing'
        session=gateway.call('checkout.sessions','create',{'mode':'subscription','customer':row['stripe_customer'],
          'client_reference_id':slug,'line_items':[{'price':plan['price_id'],'quantity':1}],
          'success_url':url+'?checkout=returned','cancel_url':url,'integration_identifier':'sign-platform-'+label,
          'billing_address_collection':'required'},key)
        if not str(session.get('url','')).startswith('https://checkout.stripe.com/'): raise HTTPException(502,'Stripe returned an invalid checkout address.')
        with transaction(app.state.database,True) as conn:
            conn.execute('INSERT INTO subscription_checkout VALUES(?,?,?,?,?) ON CONFLICT(slug) DO UPDATE SET plan_id=excluded.plan_id,session_id=excluded.session_id,url=excluded.url,expires_at=excluded.expires_at',
              (slug,plan_id,session['id'],session['url'],session['expires_at']))
        return {'url':session['url']}

def install_platform(app,owner):
    migrate(app)
    @app.get('/api/platform/billing')
    def status(user=Depends(owner)):
        return connection(app)|{'plans':plans(app),'grace_days':7,'pilot_message':'Tampa is included. Mirakol is a free pilot; simulations never charge a card.'}
    @app.put('/api/platform/billing/plans/{identifier}')
    def save_plan(identifier:str,payload:dict=Body(...),user=Depends(owner)):
        with transaction(app.state.database,True) as conn:
            row=conn.execute('SELECT * FROM subscription_plans WHERE id=?',(identifier,)).fetchone()
            if not row: raise HTTPException(404,'Plan not found.')
            amount=payload.get('monthly_cents');seats=payload.get('seats');published=payload.get('published')
            if type(amount) is not int or not 100<=amount<=1000000 or type(seats) is not int or not 1<=seats<=500 or type(published) is not bool: raise HTTPException(422,'Check price, seats and publication status.')
            price=payload.get('price_id',row['price_id']);product=payload.get('product_id',row['product_id'])
            if price and not re.fullmatch(r'price_[A-Za-z0-9]+',price): raise HTTPException(422,'Invalid Stripe price.')
            if published and not price: raise HTTPException(422,'Connect a recurring Stripe price before publishing.')
        if price:
            obj=app.state.subscription_gateway.call('prices','retrieve',identifier=price)
            if not obj.get('active') or obj.get('currency')!='usd' or obj.get('unit_amount')!=amount or obj.get('recurring',{}).get('interval')!='month' or obj['recurring'].get('interval_count',1)!=1: raise HTTPException(422,'Use an active monthly USD price matching this amount.')
            product=obj['product']
            with transaction(app.state.database) as conn:
                if conn.execute('SELECT 1 FROM subscription_plans WHERE product_id=? AND id<>?',(product,identifier)).fetchone(): raise HTTPException(422,'Each tier needs its own Stripe product.')
        with transaction(app.state.database,True) as conn:
            conflict=conn.execute('SELECT plan_id FROM subscription_price_history WHERE price_id=?',(price,)).fetchone()
            if conflict and conflict['plan_id']!=identifier: raise HTTPException(422,'This price belongs to another plan.')
            if price: conn.execute('INSERT OR IGNORE INTO subscription_price_history VALUES(?,?,?,?)',(price,identifier,amount,seats))
            conn.execute('UPDATE subscription_plans SET monthly_cents=?,seats=?,price_id=?,product_id=?,published=? WHERE id=?',(amount,seats,price,product,int(published),identifier))
            audit(conn,None,user['email'],'platform.plan_updated',{'plan':identifier,'published':published})
        return {'ok':True}
    @app.put('/api/platform/billing')
    def enable(payload:dict=Body(...),user=Depends(owner)):
        if type(payload.get('enabled')) is not bool: raise HTTPException(422,'Invalid billing setting.')
        if payload['enabled'] and (not app.state.subscription_gateway.ready or not app.state.subscription_gateway.portal_config or payload.get('tax_reviewed') is not True): raise HTTPException(422,'Connect checkout, webhooks and portal, and review subscription tax before enabling paid signup.')
        with transaction(app.state.database,True) as conn:
            conn.execute('UPDATE subscription_settings SET enabled=? WHERE id=1',(int(payload['enabled']),))
            audit(conn,None,user['email'],'platform.billing_enabled',{'enabled':payload['enabled']})
        return {'ok':True}
    @app.post('/api/platform/companies/{slug}/billing')
    def company_mode(slug:str,payload:dict=Body(...),user=Depends(owner)):
        mode=payload.get('mode');plan=payload.get('plan_id','studio')
        if mode not in ('manual','pilot','stripe') or not any(p['id']==plan for p in plans(app)): raise HTTPException(422,'Choose a billing mode and plan.')
        with transaction(app.state.database,True) as conn:
            row=conn.execute('SELECT * FROM platform_companies WHERE slug=?',(slug,)).fetchone()
            if not row: raise HTTPException(404,'Company not found.')
            if mode=='stripe' and not row['hostname']: raise HTTPException(422,'Connect this company’s hostname before enabling paid access.')
            if row['stripe_subscription']: raise HTTPException(409,'Manage the linked subscription in Stripe before changing its billing mode.')
            conn.execute('UPDATE platform_companies SET billing_mode=?,plan_id=?,subscription_status=?,grace_until=0,revision=revision+1 WHERE slug=?',(mode,plan,'active' if mode=='pilot' else '',slug))
            audit(conn,None,user['email'],'platform.billing_mode',{'slug':slug,'mode':mode})
        return {'ok':True}
    @app.post('/api/platform/billing/webhook')
    async def webhook(request:Request):
        raw=await request.body()
        if len(raw)>1024*1024: raise HTTPException(413,'Event is too large.')
        event=app.state.subscription_gateway.verify_event(raw,request.headers.get('stripe-signature',''))
        import asyncio
        await asyncio.to_thread(process_event,app,event)
        return {'received':True}

def install_company(app,require_admin):
    @app.get('/staff/billing',response_class=HTMLResponse)
    def page(): return HTMLResponse((Path(__file__).with_name('static')/'billing.html').read_text(),headers={'Cache-Control':'no-store'})
    def context():
        root=getattr(app.state,'support_root',None)
        if not root: return None,None
        with transaction(root.state.database) as conn: row=conn.execute('SELECT * FROM platform_companies WHERE slug=?',(app.state.support_slug,)).fetchone()
        return root,dict(row)
    @app.get('/api/company/billing')
    def status(user=Depends(require_admin)):
        root,row=context()
        if not root: return {'mode':'included','status':'active','company':'Tampa Signs and Stickers','plans':[],'accessible':True}
        if row['billing_mode']=='stripe' and row['stripe_subscription']:
            with root.state.subscription_lock: reconcile(root,root.state.subscription_gateway.subscription(row['stripe_subscription']))
            root,row=context()
        return {'mode':row['billing_mode'],'status':row['subscription_status'] or row['status'],'company':row['name'],
          'plan_id':row['plan_id'],'seats':entitlements.for_app(app)['seats'],'entitlements':entitlements.for_app(app),'paid_through':row['paid_through'],'grace_until':row['grace_until'],
          'cancel_at_period_end':bool(row['cancel_at_period_end']),'accessible':accessible(row),'alert':row['billing_alert'],
          'connection':connection(root),'has_customer':bool(row['stripe_customer']),
          'plans':[p for p in plans(root) if p['published'] or row['billing_mode']=='pilot']}
    @app.post('/api/company/billing/checkout')
    def start(payload:dict=Body(...),user=Depends(require_admin)):
        root,row=context()
        if not root: raise HTTPException(409,'The platform owner workspace is included.')
        return checkout(root,row['slug'],payload.get('plan_id'))
    @app.post('/api/company/billing/portal')
    def portal(user=Depends(require_admin)):
        root,row=context()
        if not root or row['billing_mode']!='stripe' or not row['stripe_customer']: raise HTTPException(409,'This company has no paid billing account.')
        gateway=root.state.subscription_gateway
        if not gateway.portal_config: raise HTTPException(503,'Billing portal is not connected.')
        result=gateway.call('billing_portal.sessions','create',{'customer':row['stripe_customer'],'configuration':gateway.portal_config,'return_url':'https://'+row['hostname']+'/staff/billing'})
        if not str(result.get('url','')).startswith('https://billing.stripe.com/'): raise HTTPException(502,'Stripe returned an invalid portal address.')
        return {'url':result['url']}
    @app.post('/api/company/billing/simulate')
    def simulate(payload:dict=Body(...),user=Depends(require_admin)):
        root,row=context();scenario=payload.get('scenario');plan=payload.get('plan_id',row['plan_id'] if row else '')
        if not root or row['billing_mode']!='pilot': raise HTTPException(403,'Simulations are available only for free pilot companies.')
        statuses={'active':'active','trial':'trialing','payment_failed':'past_due','grace_expired':'past_due','canceled':'canceled','cancel_at_period_end':'active'}
        chosen=next((p for p in plans(root) if p['id']==plan),None)
        if scenario not in statuses or not chosen: raise HTTPException(422,'Choose a pilot scenario and plan.')
        with transaction(root.state.database,True) as conn:
            conn.execute('UPDATE platform_companies SET subscription_status=?,plan_id=?,seats=?,monthly_cents=0,paid_through=?,grace_until=?,cancel_at_period_end=?,revision=revision+1 WHERE slug=?',
              (statuses[scenario],plan,chosen['seats'],time.time()+30*86400,time.time()+(-1 if scenario=='grace_expired' else 7*86400) if 'failed' in scenario or scenario=='grace_expired' else 0,int(scenario=='cancel_at_period_end'),row['slug']))
            audit(conn,None,user['email'],'platform.pilot_simulation',{'slug':row['slug'],'scenario':scenario,'plan':plan})
        return {'ok':True,'charged':False}
