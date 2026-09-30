"""Account credit discounts and loyalty points, with an append-only audit ledger.

All wallet changes run inside the caller's BEGIN IMMEDIATE transaction. Balances
are never trusted from the browser. Reservations prevent concurrent spending;
only provider-verified payments earn points. Credits in this program are shop
account discounts, not purchased gift cards or cash refunds.
"""
import hashlib
import json
import re
import uuid
from decimal import Decimal, ROUND_FLOOR

from fastapi import Body, Depends, HTTPException, Request

from .db import audit, now, settings, transaction
from .pricing import cents, cent_round, number
from .security import text

DEFAULTS = {'rewards_enabled': True, 'rewards_points_per_dollar': '1',
            'rewards_point_value_cents': '1', 'rewards_referrals_enabled': True,
            'rewards_referral_credit': '25'}
FIRST_ORDER_BONUS_POINTS = 50


def config(shop):
    return {key: shop.get(key, value) for key, value in DEFAULTS.items()}


def public_config(shop):
    cfg = config(shop)
    referral_credit_cents = cents(cfg['rewards_referral_credit'], 'Referral credit')
    return {'enabled': cfg['rewards_enabled'], 'points_per_dollar': cfg['rewards_points_per_dollar'],
            'point_value_cents': int(cfg['rewards_point_value_cents']),
            'first_order_bonus_points': FIRST_ORDER_BONUS_POINTS,
            'referrals_enabled': bool(cfg['rewards_referrals_enabled']),
            'referral_credit_cents': referral_credit_cents,
            'terms': 'Earn points on verified payments for merchandise after account discounts. '
                     'Your first paid order earns an extra 50 points once per customer account. '
                     'Prior paid orders with the same email count, including guest orders. '
                     'Referral credit is awarded to the referring customer only after the referred '
                     'customer makes a first verified payment. Self-referrals, repeat customers and '
                     'duplicate referrals are excluded. A referral reward is reversed if that '
                     'qualifying first payment is fully refunded, voided or disputed. '
                     'Tax and shipping do not earn points. Account credits and redeemed points '
                     'reduce the merchandise price before tax; they do not pay shipping. '
                     'No expiry or maintenance fees. Balances are for this account and cannot '
                     'be transferred or withdrawn as cash. Refunds or payment disputes reverse '
                     'earned points. Applied balances are returned proportionally after a '
                     'verified refund. The $35 cart minimum applies before rewards.'}


def validate_settings(shop, payload):
    cfg = config(shop)
    enabled = payload.get('rewards_enabled', cfg['rewards_enabled'])
    if type(enabled) is not bool:
        raise HTTPException(422, 'Rewards enabled must be true or false.')
    rate = number(payload.get('rewards_points_per_dollar', cfg['rewards_points_per_dollar']),
                  'Points per paid dollar', '0', '100')
    value = number(payload.get('rewards_point_value_cents', cfg['rewards_point_value_cents']),
                   'Point value in cents', '1', '100')
    referrals_enabled = payload.get('rewards_referrals_enabled', cfg['rewards_referrals_enabled'])
    if type(referrals_enabled) is not bool:
        raise HTTPException(422, 'Referral rewards enabled must be true or false.')
    referral_credit = number(payload.get('rewards_referral_credit', cfg['rewards_referral_credit']),
                             'Referral account credit', '0', '1000')
    if value != value.to_integral_value():
        raise HTTPException(422, 'Point value must be a whole number of cents.')
    shop.update(rewards_enabled=enabled, rewards_points_per_dollar=str(rate),
                rewards_point_value_cents=str(int(value)),
                rewards_referrals_enabled=referrals_enabled,
                rewards_referral_credit=str(referral_credit))


def referral_code(customer_id, address):
    checksum = hashlib.sha256(str(address or '').strip().lower().encode()).hexdigest()[:8].upper()
    return f'TS{int(customer_id)}-{checksum}'


