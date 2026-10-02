"""Platform registry and host-based isolated workspaces on a single deployment.

Each company has a private SQLite database, uploads, credentials, browser origin
and host-only cookies. Unknown hosts never fall through to the root company.
"""
from __future__ import annotations
import asyncio
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from .db import transaction, settings, audit, now
from .security import text, email, digest
from .runtime import configuration, getenv

SCHEMA='''CREATE TABLE IF NOT EXISTS platform_companies (
 slug TEXT PRIMARY KEY, name TEXT NOT NULL, owner_email TEXT NOT NULL,
 hostname TEXT UNIQUE, status TEXT NOT NULL DEFAULT 'trial', seats INTEGER NOT NULL DEFAULT 5,
 monthly_cents INTEGER NOT NULL DEFAULT 19900, setup_cents INTEGER NOT NULL DEFAULT 75000,
 trial_ends TEXT NOT NULL DEFAULT '', billing_note TEXT NOT NULL DEFAULT '',
 revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS platform_support_grants (
 token_hash TEXT PRIMARY KEY, slug TEXT NOT NULL, hostname TEXT NOT NULL,
 root_session TEXT NOT NULL, operator_email TEXT NOT NULL, expires_at REAL NOT NULL
);'''
STATUSES={'trial','active','past_due','suspended','closed'}
CONNECTIONS={'STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET','RESEND_API_KEY','EMAIL_FROM','EMAIL_REPLY_TO','CANVA_CLIENT_ID','CANVA_CLIENT_SECRET','CANVA_REDIRECT_URI','REMINDER_CRON_SECRET'}


def company_config(directory, row):
    values={'APP_ENV':os.getenv('APP_ENV','development'),'PUBLIC_URL':'https://'+(row['hostname'] or row['slug']+'.example.invalid'),
            'ALLOWED_HOSTS':row['hostname'] or row['slug']+'.example.invalid','ADMIN_EMAIL':row['owner_email'],'DEMO_SEED':'0'}
    path=directory/'companies'/row['slug']/'connections.json'
    if path.exists(): values.update({k:v for k,v in json.loads(path.read_text()).items() if k in CONNECTIONS})
    return values


def make_company(directory,row,root=None):
    from .main import create_app
    existing=(directory/'companies'/row['slug']/'signshop.sqlite3').exists()
    token=configuration.set(company_config(directory,row))
    try:
        child=create_app(directory/'companies'/row['slug'],demo=False,platform=False)
        if existing:
            from .company_setup import apply_setup
            apply_setup(child,row)
        child.state.seat_limit=row['seats']
        if root is not None:
            child.state.support_root=root
            child.state.support_slug=row['slug']
            child.state.support_hostname=row['hostname']
        return child
    finally: configuration.reset(token)


def clean_host(value):
    value=str(value or '').strip().lower().rstrip('.')
    if not value: return None
    if len(value)>253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',value):
        raise HTTPException(422,'Enter a hostname, without https:// or a path.')
    return value


