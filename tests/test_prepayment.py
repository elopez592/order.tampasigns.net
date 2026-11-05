import pytest
from app.db import transaction
from .conftest import create_banner, finalize, portal, accept, payment, proof, approve, finish, task_action
from .test_checkout_privacy import live_setup


@pytest.mark.parametrize('amount,required', [('999.99',99999), ('1000',50000), ('1000.01',50001)])
def test_prepayment_threshold_is_strict_and_overrides_saved_deposit(env, amount, required):
    app, admin, _ = env
    jid = create_banner(admin)
    with transaction(app.state.database, True) as conn:
        conn.execute('UPDATE jobs SET price_override_cents=?,deposit_percent=? WHERE id=?',
                     (round(float(amount)*100), '50', jid))
    job = admin.get(f'/api/staff/jobs/{jid}').json()
    assert job['totals']['deposit_cents'] == required
    assert job['totals']['prepayment_required'] == (float(amount) < 1000)


def test_partial_payment_cannot_release_small_job_production(env):
    app, admin, employee = env
    jid = create_banner(admin)
    finalize(admin, jid)
    customer = portal(app, admin, jid)
    accept(customer)
    pid = proof(admin, jid)
    approve(customer, pid)
    job = admin.get(f'/api/staff/jobs/{jid}').json()
    tasks = job['tasks']
    finish(employee, tasks[0]['id'])
    finish(employee, tasks[2]['id'])
    total = job['totals']['total_cents']
    assert payment(admin, jid, total / 200).status_code == 200
    blocked = task_action(employee, tasks[1]['id'], 'start')
    assert blocked.status_code == 409
    assert 'Full payment' in blocked.text
    current = admin.get(f'/api/staff/jobs/{jid}').json()
    assert current['totals']['deposit_remaining_cents'] == current['totals']['balance_cents']
    assert payment(admin, jid, current['totals']['balance_cents']/100, 'FULL-PAYMENT').status_code == 200
    finish(employee, tasks[1]['id'])
    assert task_action(employee, tasks[3]['id'], 'start').status_code == 200


def test_small_custom_quote_only_offers_full_payment_and_normalizes_old_deposit_request(live_setup):
    app, admin, _ = live_setup
    jid = create_banner(admin)
    finalize(admin, jid)
    customer = portal(app, admin, jid)
    accept(customer)
    job = customer.get('/api/portal/job').json()
    assert not job['custom_checkout']['can_pay_deposit']
    assert job['custom_checkout']['can_pay_total']
    response = customer.post('/api/portal/custom-checkout', json={'payment_kind':'deposit'})
    assert response.status_code == 200, response.text
    with transaction(app.state.database) as conn:
        session = conn.execute('SELECT * FROM custom_checkout_sessions WHERE job_id=?', (jid,)).fetchone()
    assert session['payment_kind'] == 'total'
    assert session['amount_cents'] == job['totals']['balance_cents']