def referral_summary(conn, customer_id):
    who = conn.execute('SELECT id,email FROM customers WHERE id=?', (customer_id,)).fetchone()
    if not who:
        return None
    cfg = public_config(settings(conn))
    rows = conn.execute(
        """SELECT status,reward_credit_cents FROM customer_referrals
           WHERE referrer_customer_id=? ORDER BY id DESC""",
        (customer_id,),
    ).fetchall()
    return {
        'code': referral_code(who['id'], who['email']),
        'enabled': cfg['referrals_enabled'],
        'reward_credit_cents': cfg['referral_credit_cents'],
        'referrals': len(rows),
        'rewarded': sum(row['status'] == 'rewarded' for row in rows),
        'pending': sum(row['status'] == 'pending' for row in rows),
        'earned_credit_cents': sum(max(0, int(row['reward_credit_cents'] or 0)) for row in rows if row['status'] == 'rewarded'),
    }


def _referrer_for_code(conn, code):
    match = re.fullmatch(r'TS([1-9][0-9]*)-([A-F0-9]{8})', str(code or '').strip().upper())
    if not match:
        return None
    row = conn.execute(
        'SELECT id,name,email,claimed_at FROM customers WHERE id=? AND claimed_at IS NOT NULL',
        (int(match.group(1)),),
    ).fetchone()
    if not row or referral_code(row['id'], row['email']) != str(code).strip().upper():
        return None
    return row


def _has_valid_payment_for_email(conn, address):
    return bool(conn.execute(
        """SELECT 1 FROM jobs j
           WHERE lower(j.customer_email)=lower(?)
             AND (
               EXISTS (SELECT 1 FROM payments p WHERE p.job_id=j.id AND p.amount_cents>0 AND p.voided_at IS NULL)
               OR EXISTS (
                 SELECT 1 FROM online_payments op
                 WHERE op.job_id=j.id AND op.disputed=0
                   AND op.amount_cents-op.refunded_cents>0
               )
             )
           LIMIT 1""",
        (address,),
    ).fetchone())


def record_referral(conn, job_id, referred_email, code):
    cfg = config(settings(conn))
    if not cfg['rewards_referrals_enabled'] or not code:
        return False
    referrer = _referrer_for_code(conn, code)
    address = str(referred_email or '').strip().lower()
    if not referrer or not address or referrer['email'].lower() == address:
        return False
    if _has_valid_payment_for_email(conn, address):
        return False
    if conn.execute(
        'SELECT 1 FROM customer_referrals WHERE lower(referred_email)=lower(?) LIMIT 1',
        (address,),
    ).fetchone():
        return False
    conn.execute(
        """INSERT INTO customer_referrals(
             referrer_customer_id,referred_email,source_job_id,qualifying_job_id,status,
             reward_credit_cents,created_at,updated_at
           ) VALUES(?,?,?,NULL,'pending',0,?,?)""",
        (referrer['id'], address, job_id, now(), now()),
    )
    return True


def _valid_paid_jobs(conn, address):
    return conn.execute(
        """SELECT job_id,MIN(created_at) AS first_paid_at,SUM(net_paid) AS net_paid
           FROM (
             SELECT op.job_id,op.created_at,
                    CASE WHEN op.disputed=0 THEN MAX(0,op.amount_cents-op.refunded_cents) ELSE 0 END AS net_paid
             FROM online_payments op
             UNION ALL
             SELECT p.job_id,p.created_at,
                    CASE WHEN p.voided_at IS NULL THEN MAX(0,p.amount_cents) ELSE 0 END AS net_paid
             FROM payments p
           ) paid
           JOIN jobs j ON j.id=paid.job_id
           WHERE lower(j.customer_email)=lower(?)
           GROUP BY job_id
           HAVING SUM(net_paid)>0
           ORDER BY first_paid_at,job_id""",
        (address,),
    ).fetchall()


