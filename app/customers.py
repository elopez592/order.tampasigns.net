"""Customer accounts are isolated from staff permissions and wholesale pricing."""
import json
import secrets
import time
from pathlib import Path

from fastapi import Body, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from .db import transaction, now
from .domain import create_job, stage
from .images import save_asset
from .security import digest, password_hash, password_matches, email, text

COOKIE = 'signshop_customer'


def customer(conn, request):
    token = request.cookies.get(COOKIE, '')
    if not token or len(token) > 200:
        return None
    return conn.execute(
        'SELECT c.id,c.name,c.email FROM customers c JOIN customer_sessions s ON c.id=s.customer_id '
        'WHERE s.token_hash=? AND s.expires_at>?',
        (digest(token), time.time()),
    ).fetchone()


def link_order(conn, request, job_id):
    who = customer(conn, request)
    if who:
        conn.execute('INSERT OR IGNORE INTO customer_orders(customer_id,job_id) VALUES(?,?)', (who['id'], job_id))


def reorder_item(line):
    allowed = (
        'product_id', 'width', 'height', 'quantity', 'description', 'installation_requested',
        'design_requested', 'lamination', 'material', 'coverage_option', 'include_roof_wrap',
        'vehicle_type', 'shirt_color', 'size_quantities', 'print_locations', 'usdot_design',
        'embroidery_preview',
    )
    return {key: line[key] for key in allowed if key in line}


