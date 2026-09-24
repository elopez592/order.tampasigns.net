from __future__ import annotations

import hashlib
import hmac
import html
import csv
import io
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .db import initialize, transaction, settings, audit, now
from .security import digest, password_matches, password_hash, text, email, payment_url, rate_limit
from .pricing import calculate, public_quote, validate_config, number, cents
from .domain import (get_job, totals, latest_proof, production_started, gate_reason,
                     serialize_job, create_job, validate_steps, APPROVAL_STATEMENT)
from .seed import bootstrap
from .images import sanitize, save_asset, panel_sheet, MAX_UPLOAD
from .checkout import (StripeGateway, availability, eligible_quote, checkout_policy,
                       start_checkout, process_event, order_for_job)
from .mailer import public_status as email_status, notify_customer, notify_staff, send_test_email
from . import canva
import uuid

COOKIE = 'signshop_session'
STATIC = Path(__file__).with_name('static')


def product_slug(name: str) -> str:
    value = str(name or '').strip().lower()
    if value == 'partial vehicle wraps':
        value = 'vehicle wraps'
    value = value.replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', '-', value).strip('-')


def public_product_name(name: str) -> str:
    value = str(name or '').strip()
    key = value.lower()
    if key == 'partial vehicle wraps':
        return 'Vehicle Wraps'
    if key == 'trailer / food truck wraps':
        return 'Trailer / Food Truck Wraps'
    return value


def require_staff(request: Request):
    if not request.state.user:
        raise HTTPException(401, 'Staff sign-in required.')
    return request.state.user


def require_admin(request: Request):
    user = require_staff(request)
    if user['role'] != 'admin':
        raise HTTPException(403, 'Owner/admin access required.')
    return user


def actor(user):
    return f'{user["name"]} (staff #{user["id"]})'