def sync_referral_reward(conn, referred_email):
    referral = conn.execute(
        'SELECT * FROM customer_referrals WHERE lower(referred_email)=lower(?) LIMIT 1',
        (str(referred_email or '').strip().lower(),),
    ).fetchone()
    if not referral:
        return
    cfg = public_config(settings(conn))
    qualifying_job_id = referral['qualifying_job_id']
    if qualifying_job_id is None:
        valid = _valid_paid_jobs(conn, referral['referred_email'])
        if not valid:
            return
        qualifying_job_id = valid[0]['job_id']
        conn.execute(
            'UPDATE customer_referrals SET qualifying_job_id=?,updated_at=? WHERE id=?',
            (qualifying_job_id, now(), referral['id']),
        )
    net_online = conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN disputed=0 THEN amount_cents-refunded_cents ELSE 0 END),0)
           FROM online_payments WHERE job_id=?""",
        (qualifying_job_id,),
    ).fetchone()[0]
    net_manual = conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN voided_at IS NULL THEN amount_cents ELSE 0 END),0)
           FROM payments WHERE job_id=?""",
        (qualifying_job_id,),
    ).fetchone()[0]
    desired = cfg['referral_credit_cents'] if cfg['referrals_enabled'] and (net_online + net_manual) > 0 else 0
    awarded = conn.execute(
        """SELECT COALESCE(SUM(credit_cents),0) FROM customer_reward_ledger
           WHERE customer_id=? AND job_id=? AND kind IN
             ('referral_reward','referral_reward_reversed','referral_reward_restored')""",
        (referral['referrer_customer_id'], qualifying_job_id),
    ).fetchone()[0]
    delta = desired - awarded
    if delta:
        kind = 'referral_reward' if awarded == 0 and delta > 0 else 'referral_reward_restored' if delta > 0 else 'referral_reward_reversed'
        reason = (
            ('Referral reward for ' if delta > 0 else 'Referral reward reversed for ')
            + referral['referred_email']
        )
        entry(
            conn, referral['referrer_customer_id'], delta, 0, kind, reason,
            'Rewards system', qualifying_job_id,
        )
    status = 'rewarded' if desired > 0 else 'reversed'
    conn.execute(
        """UPDATE customer_referrals SET status=?,reward_credit_cents=?,
           rewarded_at=CASE WHEN ?='rewarded' AND rewarded_at IS NULL THEN ? ELSE rewarded_at END,
           updated_at=? WHERE id=?""",
        (status, desired, status, now(), now(), referral['id']),
    )


def wallet(conn, customer_id, history=True):
    row = conn.execute('SELECT COALESCE(SUM(credit_cents),0) AS credit, '
                       'COALESCE(SUM(points),0) AS points FROM customer_reward_ledger '
                       'WHERE customer_id=?', (customer_id,)).fetchone()
    cfg = public_config(settings(conn))
    result = {'credit_cents': max(0, row['credit']), 'points': max(0, row['points']),
              'points_adjustment_due': max(0, -row['points']), 'program': cfg,
              'points_value_cents': max(0, row['points']) * cfg['point_value_cents']}
    if history:
        result['history'] = [dict(r) for r in conn.execute(
            'SELECT id,job_id,credit_cents,points,kind,reason,created_at FROM customer_reward_ledger '
            'WHERE customer_id=? ORDER BY id DESC LIMIT 100', (customer_id,))]
    return result


def entry(conn, customer_id, credit, points, kind, reason, actor, job_id=None, operation_id=None):
    operation_id = operation_id or uuid.uuid4().hex
    conn.execute('''INSERT INTO customer_reward_ledger
        (customer_id,job_id,credit_cents,points,kind,reason,operation_id,actor,created_at)
        VALUES(?,?,?,?,?,?,?,?,?)''', (customer_id, job_id, credit, points, kind, reason,
                                     operation_id, actor, now()))


def active_redemption(conn, job_id):
    return conn.execute("SELECT * FROM reward_redemptions WHERE job_id=? AND status IN ('reserved','captured')",
                        (job_id,)).fetchone()


def discount_for_job(conn, job_id):
    redemption = active_redemption(conn, job_id)
    return redemption['discount_cents'] if redemption else 0