def install(app,directory,require_admin):
    db=app.state.database
    app.state.company_apps={}
    with transaction(db,True) as conn: conn.executescript(SCHEMA)
    def owner(request:Request,user=Depends(require_admin)):
        if not user.get('platform_owner'): raise HTTPException(403,'Platform owner access required.')
        return user
    from .subscriptions import install_platform as install_billing, accessible
    install_billing(app,owner)
    reserved={urlsplit(app.state.public_url).hostname,'orders.tampasigns.net','ordertampasignsnet-production.up.railway.app'}
    reserved.update(x.strip() for x in str(getenv('ALLOWED_HOSTS','')).split(','))

    def validate_support(conn, session_hash, address, slug, hostname):
        expected=str(os.getenv('PLATFORM_OWNER_EMAIL',os.getenv('ADMIN_EMAIL','owner@example.test'))).lower()
        operator=conn.execute('SELECT u.email,u.role,u.active FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?',(session_hash,time.time())).fetchone()
        company=conn.execute('SELECT * FROM platform_companies WHERE slug=?',(slug,)).fetchone()
        if not operator or not company: return False
        from datetime import date
        return bool(operator['active'] and operator['role']=='admin' and operator['email'].lower()==expected==address.lower()
                    and company['hostname']==hostname and accessible(dict(company)))
    app.state.validate_support=validate_support

    @app.post('/api/platform/companies/{slug}/support')
    def support(slug:str,request:Request,user=Depends(owner)):
        with transaction(db,True) as conn:
            row=conn.execute('SELECT * FROM platform_companies WHERE slug=?',(slug,)).fetchone()
            if not row: raise HTTPException(404,'Company not found.')
            if not row['hostname']: raise HTTPException(422,'Connect this company’s domain in hosting first, then save it here. Each company needs its own secure workspace address.')
            if not validate_support(conn,request.state.session['token_hash'],user['email'],slug,row['hostname']):
                raise HTTPException(403,'This company is paused or its trial has ended. Update its access status before managing it.')
            token=secrets.token_urlsafe(32)
            conn.execute('DELETE FROM platform_support_grants WHERE expires_at<?',(time.time(),))
            conn.execute('INSERT INTO platform_support_grants VALUES(?,?,?,?,?,?)',(digest(token),slug,row['hostname'],request.state.session['token_hash'],user['email'],time.time()+60))
            audit(conn,None,user['email'],'platform.support_issued',{'slug':slug})
        return {'url':'https://'+row['hostname']+'/staff#support='+token}

    @app.get('/platform',response_class=HTMLResponse)
    def page(): return HTMLResponse((Path(__file__).with_name('static')/'platform.html').read_text())

    @app.get('/api/platform/companies')
    def list_companies(user=Depends(owner)):
        with transaction(db) as conn: rows=[dict(r) for r in conn.execute('SELECT * FROM platform_companies ORDER BY created_at DESC')]
        for row in rows:
            child_db=directory/'companies'/row['slug']/'signshop.sqlite3'
            with transaction(child_db) as conn:
                row['usage']={'staff':conn.execute('SELECT count(*) FROM users WHERE active=1').fetchone()[0],'jobs':conn.execute('SELECT count(*) FROM jobs').fetchone()[0]}
            row['url']='https://'+row['hostname'] if row['hostname'] else None
            cfg=company_config(directory,row)
            row['connections']={key:bool(cfg.get(key)) for key in CONNECTIONS}
        return {'companies':rows,'billing_mode':'subscriptions','billing_message':'Manage plans and billing below. Tampa is included; free pilot companies are never charged. Company order-payment connections remain separate.'}

    @app.post('/api/platform/companies')
    def create(payload:dict=Body(...),user=Depends(owner)):
        slug=str(payload.get('slug','')).lower().strip()
        if not re.fullmatch(r'[a-z][a-z0-9-]{2,39}',slug): raise HTTPException(422,'Use a 3–40 character company ID with letters, numbers and hyphens.')
        name=text(payload.get('name',''),'Company name',120,True)
        address=email(payload.get('owner_email',''))
        hostname=clean_host(payload.get('hostname'))
        if hostname in reserved: raise HTTPException(422,'That domain belongs to the platform’s existing shop.')
        company_dir=directory/'companies'/slug
        # Serialize provisioning in the root database; never adopt an existing directory.
        with transaction(db,True) as conn:
            if hostname and conn.execute('SELECT 1 FROM platform_companies WHERE hostname=?',(hostname,)).fetchone(): raise HTTPException(409,'Domain is already assigned to another company.')
            if company_dir.exists() or conn.execute('SELECT 1 FROM platform_companies WHERE slug=?',(slug,)).fetchone(): raise HTTPException(409,'Company ID already exists.')
            row={'slug':slug,'name':name,'owner_email':address,'hostname':hostname,'seats':5}
            child=make_company(directory,row,app)
            with transaction(child.state.database,True) as child_conn:
                shop=settings(child_conn)|{'shop_name':name,'contact_email':address,'contact_phone':'','rates_live':False,'checkout_enabled':False,
                     'checkout_pickup_address':'','checkout_tax_reviewed':False,'brand_custom':True,'app_short_name':''.join(x[0] for x in name.split()[:2]).upper()+' Staff'}
                child_conn.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(shop),))
                from .company import FIELDS, DEFAULTS, record_revision
                child_conn.execute('UPDATE company_draft SET data=? WHERE id=1',(json.dumps({k:(DEFAULTS|shop).get(k,'') for k in FIELDS}),))
                child_conn.execute('DELETE FROM company_revisions')
                record_revision(child_conn,shop,user['email'],'Company created from standard catalog')
            conn.execute('INSERT INTO platform_companies(slug,name,owner_email,hostname,created_at,updated_at) VALUES(?,?,?,?,?,?)',(slug,name,address,hostname,now(),now()))
            if slug=='mirakol' and name=='Mirakol Customs' and hostname=='mirakol.tampasigns.net':
                conn.execute("UPDATE platform_companies SET billing_mode='pilot',plan_id='studio',subscription_status='active',monthly_cents=0,setup_cents=0,seats=10 WHERE slug=?",(slug,))
            audit(conn,None,user['email'],'platform.company_created',{'slug':slug})
        app.state.company_apps[slug]=child
        password=next((p for role,e,p in child.state.initial_credentials if role=='Owner'),None)
        child.state.initial_credentials=[]
        return {'slug':slug,'owner_email':address,'temporary_password':password,'message':'Save this password securely. Attach and verify the company domain in hosting before opening its workspace.'}

    @app.patch('/api/platform/companies/{slug}')
    def update(slug:str,payload:dict=Body(...),user=Depends(owner)):
        with transaction(db,True) as conn:
            row=conn.execute('SELECT * FROM platform_companies WHERE slug=?',(slug,)).fetchone()
            if not row: raise HTTPException(404,'Company not found.')
            if payload.get('revision')!=row['revision']: raise HTTPException(409,'Company changed. Reload before saving.')
            value=dict(row)
            for key in ('status','seats','monthly_cents','setup_cents','trial_ends','billing_note','hostname'):
                if key in payload: value[key]=payload[key]
            if value['status'] not in STATUSES: raise HTTPException(422,'Invalid company status.')
            for key,maxval in [('seats',500),('monthly_cents',10000000),('setup_cents',10000000)]:
                if type(value[key]) is not int or value[key]<(1 if key=='seats' else 0) or value[key]>maxval: raise HTTPException(422,'Invalid seat limit or contract price.')
            value['hostname']=clean_host(value['hostname'])
            if value['hostname'] in reserved: raise HTTPException(422,'Domain belongs to the existing shop.')
            value['billing_note']=text(value['billing_note'],'Billing note',2000)
            value['trial_ends']=text(value['trial_ends'],'Trial end',10)
            if value['trial_ends']:
                from datetime import date
                try: date.fromisoformat(value['trial_ends'])
                except ValueError: raise HTTPException(422,'Use YYYY-MM-DD for the trial end.')
            with transaction(directory/'companies'/slug/'signshop.sqlite3') as child_conn:
                if value['seats']<child_conn.execute('SELECT count(*) FROM users WHERE active=1').fetchone()[0]: raise HTTPException(422,'Disable extra staff before reducing the seat limit.')
            conn.execute('UPDATE platform_companies SET hostname=?,status=?,seats=?,monthly_cents=?,setup_cents=?,trial_ends=?,billing_note=?,revision=revision+1,updated_at=? WHERE slug=?',tuple(value[k] for k in ('hostname','status','seats','monthly_cents','setup_cents','trial_ends','billing_note'))+(now(),slug))
            audit(conn,None,user['email'],'platform.company_updated',{'slug':slug,'status':value['status'],'seats':value['seats']})
        app.state.company_apps.pop(slug,None)
        return {'ok':True}

    @app.put('/api/platform/companies/{slug}/connections')
    def connections(slug:str,payload:dict=Body(...),user=Depends(owner)):
        with transaction(db,True) as conn:
            row=conn.execute('SELECT * FROM platform_companies WHERE slug=?',(slug,)).fetchone()
            if not row: raise HTTPException(404,'Company not found.')
            if not isinstance(payload,dict) or set(payload)-CONNECTIONS: raise HTTPException(422,'Unsupported connection fields.')
            path=directory/'companies'/slug/'connections.json'
            saved=json.loads(path.read_text()) if path.exists() else {}
            for key,value in payload.items():
                if not isinstance(value,str) or len(value)>4000 or '\n' in value or '\r' in value: raise HTTPException(422,'Invalid connection value.')
                saved[key]=value.strip()
            if saved.get('STRIPE_SECRET_KEY') and not saved['STRIPE_SECRET_KEY'].startswith(('sk_test_','sk_live_','rk_test_','rk_live_')): raise HTTPException(422,'Invalid payment key.')
            if saved.get('STRIPE_WEBHOOK_SECRET') and not saved['STRIPE_WEBHOOK_SECRET'].startswith('whsec_'): raise HTTPException(422,'Invalid webhook secret.')
            temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(saved));temporary.chmod(0o600);temporary.replace(path)
            audit(conn,None,user['email'],'platform.connections_updated',{'slug':slug,'fields':list(payload)})
        app.state.company_apps.pop(slug,None)
        return {'ok':True}


