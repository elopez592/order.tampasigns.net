"""Owner-managed branding with draft, publish, history and stale-write protection."""
from __future__ import annotations
import hashlib
import html
import io
import json
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from fastapi import Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, HTMLResponse
from .db import transaction, settings, now, audit
from .security import text, email
from .runtime import getenv
from .images import sanitize

SCHEMA = '''
CREATE TABLE IF NOT EXISTS company_revisions (
 id INTEGER PRIMARY KEY, snapshot TEXT NOT NULL, actor TEXT NOT NULL,
 note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS company_draft (
 id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL DEFAULT 1,
 data TEXT NOT NULL, updated_at TEXT NOT NULL
);
'''
FIELDS = ('shop_name','contact_email','contact_phone','business_address','business_hours','brand_primary','brand_dark','app_short_name','brand_logo','brand_icon')
DEFAULTS = dict(business_address='',business_hours='',brand_primary='#f28a3b',brand_dark='#102426',app_short_name='TS Staff',brand_logo='',brand_icon='')


def enrich_user(app, user):
    user = dict(user)
    owner = str(getenv('PLATFORM_OWNER_EMAIL', getenv('ADMIN_EMAIL', 'owner@example.test'))).lower()
    user['platform_owner'] = bool(getattr(app.state, 'platform_enabled', False) and user['role']=='admin' and user['email'].lower()==owner)
    return user


def check_seats(app, conn):
    limit = getattr(app.state, 'seat_limit', None)
    if limit and conn.execute('SELECT count(*) FROM users WHERE active=1').fetchone()[0] >= limit:
        raise HTTPException(403, 'This company has reached its staff seat limit. Contact the platform owner.')


def record_revision(conn, shop, who, note):
    conn.execute('INSERT INTO company_revisions(snapshot,actor,note,created_at) VALUES(?,?,?,?)', (json.dumps(shop),who,note,now()))


def validate(data):
    if not isinstance(data, dict):
        raise HTTPException(422,'Enter company settings as an object.')
    result={}
    for key in FIELDS:
        value=data.get(key,DEFAULTS.get(key,''))
        result[key]=text(value,key,1000 if key=='business_hours' else 500 if key=='business_address' else 120, key=='shop_name')
    result['contact_email']=email(result['contact_email']) if result['contact_email'] else ''
    result['app_short_name']=text(result['app_short_name'],'App short name',12,True)
    for key in ('brand_primary','brand_dark'):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',result[key]):
            raise HTTPException(422,'Brand colors must use six-digit hex colors.')
    for key in ('brand_logo','brand_icon'):
        if result[key] and not re.fullmatch(r'[a-f0-9]{64}\.png',result[key]):
            raise HTTPException(422,'Select an uploaded brand image.')
    return result