def reserve(conn, job, customer_id, payload):
    from .domain import totals, production_started
    if not public_config(settings(conn))['enabled']:
        raise HTTPException(409, 'Rewards redemption is currently paused.')
    if job['archived'] or not job['published'] or job['accepted_version'] != job['quote_version']:
        raise HTTPException(409, 'Accept the current order before applying rewards.')
    if production_started(conn, job['id']):
        raise HTTPException(409, 'Apply rewards before production begins.')
    if payload.get('confirm') is not True:
        raise HTTPException(422, 'Confirm the account credit and points to apply.')
    if payload.get('quote_version') != job['quote_version']:
        raise HTTPException(409, 'The quote changed. Reload before applying rewards.')
    if active_redemption(conn, job['id']):
        raise HTTPException(409, 'Rewards are already applied to this order. Release them before making a new selection.')
    if conn.execute('SELECT 1 FROM online_payments WHERE job_id=?', (job['id'],)).fetchone() or conn.execute(
            'SELECT 1 FROM payments WHERE job_id=? AND voided_at IS NULL', (job['id'],)).fetchone():
        raise HTTPException(409, 'Apply rewards before making a payment. Contact the shop for a paid-order adjustment.')
    if conn.execute("SELECT 1 FROM checkout_sessions s JOIN checkout_orders o ON s.order_id=o.id "
                    "WHERE o.job_id=? AND s.status IN ('creating','open','paid','review')", (job['id'],)).fetchone() or conn.execute(
            "SELECT 1 FROM custom_checkout_sessions WHERE job_id=? AND status IN ('creating','open','review')", (job['id'],)).fetchone():
        raise HTTPException(409, 'A payment checkout is already open. Close it safely before applying rewards.')
    credit = cents(payload.get('credit', '0'), 'Account credit amount')
    points = payload.get('points', 0)
    if type(points) is not int or not 0 <= points <= 100_000_000:
        raise HTTPException(422, 'Enter a nonnegative whole number of points.')
    available = wallet(conn, customer_id, history=False)
    if credit > available['credit_cents'] or points > available['points']:
        raise HTTPException(422, 'The selected amount exceeds your available account balance.')
    value = available['program']['point_value_cents']
    discount = credit + points * value
    before = totals(conn, job)
    if not 0 < discount <= before['merchandise_cents']:
        raise HTTPException(422, 'Apply a positive amount up to the merchandise subtotal. Tax and shipping are excluded.')
    # The single accepted custom-quote tax amount is apportioned to the reduced
    # pretax scope. Standard pickup uses its frozen tax rate; shipping is still
    # calculated by Stripe on the reduced merchandise price.
    order = conn.execute('SELECT * FROM checkout_orders WHERE job_id=?', (job['id'],)).fetchone()
    if order:
        policy = json.loads(order['policy'])
        tax = cent_round(Decimal(before['merchandise_cents'] - discount) * Decimal(policy['tax_percent']) / 100) if order['fulfillment'] == 'pickup' else 0
    else:
        pretax = before['merchandise_cents'] + before['shipping_cents']
        tax = cent_round(Decimal(before['tax_cents']) * (pretax - discount) / pretax) if pretax else 0
    after_total = before['merchandise_cents'] - discount + before['shipping_cents'] + tax
    if 0 < after_total < 50:
        raise HTTPException(422, 'Leave at least $0.50 due for card payment, or cover the full merchandise amount.')
    stamp = now()
    rid = conn.execute('''INSERT INTO reward_redemptions
        (customer_id,job_id,quote_version,credit_cents,points,point_value_cents,discount_cents,original_tax_cents,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)''',
        (customer_id, job['id'], job['quote_version'], credit, points, value, discount, job['tax_cents'], stamp, stamp)).lastrowid
    entry(conn, customer_id, -credit, -points, 'reserved', 'Applied to ' + job['number'],
          'Customer account', job['id'], 'reserve-' + str(rid))
    conn.execute('UPDATE jobs SET tax_cents=? WHERE id=?', (tax, job['id']))
    if not order:
        conn.execute("UPDATE jobs SET payment_url='',invoice_reference='' WHERE id=?", (job['id'],))
        if after_total == 0:
            capture(conn, job['id'])
    audit(conn, job['id'], 'Customer account', 'rewards.applied',
          {'credit_cents': credit, 'points': points, 'discount_cents': discount}, True)
    return rid


def release(conn, job_id, reason):
    item = active_redemption(conn, job_id)
    if not item or item['status'] != 'reserved':
        return False
    entry(conn, item['customer_id'], item['credit_cents'], item['points'], 'released', reason,
          'Rewards system', job_id, 'release-' + str(item['id']))
    conn.execute("UPDATE reward_redemptions SET status='released',updated_at=? WHERE id=?", (now(), item['id']))
    conn.execute('UPDATE jobs SET tax_cents=? WHERE id=?', (item['original_tax_cents'], job_id))
    audit(conn, job_id, 'Rewards system', 'rewards.released', {'reason': reason}, True)
    return True


