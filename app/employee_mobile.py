"""Employee mobile workspace; all prices and work gates remain server authoritative."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import secrets
from decimal import Decimal

from fastapi import Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from . import artwork_approval, crm, job_terms
from .db import audit, now, settings, transaction
from .domain import create_job, get_job, panel_photos, production_started, totals
from .images import MAX_UPLOAD, sanitize
from .mailer import notify_customer, notify_one
from .pricing import calculate, cent_round, number, public_quote
from .security import email, text
from .staff_icon_data import ICON_PNG_B64

SCHEMA = """
CREATE TABLE IF NOT EXISTS employee_surveys (
 id INTEGER PRIMARY KEY, client_key TEXT NOT NULL, contact_id INTEGER NOT NULL REFERENCES crm_contacts(id),
 job_id INTEGER REFERENCES jobs(id), title TEXT NOT NULL, address TEXT NOT NULL DEFAULT '',
 site_contact TEXT NOT NULL DEFAULT '', access_notes TEXT NOT NULL DEFAULT '',
 surface_notes TEXT NOT NULL DEFAULT '', removal_required INTEGER NOT NULL DEFAULT 0,
 measurements TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'draft',
 version INTEGER NOT NULL DEFAULT 1, payload_hash TEXT NOT NULL,
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(created_by,client_key)
);
CREATE INDEX IF NOT EXISTS employee_surveys_contact ON employee_surveys(contact_id,updated_at);
CREATE INDEX IF NOT EXISTS employee_surveys_job ON employee_surveys(job_id);
CREATE TABLE IF NOT EXISTS employee_survey_files (
 id INTEGER PRIMARY KEY, survey_id INTEGER NOT NULL REFERENCES employee_surveys(id),
 client_key TEXT NOT NULL, panel_key TEXT NOT NULL DEFAULT '', filename TEXT NOT NULL, stored_name TEXT NOT NULL UNIQUE,
 mime TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
 uploaded_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 UNIQUE(survey_id,client_key)
);
CREATE TABLE IF NOT EXISTS employee_estimate_requests (
 user_id INTEGER NOT NULL REFERENCES users(id), request_key TEXT NOT NULL,
 job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id), request_hash TEXT NOT NULL,
 PRIMARY KEY(user_id,request_key)
);
CREATE TABLE IF NOT EXISTS employee_quote_photos (
 id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id), quote_version INTEGER NOT NULL,
 line_index INTEGER NOT NULL, client_key TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 filename TEXT NOT NULL, stored_name TEXT NOT NULL, mime TEXT NOT NULL,
 sha256 TEXT NOT NULL, size INTEGER NOT NULL, uploaded_by INTEGER NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL, UNIQUE(job_id,quote_version,client_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS employee_quote_photo_line ON employee_quote_photos(job_id,quote_version,line_index) WHERE active=1;
CREATE TABLE IF NOT EXISTS employee_invoices (
 id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id),
 quote_version INTEGER NOT NULL, number TEXT UNIQUE, snapshot TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('draft','issued')),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 UNIQUE(job_id,quote_version,status)
);
"""

UNIT_FACTORS = {'in': Decimal(1), 'ft': Decimal(12), 'mm': Decimal(1) / Decimal('25.4'), 'cm': Decimal(1) / Decimal('2.54')}


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _id(value, label, optional=False):
    if optional and value in (None, ''):
        return None
    if type(value) is not int or value < 1:
        raise HTTPException(422, f'{label} must be a positive whole number.')
    return value


def _contact(conn, contact_id):
    row = conn.execute('SELECT * FROM crm_contacts WHERE id=?', (contact_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'CRM client not found.')
    return row


def _survey(conn, survey_id):
    row = conn.execute('SELECT * FROM employee_surveys WHERE id=?', (survey_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Survey not found.')
    return row


def _can_edit(row, user):
    if row['created_by'] != user['id'] and user['role'] != 'admin':
        raise HTTPException(403, 'Only the assigned survey employee or an admin can edit this survey.')
    if row['status'] != 'draft':
        raise HTTPException(409, 'This survey has been submitted. An admin must reopen it before changes.')


def _survey_dict(conn, row):
    item = dict(row)
    item.pop('payload_hash', None)
    item['measurements'] = json.loads(item['measurements'])
    item['removal_required'] = bool(item['removal_required'])
    contact = _contact(conn, row['contact_id'])
    item['client_name'] = contact['company'] or contact['name']
    item['files'] = [dict(f) for f in conn.execute(
        'SELECT id,panel_key,filename,mime,size,created_at FROM employee_survey_files WHERE survey_id=? ORDER BY id', (row['id'],))]
    return item


def _measurements(conn, values):
    if not isinstance(values, list) or len(values) > 100:
        raise HTTPException(422, 'Use up to 100 measured areas per survey.')
    checked = []
    keys = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise HTTPException(422, 'Invalid measured area.')
        unit = item.get('unit', 'in')
        if unit not in UNIT_FACTORS:
            raise HTTPException(422, 'Choose inches, feet, millimeters or centimeters.')
        width = number(item.get('width'), 'Survey width', '0.01', '100000')
        height = number(item.get('height'), 'Survey height', '0.01', '100000')
        quantity = number(item.get('quantity', 1), 'Survey quantity', '1', '100000')
        if quantity != quantity.to_integral():
            raise HTTPException(422, 'Survey quantity must be a whole number.')
        pid = _id(item.get('product_id'), 'Survey product', optional=True)
        if pid and not conn.execute('SELECT id FROM products WHERE id=? AND active=1', (pid,)).fetchone():
            raise HTTPException(422, 'Survey product is unavailable.')
        key = text(item.get('panel_key') or f'area-{index}', 'Panel identifier', 100, True)
        if key in keys:
            raise HTTPException(422, 'Each measured panel needs a different identifier.')
        keys.add(key)
        checked.append({
            'panel_key': key,
            'label': text(item.get('label', ''), 'Area label', 160, True),
            'width': str(width), 'height': str(height), 'unit': unit, 'quantity': int(quantity),
            'width_inches': str((width * UNIT_FACTORS[unit]).quantize(Decimal('0.0001'))),
            'height_inches': str((height * UNIT_FACTORS[unit]).quantize(Decimal('0.0001'))),
            'product_id': pid, 'notes': text(item.get('notes', ''), 'Area notes', 2000),
        })
    return checked


def _estimate(conn, payload):
    contact_id = _id(payload.get('contact_id'), 'Client')
    contact = _contact(conn, contact_id)
    wholesale = conn.execute('SELECT id FROM wholesale_clients WHERE email=? AND active=1', (contact['email'],)).fetchone() if contact['email'] else None
    items = payload.get('items', [])
    # Server rates are the only pricing input. Workflow overrides and financial
    # overrides are never forwarded from employee-submitted payloads.
    if not isinstance(items, list) or not 1 <= len(items) <= 30:
        raise HTTPException(422, 'An estimate needs 1 to 30 product lines.')
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(422, 'Invalid estimate item.')
        pid = _id(item.get('product_id'), 'Product')
        row = conn.execute('SELECT category FROM products WHERE id=? AND active=1', (pid,)).fetchone()
        if not row or row['category'] == 'Custom':
            raise HTTPException(422, 'Choose a configured catalog product; custom pricing needs owner review.')
    quote = calculate(conn, items, staff=True, wholesale_client_id=wholesale['id'] if wholesale else None)
    shop = settings(conn)
    tax_percent = number(shop.get('checkout_pickup_tax_percent', '0'), 'Configured sales tax', '0', '30')
    tax = cent_round(Decimal(quote['subtotal_cents']) * tax_percent / 100)
    survey_id = _id(payload.get('survey_id'), 'Survey', optional=True)
    survey = _survey(conn, survey_id) if survey_id else None
    if survey and survey['contact_id'] != contact_id:
        raise HTTPException(422, 'Survey belongs to a different CRM client.')
    return contact, quote, {'subtotal_cents': quote['subtotal_cents'], 'tax_cents': tax,
                           'total_cents': quote['subtotal_cents'] + tax, 'tax_percent': str(tax_percent),
                           'tax_reviewed': bool(shop.get('checkout_tax_reviewed')),
                           'owner_review_required': bool(quote['review_required'] or not shop.get('checkout_tax_reviewed') or (survey and survey['removal_required']))}


def _document_html(snapshot, status, kind, reference, order_url=None):
    esc = html.escape
    money = lambda value: f'${int(value) / 100:,.2f}'
    def specs(line):
        if line.get('coverage_label') or line.get('vehicle_type_label'):
            return ' · '.join(str(line[key]) for key in ('vehicle_type_label', 'coverage_label') if line.get(key))
        if line.get('finished_apparel'):
            return 'Garment sizes / placements shown in scope'
        if line.get('width') and line.get('height'):
            return f'{line["width"]} × {line["height"]} in'
        return str(line.get('unit') or 'Service')
    def photo(index):
        image = next((p for p in snapshot.get('panel_photos', []) if p['line_index'] == index), None)
        return (f'<br><img class="panel-photo" src="/api/quote-photos/{image["id"]}" alt="Panel reference photo">'
                '<br><small>Panel reference photo</small>') if image else ''
    lines = ''.join('<tr><td><strong>' + esc(str(line['name'])) + '</strong><br>' + esc(str(line.get('description', ''))) +
                    '<br><small>' + esc(specs(line)) + '</small>' + photo(index) + '</td><td>' + esc(str(line['quantity'])) +
                    '</td><td>' + money(line['sell_cents']) + '</td></tr>' for index, line in enumerate(snapshot['lines']))
    m = snapshot['totals']
    adjustment = m['merchandise_cents'] - sum(line['sell_cents'] for line in snapshot['lines'])
    title = kind.title()
    notice = ('Draft — owner review / customer scope acceptance required before this invoice can be issued.'
              if kind == 'invoice' and status == 'draft' else
              'Estimate — customer scope and artwork approval are required before production.' if kind == 'estimate' else
              'Issued invoice for the accepted order scope. Artwork and production requirements still apply.')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="robots" content="noindex,nofollow"><title>{esc(reference)} | {esc(snapshot['shop']['name'])}</title>
    <style>body{{font:15px system-ui,sans-serif;color:#172c2e;max-width:800px;margin:35px auto;padding:24px}}h1{{font-size:32px;margin:8px 0}}header{{border-bottom:5px solid #008b8b;padding-bottom:24px}}p{{line-height:1.6}}.muted,small{{color:#52696b}}table{{width:100%;border-collapse:collapse;margin:25px 0}}td,th{{text-align:left;padding:14px 8px;border-bottom:1px solid #dae5e4}}td:last-child,th:last-child{{text-align:right}}.totals{{margin-left:auto;max-width:320px}}.totals p{{display:flex;justify-content:space-between;margin:10px 0}}.total{{font-size:22px;border-top:2px solid #008b8b;padding-top:12px}}button{{background:#007e7e;color:white;border:0;border-radius:8px;padding:12px 20px;font:inherit}}@media print{{body{{margin:0;padding:0}}button{{display:none}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}</style>
    <style>.panel-photo{{max-width:200px;max-height:140px;object-fit:contain;margin:8px 0}}</style><script defer src="/static/employee-document.js"></script></head><body>
    <button id="print-document">Print / Save PDF</button>{f' <a href="{esc(order_url, quote=True)}">View order &amp; payment</a>' if order_url else ''}<header><p><strong>{esc(snapshot['shop']['name'])}</strong><br>{esc(snapshot['shop']['email'])} · {esc(snapshot['shop']['phone'])}</p>
    <h1>{title}{' · Draft' if status == 'draft' else ''}</h1><p>{esc(reference)} · {esc(snapshot['created_at'][:10])} · Quote version {snapshot['quote_version']}</p></header>
    <p><strong>Bill to: {esc(snapshot['customer_name'])}</strong><br>{esc(snapshot['customer_email'])}<br>{esc(snapshot['phone'])}</p>
    <h2>{esc(snapshot['title'])}</h2><p class="muted">{esc(notice)}</p>
    <table><thead><tr><th>Product / scope</th><th>Qty</th><th>Amount</th></tr></thead><tbody>{lines}</tbody></table>
    <div class="totals"><p><span>Products & services</span><strong>{money(sum(line['sell_cents'] for line in snapshot['lines']))}</strong></p>
    {f'<p><span>Adjustments / rewards</span><strong>{money(adjustment)}</strong></p>' if adjustment else ''}
    <p><span>Delivery</span><strong>{money(m['shipping_cents'])}</strong></p><p><span>Sales tax included below</span><strong>{money(m['tax_cents'])}</strong></p>
    <p class="total"><span>Total</span><strong>{money(m['total_cents'])}</strong></p><p><span>Paid when created</span><strong>{money(m['paid_cents'])}</strong></p>
    <p><span>Balance when created</span><strong>{money(m['balance_cents'])}</strong></p><p><span>Required deposit</span><strong>{money(m['deposit_cents'])}</strong></p></div>
    <p class="muted">{esc(snapshot['terms_notice'])} <a href="/terms">Full project terms</a></p></body></html>'''


def _document_snapshot(conn, job):
    shop = settings(conn)
    quote = public_quote(json.loads(job['quote_snapshot']))
    m = totals(conn, job)
    return {'title': job['title'], 'customer_name': job['customer_name'], 'customer_email': job['customer_email'],
            'phone': job['phone'], 'quote_version': job['quote_version'], 'lines': quote['lines'],
            'totals': {k: m[k] for k in ('merchandise_cents','shipping_cents','tax_cents','total_cents','paid_cents','balance_cents','deposit_cents')},
            'shop': {'name': shop['shop_name'], 'email': shop['contact_email'], 'phone': shop['contact_phone']},
            'panel_photos': panel_photos(conn, job), 'created_at': now(), 'terms_notice': job_terms.PROOF_REVIEW_NOTICE}


def _invoice_record(conn, job, user, who):
    status = 'issued' if job['published'] and job['charges_verified'] and job['accepted_version'] == job['quote_version'] else 'draft'
    prior = conn.execute('SELECT * FROM employee_invoices WHERE job_id=? AND quote_version=? AND status=?', (job['id'], job['quote_version'], status)).fetchone()
    if prior:
        return prior
    iid = conn.execute('INSERT INTO employee_invoices(job_id,quote_version,snapshot,status,created_by,created_at) VALUES(?,?,?,?,?,?)',
                       (job['id'], job['quote_version'], json.dumps(_document_snapshot(conn, job)), status, user['id'], now())).lastrowid
    reference = f'INV-{now()[:4]}-{iid:04d}'
    conn.execute('UPDATE employee_invoices SET number=? WHERE id=?', (reference, iid))
    audit(conn, job['id'], who, 'invoice.created', {'invoice_id': iid, 'number': reference, 'status': status})
    return conn.execute('SELECT * FROM employee_invoices WHERE id=?', (iid,)).fetchone()


def _invoice_result(row):
    return {'invoice_id': row['id'], 'number': row['number'], 'status': row['status']}


def _review_invoice_request(conn, job, payload):
    if job['archived']:
        raise HTTPException(409, 'This project is archived.')
    if type(payload.get('version')) is not int or payload['version'] != job['quote_version']:
        raise HTTPException(409, 'The quote changed. Reload and review the latest version.')
    money = totals(conn, job)
    if type(payload.get('total_cents')) is not int or payload['total_cents'] != money['total_cents']:
        raise HTTPException(409, 'The price changed. Reload and review the current total before sending an invoice.')
    recipient = email(job['customer_email'])
    if payload.get('recipient') != recipient:
        raise HTTPException(409, 'The client email changed. Reload and confirm the invoice recipient.')
    if payload.get('confirm') is not True:
        raise HTTPException(422, 'Confirm the client approved this scope and total before sending the invoice.')
    return money, recipient


def _check_issued_invoice(row, job, money):
    snapshot = json.loads(row['snapshot'])
    if row['status'] != 'issued' or not job['published'] or not job['charges_verified'] or job['accepted_version'] != job['quote_version']:
        raise HTTPException(409, 'Review the charges and record client price approval before sending an issued invoice.')
    if row['quote_version'] != job['quote_version'] or snapshot['totals']['total_cents'] != money['total_cents'] or snapshot['customer_email'] != job['customer_email']:
        raise HTTPException(409, 'This invoice is for an older scope, price or client email. Revise the quote before issuing an updated invoice.')


def install(app, database, uploads, require_staff, require_admin, actor, issue_email_portal, static, access_job):
    with transaction(database, True) as conn:
        conn.executescript(SCHEMA)
        if 'panel_key' not in {row['name'] for row in conn.execute('PRAGMA table_info(employee_survey_files)')}:
            conn.execute("ALTER TABLE employee_survey_files ADD COLUMN panel_key TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS employee_survey_photo_panel ON employee_survey_files(survey_id,panel_key) WHERE panel_key<>''")

    @app.get('/staff/app', response_class=HTMLResponse)
    def employee_app():
        return HTMLResponse((static / 'employee.html').read_text(), headers={'X-Robots-Tag': 'noindex, nofollow'})

    @app.get('/staff/sw.js')
    def employee_worker():
        return FileResponse(static / 'employee-sw.js', media_type='application/javascript', headers={'Service-Worker-Allowed': '/staff/', 'Cache-Control': 'no-cache'})

    @app.get('/apple-touch-icon.png')
    @app.get('/apple-touch-icon-precomposed.png')
    @app.get('/staff/apple-touch-icon.png')
    @app.get('/staff/apple-touch-icon-20261001.png')
    @app.get('/staff/icon.png')
    def employee_icon():
        if hasattr(app.state, 'company_icon'):
            return app.state.company_icon()
        return Response(base64.b64decode(ICON_PNG_B64), media_type='image/png', headers={'Cache-Control': 'public, max-age=31536000, immutable'})

    @app.get('/api/staff/clients')
    def clients(request: Request, q: str = '', user=Depends(require_staff)):
        query = text(q, 'Client search', 200).lower()
        with transaction(database, True) as conn:
            crm.sync_jobs(conn)
            rows = conn.execute('SELECT id,name,company,email,phone,status,source,updated_at FROM crm_contacts ORDER BY updated_at DESC,id DESC').fetchall()
        return {'contacts': [dict(row) for row in rows if query in ' '.join(str(row[k]) for k in ('name','company','email','phone')).lower()][:1000]}

    @app.get('/api/staff/clients/{contact_id}')
    def client_detail(contact_id: int, request: Request, user=Depends(require_staff)):
        with transaction(database, True) as conn:
            detail = crm._detail(conn, contact_id)
            # CRM notes are operational; reminder controls remain admin-only.
            return {k: detail[k] for k in ('id','name','company','email','phone','status','notes','source','jobs')}

    @app.post('/api/staff/clients')
    def add_client(request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        name = text(payload.get('name', ''), 'Client name', 120, True)
        company = text(payload.get('company', ''), 'Company', 160)
        address = email(payload['email']) if payload.get('email') else ''
        phone = text(payload.get('phone', ''), 'Phone', 60)
        if not address and not phone:
            raise HTTPException(422, 'Enter an email or phone number.')
        notes = text(payload.get('notes', ''), 'Client notes', 10000)
        with transaction(database, True) as conn:
            crm.sync_jobs(conn)
            prior = conn.execute('SELECT id FROM crm_contacts WHERE lower(email)=lower(?) AND email<>\'\'', (address,)).fetchone()
            if prior:
                raise HTTPException(409, 'This email already belongs to a CRM client. Select the existing client.')
            stamp = now()
            cid = conn.execute('INSERT INTO crm_contacts(name,company,email,phone,notes,source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                               (name, company, address, phone, notes, 'Employee app', stamp, stamp)).lastrowid
            audit(conn, None, actor(user), 'crm.contact_created', {'contact_id': cid, 'source': 'employee_app'})
            return {'id': cid, 'name': name, 'company': company, 'email': address, 'phone': phone, 'status': 'new_lead'}

    @app.patch('/api/staff/clients/{contact_id}')
    def update_client(contact_id: int, request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        with transaction(database, True) as conn:
            current = _contact(conn, contact_id)
            address = email(payload['email']) if payload.get('email') else current['email']
            values = (text(payload.get('name', current['name']), 'Client name', 120, True),
                      text(payload.get('company', current['company']), 'Company', 160), address,
                      text(payload.get('phone', current['phone']), 'Phone', 60),
                      text(payload.get('notes', current['notes']), 'Client notes', 10000), now(), contact_id)
            if not address and not values[3]:
                raise HTTPException(422, 'Enter an email or phone number.')
            conn.execute('UPDATE crm_contacts SET name=?,company=?,email=?,phone=?,notes=?,updated_at=? WHERE id=?', values)
            audit(conn, None, actor(user), 'crm.contact_updated', {'contact_id': contact_id, 'source': 'employee_app'})
            return {'ok': True}

    @app.get('/api/staff/jobs/{job_id}/site-survey/review')
    def review_job_surveys(job_id: int, user=Depends(require_admin)):
        with transaction(database) as conn:
            job = get_job(conn, job_id)
            surveys = [_survey_dict(conn, row) for row in conn.execute('SELECT * FROM employee_surveys WHERE job_id=? ORDER BY id', (job_id,))]
            for survey in surveys:
                for file in survey['files']:
                    file['url'] = f'/api/staff/jobs/{job_id}/site-survey/files/{file["id"]}'
            return {'surveys': surveys, 'quote_version': job['quote_version'],
                    'quote': public_quote(json.loads(job['quote_snapshot']))}

    @app.get('/api/staff/jobs/{job_id}/site-survey/files/{file_id}')
    def review_survey_file(job_id: int, file_id: int, user=Depends(require_admin)):
        with transaction(database) as conn:
            get_job(conn, job_id)
            file = conn.execute('SELECT f.* FROM employee_survey_files f JOIN employee_surveys s ON s.id=f.survey_id WHERE f.id=? AND s.job_id=?', (file_id, job_id)).fetchone()
            if not file or not (uploads / file['stored_name']).is_file():
                raise HTTPException(404, 'Survey file not found for this project.')
            return FileResponse(uploads / file['stored_name'], media_type=file['mime'], filename=file['filename'], content_disposition_type='inline',
                                headers={'Cache-Control': 'no-store', 'Content-Security-Policy': "sandbox; default-src 'none'"})

    @app.get('/api/staff/surveys')
    def surveys(request: Request, job_id: int | None = None, user=Depends(require_staff)):
        with transaction(database) as conn:
            where, params = (' WHERE job_id=?', (job_id,)) if job_id else ('', ())
            rows = conn.execute('SELECT * FROM employee_surveys' + where + ' ORDER BY updated_at DESC,id DESC LIMIT 500', params).fetchall()
            return {'surveys': [_survey_dict(conn, row) for row in rows]}

    @app.get('/api/staff/surveys/{survey_id}')
    def survey_detail(survey_id: int, request: Request, user=Depends(require_staff)):
        with transaction(database) as conn:
            return _survey_dict(conn, _survey(conn, survey_id))

    @app.post('/api/staff/surveys')
    def save_survey(request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        if payload.get('user_id') not in (None, user['id']):
            raise HTTPException(403, 'This device draft belongs to another staff sign-in.')
        key = text(payload.get('client_key', ''), 'Draft identifier', 100, True)
        with transaction(database, True) as conn:
            sid = _id(payload.get('id'), 'Survey', optional=True)
            current = _survey(conn, sid) if sid else conn.execute('SELECT * FROM employee_surveys WHERE created_by=? AND client_key=?', (user['id'], key)).fetchone()
            contact_id = _id(payload.get('contact_id'), 'Client')
            _contact(conn, contact_id)
            job_id = _id(payload.get('job_id'), 'Project', optional=True)
            if job_id:
                job = get_job(conn, job_id)
                if job['archived'] or production_started(conn, job_id):
                    raise HTTPException(409, 'Survey changes for an archived or producing job need a new project.')
                linked = conn.execute('SELECT contact_id FROM crm_contact_jobs WHERE job_id=?', (job_id,)).fetchone()
                if linked and linked['contact_id'] != contact_id:
                    raise HTTPException(422, 'This project belongs to a different CRM client.')
            clean = {'contact_id': contact_id, 'job_id': job_id,
                     'title': text(payload.get('title', ''), 'Survey title', 180, True),
                     'address': text(payload.get('address', ''), 'Site address', 500),
                     'site_contact': text(payload.get('site_contact', ''), 'On-site contact', 300),
                     'access_notes': text(payload.get('access_notes', ''), 'Access / installation notes', 5000),
                     'surface_notes': text(payload.get('surface_notes', ''), 'Surface / condition notes', 5000),
                     'removal_required': payload.get('removal_required', False),
                     'measurements': _measurements(conn, payload.get('measurements', []))}
            if type(clean['removal_required']) is not bool:
                raise HTTPException(422, 'Removal selection must be true or false.')
            fingerprint = _fingerprint(clean)
            if current:
                if current['created_by'] != user['id'] and user['role'] != 'admin':
                    raise HTTPException(403, 'Only the survey employee or an admin can save this survey.')
                # Retried saves after a dropped response are harmless, including
                # retries after submission. Different stale writes never overwrite.
                if current['payload_hash'] == fingerprint:
                    return _survey_dict(conn, current)
                _can_edit(current, user)
                if payload.get('version') != current['version']:
                    raise HTTPException(409, 'Survey changed elsewhere. Keep your phone draft and reload the current survey.')
                if (current['contact_id'], current['job_id']) != (contact_id, job_id):
                    raise HTTPException(422, 'A saved survey cannot move to another client or project.')
                sid = current['id']
                conn.execute('UPDATE employee_surveys SET title=?,address=?,site_contact=?,access_notes=?,surface_notes=?,removal_required=?,measurements=?,payload_hash=?,version=version+1,updated_at=? WHERE id=?',
                             (clean['title'], clean['address'], clean['site_contact'], clean['access_notes'], clean['surface_notes'], int(clean['removal_required']), json.dumps(clean['measurements']), fingerprint, now(), sid))
            else:
                sid = conn.execute('INSERT INTO employee_surveys(client_key,contact_id,job_id,title,address,site_contact,access_notes,surface_notes,removal_required,measurements,payload_hash,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                   (key, contact_id, job_id, clean['title'], clean['address'], clean['site_contact'], clean['access_notes'], clean['surface_notes'], int(clean['removal_required']), json.dumps(clean['measurements']), fingerprint, user['id'], now(), now())).lastrowid
            if job_id:
                artwork_approval.request_survey(conn, job_id, clean['address'], 'Employee survey measurements awaiting review.')
            audit(conn, job_id, actor(user), 'employee_survey.saved', {'survey_id': sid, 'areas': len(clean['measurements'])})
            return _survey_dict(conn, _survey(conn, sid))

    @app.post('/api/staff/surveys/{survey_id}/files')
    def survey_upload(survey_id: int, request: Request, file: UploadFile = File(...), client_key: str = Form(...), panel_key: str = Form(''), user=Depends(require_staff)):
        key = text(client_key, 'Attachment identifier', 100, True)
        panel_key = text(panel_key, 'Panel identifier', 100)
        raw, name, mime, suffix = sanitize(file.file.read(MAX_UPLOAD + 1), file.filename or 'site-photo')
        if panel_key and not mime.startswith('image/'):
            raise HTTPException(422, 'A panel photo must be PNG or JPEG.')
        sha = hashlib.sha256(raw).hexdigest()
        path = None
        try:
            with transaction(database, True) as conn:
                survey = _survey(conn, survey_id)
                prior = conn.execute('SELECT * FROM employee_survey_files WHERE survey_id=? AND client_key=?', (survey_id, key)).fetchone()
                if prior:
                    if prior['sha256'] != sha or prior['panel_key'] != panel_key:
                        raise HTTPException(409, 'Attachment identifier already used for a different file.')
                    return {'id': prior['id'], 'filename': prior['filename']}
                _can_edit(survey, user)
                panels = {m.get('panel_key') or f'area-{index}' for index, m in enumerate(json.loads(survey['measurements']))}
                if panel_key and panel_key not in panels:
                    raise HTTPException(422, 'Choose an existing measured panel for this photo.')
                if panel_key and conn.execute('SELECT 1 FROM employee_survey_files WHERE survey_id=? AND panel_key=?', (survey_id, panel_key)).fetchone():
                    raise HTTPException(409, 'Remove the current panel photo before attaching another.')
                count = conn.execute('SELECT COUNT(*) FROM employee_survey_files WHERE survey_id=?', (survey_id,)).fetchone()[0]
                if count >= 50:
                    raise HTTPException(422, 'Use up to 50 photos / files per survey.')
                stored = secrets.token_hex(24) + suffix
                path = uploads / stored
                path.write_bytes(raw)
                path.chmod(0o600)
                fid = conn.execute('INSERT INTO employee_survey_files(survey_id,client_key,panel_key,filename,stored_name,mime,sha256,size,uploaded_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                   (survey_id, key, panel_key, name, stored, mime, sha, len(raw), user['id'], now())).lastrowid
                audit(conn, survey['job_id'], actor(user), 'employee_survey.file_attached', {'survey_id': survey_id, 'file_id': fid})
                return {'id': fid, 'filename': name}
        except Exception:
            if path:
                path.unlink(missing_ok=True)
            raise

    @app.get('/api/staff/surveys/{survey_id}/files/{file_id}')
    def survey_file(survey_id: int, file_id: int, request: Request, user=Depends(require_staff)):
        with transaction(database) as conn:
            _survey(conn, survey_id)
            row = conn.execute('SELECT * FROM employee_survey_files WHERE id=? AND survey_id=?', (file_id, survey_id)).fetchone()
            if not row or not (uploads / row['stored_name']).is_file():
                raise HTTPException(404, 'Survey attachment not found.')
            return FileResponse(uploads / row['stored_name'], media_type=row['mime'], filename=row['filename'], content_disposition_type='inline')

    @app.delete('/api/staff/surveys/{survey_id}/files/{file_id}')
    def remove_survey_file(survey_id: int, file_id: int, request: Request, user=Depends(require_staff)):
        stored = None
        with transaction(database, True) as conn:
            survey = _survey(conn, survey_id)
            _can_edit(survey, user)
            row = conn.execute('SELECT * FROM employee_survey_files WHERE id=? AND survey_id=?', (file_id, survey_id)).fetchone()
            if row:
                conn.execute('DELETE FROM employee_survey_files WHERE id=?', (file_id,))
                if not conn.execute('SELECT 1 FROM employee_quote_photos WHERE stored_name=?', (row['stored_name'],)).fetchone():
                    stored = row['stored_name']
                audit(conn, survey['job_id'], actor(user), 'employee_survey.file_removed', {'file_id': file_id})
        if stored:
            (uploads / stored).unlink(missing_ok=True)
        return {'ok': True}

    @app.post('/api/staff/surveys/{survey_id}/action')
    def survey_action(survey_id: int, request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        operation = payload.get('action')
        with transaction(database, True) as conn:
            survey = _survey(conn, survey_id)
            if payload.get('version') != survey['version']:
                raise HTTPException(409, 'Survey changed. Reload before updating its status.')
            if operation == 'submit':
                _can_edit(survey, user)
                if not json.loads(survey['measurements']) or not survey['address']:
                    raise HTTPException(422, 'Add a site address and at least one measured area before submitting.')
                status = 'submitted'
            elif operation in ('verify', 'reopen'):
                if user['role'] != 'admin':
                    raise HTTPException(403, 'Owner/admin review required to verify or reopen measurements.')
                if operation == 'verify' and (survey['status'] != 'submitted' or payload.get('confirm') is not True):
                    raise HTTPException(422, 'Submit the survey first and confirm its measurements match the project scope.')
                status = 'verified' if operation == 'verify' else 'draft'
            else:
                raise HTTPException(422, 'Choose submit, verify or reopen.')
            if survey['job_id']:
                job = get_job(conn, survey['job_id'])
                if job['archived'] or production_started(conn, job['id']):
                    raise HTTPException(409, 'Survey status cannot change after production starts or the job is archived.')
                if status == 'verified':
                    # Another outstanding survey on this job must still block print.
                    remaining = conn.execute("SELECT id FROM employee_surveys WHERE job_id=? AND id<>? AND status!='verified' LIMIT 1", (job['id'], survey_id)).fetchone()
                    if not remaining:
                        conn.execute("UPDATE job_site_surveys SET status='complete',note=?,updated_at=? WHERE job_id=?",
                                     (f'Owner verified field survey #{survey_id}; measurements reviewed against project scope.', now(), job['id']))
                else:
                    artwork_approval.request_survey(conn, job['id'], survey['address'], 'Field survey needs verified measurements.')
            conn.execute('UPDATE employee_surveys SET status=?,version=version+1,updated_at=? WHERE id=?', (status, now(), survey_id))
            audit(conn, survey['job_id'], actor(user), 'employee_survey.' + operation, {'survey_id': survey_id})
            return _survey_dict(conn, _survey(conn, survey_id))

    @app.post('/api/staff/estimates/calculate')
    def estimate_price(request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        with transaction(database) as conn:
            _, quote, money = _estimate(conn, payload)
            result = {'quote': public_quote(quote), 'totals': money}
            return result | {'fingerprint': _fingerprint(result)}

    @app.post('/api/staff/estimates')
    def new_estimate(request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        key = text(payload.get('request_key', ''), 'Estimate identifier', 100, True)
        request_hash = _fingerprint({k: v for k, v in payload.items() if k != 'request_key'})
        with transaction(database, True) as conn:
            prior = conn.execute('SELECT * FROM employee_estimate_requests WHERE user_id=? AND request_key=?', (user['id'], key)).fetchone()
            if prior:
                if prior['request_hash'] != request_hash:
                    raise HTTPException(409, 'Estimate identifier already used. Reload the saved project.')
                return {'job_id': prior['job_id'], 'existing': True}
            contact, quote, money = _estimate(conn, payload)
            if not contact['email']:
                raise HTTPException(422, 'Add an email to this CRM client before creating an order estimate.')
            expected = {'quote': public_quote(quote), 'totals': money}
            if payload.get('fingerprint') != _fingerprint(expected):
                raise HTTPException(409, 'Pricing changed. Recalculate the estimate before saving.')
            survey_id = _id(payload.get('survey_id'), 'Survey', optional=True)
            if survey_id:
                survey = _survey(conn, survey_id)
                if survey['contact_id'] != contact['id']:
                    raise HTTPException(422, 'Survey belongs to a different client.')
                if survey['job_id']:
                    raise HTTPException(409, 'Survey already belongs to a project. Create a new survey for a new estimate.')
            references = []
            for index, item in enumerate(payload['items']):
                fid = _id(item.get('survey_file_id'), 'Panel photo', optional=True)
                if fid:
                    photo = conn.execute('SELECT * FROM employee_survey_files WHERE id=? AND survey_id=?', (fid, survey_id)).fetchone()
                    if not photo or not photo['mime'].startswith('image/'):
                        raise HTTPException(422, 'Choose a photo from the survey attached to this estimate.')
                    references.append((index, photo))
            clean = {'title': payload.get('title', ''), 'notes': payload.get('notes', ''),
                     'customer_name': contact['name'], 'customer_email': contact['email'], 'phone': contact['phone'],
                     'items': payload.get('items'), '_wholesale_client_id': quote.get('wholesale') and conn.execute('SELECT id FROM wholesale_clients WHERE email=? AND active=1', (contact['email'],)).fetchone()['id']}
            job_id = create_job(conn, clean, source='staff', actor=actor(user))
            conn.execute('UPDATE jobs SET assignee_id=?,tax_cents=?,charges_verified=? WHERE id=?', (user['id'], money['tax_cents'], int(not money['owner_review_required']), job_id))
            conn.execute('INSERT INTO crm_contact_jobs(contact_id,job_id) VALUES(?,?)', (contact['id'], job_id))
            conn.execute('INSERT INTO employee_estimate_requests(user_id,request_key,job_id,request_hash) VALUES(?,?,?,?)', (user['id'], key, job_id, request_hash))
            for index, photo in references:
                conn.execute('INSERT INTO employee_quote_photos(job_id,quote_version,line_index,client_key,filename,stored_name,mime,sha256,size,uploaded_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                             (job_id, 1, index, f'survey-{photo["id"]}', photo['filename'], photo['stored_name'], photo['mime'], photo['sha256'], photo['size'], user['id'], now()))
            if survey_id:
                conn.execute("UPDATE employee_surveys SET job_id=?,status=CASE WHEN status='verified' THEN 'submitted' ELSE status END,version=version+1,updated_at=? WHERE id=?", (job_id, now(), survey_id))
                artwork_approval.request_survey(conn, job_id, survey['address'], f'Field survey #{survey_id} linked to this estimate.')
            audit(conn, job_id, actor(user), 'employee_estimate.created', {'contact_id': contact['id'], 'survey_id': survey_id})
            return {'job_id': job_id, 'owner_review_required': money['owner_review_required']}

    def editable_photo_job(conn, job_id, version, line_index=None):
        job = get_job(conn, job_id)
        if version != job['quote_version']:
            raise HTTPException(409, 'Quote changed. Reload the project before updating panel photos.')
        if job['archived'] or production_started(conn, job_id) or job['accepted_version'] == job['quote_version']:
            raise HTTPException(409, 'Panel photos are locked for an accepted, producing or archived project.')
        if line_index is not None and not 0 <= line_index < len(json.loads(job['quote_snapshot'])['lines']):
            raise HTTPException(422, 'Choose an existing quote panel.')
        return job

    @app.post('/api/staff/jobs/{job_id}/panel-photos')
    def quote_photo_upload(job_id: int, request: Request, file: UploadFile = File(...), client_key: str = Form(...),
                           line_index: int = Form(...), version: int = Form(...), user=Depends(require_staff)):
        key = text(client_key, 'Photo identifier', 100, True)
        raw, name, mime, suffix = sanitize(file.file.read(MAX_UPLOAD + 1), file.filename or 'panel-photo')
        if not mime.startswith('image/'):
            raise HTTPException(422, 'A panel photo must be PNG or JPEG.')
        sha = hashlib.sha256(raw).hexdigest()
        path = None
        try:
            with transaction(database, True) as conn:
                job = get_job(conn, job_id)
                prior = conn.execute('SELECT * FROM employee_quote_photos WHERE job_id=? AND quote_version=? AND client_key=?', (job_id, version, key)).fetchone()
                if prior:
                    if prior['sha256'] != sha or prior['line_index'] != line_index:
                        raise HTTPException(409, 'Photo identifier already used for a different panel or image.')
                    return {'id': prior['id'], 'filename': prior['filename']}
                editable_photo_job(conn, job_id, version, line_index)
                stored = secrets.token_hex(24) + suffix
                path = uploads / stored
                path.write_bytes(raw)
                path.chmod(0o600)
                conn.execute('UPDATE employee_quote_photos SET active=0 WHERE job_id=? AND quote_version=? AND line_index=?', (job_id, version, line_index))
                fid = conn.execute('INSERT INTO employee_quote_photos(job_id,quote_version,line_index,client_key,filename,stored_name,mime,sha256,size,uploaded_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                                   (job_id, version, line_index, key, name, stored, mime, sha, len(raw), user['id'], now())).lastrowid
                audit(conn, job_id, actor(user), 'quote.panel_photo_attached', {'photo_id': fid, 'line_index': line_index})
                return {'id': fid, 'filename': name}
        except Exception:
            if path:
                path.unlink(missing_ok=True)
            raise

    @app.delete('/api/staff/jobs/{job_id}/panel-photos/{photo_id}')
    def remove_quote_photo(job_id: int, photo_id: int, request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        with transaction(database, True) as conn:
            job = editable_photo_job(conn, job_id, payload.get('version'))
            conn.execute('UPDATE employee_quote_photos SET active=0 WHERE id=? AND job_id=? AND quote_version=?', (photo_id, job_id, job['quote_version']))
            audit(conn, job_id, actor(user), 'quote.panel_photo_removed', {'photo_id': photo_id})
            return {'ok': True}

    @app.get('/api/quote-photos/{photo_id}')
    def quote_photo_file(photo_id: int, request: Request):
        with transaction(database) as conn:
            row = conn.execute('SELECT * FROM employee_quote_photos WHERE id=?', (photo_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Panel photo not found.')
            job, _ = access_job(conn, request, row['job_id'])
            if not request.state.user and not job['published']:
                raise HTTPException(404, 'Panel photo not found.')
            if not (uploads / row['stored_name']).is_file():
                raise HTTPException(404, 'Panel photo is missing. Contact the shop.')
            return FileResponse(uploads / row['stored_name'], media_type=row['mime'], filename=row['filename'], content_disposition_type='inline',
                                headers={'Cache-Control': 'no-store', 'Content-Security-Policy': "sandbox; default-src 'none'"})

    @app.post('/api/staff/estimates/{job_id}/send')
    def send_estimate(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if payload.get('version') != job['quote_version'] or payload.get('reviewed') is not True:
                raise HTTPException(409, 'Review the current quote version before sending.')
            if job['archived'] or not job['charges_verified']:
                raise HTTPException(409, 'Owner must review tax, installation and custom scope before sending this estimate.')
            quote = json.loads(job['quote_snapshot'])
            if user['role'] != 'admin' and quote['review_required']:
                raise HTTPException(403, 'Owner review required to send custom or installation estimates.')
            conn.execute('UPDATE jobs SET published=1 WHERE id=?', (job_id,))
            link = issue_email_portal(conn, job_id)
            audit(conn, job_id, actor(user), 'quote.published', {'version': job['quote_version']}, True)
            version, reference = job['quote_version'], job['number']
            shop_name = settings(conn)['shop_name']
        sent = notify_customer(database, job_id, f'quote_ready_{version}', f'Quote ready for {reference} | {shop_name}',
                               'Your quote is ready', 'Review your project estimate, scope and terms on your private order page.', link)
        return {'ok': True, 'email_sent': bool(sent), 'portal_url': link}

    @app.get('/api/staff/jobs/{job_id}/estimate-document', response_class=HTMLResponse)
    def estimate_document(job_id: int, request: Request, user=Depends(require_staff)):
        with transaction(database) as conn:
            job = get_job(conn, job_id)
            return HTMLResponse(_document_html(_document_snapshot(conn, job), 'issued' if job['published'] else 'draft', 'estimate', job['number']))

    def deliver_invoice(invoice_id, payload, user):
        with transaction(database, True) as conn:
            invoice = conn.execute('SELECT * FROM employee_invoices WHERE id=?', (invoice_id,)).fetchone()
            if not invoice:
                raise HTTPException(404, 'Invoice not found.')
            job = get_job(conn, invoice['job_id'])
            money, recipient = _review_invoice_request(conn, job, payload)
            _check_issued_invoice(invoice, job, money)
            link = issue_email_portal(conn, job['id']) + f'&invoice={invoice_id}'
            snapshot = json.loads(invoice['snapshot'])
            message = '\n'.join([f'Invoice {invoice["number"]} for {job["title"]}',
                                 *[f'{line["name"]} · Qty {line["quantity"]} · ${line["sell_cents"]/100:,.2f}' for line in snapshot['lines']],
                                 f'Total including tax: ${money["total_cents"]/100:,.2f}',
                                 f'Current balance: ${money["balance_cents"]/100:,.2f}',
                                 'Open your private invoice to view the complete scope or print / save a PDF. Artwork and production approvals still apply.'])
            result = _invoice_result(invoice)
            job_id, shop_name = job['id'], snapshot['shop']['name']
        sent = notify_one(database, job_id, f'invoice_ready_{invoice_id}', recipient, 'customer',
                          f'Invoice {result["number"]} | {shop_name}', 'Your invoice is ready', message, link,
                          'View invoice', force=payload.get('resend') is True)
        with transaction(database, True) as conn:
            audit(conn, job_id, actor(user), 'invoice.email_sent' if sent else 'invoice.email_failed',
                  {'invoice_id': invoice_id, 'recipient': recipient})
        return {**result, 'email_sent': bool(sent), 'recipient': recipient, 'portal_url': link}

    @app.post('/api/staff/jobs/{job_id}/on-site-invoice')
    def on_site_invoice(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        signer = text(payload.get('customer_name', ''), 'Client approving the price', 120, True)
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            money, _ = _review_invoice_request(conn, job, payload)
            if not job['charges_verified']:
                if user['role'] != 'admin':
                    raise HTTPException(403, 'An owner must review tax, delivery, installation and custom charges before issuing this invoice.')
                if payload.get('charges_reviewed') is not True:
                    raise HTTPException(422, 'Confirm the displayed tax, delivery, installation and custom charges have been reviewed.')
                conn.execute('UPDATE jobs SET charges_verified=1 WHERE id=?', (job_id,))
                audit(conn, job_id, actor(user), 'quote.charges_verified', {'version': job['quote_version'], 'source': 'on_site_invoice'})
            if job['accepted_version'] != job['quote_version']:
                if production_started(conn, job_id):
                    raise HTTPException(409, 'New scope approval cannot be recorded after production starts.')
                conn.execute('UPDATE jobs SET published=1,accepted_version=quote_version,accepted_name=?,accepted_at=? WHERE id=?', (signer, now(), job_id))
                audit(conn, job_id, actor(user), 'quote.accepted', {'version': job['quote_version'], 'total_cents': money['total_cents'],
                      'method': 'in_person', 'client_name': signer, 'recorded_by': user['id']}, True)
            job = get_job(conn, job_id)
            invoice = _invoice_record(conn, job, user, actor(user))
            _check_issued_invoice(invoice, job, money)
            invoice_id = invoice['id']
        return deliver_invoice(invoice_id, payload, user)

    @app.post('/api/staff/invoices/{invoice_id}/send')
    def send_invoice(invoice_id: int, request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        return deliver_invoice(invoice_id, payload, user)

    @app.post('/api/staff/jobs/{job_id}/invoices')
    def create_invoice(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_staff)):
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if job['archived'] or payload.get('version') != job['quote_version'] or payload.get('confirm') is not True:
                raise HTTPException(409, 'Review the current, active order before creating its invoice.')
            return _invoice_result(_invoice_record(conn, job, user, actor(user)))

    @app.get('/api/invoices/{invoice_id}', response_class=HTMLResponse)
    def client_invoice_document(invoice_id: int, request: Request):
        with transaction(database) as conn:
            row = conn.execute('SELECT * FROM employee_invoices WHERE id=?', (invoice_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Invoice not found.')
            job, _ = access_job(conn, request, row['job_id'])
            if not request.state.user and (row['status'] != 'issued' or not job['published']):
                raise HTTPException(404, 'Invoice not found.')
            order_url = f'/staff#job/{job["id"]}' if request.state.user else '/portal'
            return HTMLResponse(_document_html(json.loads(row['snapshot']), row['status'], 'invoice', row['number'], order_url),
                                headers={'Cache-Control': 'private, no-store', 'X-Robots-Tag': 'noindex, nofollow'})

    @app.get('/api/staff/invoices/{invoice_id}', response_class=HTMLResponse)
    def invoice_document(invoice_id: int, request: Request, user=Depends(require_staff)):
        with transaction(database) as conn:
            row = conn.execute('SELECT * FROM employee_invoices WHERE id=?', (invoice_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Invoice not found.')
            return HTMLResponse(_document_html(json.loads(row['snapshot']), row['status'], 'invoice', row['number']))

    @app.get('/api/staff/jobs/{job_id}/invoices')
    def invoice_list(job_id: int, request: Request, user=Depends(require_staff)):
        with transaction(database) as conn:
            get_job(conn, job_id)
            rows = conn.execute('SELECT id,number,quote_version,status,created_at FROM employee_invoices WHERE job_id=? ORDER BY id DESC', (job_id,)).fetchall()
            return {'invoices': [dict(row) for row in rows]}