class CompanyRouter:
    def __init__(self,root):
        self.root=root
        self.directory=root.state.database.parent
        self.lock=asyncio.Lock()
        self.root_hosts={urlsplit(root.state.public_url).hostname,'localhost','127.0.0.1','testserver','orders.tampasigns.net','ordertampasignsnet-production.up.railway.app'}
        self.root_hosts.update(x.strip() for x in os.getenv('ALLOWED_HOSTS','').split(',') if x.strip() and x.strip()!='*')

    async def __call__(self,scope,receive,send):
        if scope['type'] not in ('http','websocket'): return await self.root(scope,receive,send)
        headers=dict(scope.get('headers',[]));host=headers.get(b'host',b'').decode('ascii','ignore').split(':')[0].lower().rstrip('.')
        if host in self.root_hosts: return await self.root(scope,receive,send)
        with transaction(self.root.state.database) as conn:
            record=conn.execute('SELECT * FROM platform_companies WHERE hostname=?',(host,)).fetchone()
        if not record: return await JSONResponse({'detail':'Company domain not registered.'},404)(scope,receive,send)
        row=dict(record)
        from .subscriptions import accessible
        path=scope.get('path','')
        recovery=path in ('/staff/billing','/api/session','/api/auth/login','/api/auth/logout','/api/auth/password','/api/brand') or path.startswith(('/api/company/billing','/static/','/brand/'))
        if not accessible(row) and not recovery:
            if 'text/html' in headers.get(b'accept',b'').decode():
                return await HTMLResponse('<h1>Workspace access is paused</h1><p>Your company data is retained. The owner can review billing or restore pilot access.</p><a href="/staff/billing">Open billing</a>',status_code=403)(scope,receive,send)
            return await JSONResponse({'detail':'Workspace access is paused. Open Billing to restore subscription access.','billing_url':'/staff/billing'},403)(scope,receive,send)
        async with self.lock:
            child=self.root.state.company_apps.get(row['slug'])
            if child is None:
                child=await asyncio.to_thread(make_company,self.directory,row,self.root)
                child.state.initial_credentials=[]
                self.root.state.company_apps[row['slug']]=child
        child.state.seat_limit=row['seats']
        token=configuration.set(company_config(self.directory,row))
        try: return await child(scope,receive,send)
        finally: configuration.reset(token)