def capture(conn, job_id):
    conn.execute("UPDATE reward_redemptions SET status='captured',updated_at=? WHERE job_id=? AND status='reserved'", (now(), job_id))


def sync_first_order_bonus(conn, owner, job, eligible, net_paid, first_earning):
    """Keep one lifetime bonus tied to the first paid job, including reversals.

    The original ledger entry remains after a reversal. A refund cannot turn a
    later order into another first order. The caller holds BEGIN IMMEDIATE, and
    the original entry also has a unique operation identifier.
    """
    original = conn.execute("SELECT * FROM customer_reward_ledger WHERE customer_id=? "
                            "AND kind='first_order_bonus' ORDER BY id LIMIT 1", (owner['id'],)).fetchone()
    if not original:
        # Payments already reconciled before this feature are not backfilled by
        # a later refund, deposit balance or webhook retry.
        if not first_earning or eligible <= 0 or net_paid <= 0:
            return
        first = conn.execute('''SELECT paid.job_id FROM (
            SELECT job_id,created_at FROM online_payments WHERE amount_cents>0
            UNION ALL SELECT job_id,created_at FROM payments WHERE amount_cents>0
            ) paid JOIN jobs j ON j.id=paid.job_id
            WHERE j.customer_email=? COLLATE NOCASE
            ORDER BY paid.created_at,paid.job_id LIMIT 1''', (job['customer_email'],)).fetchone()
        if not first or first['job_id'] != job['id']:
            return
        entry(conn, owner['id'], 0, FIRST_ORDER_BONUS_POINTS, 'first_order_bonus',
              'First paid order bonus for ' + job['number'], 'Rewards system', job['id'],
              'first-order-bonus-' + str(owner['id']))
        return
    if original['job_id'] != job['id']:
        return
    awarded = conn.execute("SELECT COALESCE(SUM(points),0) FROM customer_reward_ledger "
                           "WHERE customer_id=? AND job_id=? AND kind IN "
                           "('first_order_bonus','first_order_bonus_reversed','first_order_bonus_restored')",
                           (owner['id'], job['id'])).fetchone()[0]
    desired = original['points'] if net_paid > 0 else 0
    delta = desired - awarded
    if delta:
        entry(conn, owner['id'], 0, delta,
              'first_order_bonus_restored' if delta > 0 else 'first_order_bonus_reversed',
              ('First-order bonus restored for ' if delta > 0 else 'First-order bonus reversed for ') + job['number'],
              'Rewards system', job['id'])


