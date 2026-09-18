"""Customer accounts are isolated from staff permissions and wholesale pricing."""
import secrets
import time
from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse
from .db import transaction, now
from .domain import stage
from .security import digest, password_hash, password_matches, email, text

COOKIE = 'signshop_customer'


def customer(conn, request):
    token = request.cookies.get(COOKIE, '')
    if not token or len(token) > 200:
        return None
    return conn.execute('SELECT c.id,c.name,c.email FROM customers c JOIN customer_sessions s ON c.id=s.customer_id WHERE s.token_hash=? AND s.expires_at>?', (digest(token), time.time())).fetchone()


def link_order(conn, request, job_id):
    who = customer(conn, request)
    if who:
        conn.execute('INSERT OR IGNORE INTO customer_orders(customer_id,job_id) VALUES(?,?)', (who['id'], job_id))


def install(app, database, production, throttle, issue_portal):
    with transaction(database, True) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE COLLATE NOCASE,password_hash TEXT NOT NULL,created_at TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS customer_sessions(token_hash TEXT PRIMARY KEY,customer_id INTEGER NOT NULL REFERENCES customers(id),expires_at REAL NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS customer_orders(customer_id INTEGER NOT NULL REFERENCES customers(id),job_id INTEGER NOT NULL REFERENCES jobs(id),PRIMARY KEY(customer_id,job_id))')

    @app.get('/api/customer')
    def profile(request: Request):
        with transaction(database) as conn:
            who = customer(conn, request)
            rows = [] if not who else conn.execute('SELECT j.* FROM jobs j JOIN customer_orders o ON o.job_id=j.id WHERE o.customer_id=? ORDER BY j.id DESC LIMIT 100', (who['id'],)).fetchall()
            orders = [{'id': row['id'], 'title': row['title'], 'stage': stage(conn, row), 'created_at': row['created_at']} for row in rows]
            return {'customer': dict(who) if who else None, 'orders': orders}

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

    @app.post('/api/customer/orders/{job_id}/open')
    def open_order(job_id: int, request: Request):
        with transaction(database, True) as conn:
            who = customer(conn, request)
            if not who or not conn.execute('SELECT 1 FROM customer_orders WHERE customer_id=? AND job_id=?', (who['id'], job_id)).fetchone():
                raise HTTPException(404, 'Order not found.')
            return {'portal_url': issue_portal(conn, job_id)}

    @app.post('/api/wholesale/logout')
    def wholesale_logout(request: Request, payload: dict = Body(...)):
        token = text(payload.get('token', ''), 'Token', 200)
        with transaction(database, True) as conn:
            conn.execute('DELETE FROM wholesale_sessions WHERE token_hash=?', (digest(token),))
        return {'ok': True}
