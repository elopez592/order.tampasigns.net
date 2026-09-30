from app.db import transaction
from tests.conftest import anonymous, finalize, portal, accept, payment


def register_customer(app, name, address):
    client = anonymous(app)
    response = client.post('/api/customer/register', json={
        'name': name,
        'email': address,
        'password': 'ReferralCustomerPassword2026',
    })
    assert response.status_code == 200, response.text
    return client


def submit_referred_request(app, email, referral_code):
    client = anonymous(app)
    items = [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1}]
    quote = client.post('/api/calculate', json={'items': items})
    assert quote.status_code == 200, quote.text
    response = client.post('/api/requests', json={
        'items': items,
        'fingerprint': quote.json()['fingerprint'],
        'customer_name': 'Referred Customer',
        'customer_email': email,
        'phone': '8135550310',
        'title': 'Referral banner',
        'notes': 'Referral integration test',
        'referral_code': referral_code,
    })
    assert response.status_code == 200, response.text
    return response.json()['job_id']


def test_referral_credit_awards_after_first_verified_payment_and_reverses(env):
    app, admin, employee = env
    referrer = register_customer(app, 'Referral Partner', 'referrer@example.test')
    account = referrer.get('/api/customer').json()
    referral = account['referral']
    assert referral['enabled'] is True
    assert referral['reward_credit_cents'] == 2500
    assert referral['code'].startswith('TS')

    job_id = submit_referred_request(app, 'new-referral@example.test', referral['code'])
    with transaction(app.state.database) as conn:
        tracked = conn.execute(
            'SELECT * FROM customer_referrals WHERE source_job_id=?', (job_id,)
        ).fetchone()
        assert tracked is not None
        assert tracked['status'] == 'pending'

    finalize(admin, job_id)
    customer = portal(app, admin, job_id)
    accept(customer)
    paid = payment(admin, job_id, '25.00', 'REFERRAL-PAYMENT-1')
    assert paid.status_code == 200, paid.text

    account = referrer.get('/api/customer').json()
    assert account['wallet']['credit_cents'] == 2500
    assert account['referral']['referrals'] == 1
    assert account['referral']['rewarded'] == 1
    assert account['referral']['pending'] == 0

    # A retry/reconciliation cannot duplicate the referral credit.
    with transaction(app.state.database, True) as conn:
        from app import rewards
        rewards.sync_earnings(conn, job_id)
    assert referrer.get('/api/customer').json()['wallet']['credit_cents'] == 2500

    voided = admin.post(
        f"/api/staff/payments/{paid.json()['payment_id']}/void",
        json={'reason': 'Test full payment reversal'},
    )
    assert voided.status_code == 200, voided.text
    account = referrer.get('/api/customer').json()
    assert account['wallet']['credit_cents'] == 0
    with transaction(app.state.database) as conn:
        tracked = conn.execute(
            'SELECT * FROM customer_referrals WHERE source_job_id=?', (job_id,)
        ).fetchone()
        assert tracked['status'] == 'reversed'
        assert tracked['reward_credit_cents'] == 2500


def test_referral_blocks_self_referrals_and_duplicate_customer_attribution(env):
    app, admin, employee = env
    referrer = register_customer(app, 'No Self Referral', 'no-self@example.test')
    code = referrer.get('/api/customer').json()['referral']['code']

    self_job = submit_referred_request(app, 'no-self@example.test', code)
    with transaction(app.state.database) as conn:
        assert not conn.execute(
            'SELECT 1 FROM customer_referrals WHERE source_job_id=?', (self_job,)
        ).fetchone()

    first_job = submit_referred_request(app, 'one-referral@example.test', code)
    second_job = submit_referred_request(app, 'one-referral@example.test', code)
    with transaction(app.state.database) as conn:
        rows = conn.execute(
            "SELECT * FROM customer_referrals WHERE referred_email='one-referral@example.test'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]['source_job_id'] == first_job
        assert rows[0]['source_job_id'] != second_job


def test_referral_amount_is_configurable_and_frozen_when_qualified(env):
    app, admin, employee = env
    settings = admin.get('/api/admin/settings').json()
    saved = admin.put('/api/admin/settings', json={
        **settings,
        'rewards_referrals_enabled': True,
        'rewards_referral_credit': '40',
    })
    assert saved.status_code == 200, saved.text

    referrer = register_customer(app, 'Forty Dollar Referrer', 'forty-referrer@example.test')
    referral = referrer.get('/api/customer').json()['referral']
    assert referral['reward_credit_cents'] == 4000

    job_id = submit_referred_request(app, 'forty-new@example.test', referral['code'])
    finalize(admin, job_id)
    customer = portal(app, admin, job_id)
    accept(customer)
    paid = payment(admin, job_id, '25.00', 'REFERRAL-PAYMENT-40')
    assert paid.status_code == 200, paid.text
    assert referrer.get('/api/customer').json()['wallet']['credit_cents'] == 4000

    # Later program changes apply only to future qualifying referrals.
    settings = admin.get('/api/admin/settings').json()
    changed = admin.put('/api/admin/settings', json={
        **settings,
        'rewards_referral_credit': '10',
    })
    assert changed.status_code == 200, changed.text
    with transaction(app.state.database, True) as conn:
        from app import rewards
        rewards.sync_earnings(conn, job_id)
    assert referrer.get('/api/customer').json()['wallet']['credit_cents'] == 4000