def sync_earnings(conn, job_id):
    """Idempotently reconcile earnings against receipts, refunds and voids."""
    from .domain import get_job, totals
    job = get_job(conn, job_id)
    sync_referral_reward(conn, job['customer_email'])
    owner = conn.execute('SELECT c.id FROM customer_orders o JOIN customers c ON c.id=o.customer_id '
                         'JOIN jobs j ON j.id=o.job_id WHERE o.job_id=? AND c.email=j.customer_email COLLATE NOCASE', (job_id,)).fetchone()
    if not owner:
        return
    money = totals(conn, job)
    eligible = max(0, money['merchandise_cents'])
    cfg = config(settings(conn))
    first_earning = cfg['rewards_enabled'] and not conn.execute(
        'SELECT 1 FROM reward_earnings WHERE customer_id=? LIMIT 1', (owner['id'],)).fetchone()
    receipts = [('online-' + str(row['id']), row['amount_cents'],
                 0 if row['disputed'] else max(0, row['amount_cents'] - row['refunded_cents']))
                for row in conn.execute('SELECT * FROM online_payments WHERE job_id=?', (job_id,))]
    receipts += [('manual-' + str(row['id']), row['amount_cents'], 0 if row['voided_at'] else row['amount_cents'])
                 for row in conn.execute('SELECT * FROM payments WHERE job_id=?', (job_id,))]
    for source, paid, net in receipts:
        old = conn.execute('SELECT * FROM reward_earnings WHERE source=?', (source,)).fetchone()
        if not old:
            if not cfg['rewards_enabled'] or net <= 0:
                continue
            allocated = int(Decimal(min(paid, money['total_cents'])) * eligible / money['total_cents']) if money['total_cents'] else 0
            conn.execute('INSERT INTO reward_earnings VALUES(?,?,?,?,?,?,0)',
                         (source, owner['id'], job_id, cfg['rewards_points_per_dollar'], allocated, paid))
            old = conn.execute('SELECT * FROM reward_earnings WHERE source=?', (source,)).fetchone()
        desired = int((Decimal(old['eligible_cents']) * net / old['paid_cents'] / 100 * Decimal(old['points_per_dollar'])).to_integral_value(rounding=ROUND_FLOOR)) if old['paid_cents'] else 0
        delta = desired - old['awarded_points']
        if delta:
            entry(conn, old['customer_id'], 0, delta, 'earned' if delta > 0 else 'reversed',
                  ('Payment reward for ' if delta > 0 else 'Payment adjustment for ') + job['number'], 'Rewards system', job_id)
            conn.execute('UPDATE reward_earnings SET awarded_points=? WHERE source=?', (desired, source))
    sync_first_order_bonus(conn, owner, job, eligible, sum(net for _, _, net in receipts), first_earning)
    redemption = active_redemption(conn, job_id)
    if redemption and redemption['status'] == 'captured':
        paid = conn.execute('SELECT COALESCE(SUM(amount_cents),0) FROM online_payments WHERE job_id=?', (job_id,)).fetchone()[0]
        refunded = conn.execute('SELECT COALESCE(SUM(refunded_cents),0) FROM online_payments WHERE job_id=?', (job_id,)).fetchone()[0]
        # Refunds reinstate wallet balances once; disputed funds remain held until
        # the provider resolves the payment or the owner issues a credit.
        if paid and refunded:
            target_credit = redemption['credit_cents'] * min(refunded, paid) // paid
            target_points = redemption['points'] * min(refunded, paid) // paid
            dc, dp = target_credit - redemption['returned_credit_cents'], target_points - redemption['returned_points']
            if dc or dp:
                entry(conn, redemption['customer_id'], dc, dp, 'refund', 'Applied balance returned for ' + job['number'], 'Rewards system', job_id)
                conn.execute('UPDATE reward_redemptions SET returned_credit_cents=?,returned_points=?,updated_at=? WHERE id=?',
                             (target_credit, target_points, now(), redemption['id']))


