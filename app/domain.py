from __future__ import annotations
import json
from datetime import date
from decimal import Decimal
from fastapi import HTTPException
from .db import now, settings, audit
from .pricing import calculate, public_quote, number, cent_round
from .security import text, email

APPROVAL_STATEMENT = ('I approve this complete proof package for production, including wording, spelling, '
                      'dimensions, layout and placement. I understand screen colors are not an exact print-color match. '
                      'This approval applies only to the displayed proof version; later revisions require a new approval.')


def get_job(conn, job_id: int):
    row = conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Job not found.')
    return row


def totals(conn, job) -> dict:
    quote = json.loads(job['quote_snapshot'])
    merchandise = job['price_override_cents'] if job['price_override_cents'] is not None else quote['subtotal_cents'] + job['extra_price_cents']
    pretax = merchandise + job['shipping_cents']
    total = pretax + job['tax_cents']
    paid = conn.execute('SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE job_id=? AND voided_at IS NULL', (job['id'],)).fetchone()[0]
    paid += conn.execute('SELECT COALESCE(SUM(CASE WHEN disputed=0 THEN amount_cents-refunded_cents ELSE 0 END),0) FROM online_payments WHERE job_id=?', (job['id'],)).fetchone()[0]
    cost = quote['cost_cents'] + job['extra_cost_cents']
    deposit = cent_round(Decimal(total) * Decimal(job['deposit_percent']) / 100)
    return {'merchandise_cents': merchandise, 'shipping_cents': job['shipping_cents'],
            'tax_cents': job['tax_cents'], 'total_cents': total, 'paid_cents': paid,
            'balance_cents': max(total - paid, 0), 'credit_cents': max(paid - total, 0),
            'deposit_cents': deposit, 'deposit_remaining_cents': max(deposit - paid, 0),
            'cost_cents': cost, 'profit_cents': pretax - cost,
            'margin_percent': float(Decimal(pretax - cost) / pretax * 100) if pretax else 0,
            'suggested_pretax_cents': cent_round(Decimal(cost) / (1 - Decimal(quote['settings_snapshot']['target_margin_percent']) / 100))}


def latest_proof(conn, job_id):
    return conn.execute('SELECT * FROM proofs WHERE job_id=? ORDER BY version DESC LIMIT 1', (job_id,)).fetchone()


def production_started(conn, job_id):
    return conn.execute("SELECT id FROM tasks WHERE job_id=? AND gate IN ('production','delivery') AND started_at IS NOT NULL LIMIT 1", (job_id,)).fetchone() is not None


def gate_reason(conn, job, task) -> str:
    for dependency in json.loads(task['dependencies']):
        dep = conn.execute('SELECT title,status FROM tasks WHERE id=? AND job_id=?', (dependency, job['id'])).fetchone()
        if not dep or dep['status'] != 'done':
            return 'Finish prerequisite: ' + (dep['title'] if dep else 'missing task')
    if job['archived']:
        return 'Job is archived.'
    gate = task['gate']
    if gate == 'none':
        return ''
    if not job['published'] or job['accepted_version'] != job['quote_version']:
        return 'Customer must accept the current quote.'
    financials = totals(conn, job)
    if gate in ('deposit', 'production', 'delivery') and financials['deposit_remaining_cents'] > 0:
        return 'Required deposit has not been verified.'
    if gate in ('production', 'delivery'):
        proof = latest_proof(conn, job['id'])
        if not proof or proof['status'] != 'approved':
            return 'Latest complete proof package must be approved.'
    if gate == 'delivery' and financials['balance_cents'] > 0:
        return 'Remaining balance must be verified before delivery.'
    return ''


def stage(conn, job, tasks=None):
    tasks = tasks or conn.execute('SELECT * FROM tasks WHERE job_id=?', (job['id'],)).fetchall()
    if job['archived']:
        return 'archived'
    if tasks and all(t['status'] == 'done' for t in tasks):
        return 'complete'
    if production_started(conn, job['id']):
        return 'production'
    if not job['published'] or job['accepted_version'] != job['quote_version']:
        return 'quote'
    proof = latest_proof(conn, job['id'])
    if proof and proof['status'] == 'approved' and totals(conn, job)['deposit_remaining_cents'] == 0:
        next_production = next((t for t in tasks if t['gate'] == 'production' and t['status'] != 'done'), None)
        if next_production is not None and not gate_reason(conn, job, next_production):
            return 'ready'
    return 'prepress'