def create_app(data_dir=None, demo=None) -> FastAPI:
    directory = Path(data_dir or os.getenv('DATA_DIR', './data')).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / 'signshop.sqlite3'
    uploads = directory / 'uploads'
    uploads.mkdir(exist_ok=True)
    for private_dir in (directory, uploads):
        try:
            private_dir.chmod(0o700)
        except OSError:
            pass
    production = os.getenv('APP_ENV', 'development') == 'production'
    public_url = os.getenv('PUBLIC_URL', 'http://localhost:8000').rstrip('/')
    if production and not public_url.startswith('https://'):
        raise RuntimeError('Production requires an HTTPS PUBLIC_URL behind a TLS-terminating reverse proxy.')
    initialize(database)
    try:
        database.chmod(0o600)
    except OSError:
        pass
    credentials = bootstrap(database, demo=demo if demo is not None else os.getenv('DEMO_SEED', '0') == '1')
    from .storefront import upgrade_catalog
    upgrade_catalog(database)
    app = FastAPI(title='Tampa Signs and Stickers', version='0.2.0', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.database = database
    app.state.uploads = uploads
    app.state.initial_credentials = credentials
    app.state.public_url = public_url

    def seo_html(title: str, description: str, canonical: str, product=None) -> str:
        source = (STATIC / 'index.html').read_text()
        safe_title = html.escape(title, quote=True)
        safe_description = html.escape(description, quote=True)
        safe_canonical = html.escape(canonical, quote=True)
        schema = {
            '@context': 'https://schema.org',
            '@type': 'Product' if product else 'WebSite',
            'name': public_product_name(product['name']) if product else 'Tampa Signs and Stickers Online Ordering',
            'description': description,
            'url': canonical,
        }
        if product:
            schema['brand'] = {'@type': 'Brand', 'name': 'Tampa Signs and Stickers'}
            schema['category'] = product['category']
        else:
            schema['publisher'] = {'@type': 'Organization', 'name': 'Tampa Signs and Stickers'}
        schema_json = json.dumps(schema, ensure_ascii=False).replace('</', '<\\/')
        metadata = (f'<meta name="description" content="{safe_description}">\n'
                    f'  <meta name="robots" content="index,follow,max-image-preview:large">\n'
                    f'  <link rel="canonical" href="{safe_canonical}">\n'
                    f'  <meta property="og:type" content="{("product" if product else "website")}">\n'
                    f'  <meta property="og:title" content="{safe_title}">\n'
                    f'  <meta property="og:description" content="{safe_description}">\n'
                    f'  <meta property="og:url" content="{safe_canonical}">\n'
                    f'  <meta name="twitter:card" content="summary">\n'
                    f'  <script type="application/ld+json">{schema_json}</script>')
        source = re.sub(r'<title>.*?</title>', f'<title>{safe_title}</title>\n  {metadata}', source, count=1, flags=re.S)
        if product:
            name = html.escape(public_product_name(product['name']))
            category = html.escape(product['category'])
            body_description = html.escape(description)
            fallback = f'<main class="initial-loading seo-product"><p>{category}</p><h1>{name}</h1><p>{body_description}</p></main>'
            source = source.replace('<div id="app"><div class="initial-loading"><img class="loading-logo" src="/static/brand/tampa-black.png" alt="Tampa Signs and Stickers"><p>Opening Tampa Signs and Stickers...</p></div></div>', f'<div id="app">{fallback}</div>')
        return source
    app.state.gateway = StripeGateway()
    allowed_hosts = [h.strip() for h in os.getenv('ALLOWED_HOSTS', '').split(',') if h.strip()]
    if not allowed_hosts:
        allowed_hosts = [urlsplit(public_url).hostname or 'localhost', 'localhost', '127.0.0.1', 'testserver']
    if production and '*' in allowed_hosts:
        raise RuntimeError('Do not use a wildcard ALLOWED_HOSTS in production.')
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    def throttle(request, scope, limit, seconds=300):
        ip = request.client.host if request.client else 'unknown'
        with transaction(database, True) as conn:
            permitted = rate_limit(conn, f'{scope}:{digest(ip)}', limit, seconds)
        if not permitted:
            raise HTTPException(429, 'Too many requests. Please wait and try again.')

    def new_session(conn, user_id=None, portal_job_id=None, generation=None):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        conn.execute('DELETE FROM sessions WHERE expires_at<?', (time.time(),))
        conn.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)',
                     (digest(token), csrf, user_id, portal_job_id, generation, time.time() + 8 * 3600))
        return token, csrf

    def session_response(data, token):
        response = JSONResponse(data)
        response.set_cookie(COOKIE, token, httponly=True, secure=production, samesite='lax', max_age=8 * 3600, path='/')
        return response

    def portal_job(conn, request):
        sess = request.state.session
        if not sess or not sess['portal_job_id']:
            raise HTTPException(401, 'Open your private job link to access the customer portal.')
        job = get_job(conn, sess['portal_job_id'])
        if (not job['portal_hash'] or job['portal_hash'] != sess['portal_generation']
                or (job['portal_expires'] or 0) < time.time()):
            raise HTTPException(401, 'This job link expired or was replaced. Ask the shop for a new link.')
        return job

    def access_job(conn, request, job_id):
        if request.state.user:
            return get_job(conn, job_id), actor(request.state.user)
        job = portal_job(conn, request)
        if job['id'] != job_id:
            raise HTTPException(404, 'Job not found.')
        return job, 'Customer via private job link'

    def issue_portal(conn, job_id):
        token = secrets.token_urlsafe(32)
        conn.execute('UPDATE jobs SET portal_hash=?,portal_expires=? WHERE id=?',
                     (digest(token), time.time() + 14 * 86400, job_id))
        return f'{public_url}/portal#token={token}'

    def issue_email_portal(conn, job_id, days=14):
        job = get_job(conn, job_id)
        if not job['portal_hash'] or (job['portal_expires'] or 0) < time.time():
            master = secrets.token_urlsafe(32)
            conn.execute('UPDATE jobs SET portal_hash=?,portal_expires=? WHERE id=?',
                         (digest(master), time.time() + 30 * 86400, job_id))
        token = secrets.token_urlsafe(32)
        conn.execute('DELETE FROM portal_links WHERE expires_at<?', (time.time(),))
        conn.execute('INSERT INTO portal_links(token_hash,job_id,expires_at,created_at) VALUES(?,?,?,?)',
                     (digest(token), job_id, time.time() + days * 86400, now()))
        return f'{public_url}/portal#token={token}'

    def wholesale_username(value):
        value = text(value, 'Wholesale username', 60, True).lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{2,59}', value):
            raise HTTPException(422, 'Wholesale usernames must be 3-60 characters using letters, numbers, dots, hyphens or underscores.')
        return value

    def wholesale_client(conn, token_value):
        if not token_value:
            return None
        if not isinstance(token_value, str) or len(token_value) > 200:
            raise HTTPException(422, 'Wholesale pricing session is invalid.')
        conn.execute('DELETE FROM wholesale_sessions WHERE expires_at<?', (time.time(),))
        return conn.execute(
            '''SELECT c.* FROM wholesale_sessions s
               JOIN wholesale_clients c ON c.id=s.client_id
               WHERE s.token_hash=? AND s.expires_at>? AND c.active=1''',
            (digest(token_value), time.time())
        ).fetchone()

    def proof_specs(job):
        return [{k: item[k] for k in ('name','description','width','height','quantity')} for item in json.loads(job['quote_snapshot'])['lines']]

    def add_proof(conn, job, asset_id, label, note, who):
        last = latest_proof(conn, job['id'])
        version = last['version'] + 1 if last else 1
        pid = conn.execute('INSERT INTO proofs(job_id,version,asset_id,label,note,specs,created_at) VALUES(?,?,?,?,?,?,?)',
                           (job['id'], version, asset_id, label, note, json.dumps(proof_specs(job)), now())).lastrowid
        audit(conn, job['id'], who, 'proof.published', {'version': version, 'label': label}, True)
        return pid

    @app.middleware('http')
    async def security_boundary(request: Request, call_next):
        length = request.headers.get('content-length')
        if length:
            try:
                if int(length) > 55 * 1024 * 1024 or int(length) < 0:
                    return JSONResponse({'detail': 'Request exceeds the 55 MB limit.'}, status_code=413)
            except ValueError:
                return JSONResponse({'detail': 'Invalid Content-Length.'}, status_code=400)
        if request.method in ('POST', 'PUT', 'PATCH') and length is None:
            return JSONResponse({'detail': 'Content-Length is required.'}, status_code=411)
        request.state.session = None
        request.state.user = None
        token = request.cookies.get(COOKIE, '')
        if token and len(token) <= 200:
            with transaction(database) as conn:
                row = conn.execute('SELECT * FROM sessions WHERE token_hash=? AND expires_at>?', (digest(token), time.time())).fetchone()
                if row:
                    request.state.session = dict(row)
                    if row['user_id']:
                        user = conn.execute('SELECT id,name,email,role FROM users WHERE id=? AND active=1', (row['user_id'],)).fetchone()
                        if user:
                            request.state.user = dict(user)
        if request.url.path.startswith('/api/') and request.url.path != '/api/payments/stripe/webhook' and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            sess = request.state.session
            csrf = request.headers.get('x-csrf-token', '')
            if not sess or not hmac.compare_digest(sess['csrf'], csrf):
                return JSONResponse({'detail': 'Security token missing or expired. Reload and try again.'}, status_code=403)
            origin = request.headers.get('origin')
            allowed_origin = {public_url, str(request.base_url).rstrip('/')}
            if origin and origin not in allowed_origin:
                return JSONResponse({'detail': 'Cross-origin requests are not allowed.'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers.setdefault('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        if production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        if not request.url.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity_error(request, exc):
        return JSONResponse({'detail': 'That record already exists or conflicts with a related record.'}, status_code=409)

    @app.get('/health')
    def health():
        with transaction(database) as conn:
            conn.execute('SELECT 1')
        return {'status': 'ok', 'version': '0.2.0'}

    @app.get('/api/session')
    def get_session(request: Request):
        throttle(request, 'session', 90, 60)
        if request.state.session:
            return {'csrf': request.state.session['csrf'], 'user': request.state.user,
                    'portal_available': bool(request.state.session['portal_job_id'])}
        with transaction(database, True) as conn:
            token, csrf = new_session(conn)
        return session_response({'csrf': csrf, 'user': None, 'portal_available': False}, token)

    @app.get('/api/canva/status')
    def canva_status(request: Request):
        configured = canva.config(public_url)['configured']
        connected = False
        if request.state.session:
            with transaction(database) as conn:
                connected = bool(conn.execute('SELECT 1 FROM canva_tokens WHERE token_hash=?', (request.state.session['token_hash'],)).fetchone())
        return {'configured': configured, 'connected': connected, 'scope': canva.SCOPE}

    @app.post('/api/canva/connect')
    def canva_connect(request: Request, payload: dict = Body(default={})):
        return_path = str(payload.get('return_path') or '/studio')
        with transaction(database, True) as conn:
            authorize_url = canva.begin_oauth(conn, request.state.session['token_hash'], public_url, return_path)
        return {'authorize_url': authorize_url}

    @app.get('/api/canva/callback')
    def canva_callback(request: Request, code: str = '', state: str = '', error: str = ''):
        if error:
            return RedirectResponse('/studio?canva=denied', status_code=303)
        if not code or not state:
            return RedirectResponse('/studio?canva=missing', status_code=303)
        with transaction(database, True) as conn:
            return_path = canva.exchange_code(conn, state, code, public_url)
        glue = '&' if '?' in return_path else '?'
        return RedirectResponse(f'{return_path}{glue}canva=connected', status_code=303)

    @app.post('/api/canva/design')
    def canva_design(request: Request, payload: dict = Body(...)):
        title = text(payload.get('title') or 'Tampa Signs artwork', 'Design title', 180, True)
        width = number(payload.get('width'), 'Width', '0.1', '10000')
        height = number(payload.get('height'), 'Height', '0.1', '10000')
        with transaction(database, True) as conn:
            result = canva.create_design(conn, request.state.session['token_hash'], public_url, title, float(width), float(height))
        if not result.get('edit_url'):
            raise HTTPException(502, 'Canva created the design but did not return an edit link.')
        return result

    @app.post('/api/auth/login')
    def login(request: Request, payload: dict = Body(...)):
        throttle(request, 'login', 12, 900)
        address = str(payload.get('email', '')).strip().lower()
        with transaction(database) as conn:
            user = conn.execute('SELECT * FROM users WHERE email=? AND active=1', (address,)).fetchone()
        if not user or not password_matches(payload.get('password', ''), user['password_hash']):
            # Equivalent KDF work for nonexistent accounts limits timing-based account enumeration.
            if not user:
                password_hash('dummy-' + secrets.token_urlsafe(12))
            raise HTTPException(401, 'Email or password is incorrect.')
        with transaction(database, True) as conn:
            conn.execute('DELETE FROM sessions WHERE token_hash=?', (request.state.session['token_hash'],))
            token, csrf = new_session(conn, user_id=user['id'])
            audit(conn, None, actor(user), 'staff.signed_in', {})
        return session_response({'csrf': csrf, 'user': {k: user[k] for k in ('id','name','email','role')}}, token)

    @app.post('/api/auth/logout')
    def logout(request: Request):
        with transaction(database, True) as conn:
            conn.execute('DELETE FROM sessions WHERE token_hash=?', (request.state.session['token_hash'],))
            token, csrf = new_session(conn)
        return session_response({'csrf': csrf, 'user': None}, token)

    @app.post('/api/auth/password')
    def change_password(request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        throttle(request, 'password', 5, 900)
        with transaction(database, True) as conn:
            stored = conn.execute('SELECT password_hash FROM users WHERE id=?', (user['id'],)).fetchone()[0]
            if not password_matches(payload.get('current_password', ''), stored):
                raise HTTPException(403, 'Current password is incorrect.')
            conn.execute('UPDATE users SET password_hash=? WHERE id=?', (password_hash(payload.get('new_password', '')), user['id']))
            conn.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
            token, csrf = new_session(conn, user_id=user['id'])
            audit(conn, None, actor(user), 'staff.password_changed', {})
        return session_response({'csrf': csrf, 'user': user}, token)

    @app.get('/api/catalog')
    def catalog():
        with transaction(database) as conn:
            shop = settings(conn)
            products = []
            for row in conn.execute("""SELECT * FROM products WHERE public=1 AND active=1 ORDER BY
                CASE WHEN name='Die-cut stickers' THEN 1 WHEN name='Transfer stickers' THEN 2 ELSE 100+id END, id"""):
                cfg = json.loads(row['config'])
                keys = ('finished_apparel','shirt_colors','shirt_sizes','apparel_kind','apparel_unit_price','digitizing_fee','quote_only','unit','description','min_quantity','max_quantity','max_width','max_height',
                        'default_width','default_height','min_width','min_height','instant','supports_installation',
                        'supports_multiple_dimensions','self_approve_artwork','lamination_options','material_options',
                        'storefront_categories','size_options','placement_options','quantity_presets','coverage_options','vehicle_type_options','quantity_only_note','max_short_axis','max_long_axis','usdot_customizer','contour_customizer','quantity_only','vehicle_details_required','tint_package_selector','artwork_upload_disabled')
                defaults = {'supports_installation': False, 'supports_multiple_dimensions': False,
                            'self_approve_artwork': False, 'lamination_options': [], 'material_options': [],
                            'storefront_categories': [], 'size_options': [], 'placement_options': [], 'quantity_presets': [], 'coverage_options': [], 'vehicle_type_options': [], 'quantity_only_note': '', 'max_short_axis': '10000',
                            'max_long_axis': '10000', 'usdot_customizer': False, 'contour_customizer': False, 'quantity_only': False,
                            'vehicle_details_required': False, 'tint_package_selector': False,
                            'artwork_upload_disabled': False}
                products.append({k: row[k] for k in ('id','name','category','version')} | {
                    'config': {k: cfg.get(k, defaults.get(k)) for k in keys}})
            return {'products': products, 'shop': {k: shop[k] for k in ('shop_name','contact_email','contact_phone','rates_live','quote_note')},
                    'checkout': availability(shop, app.state.gateway), 'notifications': email_status()}

    @app.post('/api/wholesale/activate')
    def activate_wholesale(request: Request, payload: dict = Body(...)):
        throttle(request, 'wholesale_activate', 10, 900)
        username = wholesale_username(payload.get('username', ''))
        password = payload.get('password', '')
        with transaction(database, True) as conn:
            client = conn.execute('SELECT * FROM wholesale_clients WHERE username=? AND active=1', (username,)).fetchone()
            if not client or not password_matches(password, client['code_hash']):
                if not client:
                    password_hash('dummy-' + secrets.token_urlsafe(12))
                raise HTTPException(401, 'Wholesale username or password is incorrect.')
            token = secrets.token_urlsafe(32)
            conn.execute('DELETE FROM wholesale_sessions WHERE expires_at<?', (time.time(),))
            conn.execute('INSERT INTO wholesale_sessions(token_hash,client_id,expires_at,created_at) VALUES(?,?,?,?)',
                         (digest(token), client['id'], time.time()+30*86400, now()))
        return {'token': token, 'client': {'name': client['name'], 'email': client['email'], 'username': client['username']}}

    @app.post('/api/calculate')
    def customer_calculate(request: Request, payload: dict = Body(...)):
        throttle(request, 'calculate', 180, 60)
        with transaction(database, True) as conn:
            wholesale = wholesale_client(conn, payload.get('wholesale_token', ''))
            quote = calculate(conn, payload.get('items', []), wholesale_client_id=wholesale['id'] if wholesale else None)
        result = public_quote(quote)
        result['fingerprint'] = digest(json.dumps(result, sort_keys=True))
        return result

    @app.post('/api/orders')
    def instant_order(request: Request, payload: dict = Body(...)):
        throttle(request, 'orders', 20, 3600)
        if payload.get('website') or payload.get('confirm') is not True:
            raise HTTPException(422, 'Confirm your product, size, quantity and checkout terms.')
        request_id = str(payload.get('request_id',''))
        try:
            uuid.UUID(request_id)
        except (ValueError, TypeError):
            raise HTTPException(422, 'A checkout request identifier is required.')
        request_hash = digest(json.dumps(payload, sort_keys=True))
        with transaction(database, True) as conn:
            shop = settings(conn)
            delivery = payload.get('fulfillment','pickup')
            if delivery not in ('pickup','shipping') or not availability(shop, app.state.gateway).get(delivery):
                raise HTTPException(503, 'Online checkout is not active for this delivery method. Please request a quote.')
            previous = conn.execute('SELECT * FROM checkout_orders WHERE request_id=?',(request_id,)).fetchone()
            if previous:
                sess = request.state.session
                if previous['request_hash'] != request_hash or not (previous['owner_session']==sess['token_hash'] or sess['portal_job_id']==previous['job_id']):
                    raise HTTPException(409, 'This checkout request is already in use.')
                job_id = previous['job_id']
            else:
                wholesale = wholesale_client(conn, payload.get('wholesale_token', ''))
                if wholesale and email(payload.get('customer_email', '')) != wholesale['email']:
                    raise HTTPException(422, 'Use the approved wholesale account email for this pricing.')
                quote = eligible_quote(conn, payload.get('items',[]), wholesale_client_id=wholesale['id'] if wholesale else None)
                expected = digest(json.dumps(public_quote(quote), sort_keys=True))
                if payload.get('fingerprint') != expected:
                    raise HTTPException(409, 'Pricing has changed. Recalculate before ordering.')
                policy = checkout_policy(shop, delivery)
                order_payload = dict(payload)
                if wholesale:
                    order_payload['_wholesale_client_id'] = wholesale['id']
                job_id = create_job(conn,order_payload,source='checkout',actor='Online customer')
                from .customers import link_order
                link_order(conn, request, job_id)
                tax = 0
                if delivery=='pickup':
                    from decimal import Decimal
                    from .pricing import cent_round
                    tax = cent_round(Decimal(quote['subtotal_cents'])*Decimal(policy['tax_percent'])/100)
                conn.execute("UPDATE jobs SET published=1,accepted_version=quote_version,accepted_name=customer_name,accepted_at=?,deposit_percent='100',shipping_cents=?,tax_cents=? WHERE id=?",(now(),policy['shipping_cents'],tax,job_id))
                conn.execute('INSERT INTO checkout_orders VALUES(?,?,?,?,?,?,?,?)',
                    (uuid.uuid4().hex,job_id,request_id,request_hash,request.state.session['token_hash'],delivery,json.dumps(policy),now()))
                audit(conn,job_id,'Online customer','checkout.order_submitted',{'terms':policy['terms'],'fulfillment':delivery},False)
            link = issue_portal(conn,job_id)
            generation = conn.execute('SELECT portal_hash FROM jobs WHERE id=?',(job_id,)).fetchone()[0]
            token,csrf = new_session(conn,portal_job_id=job_id,generation=generation)
        notify_customer(database, job_id, 'order_received', f'JOB-{job_id:04d} received | Tampa Signs and Stickers',
                        'Order received', 'We have your order. We will keep you updated when a proof is ready, production begins, and your order is finished.', link)
        notify_staff(database, job_id, 'order_received', f'New order JOB-{job_id:04d}',
                     'New order received', 'A new customer order has been received and is ready for review.', public_url)
        return session_response({'job_id':job_id,'number':f'JOB-{job_id:04d}','portal_url':link,'csrf':csrf},token)

    @app.post('/api/portal/checkout')
    def begin_checkout(request: Request):
        throttle(request,'checkout',20,3600)
        with transaction(database) as conn:
            job_id = portal_job(conn,request)['id']
        return start_checkout(database,job_id,app.state.gateway,public_url)

    @app.post('/api/payments/stripe/webhook')
    async def stripe_webhook(request: Request):
        # Stripe cannot provide browser CSRF tokens; HMAC verification is mandatory here.
        raw = await request.body()
        if len(raw)>1024*1024:
            raise HTTPException(413,'Webhook body too large.')
        event = app.state.gateway.verify_event(raw,request.headers.get('stripe-signature',''))
        with transaction(database,True) as conn:
            return process_event(conn,event,app.state.gateway)

    @app.post('/api/requests')
    def submit_request(request: Request, payload: dict = Body(...)):
        throttle(request, 'request', 12, 3600)
        if payload.get('website'):
            raise HTTPException(422, 'Request could not be submitted.')
        with transaction(database, True) as conn:
            wholesale = wholesale_client(conn, payload.get('wholesale_token', ''))
            if wholesale and email(payload.get('customer_email', '')) != wholesale['email']:
                raise HTTPException(422, 'Use the approved wholesale account email for this pricing.')
            wholesale_id = wholesale['id'] if wholesale else None
            computed = public_quote(calculate(conn, payload.get('items', []), wholesale_client_id=wholesale_id))
            expected = digest(json.dumps(computed, sort_keys=True))
            if payload.get('fingerprint') != expected:
                raise HTTPException(409, 'Pricing has changed. Recalculate your estimate before submitting.')
            request_payload = dict(payload)
            if wholesale:
                request_payload['_wholesale_client_id'] = wholesale['id']
            job_id = create_job(conn, request_payload, source='customer', actor='Public estimate request')
            from .customers import link_order
            link_order(conn, request, job_id)
            link = issue_portal(conn, job_id)
        notify_customer(database, job_id, 'order_received', f'{f"JOB-{job_id:04d}"} received | Tampa Signs and Stickers',
                        'Project received', 'We received your project. Our team will review the details and keep you updated as it moves forward.', link)
        notify_staff(database, job_id, 'order_received', f'New project JOB-{job_id:04d}',
                     'New project received', 'A new customer project has been submitted and is ready for review.', public_url)
        return {'job_id': job_id, 'number': f'JOB-{job_id:04d}', 'portal_url': link,
                'message': 'Order received. The shop will review any custom specifications, tax and delivery before production.'}

    @app.post('/api/custom-requests')
    def custom_request(request: Request, payload: dict = Body(...)):
        throttle(request, 'custom_request', 12, 3600)
        if payload.get('website'):
            raise HTTPException(422, 'Request could not be submitted.')
        project_type = text(payload.get('project_type', ''), 'Project type', 120, True)
        customer_name = text(payload.get('customer_name', ''), 'Customer name', 120, True)
        customer_email = email(payload.get('customer_email', ''))
        phone = text(payload.get('phone', ''), 'Phone', 60)
        notes = text(payload.get('notes', ''), 'Project details', 5000, True)
        quantity = text(payload.get('quantity', ''), 'Quantity / scope', 120)
        vehicle_count = text(payload.get('vehicle_count', ''), 'Vehicle count', 120)
        dimensions = payload.get('dimensions', [])
        if not isinstance(dimensions, list) or len(dimensions) > 20:
            raise HTTPException(422, 'Use no more than 20 optional dimension rows.')
        checked_dimensions = []
        for i, dim in enumerate(dimensions):
            if not isinstance(dim, dict):
                raise HTTPException(422, 'Invalid dimension row.')
            width = dim.get('width')
            height = dim.get('height')
            if width in ('', None) and height in ('', None):
                continue
            if width in ('', None) or height in ('', None):
                raise HTTPException(422, 'Each dimension row needs both width and height.')
            w = number(width, f'Width {i+1}', '0.1', '10000')
            h = number(height, f'Height {i+1}', '0.1', '10000')
            q = number(dim.get('quantity', 1) or 1, f'Quantity {i+1}', '1', '100000')
            if q != q.to_integral():
                raise HTTPException(422, 'Dimension quantities must be whole numbers.')
            label = text(dim.get('label', ''), f'Dimension label {i+1}', 120)
            checked_dimensions.append({'width': str(w), 'height': str(h), 'quantity': int(q), 'label': label})
        details = notes
        if quantity:
            details += '\nQuantity / scope: ' + quantity
        if vehicle_count:
            details += '\nFleet / vehicle count: ' + vehicle_count
        if checked_dimensions:
            details += '\nDimensions:\n' + '\n'.join(
                f"- {d['label'] + ': ' if d['label'] else ''}{d['width']} x {d['height']} in x {d['quantity']}"
                for d in checked_dimensions
            )
        with transaction(database, True) as conn:
            product = conn.execute("SELECT id FROM products WHERE category='Custom' AND active=1 ORDER BY id LIMIT 1").fetchone()
            if not product:
                raise HTTPException(503, 'Custom quote intake is temporarily unavailable.')
            items = [{'product_id': product['id'], 'description': d['label'] or project_type,
                      'width': d['width'], 'height': d['height'], 'quantity': d['quantity']}
                     for d in checked_dimensions] or [
                        {'product_id': product['id'], 'description': project_type, 'width': 12, 'height': 12, 'quantity': 1}
                     ]
            job_id = create_job(conn, {
                'title': project_type,
                'customer_name': customer_name,
                'customer_email': customer_email,
                'phone': phone,
                'notes': details,
                'items': items
            }, source='custom', actor='Custom quote request')
            link = issue_portal(conn, job_id)
        notify_customer(database, job_id, 'order_received', f'JOB-{job_id:04d} received | Tampa Signs and Stickers',
                        'Custom quote request received', 'We received your custom project request. Our team will review it and follow up with a tailored quote.', link)
        notify_staff(database, job_id, 'order_received', f'New custom quote JOB-{job_id:04d}',
                     'New custom quote request', f'New custom request: {project_type}.', public_url)
        return {'job_id': job_id, 'number': f'JOB-{job_id:04d}', 'portal_url': link}

    @app.post('/api/portal/exchange')
    def portal_exchange(request: Request, payload: dict = Body(...)):
        throttle(request, 'portal', 30, 900)
        token_value = text(payload.get('token', ''), 'Portal token', 200, True)
        with transaction(database, True) as conn:
            token_hash = digest(token_value)
            job = conn.execute('SELECT * FROM jobs WHERE portal_hash=? AND portal_expires>?', (token_hash, time.time())).fetchone()
            if not job:
                link = conn.execute('SELECT job_id FROM portal_links WHERE token_hash=? AND expires_at>?', (token_hash, time.time())).fetchone()
                job = get_job(conn, link['job_id']) if link else None
            if not job:
                raise HTTPException(401, 'This private link is invalid, expired or replaced.')
            # Preserve a staff login only in this same browser for owner previews.
            staff_id = request.state.user['id'] if request.state.user else None
            conn.execute('DELETE FROM sessions WHERE token_hash=?', (request.state.session['token_hash'],))
            token, csrf = new_session(conn, staff_id, job['id'], job['portal_hash'])
        return session_response({'csrf': csrf, 'job_id': job['id'], 'user': request.state.user}, token)

    @app.get('/api/portal/job')
    def portal_detail(request: Request):
        with transaction(database) as conn:
            job = portal_job(conn, request)
            return serialize_job(conn, job, audience='customer', gateway=app.state.gateway)

    @app.post('/api/portal/accept-quote')
    def accept_quote(request: Request, payload: dict = Body(...)):
        signer = text(payload.get('name', ''), 'Full name', 120, True)
        if payload.get('confirm') is not True:
            raise HTTPException(422, 'Confirm acceptance of the current quote.')
        with transaction(database, True) as conn:
            job = portal_job(conn, request)
            if job['archived'] or not job['published'] or not job['charges_verified']:
                raise HTTPException(409, 'This quote is not available for acceptance yet.')
            if payload.get('version') != job['quote_version']:
                raise HTTPException(409, 'The quote changed. Reload and review the latest version.')
            if job['accepted_version'] == job['quote_version']:
                return {'ok': True}
            conn.execute('UPDATE jobs SET accepted_version=quote_version,accepted_name=?,accepted_at=? WHERE id=?',
                         (signer, now(), job['id']))
            audit(conn, job['id'], signer + ' (private job link)', 'quote.accepted',
                  {'version': job['quote_version'], 'total_cents': totals(conn, job)['total_cents'], 'method': 'private_job_link'}, True)
        return {'ok': True}

    @app.post('/api/portal/proofs/{proof_id}/decision')
    def proof_decision(proof_id: int, request: Request, payload: dict = Body(...)):
        action_ = payload.get('action')
        if action_ not in ('approve', 'request_changes'):
            raise HTTPException(422, 'Choose approve or request_changes.')
        signer = text(payload.get('name', ''), 'Full name', 120, True)
        comment = text(payload.get('comment', ''), 'Comments', 3000, required=action_ == 'request_changes')
        with transaction(database, True) as conn:
            job = portal_job(conn, request)
            proof = latest_proof(conn, job['id'])
            if job['archived'] or not proof or proof['id'] != proof_id:
                raise HTTPException(409, 'Only the latest complete proof package can be reviewed.')
            if proof['status'] != 'pending':
                raise HTTPException(409, 'This proof already has a decision. Revisions require a new version.')
            if job['accepted_version'] != job['quote_version']:
                raise HTTPException(409, 'Accept the current quote before reviewing the proof.')
            if action_ == 'approve' and payload.get('confirm') is not True:
                raise HTTPException(422, 'Confirm the proof approval checklist.')
            asset = conn.execute('SELECT * FROM assets WHERE id=?', (proof['asset_id'],)).fetchone()
            try:
                actual_hash = hashlib.sha256((uploads / asset['stored_name']).read_bytes()).hexdigest()
            except (OSError, TypeError):
                raise HTTPException(409, 'The proof file is unavailable. Contact the shop for a new proof.')
            if actual_hash != asset['sha256']:
                raise HTTPException(409, 'The proof file changed. Contact the shop for a new proof.')
            conn.execute('INSERT INTO proof_decisions(proof_id,action,signer_name,comment,statement,quote_version,file_hash,created_at) VALUES(?,?,?,?,?,?,?,?)',
                         (proof_id, action_, signer, comment, APPROVAL_STATEMENT if action_ == 'approve' else 'Changes requested; not approved for production.', job['quote_version'], asset['sha256'], now()))
            conn.execute('UPDATE proofs SET status=? WHERE id=?', ('approved' if action_ == 'approve' else 'changes_requested', proof_id))
            audit(conn, job['id'], signer + ' (private job link)', 'proof.' + action_,
                  {'proof_version': proof['version'], 'comment': comment, 'sha256': asset['sha256']}, True)
            decision_job_id = job['id']
            decision_number = job['number']
            decision_version = proof['version']
        notify_staff(database, decision_job_id, f'proof_decision_{decision_version}_{action_}',
                     f'Proof {action_.replace("_", " ")} for {decision_number}',
                     'Customer proof activity',
                     f'The customer {action_.replace("_", " ")} proof version {decision_version}.' + (f' Comment: {comment}' if comment else ''), public_url)
        return {'ok': True}

    @app.post('/api/portal/message')
    def portal_message(request: Request, payload: dict = Body(...)):
        throttle(request, 'messages', 60, 3600)
        message = text(payload.get('message', ''), 'Message', 3000, True)
        with transaction(database, True) as conn:
            job = portal_job(conn, request)
            audit(conn, job['id'], 'Customer via private job link', 'customer.message', {'message': message}, True)
            message_job_id = job['id']
            message_number = job['number']
            message_event = secrets.token_hex(6)
        notify_staff(database, message_job_id, f'customer_message_{message_event}', f'New message on {message_number}',
                     'Customer sent a message', message, public_url)
        return {'ok': True}

    @app.post('/api/portal/payment-notice')
    def payment_notice(request: Request, payload: dict = Body(...)):
        throttle(request, 'payment_notice', 10, 3600)
        reference = text(payload.get('reference', ''), 'Payment reference', 200, True)
        with transaction(database, True) as conn:
            job = portal_job(conn, request)
            audit(conn, job['id'], 'Customer via private job link', 'payment.customer_reported',
                  {'reference': reference, 'verified': False}, True)
            notice_job_id = job['id']
            notice_number = job['number']
        notify_staff(database, notice_job_id, f'payment_notice_{digest(reference)[:12]}', f'Payment notice for {notice_number}',
                     'Customer reported a payment', 'The customer reported a payment. Verify it in QuickBooks before changing the balance.', public_url)
        return {'ok': True, 'message': 'The shop will verify this payment in QuickBooks. The balance has not changed yet.'}

    @app.get('/api/staff/jobs')
    def job_list(request: Request, user=Depends(require_staff)):
        with transaction(database) as conn:
            rows = conn.execute('SELECT * FROM jobs WHERE archived=0 ORDER BY id DESC LIMIT 500').fetchall()
            return {'jobs': [serialize_job(conn, row, user['role'], detail=False) for row in rows],
                    'limit': 500, 'shop': settings(conn)['shop_name']}

    def report_data(conn, start_value: str = '', end_value: str = ''):
        try:
            start = date.fromisoformat(start_value).isoformat() if start_value else ''
            end = date.fromisoformat(end_value).isoformat() if end_value else ''
        except (TypeError, ValueError):
            raise HTTPException(422, 'Report dates must use YYYY-MM-DD.')
        where, params = ['archived=0'], []
        if start:
            where.append('created_at>=?')
            params.append(start + 'T00:00:00')
        if end:
            where.append('created_at<?')
            params.append(end + 'T23:59:59.999999')
        jobs = conn.execute('SELECT * FROM jobs WHERE ' + ' AND '.join(where) + ' ORDER BY created_at DESC', params).fetchall()
        rows, services = [], {}
        totals_out = {'order_count': 0, 'booked_order_count': 0, 'quoted_revenue_cents': 0,
                      'revenue_cents': 0, 'collected_cents': 0, 'outstanding_cents': 0,
                      'cost_cents': 0, 'profit_cents': 0, 'tax_cents': 0}
        for job in jobs:
            quote, money = json.loads(job['quote_snapshot']), totals(conn, job)
            booked = bool(job['accepted_version'] == job['quote_version'] or money['paid_cents'] > 0)
            totals_out['order_count'] += 1
            totals_out['quoted_revenue_cents'] += money['merchandise_cents']
            totals_out['collected_cents'] += money['paid_cents']
            totals_out['tax_cents'] += money['tax_cents']
            if booked:
                gross_profit = money['merchandise_cents'] - money['cost_cents']
                totals_out['booked_order_count'] += 1
                totals_out['revenue_cents'] += money['merchandise_cents']
                totals_out['outstanding_cents'] += money['balance_cents']
                totals_out['cost_cents'] += money['cost_cents']
                totals_out['profit_cents'] += gross_profit
            else:
                gross_profit = money['merchandise_cents'] - money['cost_cents']
            rows.append({'number': job['number'], 'created_at': job['created_at'], 'customer': job['customer_name'],
                         'title': job['title'], 'booked': booked, 'revenue_cents': money['merchandise_cents'],
                         'cost_cents': money['cost_cents'], 'profit_cents': gross_profit,
                         'paid_cents': money['paid_cents'], 'balance_cents': money['balance_cents']})
            if booked:
                for line in quote.get('lines', []):
                    name = str(line.get('name') or 'Other')
                    service = services.setdefault(name, {'name': name, 'orders': set(), 'quantity': 0,
                                                          'revenue_cents': 0, 'cost_cents': 0, 'profit_cents': 0})
                    service['orders'].add(job['id'])
                    service['quantity'] += int(line.get('quantity') or 0)
                    service['revenue_cents'] += int(line.get('sell_cents') or 0)
                    service['cost_cents'] += int(line.get('cost_cents') or 0)
                    service['profit_cents'] += int(line.get('sell_cents') or 0) - int(line.get('cost_cents') or 0)
        totals_out['margin_percent'] = round(totals_out['profit_cents'] / totals_out['revenue_cents'] * 100, 1) if totals_out['revenue_cents'] else 0
        service_rows = []
        for service in services.values():
            service['orders'] = len(service['orders'])
            service['margin_percent'] = round(service['profit_cents'] / service['revenue_cents'] * 100, 1) if service['revenue_cents'] else 0
            service_rows.append(service)
        service_rows.sort(key=lambda item: item['revenue_cents'], reverse=True)
        return {'period': {'start': start, 'end': end}, 'totals': totals_out, 'services': service_rows, 'orders': rows}

    @app.get('/api/admin/reports')
    def owner_reports(request: Request, start: str = '', end: str = '', user=Depends(require_admin)):
        with transaction(database) as conn:
            return report_data(conn, start, end)

    @app.get('/api/admin/reports.csv')
    def export_owner_report(request: Request, start: str = '', end: str = '', user=Depends(require_admin)):
        with transaction(database) as conn:
            report = report_data(conn, start, end)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Order', 'Date', 'Customer', 'Project', 'Booked', 'Revenue', 'Estimated cost', 'Estimated profit', 'Collected', 'Balance'])
        for row in report['orders']:
            writer.writerow([row['number'], row['created_at'], row['customer'], row['title'], 'Yes' if row['booked'] else 'No',
                             f"{row['revenue_cents']/100:.2f}", f"{row['cost_cents']/100:.2f}", f"{row['profit_cents']/100:.2f}",
                             f"{row['paid_cents']/100:.2f}", f"{row['balance_cents']/100:.2f}"])
        return Response(output.getvalue(), media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="tampa-signs-owner-report.csv"', 'Cache-Control': 'no-store'})

    @app.get('/api/staff/task-queue')
    def task_queue(request: Request, user=Depends(require_staff)):
        with transaction(database) as conn:
            rows = conn.execute("SELECT t.*,j.number,j.title AS job_title,u.name AS assignee FROM tasks t JOIN jobs j ON j.id=t.job_id LEFT JOIN users u ON u.id=t.assignee_id WHERE j.archived=0 AND t.status!='done' ORDER BY j.priority DESC,j.id,t.position LIMIT 300").fetchall()
            cache = {}
            output = []
            for row in rows:
                if row['job_id'] not in cache:
                    cache[row['job_id']] = get_job(conn, row['job_id'])
                output.append(dict(row) | {'blocked_reason': gate_reason(conn, cache[row['job_id']], row)})
            return {'tasks': output, 'limit': 300}

    @app.get('/api/staff/jobs/{job_id}')
    def job_detail(job_id: int, request: Request, user=Depends(require_staff)):
        with transaction(database) as conn:
            return serialize_job(conn, get_job(conn, job_id), audience=user['role'], gateway=app.state.gateway)

    @app.post('/api/staff/jobs')
    def new_job(request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        with transaction(database, True) as conn:
            job_id = create_job(conn, payload, actor=actor(user))
        return {'job_id': job_id}

    @app.post('/api/staff/jobs/{job_id}/claim')
    def claim_job(job_id: int, request: Request, user=Depends(require_staff)):
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if job['archived']:
                raise HTTPException(409, 'Job is archived.')
            if job['assignee_id'] and job['assignee_id'] != user['id']:
                raise HTTPException(409, 'Another employee already owns this job. Ask an admin to reassign it.')
            conn.execute('UPDATE jobs SET assignee_id=? WHERE id=?', (user['id'], job_id))
            audit(conn, job_id, actor(user), 'job.claimed', {})
        return {'ok': True}

    @app.patch('/api/staff/jobs/{job_id}/meta')
    def job_meta(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            due = payload.get('due_date') or None
            if due:
                try:
                    date.fromisoformat(due)
                except (ValueError, TypeError):
                    raise HTTPException(422, 'Due date must be YYYY-MM-DD.')
            priority = payload.get('priority', job['priority'])
            if priority not in ('normal', 'rush'):
                raise HTTPException(422, 'Invalid priority.')
            owner = payload.get('assignee_id')
            if owner and not conn.execute('SELECT id FROM users WHERE id=? AND active=1', (owner,)).fetchone():
                raise HTTPException(422, 'Choose an active employee.')
            conn.execute('UPDATE jobs SET due_date=?,priority=?,assignee_id=? WHERE id=?', (due, priority, owner, job_id))
            audit(conn, job_id, actor(user), 'job.schedule_updated', {'due_date': due, 'priority': priority, 'assignee_id': owner})
        return {'ok': True}

    @app.post('/api/staff/jobs/{job_id}/cancel')
    def cancel_job(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        reason = text(payload.get('reason', ''), 'Cancellation reason', 1000, True)
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if job['archived']:
                return {'ok': True, 'already_cancelled': True}
            conn.execute('UPDATE time_entries SET stopped_at=? WHERE task_id IN (SELECT id FROM tasks WHERE job_id=?) AND stopped_at IS NULL',
                         (now(), job_id))
            conn.execute("UPDATE tasks SET status=CASE WHEN status='done' THEN status ELSE 'blocked' END, note=CASE WHEN status='done' THEN note ELSE ? END WHERE job_id=?",
                         ('Job cancelled: ' + reason, job_id))
            conn.execute('UPDATE jobs SET archived=1 WHERE id=?', (job_id,))
            audit(conn, job_id, actor(user), 'job.cancelled', {'reason': reason}, False)
        return {'ok': True}

    @app.post('/api/staff/jobs/{job_id}/quote')
    def edit_quote(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if order_for_job(conn, job_id):
                raise HTTPException(409, 'Online orders have a locked checkout total. Use a separately reviewed change order; handle refunds in Stripe.')
            if job['archived'] or production_started(conn, job_id):
                raise HTTPException(409, 'Financial revisions after production begins require a separate change-order job.')
            if payload.get('version') != job['quote_version']:
                raise HTTPException(409, 'This quote was edited elsewhere. Reload before saving.')
            extra_price = cents(payload.get('extra_price', 0), 'Additional services price')
            extra_cost = cents(payload.get('extra_cost', 0), 'Additional job cost')
            shipping = cents(payload.get('shipping', 0), 'Delivery charge')
            tax = cents(payload.get('tax', 0), 'Tax amount')
            override = None if payload.get('price_override') in (None, '') else cents(payload['price_override'], 'Agreed pretax price')
            note = text(payload.get('adjustment_note', ''), 'Adjustment explanation', 2000)
            if (override is not None or extra_price or extra_cost) and not note:
                raise HTTPException(422, 'Explain the price adjustment or additional services.')
            deposit = str(number(payload.get('deposit_percent', job['deposit_percent']), 'Deposit %', '0', '100'))
            verified = payload.get('charges_verified') is True
            conn.execute('''UPDATE jobs SET extra_price_cents=?,extra_cost_cents=?,shipping_cents=?,tax_cents=?,
                price_override_cents=?,adjustment_note=?,deposit_percent=?,charges_verified=?,
                quote_version=quote_version+1,published=0,accepted_version=NULL,accepted_name=NULL,accepted_at=NULL,
                payment_url=NULL,invoice_reference='' WHERE id=?''',
                (extra_price, extra_cost, shipping, tax, override, note, deposit, int(verified), job_id))
            revised = get_job(conn, job_id)
            summary = totals(conn, revised)
            if summary['total_cents'] <= 0 or summary['total_cents'] < summary['paid_cents']:
                raise HTTPException(422, 'Quote total must be positive and not below already verified payments.')
            audit(conn, job_id, actor(user), 'quote.revised', {'version': revised['quote_version'],
                  'total_cents': summary['total_cents'], 'note': note, 'payment_link_cleared': True}, True)
        return {'ok': True}

    @app.post('/api/staff/jobs/{job_id}/publish')
    def publish_quote(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if job['archived'] or not job['charges_verified'] or payload.get('reviewed') is not True:
                raise HTTPException(422, 'Review the scope, material costs, tax, delivery and total before publishing.')
            if payload.get('version') != job['quote_version']:
                raise HTTPException(409, 'Quote version changed. Reload.')
            conn.execute('UPDATE jobs SET published=1 WHERE id=?', (job_id,))
            audit(conn, job_id, actor(user), 'quote.published', {'version': job['quote_version']}, True)
            quote_email_link = issue_email_portal(conn, job_id)
            quote_number = job['number']
            quote_version = job['quote_version']
        notify_customer(database, job_id, f'quote_ready_{quote_version}', f'Quote ready for {quote_number} | Tampa Signs and Stickers',
                        'Your quote is ready', 'Your project quote is ready to review in your private order page.', quote_email_link)
        return {'ok': True}

    @app.post('/api/staff/jobs/{job_id}/share')
    def share_job(job_id: int, request: Request, user=Depends(require_staff)):
        with transaction(database, True) as conn:
            get_job(conn, job_id)
            link = issue_portal(conn, job_id)
            audit(conn, job_id, actor(user), 'portal.link_rotated', {'expires_in_days': 14})
        return {'portal_url': link, 'expires_in_days': 14}

    @app.post('/api/staff/jobs/{job_id}/message')
    def staff_message(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        message = text(payload.get('message', ''), 'Message', 3000, True)
        public_message = payload.get('public') is True
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            audit(conn, job_id, actor(user), 'shop.message', {'message': message}, public_message)
            email_link = issue_email_portal(conn, job_id) if public_message else None
            job_number = job['number']
            message_event = secrets.token_hex(6)
        if public_message:
            notify_customer(database, job_id, f'shop_message_{message_event}', f'Update on {job_number} | Tampa Signs and Stickers',
                            'You have a project update', message, email_link)
        return {'ok': True}

    @app.post('/api/staff/jobs/{job_id}/payment-link')
    def attach_link(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        link = payment_url(payload.get('url', ''))
        kind = payload.get('kind', 'invoice')
        if kind not in ('invoice','payment_link'):
            raise HTTPException(422, 'Choose invoice or payment_link.')
        reference = text(payload.get('invoice_reference', ''), 'Invoice/reference', 200, True)
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if order_for_job(conn, job_id):
                raise HTTPException(409, 'This is an online checkout order. Payments are reconciled by the payment provider, not manual QuickBooks entries.')
            if not job['published'] or job['accepted_version'] != job['quote_version']:
                raise HTTPException(409, 'Publish the quote and obtain customer acceptance before requesting payment.')
            conn.execute('UPDATE jobs SET payment_url=?,payment_kind=?,invoice_reference=? WHERE id=?', (link, kind, reference, job_id))
            audit(conn, job_id, actor(user), 'payment.link_attached', {'kind': kind, 'invoice_reference': reference}, True)
        return {'ok': True}

    @app.post('/api/staff/jobs/{job_id}/payments')
    def verify_payment(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        amount = cents(payload.get('amount'), 'Verified payment amount')
        reference = text(payload.get('reference', ''), 'Unique QuickBooks transaction reference', 200, True)
        note = text(payload.get('note', ''), 'Payment note', 1000)
        if amount <= 0 or payload.get('verified_in_quickbooks') is not True:
            raise HTTPException(422, 'Verify a positive payment in QuickBooks first.')
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if order_for_job(conn, job_id):
                raise HTTPException(409, 'This is an online checkout order. Payments are reconciled by the payment provider, not manual QuickBooks entries.')
            existing = conn.execute('SELECT * FROM payments WHERE job_id=? AND reference=?', (job_id, reference)).fetchone()
            if existing:
                if existing['amount_cents'] == amount and not existing['voided_at']:
                    return {'ok': True, 'payment_id': existing['id'], 'already_recorded': True}
                raise HTTPException(409, 'This payment reference was already used. Do not record it twice.')
            if not job['published'] or job['accepted_version'] != job['quote_version']:
                raise HTTPException(409, 'The current quote must be accepted before recording payment.')
            if amount > totals(conn, job)['balance_cents']:
                raise HTTPException(422, 'Payment exceeds the remaining balance. Credits/refunds require separate reconciliation.')
            pid = conn.execute('INSERT INTO payments(job_id,amount_cents,reference,note,verified_by,created_at) VALUES(?,?,?,?,?,?)',
                               (job_id, amount, reference, note, user['id'], now())).lastrowid
            audit(conn, job_id, actor(user), 'payment.verified', {'amount_cents': amount, 'reference': reference}, True)
        return {'ok': True, 'payment_id': pid}

    @app.post('/api/staff/payments/{payment_id}/void')
    def void_payment(payment_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        reason = text(payload.get('reason', ''), 'Correction reason', 1000, True)
        with transaction(database, True) as conn:
            payment = conn.execute('SELECT * FROM payments WHERE id=?', (payment_id,)).fetchone()
            if not payment or payment['voided_at']:
                raise HTTPException(409, 'Payment is missing or already voided.')
            conn.execute('UPDATE payments SET voided_at=?,void_reason=? WHERE id=?', (now(), reason, payment_id))
            audit(conn, payment['job_id'], actor(user), 'payment.record_voided', {'reference': payment['reference'], 'reason': reason, 'not_a_quickbooks_refund': True}, True)
        return {'ok': True}

    @app.post('/api/staff/tasks/{task_id}/action')
    def task_action(task_id: int, request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        operation = payload.get('action')
        if operation not in ('claim','start','pause','block','complete','release'):
            raise HTTPException(422, 'Unsupported task action.')
        with transaction(database, True) as conn:
            task = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if not task:
                raise HTTPException(404, 'Task not found.')
            job = get_job(conn, task['job_id'])
            was_production = production_started(conn, job['id'])
            if job['archived'] or task['status'] == 'done':
                raise HTTPException(409, 'Archived or completed tasks cannot be changed.')
            if task['assignee_id'] and task['assignee_id'] != user['id'] and user['role'] != 'admin':
                raise HTTPException(409, 'This task belongs to another employee.')
            note = text(payload.get('note', task['note']), 'Task note', 2000)
            if operation == 'claim':
                conn.execute('UPDATE tasks SET assignee_id=? WHERE id=?', (user['id'], task_id))
            elif operation == 'release':
                if task['status'] == 'in_progress':
                    raise HTTPException(409, 'Pause the timer before releasing this task.')
                conn.execute('UPDATE tasks SET assignee_id=NULL WHERE id=?', (task_id,))
            else:
                if operation in ('start', 'complete'):
                    reason = gate_reason(conn, job, task)
                    if reason:
                        raise HTTPException(409, reason)
                if operation == 'start':
                    if task['status'] == 'in_progress':
                        raise HTTPException(409, 'This task is already running.')
                    conn.execute("UPDATE tasks SET status='in_progress',assignee_id=?,started_at=COALESCE(started_at,?),note=? WHERE id=?",
                                 (user['id'], now(), note, task_id))
                    conn.execute('INSERT INTO time_entries(task_id,user_id,started_at) VALUES(?,?,?)', (task_id, user['id'], now()))
                else:
                    if operation in ('pause','complete') and task['status'] != 'in_progress':
                        raise HTTPException(409, 'Start the task before pausing or completing it.')
                    if operation == 'block' and not note:
                        raise HTTPException(422, 'Explain why this task is blocked.')
                    conn.execute('UPDATE time_entries SET stopped_at=? WHERE task_id=? AND stopped_at IS NULL', (now(), task_id))
                    status = {'pause': 'paused', 'block': 'blocked', 'complete': 'done'}[operation]
                    conn.execute('UPDATE tasks SET status=?,note=?,completed_at=?,assignee_id=COALESCE(assignee_id,?) WHERE id=?',
                                 (status, note, now() if operation == 'complete' else None, user['id'], task_id))
            audit(conn, job['id'], actor(user), 'task.' + operation, {'task': task['title'], 'note': note}, False)
            now_production = production_started(conn, job['id'])
            finished_now = conn.execute("SELECT id FROM tasks WHERE job_id=? AND status!='done' LIMIT 1", (job['id'],)).fetchone() is None
            milestone_link = issue_email_portal(conn, job['id']) if ((not was_production and now_production) or finished_now) else None
            job_number = job['number']
            milestone_job_id = job['id']
        if not was_production and now_production:
            notify_customer(database, milestone_job_id, 'production_started', f'{job_number} is in production | Tampa Signs and Stickers',
                            'Your order is in production', 'Your approved order has moved into production. We will email you again when it is finished.', milestone_link)
            notify_staff(database, milestone_job_id, 'production_started', f'{job_number} entered production',
                         'Job entered production', 'Production has started on this job.', public_url)
        if finished_now:
            notify_customer(database, milestone_job_id, 'order_finished', f'{job_number} is finished | Tampa Signs and Stickers',
                            'Your order is finished', 'Your order has been completed. Check your order page for the latest details.', milestone_link)
            notify_staff(database, milestone_job_id, 'order_finished', f'{job_number} completed',
                         'Job completed', 'All production tasks for this job are complete.', public_url)
        return {'ok': True}

    @app.post('/api/staff/jobs/{job_id}/tasks')
    def add_task(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        title = text(payload.get('title', ''), 'Task name', 120, True)
        department = text(payload.get('department', 'Production'), 'Department', 60, True)
        gate = payload.get('gate', 'production')
        if gate not in ('none','quote','deposit','production','delivery'):
            raise HTTPException(422, 'Invalid gate.')
        deps = payload.get('dependencies', [])
        if not isinstance(deps, list) or len(deps) > 40 or any(type(x) is not int for x in deps):
            raise HTTPException(422, 'Invalid dependencies.')
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if job['archived'] or production_started(conn, job_id):
                raise HTTPException(409, 'Customize job tasks before production begins.')
            for dep in deps:
                if not conn.execute('SELECT id FROM tasks WHERE id=? AND job_id=?', (dep, job_id)).fetchone():
                    raise HTTPException(422, 'Dependencies must belong to this job.')
            pos = conn.execute('SELECT COALESCE(MAX(position),0)+1 FROM tasks WHERE job_id=?', (job_id,)).fetchone()[0]
            conn.execute('INSERT INTO tasks(job_id,position,title,department,gate,dependencies) VALUES(?,?,?,?,?,?)',
                         (job_id, pos, title, department, gate, json.dumps(deps)))
            audit(conn, job_id, actor(user), 'task.added', {'title': title, 'gate': gate})
        return {'ok': True}

    @app.post('/api/jobs/{job_id}/artwork')
    def upload_artwork(job_id: int, request: Request, file: UploadFile = File(...)):
        throttle(request, 'uploads', 40, 3600)
        with transaction(database) as conn:
            access_job(conn, request, job_id)
        raw, name, mime, suffix = sanitize(file.file.read(MAX_UPLOAD + 1), file.filename or 'artwork')
        with transaction(database, True) as conn:
            job, who = access_job(conn, request, job_id)
            if job['archived']:
                raise HTTPException(409, 'Job is archived.')
            aid = save_asset(conn, uploads, job_id, raw, name, mime, suffix, 'artwork', who)
            audit(conn, job_id, who, 'artwork.uploaded', {'filename': name}, True)
            artwork_number = job['number']
            customer_upload = not bool(request.state.user)
        if customer_upload:
            notify_staff(database, job_id, f'artwork_uploaded_{aid}', f'Artwork uploaded for {artwork_number}',
                         'Customer uploaded artwork', f'New customer artwork is attached: {name}', public_url)
        return {'ok': True, 'asset_id': aid}

    @app.post('/api/portal/artwork/{asset_id}/approve')
    def approve_uploaded_artwork(asset_id: int, request: Request, payload: dict = Body(...)):
        signer = text(payload.get('name', ''), 'Full name', 120, True)
        if payload.get('confirm') is not True:
            raise HTTPException(422, 'Confirm that the uploaded artwork is approved to print as supplied.')
        with transaction(database, True) as conn:
            job = portal_job(conn, request)
            if job['archived']:
                raise HTTPException(409, 'This job is cancelled.')
            if job['accepted_version'] != job['quote_version']:
                raise HTTPException(409, 'Accept the current quote before approving artwork.')
            quote = json.loads(job['quote_snapshot'])
            if not quote['lines'] or not all(bool(line.get('self_approve_artwork')) for line in quote['lines']):
                raise HTTPException(409, 'This product requires a shop proof before artwork approval.')
            if latest_proof(conn, job['id']):
                raise HTTPException(409, 'A proof already exists for this job. Review the latest proof instead.')
            asset = conn.execute("SELECT * FROM assets WHERE id=? AND job_id=? AND kind='artwork'", (asset_id, job['id'])).fetchone()
            if not asset:
                raise HTTPException(404, 'Artwork file not found.')
            try:
                actual_hash = hashlib.sha256((uploads / asset['stored_name']).read_bytes()).hexdigest()
            except (OSError, TypeError):
                raise HTTPException(409, 'The artwork file is unavailable. Upload it again.')
            if actual_hash != asset['sha256']:
                raise HTTPException(409, 'The artwork file changed. Upload it again before approval.')
            pid = add_proof(conn, job, asset_id, 'Customer-approved print-ready artwork',
                            'Approved by the customer to print as supplied without design changes.',
                            signer + ' (private job link)')
            conn.execute('INSERT INTO proof_decisions(proof_id,action,signer_name,comment,statement,quote_version,file_hash,created_at) VALUES(?,?,?,?,?,?,?,?)',
                         (pid, 'approve', signer, 'Customer approved uploaded artwork as supplied.',
                          APPROVAL_STATEMENT, job['quote_version'], asset['sha256'], now()))
            conn.execute("UPDATE proofs SET status='approved' WHERE id=?", (pid,))
            audit(conn, job['id'], signer + ' (private job link)', 'artwork.self_approved',
                  {'proof_version': 1, 'filename': asset['filename'], 'sha256': asset['sha256']}, True)
            job_id = job['id']
            job_number = job['number']
        notify_staff(database, job_id, f'artwork_self_approved_{pid}', f'Artwork approved for {job_number}',
                     'Customer approved print-ready artwork',
                     f'The customer approved {asset["filename"]} to print as supplied.', public_url)
        return {'ok': True, 'proof_id': pid}

    @app.post('/api/staff/jobs/{job_id}/proofs')
    def upload_proof(job_id: int, request: Request, file: UploadFile = File(...),
                     label: str = Form('Complete job proof'), note: str = Form(''),
                     covers_all_items: bool = Form(False), user=Depends(require_staff)):
        if not covers_all_items:
            raise HTTPException(422, 'Confirm this proof package covers every item in the job.')
        label = text(label, 'Proof label', 180, True)
        note = text(note, 'Proof note', 3000)
        raw, name, mime, suffix = sanitize(file.file.read(MAX_UPLOAD + 1), file.filename or 'proof')
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if job['archived'] or production_started(conn, job_id):
                raise HTTPException(409, 'Proof revisions after production starts require a separate change-order job.')
            aid = save_asset(conn, uploads, job_id, raw, name, mime, suffix, 'proof', actor(user))
            pid = add_proof(conn, job, aid, label, note, actor(user))
            email_link = issue_email_portal(conn, job_id)
            job_number = job['number']
        notify_customer(database, job_id, f'proof_pending_{pid}', f'Proof ready for {job_number} | Tampa Signs and Stickers',
                        'Your proof is ready', 'A new proof is waiting for your review. Please check the artwork carefully and approve it or request changes.', email_link)
        notify_staff(database, job_id, f'proof_pending_{pid}', f'Proof pending for {job_number}',
                     'Proof sent for approval', 'The current proof is now waiting for customer review.', public_url)
        return {'ok': True, 'proof_id': pid}

    @app.post('/api/staff/jobs/{job_id}/proofs/{proof_id}/send')
    def send_proof_for_approval(job_id: int, proof_id: int, request: Request, user=Depends(require_staff)):
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            proof = latest_proof(conn, job_id)
            if job['archived'] or not proof or proof['id'] != proof_id or proof['status'] != 'pending':
                raise HTTPException(409, 'Only the latest pending proof can be sent for approval.')
            email_link = issue_email_portal(conn, job_id)
            job_number = job['number']
            version = proof['version']
            audit(conn, job_id, actor(user), 'proof.sent_for_approval', {'version': version}, True)
        sent = notify_customer(database, job_id, f'proof_pending_{proof_id}',
                               f'Proof ready for {job_number} | Tampa Signs and Stickers',
                               'Your proof is ready',
                               'A proof is waiting for your review. Please check the artwork carefully and approve it or request changes.',
                               email_link, force=True)
        return {'ok': True, 'email_sent': bool(sent)}

    @app.post('/api/staff/jobs/{job_id}/layout')
    def generate_layout(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        mappings = payload.get('artwork', {})
        if not isinstance(mappings, dict) or len(mappings) > 30:
            raise HTTPException(422, 'Invalid artwork mapping.')
        for k, value in mappings.items():
            if not str(k).isdigit() or type(value) is not int:
                raise HTTPException(422, 'Artwork mappings must contain panel numbers and image asset IDs.')
        is_proof = payload.get('publish_as_proof') is True
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if job['archived'] or (is_proof and production_started(conn, job_id)):
                raise HTTPException(409, 'This job cannot accept a new proof. Create a change-order job.')
            lines = json.loads(job['quote_snapshot'])['lines']
            if is_proof and any(str(i) not in mappings for i in range(len(lines))):
                raise HTTPException(422, 'Assign artwork to every item before publishing a complete proof package.')
            raw = panel_sheet(conn, uploads, job, mappings, payload.get('fit', 'contain'))
            aid = save_asset(conn, uploads, job_id, raw, job['number'] + '-layout.png', 'image/png', '.png', 'proof' if is_proof else 'layout', actor(user))
            if is_proof:
                pid = add_proof(conn, job, aid, 'Generated panel proof', 'Review every item. This is a dimensioned design preview, not a full-size production file.', actor(user))
                email_link = issue_email_portal(conn, job_id)
                job_number = job['number']
            else:
                audit(conn, job_id, actor(user), 'layout.generated', {'asset_id': aid, 'approval_eligible': False})
        if is_proof:
            notify_customer(database, job_id, f'proof_pending_{pid}', f'Proof ready for {job_number} | Tampa Signs and Stickers',
                            'Your proof is ready', 'A new proof is waiting for your review. Please check the artwork carefully and approve it or request changes.', email_link)
            notify_staff(database, job_id, f'proof_pending_{pid}', f'Proof pending for {job_number}',
                         'Proof sent for approval', 'The current proof is now waiting for customer review.', public_url)
        return {'ok': True, 'asset_id': aid}

    @app.get('/api/assets/{asset_id}')
    def download_asset(asset_id: int, request: Request):
        with transaction(database) as conn:
            asset = conn.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone()
            if not asset:
                raise HTTPException(404, 'File not found.')
            access_job(conn, request, asset['job_id'])
            if not request.state.user and asset['kind'] not in ('artwork','proof'):
                raise HTTPException(404, 'File not found.')
            path = uploads / asset['stored_name']
            if not path.is_file():
                raise HTTPException(404, 'Stored file is missing. Contact the shop.')
            return FileResponse(path, media_type=asset['mime'], filename=asset['filename'],
                                content_disposition_type='inline' if asset['mime'] == 'image/png' else 'attachment',
                                headers={'Content-Security-Policy': "sandbox; default-src 'none'", 'Cache-Control': 'no-store'})

    @app.get('/api/admin/products')
    def admin_products(request: Request, user=Depends(require_admin)):
        with transaction(database) as conn:
            return {'products': [dict(p) | {'config': json.loads(p['config'])} for p in conn.execute('SELECT * FROM products ORDER BY id')]}

    @app.post('/api/admin/products')
    def create_product(request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        cfg = validate_config(payload.get('config', {}))
        name = text(payload.get('name', ''), 'Product name', 120, True)
        category = text(payload.get('category', ''), 'Category', 60, True)
        with transaction(database, True) as conn:
            workflow_id = payload.get('workflow_id')
            if not conn.execute('SELECT id FROM workflows WHERE id=?', (workflow_id,)).fetchone():
                raise HTTPException(422, 'Choose a workflow.')
            pid = conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?,?)',
                               (name, category, int(payload.get('active', True) is True), int(payload.get('public', True) is True), workflow_id, json.dumps(cfg), now())).lastrowid
            audit(conn, None, actor(user), 'product.created', {'product_id': pid, 'name': name})
        return {'product_id': pid}

    @app.put('/api/admin/products/{product_id}')
    def save_product(product_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        cfg = validate_config(payload.get('config', {}))
        with transaction(database, True) as conn:
            product = conn.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
            if not product:
                raise HTTPException(404, 'Product not found.')
            if payload.get('version') != product['version']:
                raise HTTPException(409, 'Another editor changed this product. Reload before saving.')
            if not conn.execute('SELECT id FROM workflows WHERE id=?', (payload.get('workflow_id'),)).fetchone():
                raise HTTPException(422, 'Choose a workflow.')
            conn.execute('''UPDATE products SET name=?,category=?,active=?,public=?,workflow_id=?,config=?,
                            version=version+1,updated_at=? WHERE id=?''',
                         (text(payload.get('name', ''), 'Name', 120, True), text(payload.get('category', ''), 'Category', 60, True),
                          int(payload.get('active') is True), int(payload.get('public') is True), payload['workflow_id'], json.dumps(cfg), now(), product_id))
            audit(conn, None, actor(user), 'product.updated', {'product_id': product_id, 'version': product['version'] + 1, 'previous_config': json.loads(product['config']), 'new_config': cfg})
        return {'ok': True}

    @app.get('/api/staff/workflows')
    def workflows(request: Request, user=Depends(require_staff)):
        with transaction(database) as conn:
            return {'workflows': [dict(w) | {'steps': json.loads(w['steps'])} for w in conn.execute('SELECT * FROM workflows ORDER BY id')]}

    @app.post('/api/admin/workflows')
    def create_workflow(request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        steps = validate_steps(payload.get('steps'))
        name = text(payload.get('name', ''), 'Workflow name', 120, True)
        with transaction(database, True) as conn:
            wid = conn.execute('INSERT INTO workflows(name,steps) VALUES(?,?)', (name, json.dumps(steps))).lastrowid
            audit(conn, None, actor(user), 'workflow.created', {'workflow_id': wid})
        return {'workflow_id': wid}

    @app.put('/api/admin/workflows/{workflow_id}')
    def save_workflow(workflow_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        steps = validate_steps(payload.get('steps'))
        with transaction(database, True) as conn:
            old = conn.execute('SELECT * FROM workflows WHERE id=?', (workflow_id,)).fetchone()
            if not old:
                raise HTTPException(404, 'Workflow not found.')
            if payload.get('version') != old['version']:
                raise HTTPException(409, 'Workflow changed elsewhere. Reload.')
            conn.execute('UPDATE workflows SET name=?,steps=?,version=version+1 WHERE id=?',
                         (text(payload.get('name', ''), 'Workflow name', 120, True), json.dumps(steps), workflow_id))
            audit(conn, None, actor(user), 'workflow.updated', {'workflow_id': workflow_id, 'version': old['version'] + 1})
        return {'ok': True}

    @app.get('/api/admin/wholesale')
    def wholesale_profiles(request: Request, user=Depends(require_admin)):
        with transaction(database) as conn:
            clients = []
            for row in conn.execute('SELECT id,name,email,username,discount_percent,active,created_at,updated_at FROM wholesale_clients ORDER BY name,email'):
                discounts = [dict(x) for x in conn.execute(
                    '''SELECT d.product_id,p.name AS product_name,d.discount_percent
                       FROM wholesale_product_discounts d JOIN products p ON p.id=d.product_id
                       WHERE d.client_id=? ORDER BY p.name''', (row['id'],))]
                clients.append(dict(row) | {'product_discounts': discounts})
            products = [dict(p) for p in conn.execute('SELECT id,name FROM products WHERE active=1 ORDER BY name')]
        return {'clients': clients, 'products': products}

    @app.post('/api/admin/wholesale')
    def create_wholesale_profile(request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        name = text(payload.get('name', ''), 'Wholesale client name', 120, True)
        address = email(payload.get('email', ''))
        username = wholesale_username(payload.get('username', ''))
        discount = str(number(payload.get('discount_percent', 0), 'Wholesale discount', '0', '90'))
        overrides = payload.get('product_discounts', {})
        if not isinstance(overrides, dict) or len(overrides) > 100:
            raise HTTPException(422, 'Wholesale product discounts must be a product-to-discount map.')
        temporary_password = secrets.token_urlsafe(18)
        with transaction(database, True) as conn:
            cid = conn.execute(
                'INSERT INTO wholesale_clients(name,email,username,code_hash,discount_percent,active,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?)',
                (name, address, username, password_hash(temporary_password), discount, now(), now())
            ).lastrowid
            for pid, value in overrides.items():
                product_id = int(number(pid, 'Product ID', '1', '100000000'))
                pct = str(number(value, 'Product discount', '0', '90'))
                if not conn.execute('SELECT id FROM products WHERE id=?', (product_id,)).fetchone():
                    raise HTTPException(422, 'Wholesale discount references an unknown product.')
                conn.execute('INSERT INTO wholesale_product_discounts(client_id,product_id,discount_percent) VALUES(?,?,?)',
                             (cid, product_id, pct))
            audit(conn, None, actor(user), 'wholesale.created', {'client_id': cid, 'email': address, 'username': username, 'discount_percent': discount})
        return {'client_id': cid, 'username': username, 'temporary_password': temporary_password,
                'message': 'Save this temporary wholesale password securely. It is displayed only once.'}

    @app.put('/api/admin/wholesale/{client_id}')
    def update_wholesale_profile(client_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        overrides = payload.get('product_discounts')
        new_password = secrets.token_urlsafe(18) if payload.get('reset_password') is True else None
        with transaction(database, True) as conn:
            current = conn.execute('SELECT * FROM wholesale_clients WHERE id=?', (client_id,)).fetchone()
            if not current:
                raise HTTPException(404, 'Wholesale client not found.')
            name = text(payload.get('name', current['name']), 'Wholesale client name', 120, True)
            address = email(payload.get('email', current['email']))
            username = wholesale_username(payload.get('username', current['username']))
            discount = str(number(payload.get('discount_percent', current['discount_percent']), 'Wholesale discount', '0', '90'))
            active = payload.get('active', bool(current['active']))
            if not isinstance(active, bool):
                raise HTTPException(422, 'active must be true or false.')
            conn.execute('UPDATE wholesale_clients SET name=?,email=?,username=?,discount_percent=?,active=?,updated_at=? WHERE id=?',
                         (name, address, username, discount, int(active), now(), client_id))
            if new_password:
                conn.execute('UPDATE wholesale_clients SET code_hash=? WHERE id=?', (password_hash(new_password), client_id))
                conn.execute('DELETE FROM wholesale_sessions WHERE client_id=?', (client_id,))
            if overrides is not None:
                if not isinstance(overrides, dict) or len(overrides) > 100:
                    raise HTTPException(422, 'Wholesale product discounts must be a product-to-discount map.')
                conn.execute('DELETE FROM wholesale_product_discounts WHERE client_id=?', (client_id,))
                for pid, value in overrides.items():
                    if value in ('', None):
                        continue
                    product_id = int(number(pid, 'Product ID', '1', '100000000'))
                    pct = str(number(value, 'Product discount', '0', '90'))
                    if not conn.execute('SELECT id FROM products WHERE id=?', (product_id,)).fetchone():
                        raise HTTPException(422, 'Wholesale discount references an unknown product.')
                    conn.execute('INSERT INTO wholesale_product_discounts(client_id,product_id,discount_percent) VALUES(?,?,?)',
                                 (client_id, product_id, pct))
            audit(conn, None, actor(user), 'wholesale.updated',
                  {'client_id': client_id, 'active': active, 'username': username, 'discount_percent': discount, 'password_reset': bool(new_password)})
        return {'ok': True, 'username': username, 'temporary_password': new_password}

    @app.get('/api/admin/email-status')
    def admin_email_status(request: Request, user=Depends(require_admin)):
        with transaction(database) as conn:
            rows = conn.execute('SELECT job_id,event_key,recipient,audience,status,error,created_at,updated_at FROM email_notifications ORDER BY id DESC LIMIT 50').fetchall()
            counts = {row['status']: row['count'] for row in conn.execute('SELECT status,COUNT(*) AS count FROM email_notifications GROUP BY status')}
        return {'configured': email_status()['enabled'], 'provider': email_status()['provider'],
                'counts': counts, 'recent': [dict(row) for row in rows]}

    @app.post('/api/admin/email-test')
    def admin_email_test(request: Request, user=Depends(require_admin)):
        ok, error = send_test_email(user['email'])
        if not ok:
            raise HTTPException(502, error or 'Email test failed.')
        return {'ok': True, 'recipient': user['email']}

    @app.get('/api/admin/settings')
    def get_settings(request: Request, user=Depends(require_admin)):
        with transaction(database) as conn:
            return settings(conn) | {'checkout_connection': {'configured': app.state.gateway.ready, 'test_mode': not app.state.gateway.live}}

    @app.put('/api/admin/settings')
    def save_settings(request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        with transaction(database, True) as conn:
            shop = settings(conn)
            for key, maxlen in [('shop_name',120),('contact_phone',60),('quote_note',1000)]:
                shop[key] = text(payload.get(key, shop[key]), key, maxlen, required=key == 'shop_name')
            shop['contact_email'] = email(payload['contact_email']) if payload.get('contact_email') else ''
            for key, maximum in [('deposit_percent','100'),('target_margin_percent','90'),('overhead_percent','200'),
                                 ('labor_cost_per_hour','10000'),('labor_sell_per_hour','10000'),('minimum_order_price','10000')]:
                shop[key] = str(number(payload.get(key, shop[key]), key, '0', maximum))
            if not isinstance(payload.get('rates_live', shop['rates_live']), bool):
                raise HTTPException(422, 'rates_live must be true or false.')
            shop['rates_live'] = payload.get('rates_live', shop['rates_live'])
            for key in ('checkout_enabled','checkout_tax_reviewed','checkout_pickup_enabled','checkout_shipping_enabled'):
                val = payload.get(key,shop.get(key,False))
                if not isinstance(val,bool):
                    raise HTTPException(422, f'{key} must be true or false.')
                shop[key]=val
            shop['checkout_pickup_address']=text(payload.get('checkout_pickup_address',shop['checkout_pickup_address']),'Pickup address',500)
            shop['checkout_terms']=text(payload.get('checkout_terms',shop['checkout_terms']),'Checkout terms',2000,True)
            shop['checkout_pickup_tax_percent']=str(number(payload.get('checkout_pickup_tax_percent',shop['checkout_pickup_tax_percent']),'Pickup sales tax %','0','30'))
            shop['checkout_shipping_price']=str(number(payload.get('checkout_shipping_price',shop['checkout_shipping_price']),'Shipping price','0','10000'))
            if shop['checkout_enabled']:
                if not shop['rates_live'] or not shop['checkout_tax_reviewed']:
                    raise HTTPException(422,'Review catalog rates and tax/delivery settings before enabling checkout.')
                if not shop['checkout_pickup_enabled'] and not shop['checkout_shipping_enabled']:
                    raise HTTPException(422,'Enable pickup or shipping for online orders.')
                if shop['checkout_pickup_enabled'] and not shop['checkout_pickup_address']:
                    raise HTTPException(422,'Enter the actual pickup address before enabling local pickup.')

            conn.execute('UPDATE settings SET data=? WHERE id=1', (json.dumps(shop),))
            audit(conn, None, actor(user), 'settings.updated', shop)
        return {'ok': True}

    @app.get('/api/staff/users')
    def staff_users(request: Request, user=Depends(require_staff)):
        with transaction(database) as conn:
            fields = 'id,name,email,role,active' if user['role'] == 'admin' else 'id,name,role,active'
            return {'users': [dict(u) for u in conn.execute(f'SELECT {fields} FROM users ORDER BY name')]}

    @app.post('/api/admin/users')
    def create_user(request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        address = email(payload.get('email', ''))
        name = text(payload.get('name', ''), 'Name', 120, True)
        role = payload.get('role', 'employee')
        if role not in ('admin', 'employee'):
            raise HTTPException(422, 'Role must be admin or employee.')
        temporary_password = secrets.token_urlsafe(18)
        with transaction(database, True) as conn:
            uid = conn.execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                               (name, address, password_hash(temporary_password), role, now())).lastrowid
            audit(conn, None, actor(user), 'staff.created', {'user_id': uid, 'role': role})
        return {'user_id': uid, 'temporary_password': temporary_password, 'message': 'Share this password securely. It is displayed only once.'}

    @app.patch('/api/admin/users/{user_id}')
    def update_user(user_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        with transaction(database, True) as conn:
            target = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if not target:
                raise HTTPException(404, 'User not found.')
            if user_id == user['id']:
                raise HTTPException(422, 'Use the password form for your own account; you cannot disable or reset yourself here.')
            active = payload.get('active', bool(target['active']))
            if not isinstance(active, bool):
                raise HTTPException(422, 'active must be a boolean.')
            new_password = secrets.token_urlsafe(18) if payload.get('reset_password') is True else None
            conn.execute('UPDATE users SET active=? WHERE id=?', (int(active), user_id))
            if new_password:
                conn.execute('UPDATE users SET password_hash=? WHERE id=?', (password_hash(new_password), user_id))
            conn.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            audit(conn, None, actor(user), 'staff.updated', {'user_id': user_id, 'active': active, 'password_reset': bool(new_password)})
        return {'ok': True, 'temporary_password': new_password}

    @app.get('/api/admin/events')
    def all_events(request: Request, user=Depends(require_admin)):
        with transaction(database) as conn:
            return {'events': [dict(e) | {'details': json.loads(e['details'])} for e in conn.execute('SELECT * FROM events ORDER BY id DESC LIMIT 300')]}

    @app.get('/api/admin/openapi')
    def api_schema(request: Request, user=Depends(require_admin)):
        return app.openapi()

    from .customers import install as install_customers
    install_customers(app, database, production, throttle, issue_portal)

    app.mount('/static', StaticFiles(directory=STATIC), name='static')

    @app.get('/robots.txt')
    def robots():
        body = ('User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /staff\nDisallow: /portal\n'
                'Disallow: /project\nDisallow: /studio\nDisallow: /account\n'
                f'Sitemap: {public_url}/sitemap.xml\n')
        return Response(body, media_type='text/plain')

    @app.get('/sitemap.xml')
    def sitemap():
        with transaction(database) as conn:
            rows = conn.execute('SELECT name,updated_at FROM products WHERE public=1 AND active=1 ORDER BY name').fetchall()
        pages = [(public_url + '/', None), (public_url + '/products', None)]
        pages.extend((public_url + '/products/' + product_slug(row['name']), str(row['updated_at'] or '')[:10]) for row in rows)
        urls = ''.join('<url><loc>' + html.escape(url) + '</loc>' + (f'<lastmod>{html.escape(lastmod)}</lastmod>' if lastmod else '') + '</url>' for url, lastmod in pages)
        return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + '</urlset>', media_type='application/xml')

    @app.get('/products/{slug}', response_class=HTMLResponse)
    def product_page(slug: str):
        with transaction(database) as conn:
            rows = conn.execute('SELECT * FROM products WHERE public=1 AND active=1 ORDER BY id').fetchall()
            product = next((row for row in rows if product_slug(row['name']) == slug), None)
        if not product:
            raise HTTPException(404, 'Product not found.')
        cfg = json.loads(product['config'])
        name = public_product_name(product['name'])
        description = str(cfg.get('description') or f'Customize and order {name} from Tampa Signs and Stickers in Tampa, Florida.')[:300]
        canonical = public_url + '/products/' + product_slug(product['name'])
        return HTMLResponse(seo_html(f'{name} | Tampa Signs and Stickers', description, canonical, product), headers={'Cache-Control': 'no-cache'})

    @app.get('/', response_class=HTMLResponse)
    @app.get('/staff', response_class=HTMLResponse)
    @app.get('/portal', response_class=HTMLResponse)
    @app.get('/products', response_class=HTMLResponse)
    @app.get('/project', response_class=HTMLResponse)
    @app.get('/studio', response_class=HTMLResponse)
    @app.get('/contour', response_class=HTMLResponse)
    @app.get('/account', response_class=HTMLResponse)
    def frontend(request: Request):
        path = request.url.path
        if path == '/products':
            return HTMLResponse(seo_html('Custom Signs, Wraps, Decals and Apparel | Tampa Signs', 'Browse custom signs, vehicle wraps, window graphics, decals, banners, apparel and event displays from Tampa Signs and Stickers.', public_url + '/products'), headers={'Cache-Control': 'no-cache'})
        if path == '/':
            return HTMLResponse(seo_html('Tampa Signs and Stickers | Custom Signs, Wraps and Printing', 'Order custom signs, stickers, vehicle wraps, window graphics, banners and apparel from Tampa Signs and Stickers.', public_url + '/'), headers={'Cache-Control': 'no-cache'})
        return HTMLResponse((STATIC / 'index.html').read_text(), headers={'Cache-Control': 'no-cache', 'X-Robots-Tag': 'noindex, nofollow'})

    return app