def install(app, database, require_admin, portal_job):
    from .customers import customer

    with transaction(database, True) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS customer_referrals(
            id INTEGER PRIMARY KEY,
            referrer_customer_id INTEGER NOT NULL REFERENCES customers(id),
            referred_email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            source_job_id INTEGER NOT NULL REFERENCES jobs(id),
            qualifying_job_id INTEGER REFERENCES jobs(id),
            status TEXT NOT NULL CHECK(status IN ('pending','rewarded','reversed')),
            reward_credit_cents INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            rewarded_at TEXT,
            updated_at TEXT NOT NULL
        )""")
        conn.execute('CREATE INDEX IF NOT EXISTS customer_referrals_referrer ON customer_referrals(referrer_customer_id,id)')

    def account_for_job(conn, request):
        who = customer(conn, request)
        if not who:
            raise HTTPException(401, 'Sign in to use your account credits and points.')
        job = portal_job(conn, request)
        if who['email'].lower() != job['customer_email'].lower():
            raise HTTPException(403, 'Use the customer account for this order.')
        if conn.execute('SELECT 1 FROM customer_orders WHERE job_id=? AND customer_id<>?', (job['id'], who['id'])).fetchone():
            raise HTTPException(403, 'This order belongs to another customer account.')
        conn.execute('INSERT OR IGNORE INTO customer_orders VALUES(?,?)', (who['id'], job['id']))
        return who, job

    @app.get('/api/admin/rewards/customers')
    def accounts(request: Request, user=Depends(require_admin)):
        query = text(request.query_params.get('q', ''), 'Customer search', 160)
        with transaction(database) as conn:
            rows = conn.execute("SELECT id,name,email FROM customers WHERE name LIKE ? OR email LIKE ? ORDER BY name LIMIT 250",
                                ('%' + query + '%', '%' + query + '%')).fetchall()
            return {'customers': [dict(row) | {'wallet': wallet(conn, row['id'], history=False)} for row in rows],
                    'program': public_config(settings(conn))}

    @app.get('/api/admin/rewards/customers/{customer_id}')
    def account_history(customer_id: int, request: Request, user=Depends(require_admin)):
        with transaction(database) as conn:
            who = conn.execute('SELECT id,name,email FROM customers WHERE id=?', (customer_id,)).fetchone()
            if not who:
                raise HTTPException(404, 'Customer account not found.')
            return {'customer': dict(who), 'wallet': wallet(conn, customer_id)}

    @app.post('/api/admin/rewards/customers/{customer_id}/adjust')
    def adjust(customer_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        reason = text(payload.get('reason', ''), 'Adjustment reason', 500, True)
        operation = text(payload.get('operation_id', ''), 'Adjustment identifier', 80, True)
        action = payload.get('action')
        if action not in ('add', 'deduct'):
            raise HTTPException(422, 'Choose add or deduct.')
        credit = cents(payload.get('credit', '0'), 'Account credit amount')
        points = payload.get('points', 0)
        if type(points) is not int or not 0 <= points <= 100_000_000 or credit > 100_000_000 or not (credit or points):
            raise HTTPException(422, 'Enter a positive credit amount or whole points value.')
        sign = 1 if action == 'add' else -1
        with transaction(database, True) as conn:
            if not conn.execute('SELECT id FROM customers WHERE id=?', (customer_id,)).fetchone():
                raise HTTPException(404, 'Customer account not found.')
            previous = conn.execute('SELECT * FROM customer_reward_ledger WHERE operation_id=?', (operation,)).fetchone()
            if previous:
                if (previous['customer_id'], previous['credit_cents'], previous['points'], previous['reason']) != (customer_id, sign * credit, sign * points, reason):
                    raise HTTPException(409, 'This adjustment identifier was already used for a different adjustment.')
                return {'ok': True, 'already_recorded': True, 'wallet': wallet(conn, customer_id)}
            available = wallet(conn, customer_id, history=False)
            if action == 'deduct' and (credit > available['credit_cents'] or points > available['points']):
                raise HTTPException(422, 'A deduction cannot exceed the available account balance.')
            actor = f'{user["name"]} (staff #{user["id"]})'
            entry(conn, customer_id, sign * credit, sign * points, 'manual', reason, actor, operation_id=operation)
            audit(conn, None, actor, 'rewards.manual_adjustment', {'customer_id': customer_id,
                  'credit_cents': sign * credit, 'points': sign * points, 'reason': reason})
            return {'ok': True, 'wallet': wallet(conn, customer_id)}

    @app.get('/api/portal/rewards')
    def portal_rewards(request: Request):
        with transaction(database) as conn:
            job = portal_job(conn, request)
            who = customer(conn, request)
            same = who and who['email'].lower() == job['customer_email'].lower()
            item = active_redemption(conn, job['id'])
            return {'wallet': wallet(conn, who['id']) if same else None,
                    'redemption': {key: item[key] for key in ('credit_cents', 'points', 'discount_cents', 'status')} if item else None,
                    'program': public_config(settings(conn))}

    @app.post('/api/portal/rewards/apply')
    def apply_rewards(request: Request, payload: dict = Body(...)):
        with transaction(database, True) as conn:
            who, job = account_for_job(conn, request)
            rid = reserve(conn, job, who['id'], payload)
            return {'ok': True, 'redemption_id': rid, 'wallet': wallet(conn, who['id'])}

    @app.post('/api/portal/rewards/link')
    def link_rewards(request: Request):
        with transaction(database, True) as conn:
            who, job = account_for_job(conn, request)
            sync_earnings(conn, job['id'])
            return {'ok': True, 'wallet': wallet(conn, who['id'])}

    def release_for_job(job_id, reason):
        from .checkout import reconcile_paid, reconcile_custom_paid
        from .domain import get_job
        with transaction(database, True) as conn:
            get_job(conn, job_id)
            item = active_redemption(conn, job_id)
            if not item or item['status'] != 'reserved':
                raise HTTPException(409, 'Only unused reserved rewards can be returned before payment.')
            if conn.execute('SELECT 1 FROM online_payments WHERE job_id=?', (job_id,)).fetchone() or conn.execute(
                    'SELECT 1 FROM payments WHERE job_id=? AND voided_at IS NULL', (job_id,)).fetchone():
                raise HTTPException(409, 'Payment was received. Contact the shop about a refund or credit.')
            standard = [dict(row) | {'custom': False} for row in conn.execute(
                "SELECT s.* FROM checkout_sessions s JOIN checkout_orders o ON o.id=s.order_id WHERE o.job_id=? AND s.status IN ('creating','open','review')", (job_id,))]
            custom = [dict(row) | {'custom': True} for row in conn.execute(
                "SELECT * FROM custom_checkout_sessions WHERE job_id=? AND status IN ('creating','open','review')", (job_id,))]
            sessions = standard + custom
            customer_id, redemption_id = item['customer_id'], item['id']
        # An unresolved provider session may still collect payment. Confirm its
        # expiration before releasing funds; never infer expiration from a clock.
        for session in sessions:
            if not session['stripe_id'] or session['status'] in ('creating','review'):
                raise HTTPException(409, 'An interrupted payment needs shop review before returning the reserved balance.')
            data = app.state.gateway.retrieve_session(session['stripe_id'])
            if data.get('payment_status') == 'paid':
                with transaction(database, True) as conn:
                    fn = reconcile_custom_paid if session['custom'] else reconcile_paid
                    fn(conn, session, data, 'reconcile:' + session['stripe_id'], app.state.gateway.live)
                raise HTTPException(409, 'Payment was received. Refresh your order; the applied balance cannot be released.')
            if data.get('status') == 'open':
                data = app.state.gateway.expire_session(session['stripe_id'])
            if data.get('status') != 'expired':
                raise HTTPException(409, 'Payment is still being confirmed. Wait before returning the reserved balance.')
        with transaction(database, True) as conn:
            current_ids = {row[0] for row in conn.execute(
                "SELECT s.id FROM checkout_sessions s JOIN checkout_orders o ON o.id=s.order_id WHERE o.job_id=? AND s.status IN ('creating','open','review')", (job_id,))}
            current_ids.update(row[0] for row in conn.execute(
                "SELECT id FROM custom_checkout_sessions WHERE job_id=? AND status IN ('creating','open','review')", (job_id,)))
            if not current_ids.issubset({session['id'] for session in sessions}):
                raise HTTPException(409, 'Another payment checkout opened. Refresh before releasing rewards.')
            if conn.execute('SELECT 1 FROM online_payments WHERE job_id=?', (job_id,)).fetchone() or conn.execute('SELECT 1 FROM payments WHERE job_id=? AND voided_at IS NULL', (job_id,)).fetchone():
                raise HTTPException(409, 'Payment was received while updating this order. Refresh your order.')
            for session in sessions:
                table = 'custom_checkout_sessions' if session['custom'] else 'checkout_sessions'
                conn.execute(f"UPDATE {table} SET status='expired' WHERE id=? AND status='open'", (session['id'],))
            current = active_redemption(conn, job_id)
            if current and (current['id'] != redemption_id or current['status'] != 'reserved'):
                raise HTTPException(409, 'The rewards selection changed. Refresh the order.')
            released = release(conn, job_id, reason)
            return {'ok': True, 'released': released, 'wallet': wallet(conn, customer_id)}

    @app.post('/api/portal/rewards/release')
    def release_rewards(request: Request, payload: dict = Body(...)):
        if payload.get('confirm') is not True:
            raise HTTPException(422, 'Confirm returning applied credits and points to your account.')
        with transaction(database, True) as conn:
            _, job = account_for_job(conn, request)
            job_id = job['id']
        return release_for_job(job_id, 'Customer returned unused applied credits and points.')

    @app.post('/api/admin/rewards/jobs/{job_id}/release')
    def owner_release(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        if payload.get('confirm') is not True:
            raise HTTPException(422, "Confirm returning this order's unused credits and points.")
        return release_for_job(job_id, 'Shop returned unused applied credits and points before payment.')