def validate_steps(steps):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 40:
        raise HTTPException(422, 'A workflow needs 1 to 40 tasks.')
    checked = []
    for i, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise HTTPException(422, 'Invalid workflow step.')
        deps = step.get('depends_on', [i - 1] if i > 1 else [])
        if not isinstance(deps, list) or any(type(d) is not int or d < 1 or d >= i for d in deps):
            raise HTTPException(422, 'Dependencies must refer to earlier step numbers.')
        gate = step.get('gate', 'production')
        if gate not in ('none', 'quote', 'deposit', 'production', 'delivery'):
            raise HTTPException(422, 'Invalid task gate.')
        checked.append({'title': text(step.get('title', ''), 'Task title', 120, True),
                        'department': text(step.get('department', ''), 'Department', 60, True),
                        'gate': gate, 'depends_on': list(dict.fromkeys(deps))})
    # Every standard workflow includes a production gate and final paid-delivery gate.
    if not any(s['gate'] == 'production' for s in checked) or checked[-1]['gate'] != 'delivery':
        raise HTTPException(422, 'Include a production-gated task and finish with a delivery-gated task.')
    return checked


def create_job(conn, payload, source='staff', actor='staff'):
    quote = calculate(conn, payload.get('items', []), staff=source == 'staff')
    customer_name = text(payload.get('customer_name', ''), 'Customer name', 120, True)
    customer_email = email(payload.get('customer_email', ''))
    title = text(payload.get('title', 'Custom print order'), 'Job title', 180, True)
    notes = text(payload.get('notes', ''), 'Job notes', 5000)
    phone = text(payload.get('phone', ''), 'Phone', 60)
    due = payload.get('due_date') or None
    if due:
        try:
            date.fromisoformat(due)
        except (ValueError, TypeError):
            raise HTTPException(422, 'Due date must be YYYY-MM-DD.')
    workflow_id = payload.get('workflow_id') if source == 'staff' else None
    workflow_id = workflow_id or quote['lines'][0]['workflow_id']
    workflow = conn.execute('SELECT * FROM workflows WHERE id=?', (workflow_id,)).fetchone()
    if not workflow:
        raise HTTPException(422, 'Workflow not found.')
    priority = payload.get('priority', 'normal') if source == 'staff' else 'normal'
    if priority not in ('normal', 'rush'):
        raise HTTPException(422, 'Priority must be normal or rush.')
    cursor = conn.execute('''INSERT INTO jobs(title,customer_name,customer_email,phone,notes,source,created_at,
        due_date,priority,quote_snapshot,deposit_percent,workflow_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
        (title, customer_name, customer_email, phone, notes, source, now(), due, priority,
         json.dumps(quote), str(settings(conn)['deposit_percent']), workflow_id))
    job_id = cursor.lastrowid
    number_ = f'JOB-{job_id:04d}'
    conn.execute('UPDATE jobs SET number=? WHERE id=?', (number_, job_id))
    task_ids = []
    for i, step in enumerate(json.loads(workflow['steps']), start=1):
        dependencies = [task_ids[d - 1] for d in step['depends_on']]
        task_id = conn.execute('INSERT INTO tasks(job_id,position,title,department,gate,dependencies) VALUES(?,?,?,?,?,?)',
                              (job_id, i, step['title'], step['department'], step['gate'], json.dumps(dependencies))).lastrowid
        task_ids.append(task_id)
    audit(conn, job_id, actor, 'job.created', {'source': source, 'workflow': workflow['name'], 'workflow_version': workflow['version']}, True)
    return job_id


def serialize_job(conn, job, audience='admin', detail=True, gateway=None):
    tasks = conn.execute('SELECT t.*,u.name AS assignee FROM tasks t LEFT JOIN users u ON u.id=t.assignee_id WHERE t.job_id=? ORDER BY position', (job['id'],)).fetchall()
    money = totals(conn, job)
    if audience != 'admin':
        for key in ['cost_cents', 'profit_cents', 'margin_percent', 'suggested_pretax_cents']:
            money.pop(key, None)
    owner = conn.execute('SELECT name FROM users WHERE id=?', (job['assignee_id'],)).fetchone()
    result = {k: job[k] for k in ['id','number','title','customer_name','customer_email','phone','notes','created_at',
                                 'due_date','priority','assignee_id','quote_version','published','accepted_version',
                                 'accepted_name','accepted_at','deposit_percent','workflow_id','archived']}
    result.update({'assignee': owner['name'] if owner else None, 'stage': stage(conn, job, tasks),
                   'totals': money, 'tasks_done': sum(t['status'] == 'done' for t in tasks), 'task_count': len(tasks)})
    if audience == 'customer':
        result['stage'] = 'finished' if result['stage']=='complete' else 'production' if production_started(conn, job['id']) else 'received'
        for key in ('notes','priority','due_date','assignee_id','assignee','workflow_id','tasks_done','task_count'):
            result.pop(key, None)
    if not detail:
        return result
    quote = json.loads(job['quote_snapshot'])
    result['quote'] = quote if audience == 'admin' else public_quote(quote)
    result['payment_url'] = job['payment_url']
    result['payment_kind'] = job['payment_kind']
    result['invoice_reference'] = job['invoice_reference']
    result['production_started'] = production_started(conn, job['id'])
    result['approval_statement'] = APPROVAL_STATEMENT
    result['charges_verified'] = bool(job['charges_verified'])
    result['extra_price_cents'] = job['extra_price_cents']
    result['price_override_cents'] = job['price_override_cents']
    result['adjustment_note'] = job['adjustment_note']
    if audience == 'admin':
        result['extra_cost_cents'] = job['extra_cost_cents']
    result['tasks'] = []
    for t in ([] if audience=='customer' else tasks):
        item = {k: t[k] for k in ['id','position','title','department','status','assignee_id','assignee','started_at','completed_at']}
        if audience != 'customer':
            item.update({'gate': t['gate'], 'dependencies': json.loads(t['dependencies']),
                         'note': t['note'], 'blocked_reason': gate_reason(conn, job, t) if t['status'] != 'done' else ''})
            entries = conn.execute('SELECT * FROM time_entries WHERE task_id=?', (t['id'],)).fetchall()
            from datetime import datetime, timezone
            seconds = sum(max(0, ((datetime.fromisoformat(e['stopped_at']) if e['stopped_at'] else datetime.now(timezone.utc))
                                   - datetime.fromisoformat(e['started_at'])).total_seconds()) for e in entries)
            item['tracked_minutes'] = round(seconds / 60, 1)
        result['tasks'].append(item)
    assets = conn.execute('SELECT id,filename,mime,sha256,size,kind,created_at FROM assets WHERE job_id=? ORDER BY id DESC', (job['id'],)).fetchall()
    result['assets'] = [dict(a) for a in assets if audience != 'customer' or a['kind'] in ('artwork','proof')]
    proofs = conn.execute('SELECT p.*,a.filename,a.mime,a.sha256 FROM proofs p JOIN assets a ON a.id=p.asset_id WHERE p.job_id=? ORDER BY version DESC', (job['id'],)).fetchall()
    result['proofs'] = []
    for p in proofs:
        item = dict(p)
        item['specs'] = json.loads(item['specs'])
        item['decisions'] = [dict(d) for d in conn.execute('SELECT * FROM proof_decisions WHERE proof_id=? ORDER BY id', (p['id'],))]
        result['proofs'].append(item)
    result['payments'] = [dict(p) for p in conn.execute('SELECT id,amount_cents,reference,note,created_at,voided_at,void_reason FROM payments WHERE job_id=? ORDER BY id DESC', (job['id'],))]
    event_query = 'SELECT * FROM events WHERE job_id=?' + (' AND public=1' if audience == 'customer' else '') + ' ORDER BY id DESC LIMIT 120'
    if audience == 'customer':
        for payment in result['payments']:
            payment.pop('note', None)
    result['events'] = [dict(e) | {'details': json.loads(e['details'])} for e in conn.execute(event_query, (job['id'],))]
    from .checkout import order_summary, StripeGateway
    result['checkout'] = order_summary(conn, job, gateway or StripeGateway())
    for receipt in conn.execute('SELECT * FROM online_payments WHERE job_id=? ORDER BY id DESC', (job['id'],)):
        result['payments'].append({'id': 'online-' + str(receipt['id']), 'amount_cents': receipt['amount_cents'],
            'reference': 'Online card payment', 'note': 'Stripe-verified receipt', 'created_at': receipt['created_at'],
            'voided_at': None, 'void_reason': None, 'source': 'stripe',
            'refunded_cents': receipt['refunded_cents'], 'disputed': bool(receipt['disputed'])})
    if audience == 'customer':
        # Do not merely hide workflow details in the browser. They are absent from the API.
        result.pop('tasks', None)
        result.pop('production_started', None)
        allowed = {
            'job.created': (), 'quote.published': ('version','total_cents'),
            'quote.accepted': ('version',), 'quote.revised': ('version','total_cents','note'),
            'customer.message': ('message',), 'staff.message': ('message',),
            'proof.published': ('version','label'), 'proof.approve': ('proof_version','comment'),
            'proof.request_changes': ('proof_version','comment'),
            'payment.received': ('amount_cents',), 'payment.verified': ('amount_cents',),
            'payment.updated': ('refunded_cents','under_review'),
            'payment.customer_reported': ('reference','verified')}
        visible = []
        for event in result['events']:
            if event['action'] not in allowed:
                continue
            details = {key:event['details'][key] for key in allowed[event['action']] if key in event['details']}
            who = 'You' if 'private job link' in event['actor'].lower() else settings(conn)['shop_name']
            visible.append({'id':event['id'], 'action':event['action'], 'actor':who,
                            'created_at':event['created_at'], 'details':details})
        result['events'] = visible
        for record in result['payments']:
            record.pop('note', None)
    return result