def install(app, database, production, throttle, issue_portal, uploads):
    with transaction(database, True) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE COLLATE NOCASE,password_hash TEXT NOT NULL,created_at TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS customer_sessions(token_hash TEXT PRIMARY KEY,customer_id INTEGER NOT NULL REFERENCES customers(id),expires_at REAL NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS customer_orders(customer_id INTEGER NOT NULL REFERENCES customers(id),job_id INTEGER NOT NULL REFERENCES jobs(id),PRIMARY KEY(customer_id,job_id))')
        conn.execute("""CREATE TABLE IF NOT EXISTS customer_profiles(
            customer_id INTEGER PRIMARY KEY REFERENCES customers(id),
            account_type TEXT NOT NULL DEFAULT 'standard',
            company TEXT NOT NULL DEFAULT '',
            po_number TEXT NOT NULL DEFAULT '',
            locations TEXT NOT NULL DEFAULT '',
            fleet_notes TEXT NOT NULL DEFAULT '',
            brand_notes TEXT NOT NULL DEFAULT '',
            authorized_buyers TEXT NOT NULL DEFAULT '',
            tax_exempt_note TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )""")

    def require_customer(conn, request):
        who = customer(conn, request)
        if not who:
            raise HTTPException(401, 'Sign in to your customer account.')
        return who

    def profile_row(conn, customer_id):
        row = conn.execute('SELECT * FROM customer_profiles WHERE customer_id=?', (customer_id,)).fetchone()
        if row:
            return dict(row)
        return {
            'customer_id': customer_id, 'account_type': 'standard', 'company': '', 'po_number': '',
            'locations': '', 'fleet_notes': '', 'brand_notes': '', 'authorized_buyers': '',
            'tax_exempt_note': '', 'updated_at': '',
        }

    @app.get('/api/customer')
    def profile(request: Request):
        with transaction(database) as conn:
            who = customer(conn, request)
            if not who:
                return {'customer': None, 'orders': [], 'profile': None, 'saved_assets': []}
            rows = conn.execute(
                'SELECT j.* FROM jobs j JOIN customer_orders o ON o.job_id=j.id '
                'WHERE o.customer_id=? ORDER BY j.id DESC LIMIT 100', (who['id'],)
            ).fetchall()
            orders = [{
                'id': row['id'], 'number': row['number'], 'title': row['title'],
                'stage': stage(conn, row), 'created_at': row['created_at'],
                'due_date': row['due_date'], 'priority': row['priority'],
            } for row in rows]
            artwork = conn.execute(
                """SELECT a.id,a.filename,a.mime,a.size,a.sha256,a.created_at,j.id AS job_id,j.number AS job_number
                   FROM assets a
                   JOIN customer_orders o ON o.job_id=a.job_id
                   JOIN jobs j ON j.id=a.job_id
                   WHERE o.customer_id=? AND a.kind='artwork'
                   ORDER BY a.id DESC LIMIT 200""",
                (who['id'],),
            ).fetchall()
            seen = set()
            saved_assets = []
            for asset in artwork:
                if asset['sha256'] in seen:
                    continue
                seen.add(asset['sha256'])
                saved_assets.append({key: asset[key] for key in asset.keys() if key != 'sha256'})
                if len(saved_assets) >= 50:
                    break
            return {
                'customer': dict(who),
                'orders': orders,
                'profile': profile_row(conn, who['id']),
                'saved_assets': saved_assets,
            }

    def signed_in(conn, who, request):
        conn.execute('DELETE FROM customer_sessions WHERE token_hash=? OR expires_at<?', (digest(request.cookies.get(COOKIE, '')), time.time()))
        token = secrets.token_urlsafe(32)
        conn.execute('INSERT INTO customer_sessions VALUES(?,?,?)', (digest(token), who['id'], time.time() + 30 * 86400))
        response = JSONResponse({'customer': {k: who[k] for k in ('id', 'name', 'email')}})
        response.set_cookie(COOKIE, token, httponly=True, secure=production, samesite='lax', max_age=30*86400)
        return response

    @app.post('/api/customer/register')
    def register(request: Request, payload: dict = Body(...)):
        throttle(request, 'customer_register', 6, 3600)
        address = email(payload.get('email', ''))
        name = text(payload.get('name', ''), 'Name', 120, True)
        password = text(payload.get('password', ''), 'Password', 128, True)
        if len(password) < 12:
            raise HTTPException(422, 'Use a password of at least 12 characters.')
        hashed = password_hash(password)
        with transaction(database, True) as conn:
            if conn.execute('SELECT id FROM customers WHERE email=?', (address,)).fetchone():
                raise HTTPException(409, 'Unable to create this account. Try signing in or contact the shop.')
            cursor = conn.execute('INSERT INTO customers(name,email,password_hash,created_at) VALUES(?,?,?,?)', (name, address, hashed, now()))
            return signed_in(conn, {'id': cursor.lastrowid, 'name': name, 'email': address}, request)

    @app.post('/api/customer/login')
    def login(request: Request, payload: dict = Body(...)):
        throttle(request, 'customer_login', 12, 900)
        address = email(payload.get('email', ''))
        password = text(payload.get('password', ''), 'Password', 128, True)
        with transaction(database, True) as conn:
            who = conn.execute('SELECT * FROM customers WHERE email=?', (address,)).fetchone()
            if not who or not password_matches(password, who['password_hash']):
                if not who:
                    password_hash('unavailable-account')
                raise HTTPException(401, 'Email or password is incorrect.')
            return signed_in(conn, who, request)

    @app.post('/api/customer/logout')
    def logout(request: Request):
        with transaction(database, True) as conn:
            conn.execute('DELETE FROM customer_sessions WHERE token_hash=?', (digest(request.cookies.get(COOKIE, '')),))
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE)
        return response

    @app.put('/api/customer/profile')
    def update_profile(request: Request, payload: dict = Body(...)):
        with transaction(database, True) as conn:
            who = require_customer(conn, request)
            account_type = str(payload.get('account_type', 'standard')).strip().lower()
            if account_type not in ('standard', 'commercial'):
                raise HTTPException(422, 'Choose standard or commercial account.')
            values = {
                'company': text(payload.get('company', ''), 'Company', 160),
                'po_number': text(payload.get('po_number', ''), 'Default PO number', 120),
                'locations': text(payload.get('locations', ''), 'Locations', 4000),
                'fleet_notes': text(payload.get('fleet_notes', ''), 'Fleet / vehicle notes', 4000),
                'brand_notes': text(payload.get('brand_notes', ''), 'Brand notes', 4000),
                'authorized_buyers': text(payload.get('authorized_buyers', ''), 'Authorized buyers', 2000),
                'tax_exempt_note': text(payload.get('tax_exempt_note', ''), 'Tax-exempt reference', 1000),
            }
            conn.execute(
                """INSERT INTO customer_profiles(customer_id,account_type,company,po_number,locations,fleet_notes,brand_notes,authorized_buyers,tax_exempt_note,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(customer_id) DO UPDATE SET
                     account_type=excluded.account_type,company=excluded.company,po_number=excluded.po_number,
                     locations=excluded.locations,fleet_notes=excluded.fleet_notes,brand_notes=excluded.brand_notes,
                     authorized_buyers=excluded.authorized_buyers,tax_exempt_note=excluded.tax_exempt_note,updated_at=excluded.updated_at""",
                (who['id'], account_type, values['company'], values['po_number'], values['locations'],
                 values['fleet_notes'], values['brand_notes'], values['authorized_buyers'],
                 values['tax_exempt_note'], now()),
            )
            return {'ok': True, 'profile': profile_row(conn, who['id'])}

    @app.get('/api/customer/assets/{asset_id}')
    def customer_asset(asset_id: int, request: Request):
        with transaction(database) as conn:
            who = require_customer(conn, request)
            asset = conn.execute(
                """SELECT a.* FROM assets a JOIN customer_orders o ON o.job_id=a.job_id
                   WHERE a.id=? AND o.customer_id=? AND a.kind='artwork'""",
                (asset_id, who['id']),
            ).fetchone()
            if not asset:
                raise HTTPException(404, 'Saved artwork not found.')
            path = uploads / asset['stored_name']
            if not path.is_file():
                raise HTTPException(404, 'Saved artwork file is unavailable.')
            return FileResponse(path, media_type=asset['mime'], filename=asset['filename'])

    @app.post('/api/customer/orders/{job_id}/open')
    def open_order(job_id: int, request: Request):
        with transaction(database, True) as conn:
            who = require_customer(conn, request)
            if not conn.execute('SELECT 1 FROM customer_orders WHERE customer_id=? AND job_id=?', (who['id'], job_id)).fetchone():
                raise HTTPException(404, 'Order not found.')
            return {'portal_url': issue_portal(conn, job_id)}

    @app.post('/api/customer/orders/{job_id}/reorder')
    def reorder(job_id: int, request: Request):
        throttle(request, 'customer_reorder', 12, 3600)
        with transaction(database, True) as conn:
            who = require_customer(conn, request)
            old = conn.execute(
                'SELECT j.* FROM jobs j JOIN customer_orders o ON o.job_id=j.id WHERE j.id=? AND o.customer_id=?',
                (job_id, who['id']),
            ).fetchone()
            if not old:
                raise HTTPException(404, 'Order not found.')
            quote = json.loads(old['quote_snapshot'])
            items = [reorder_item(line) for line in quote.get('lines', []) if line.get('product_id')]
            if not items:
                raise HTTPException(409, 'This project cannot be reordered automatically. Ask the shop to duplicate it.')
            payload = {
                'customer_name': who['name'],
                'customer_email': who['email'],
                'phone': old['phone'],
                'title': ('Reorder - ' + old['title'])[:180],
                'notes': f'Reorder of {old["number"]}. Pricing is recalculated at current rates. Previous artwork is copied only as a reference and a new proof is still required.',
                'items': items,
            }
            new_id = create_job(conn, payload, source='customer', actor='Customer reorder')
            conn.execute('INSERT OR IGNORE INTO customer_orders(customer_id,job_id) VALUES(?,?)', (who['id'], new_id))
            for asset in conn.execute("SELECT * FROM assets WHERE job_id=? AND kind='artwork' ORDER BY id", (old['id'],)).fetchall():
                path = uploads / asset['stored_name']
                if not path.is_file():
                    continue
                save_asset(
                    conn, uploads, new_id, path.read_bytes(), asset['filename'], asset['mime'],
                    Path(asset['stored_name']).suffix or '.bin', 'artwork', 'Customer reorder reference',
                )
            link = issue_portal(conn, new_id)
            return {'job_id': new_id, 'number': f'JOB-{new_id:04d}', 'portal_url': link}

    @app.post('/api/wholesale/logout')
    def wholesale_logout(request: Request, payload: dict = Body(...)):
        token = text(payload.get('token', ''), 'Token', 200)
        with transaction(database, True) as conn:
            conn.execute('DELETE FROM wholesale_sessions WHERE token_hash=?', (digest(token),))
        return {'ok': True}
