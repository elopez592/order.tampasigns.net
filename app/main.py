from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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
from .mailer import public_status as email_status, notify_customer, notify_staff
import uuid

COOKIE = 'signshop_session'
STATIC = Path(__file__).with_name('static')


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
    app = FastAPI(title='Tampa Signs and Stickers', version='0.2.0', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.database = database
    app.state.uploads = uploads
    app.state.initial_credentials = credentials
    app.state.public_url = public_url
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
                if int(length) > 12 * 1024 * 1024 or int(length) < 0:
                    return JSONResponse({'detail': 'Request exceeds the 12 MB limit.'}, status_code=413)
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
            for row in conn.execute('SELECT * FROM products WHERE public=1 AND active=1 ORDER BY id'):
                cfg = json.loads(row['config'])
                products.append({k: row[k] for k in ('id','name','category','version')} | {
                    'config': {k: cfg[k] for k in ('unit','description','min_quantity','max_quantity','max_width','max_height',
                                                  'default_width','default_height','instant')}})
            return {'products': products, 'shop': {k: shop[k] for k in ('shop_name','contact_email','contact_phone','rates_live','quote_note')},
                    'checkout': availability(shop, app.state.gateway), 'notifications': email_status()}

    @app.post('/api/calculate')
    def customer_calculate(request: Request, payload: dict = Body(...)):
        throttle(request, 'calculate', 180, 60)
        with transaction(database) as conn:
            quote = calculate(conn, payload.get('items', []))
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
                quote = eligible_quote(conn, payload.get('items',[]))
                expected = digest(json.dumps(public_quote(quote), sort_keys=True))
                if payload.get('fingerprint') != expected:
                    raise HTTPException(409, 'Pricing has changed. Recalculate before ordering.')
                policy = checkout_policy(shop, delivery)
                job_id = create_job(conn,payload,source='checkout',actor='Online customer')
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
        notify_customer(database, job_id, 'order_received', f'{f"JOB-{job_id:04d}"} received | Tampa Signs and Stickers',
                        'Order received', 'We have your order. We will keep you updated when a proof is ready, production begins, and your order is finished.', link)
        notify_staff(database, job_id, 'order_received', f'New order {f"JOB-{job_id:04d}"}',
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
            computed = public_quote(calculate(conn, payload.get('items', [])))
            expected = digest(json.dumps(computed, sort_keys=True))
            if payload.get('fingerprint') != expected:
                raise HTTPException(409, 'Pricing has changed. Recalculate your estimate before submitting.')
            job_id = create_job(conn, payload, source='customer', actor='Public estimate request')
            link = issue_portal(conn, job_id)
        notify_customer(database, job_id, 'order_received', f'{f"JOB-{job_id:04d}"} received | Tampa Signs and Stickers',
                        'Project received', 'We received your project. Our team will review the details and keep you updated as it moves forward.', link)
        notify_staff(database, job_id, 'order_received', f'New project {f"JOB-{job_id:04d}"}',
                     'New project received', 'A new customer project has been submitted and is ready for review.', public_url)
        return {'job_id': job_id, 'number': f'JOB-{job_id:04d}', 'portal_url': link,
                'message': 'Order received. The shop will review any custom specifications, tax and delivery before production.'}

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
        return {'ok': True}

    @app.post('/api/portal/message')
    def portal_message(request: Request, payload: dict = Body(...)):
        throttle(request, 'messages', 60, 3600)
        message = text(payload.get('message', ''), 'Message', 3000, True)
        with transaction(database, True) as conn:
            job = portal_job(conn, request)
            audit(conn, job['id'], 'Customer via private job link', 'customer.message', {'message': message}, True)
        return {'ok': True}

    @app.post('/api/portal/payment-notice')
    def payment_notice(request: Request, payload: dict = Body(...)):
        throttle(request, 'payment_notice', 10, 3600)
        reference = text(payload.get('reference', ''), 'Payment reference', 200, True)
        with transaction(database, True) as conn:
            job = portal_job(conn, request)
            audit(conn, job['id'], 'Customer via private job link', 'payment.customer_reported',
                  {'reference': reference, 'verified': False}, True)
        return {'ok': True, 'message': 'The shop will verify this payment in QuickBooks. The balance has not changed yet.'}

    @app.get('/api/staff/jobs')
    def job_list(request: Request, user=Depends(require_staff)):
        with transaction(database) as conn:
            rows = conn.execute('SELECT * FROM jobs WHERE archived=0 ORDER BY id DESC LIMIT 500').fetchall()
            return {'jobs': [serialize_job(conn, row, user['role'], detail=False) for row in rows],
                    'limit': 500, 'shop': settings(conn)['shop_name']}

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
        with transaction(database, True) as conn:
            get_job(conn, job_id)
            audit(conn, job_id, actor(user), 'shop.message', {'message': message}, payload.get('public') is True)
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
        return {'ok': True, 'asset_id': aid}

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
        return {'ok': True, 'proof_id': pid}

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
                add_proof(conn, job, aid, 'Generated panel proof', 'Review every item. This is a dimensioned design preview, not a full-size production file.', actor(user))
            else:
                audit(conn, job_id, actor(user), 'layout.generated', {'asset_id': aid, 'approval_eligible': False})
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
                                 ('labor_cost_per_hour','10000'),('labor_sell_per_hour','10000')]:
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

    app.mount('/static', StaticFiles(directory=STATIC), name='static')

    @app.get('/', response_class=HTMLResponse)
    @app.get('/staff', response_class=HTMLResponse)
    @app.get('/portal', response_class=HTMLResponse)
    def frontend():
        return (STATIC / 'index.html').read_text()

    return app