def install(app, directory, require_admin, platform=True):
    db=app.state.database
    app.state.platform_enabled=platform
    brand=directory/'brand';brand.mkdir(exist_ok=True);brand.chmod(0o700)
    with transaction(db,True) as conn:
        conn.executescript(SCHEMA)
        if not conn.execute('SELECT 1 FROM company_revisions').fetchone():
            record_revision(conn,settings(conn),'System','Initial settings')
        conn.execute('INSERT OR IGNORE INTO company_draft VALUES(1,1,?,?)',(json.dumps({k:(DEFAULTS|settings(conn)).get(k,'') for k in FIELDS}),now()))

    @app.get('/api/admin/company')
    def company(user=Depends(require_admin)):
        with transaction(db) as conn:
            draft=dict(conn.execute('SELECT * FROM company_draft WHERE id=1').fetchone())
            draft['data']=json.loads(draft['data'])
            return {'published':{k:(DEFAULTS|settings(conn)).get(k,'') for k in FIELDS},'draft':draft,
                    'history':[dict(r) for r in conn.execute('SELECT id,actor,note,created_at FROM company_revisions ORDER BY id DESC LIMIT 50')],
                    'seat_limit':getattr(app.state,'seat_limit',None)}

    @app.put('/api/admin/company/draft')
    def draft(payload:dict=Body(...),user=Depends(require_admin)):
        data=validate(payload.get('data'))
        with transaction(db,True) as conn:
            row=conn.execute('SELECT version FROM company_draft WHERE id=1').fetchone()
            if type(payload.get('version')) is not int or payload['version']!=row['version']:
                raise HTTPException(409,'Another owner changed the draft. Reload before saving.')
            for key in ('brand_logo','brand_icon'):
                if data[key] and not (brand/data[key]).is_file():
                    raise HTTPException(422,'Brand image not found in this company.')
            conn.execute('UPDATE company_draft SET version=version+1,data=?,updated_at=? WHERE id=1',(json.dumps(data),now()))
            audit(conn,None,user['email'],'company.draft_saved',{})
        return {'ok':True,'version':payload['version']+1}

    @app.post('/api/admin/company/publish')
    def publish(payload:dict=Body(...),user=Depends(require_admin)):
        with transaction(db,True) as conn:
            row=conn.execute('SELECT * FROM company_draft WHERE id=1').fetchone()
            if type(payload.get('version')) is not int or payload['version']!=row['version']:
                raise HTTPException(409,'Draft changed. Reload before publishing.')
            data=validate(json.loads(row['data']))
            shop=settings(conn)|data|{'brand_custom':True}
            record_revision(conn,shop,user['email'],'Company branding published')
            conn.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(shop),))
            conn.execute('UPDATE company_draft SET version=version+1,updated_at=? WHERE id=1',(now(),))
            audit(conn,None,user['email'],'company.published',data)
        return {'ok':True}

    @app.post('/api/admin/company/restore/{revision_id}')
    def restore(revision_id:int,payload:dict=Body(...),user=Depends(require_admin)):
        # Restore branding into a draft; prices, checkout and existing order snapshots stay intact.
        with transaction(db,True) as conn:
            row=conn.execute('SELECT snapshot FROM company_revisions WHERE id=?',(revision_id,)).fetchone()
            if not row: raise HTTPException(404,'Revision not found.')
            version=conn.execute('SELECT version FROM company_draft WHERE id=1').fetchone()[0]
            if payload.get('version')!=version: raise HTTPException(409,'Draft changed. Reload before restoring.')
            snapshot=DEFAULTS|json.loads(row['snapshot'])
            conn.execute('UPDATE company_draft SET version=version+1,data=?,updated_at=? WHERE id=1',(json.dumps({k:snapshot.get(k,'') for k in FIELDS}),now()))
            audit(conn,None,user['email'],'company.draft_restored',{'revision_id':revision_id})
        return {'ok':True}

    @app.post('/api/admin/company/image')
    async def image(file:UploadFile=File(...),user=Depends(require_admin)):
        raw=await file.read(5*1024*1024+1)
        if len(raw)>5*1024*1024: raise HTTPException(413,'Brand images must be under 5 MB.')
        clean,_,mime,_=sanitize(raw,file.filename or '')
        if mime!='image/png': raise HTTPException(422,'Upload a PNG or JPEG brand image.')
        name=hashlib.sha256(clean).hexdigest()+'.png'
        (brand/name).write_bytes(clean);(brand/name).chmod(0o600)
        return {'image':name,'url':'/brand/images/'+name}

    @app.get('/brand/images/{name}')
    def brand_image(name:str):
        if not re.fullmatch(r'[a-f0-9]{64}\.png',name) or not (brand/name).is_file(): raise HTTPException(404,'Image not found.')
        return Response((brand/name).read_bytes(),media_type='image/png',headers={'Cache-Control':'public,max-age=31536000,immutable'})

    @app.get('/api/brand')
    def public_brand():
        with transaction(db) as conn:
            shop=DEFAULTS|settings(conn)
        return {k:shop.get(k,'') for k in FIELDS}|{'custom':bool(shop.get('brand_custom'))}

    @app.get('/brand/theme.css')
    def theme():
        with transaction(db) as conn: shop=DEFAULTS|settings(conn)
        primary=shop['brand_primary'];dark=shop['brand_dark']
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',primary+'' ) or not re.fullmatch(r'#[0-9a-fA-F]{6}',dark): raise HTTPException(422,'Invalid colors.')
        return Response(f':root{{--teal:{primary};--accent:{primary};--brand-orange:{primary};--ink:{dark}}}.btn.primary{{background:{primary}}}.sidebar,.login-art{{background:{dark}}}' if shop.get('brand_custom') else '',media_type='text/css')

    @app.get('/staff/manifest.webmanifest')
    def manifest():
        with transaction(db) as conn: shop=DEFAULTS|settings(conn)
        return Response(json.dumps({'id':'/staff/app','name':shop['shop_name']+' Staff','short_name':shop['app_short_name'],'start_url':'/staff/app','scope':'/staff/','display':'standalone','background_color':'#f0f5f4','theme_color':shop['brand_dark'],'icons':[{'src':'/brand/app-icon.png','sizes':'180x180','type':'image/png','purpose':'any'}]}),media_type='application/manifest+json')

    @app.get('/brand/app-icon.png')
    def icon():
        with transaction(db) as conn: shop=DEFAULTS|settings(conn)
        if shop['brand_icon'] and (brand/shop['brand_icon']).is_file():
            image=Image.open(brand/shop['brand_icon']).convert('RGBA');image.thumbnail((180,180))
            canvas=Image.new('RGBA',(180,180),shop['brand_dark']);canvas.alpha_composite(image,((180-image.width)//2,(180-image.height)//2))
        elif not shop.get('brand_custom') and not shop.get('brand_icon'):
            import base64
            from .staff_icon_data import ICON_PNG_B64
            return Response(base64.b64decode(ICON_PNG_B64),media_type='image/png')
        else:
            canvas=Image.new('RGB',(180,180),shop['brand_dark']);draw=ImageDraw.Draw(canvas)
            letters=''.join(x[0] for x in shop['shop_name'].split()[:2]).upper()
            draw.text((90,90),letters,font=ImageFont.load_default(size=65),fill='white',anchor='mm')
        out=io.BytesIO();canvas.save(out,'PNG');return Response(out.getvalue(),media_type='image/png')

    app.state.company_icon=icon

    # Transform only HTML responses. No external branding scripts or inline JavaScript.
    @app.middleware('http')
    async def branding(request:Request,call_next):
        from .runtime import configuration
        import os
        with transaction(db) as conn: current=DEFAULTS|settings(conn)
        config=configuration.get()
        context=configuration.set((dict(os.environ) if config is None else dict(config))|{'SHOP_NAME':current['shop_name'],'SHOP_PHONE':current['contact_phone'],'BRAND_PRIMARY':current['brand_primary'],'BRAND_DARK':current['brand_dark']})
        try:
            response=await call_next(request)
        finally:
            configuration.reset(context)
        if 'text/html' not in response.headers.get('content-type',''): return response
        body=b''.join([part async for part in response.body_iterator]).decode('utf-8')
        with transaction(db) as conn: shop=DEFAULTS|settings(conn)
        if shop.get('brand_custom') or shop['brand_logo'] or shop['shop_name']!='Tampa Signs and Stickers':
            logo='/brand/images/'+shop['brand_logo'] if shop['brand_logo'] else '/brand/app-icon.png'
            body=re.sub(r'/static/brand/tampa-(?:black|white)\.png',logo,body)
            body=body.replace('Tampa Signs and Stickers',html.escape(shop['shop_name'])).replace('Tampa Signs Staff',html.escape(shop['shop_name']+' Staff')).replace('(813) 749-4500',html.escape(shop['contact_phone']))
        body=body.replace('/static/employee.webmanifest?v=20261001-3','/staff/manifest.webmanifest').replace('/static/employee.webmanifest','/staff/manifest.webmanifest')
        body=body.replace('/staff/apple-touch-icon-20261001.png','/brand/app-icon.png')
        body=body.replace('</head>','<link rel="stylesheet" href="/brand/theme.css"><script src="/static/company-brand.js?v=1" defer></script></head>')
        headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding')}
        return HTMLResponse(body,status_code=response.status_code,headers=headers)

    from .access import install as install_access
    install_access(app,require_admin)

    if platform:
        from .platform import install as install_platform
        install_platform(app,directory,require_admin)
