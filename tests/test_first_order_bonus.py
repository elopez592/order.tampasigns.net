"""First-order promotion regressions use local accounts and the fake payment gateway."""
from concurrent.futures import ThreadPoolExecutor

from app import rewards
from app.db import transaction
from .conftest import anonymous, create_banner, finalize, portal, accept, payment
from .test_checkout_privacy import live_setup, new_order, open_session, paid_object, send_event
from .test_rewards_preview_terms import account


def pay_order(app, client):
    client, result, _ = new_order(app, client=client)
    assert result.status_code == 200, result.text
    jid = result.json()['job_id']
    session = open_session(app, client, jid)
    paid = paid_object(app, session)
    assert send_event(app, paid).status_code == 200
    return jid, paid


def wallet(client):
    return client.get('/api/customer').json()['wallet']


def bonus_history(client):
    return [row for row in wallet(client)['history'] if row['kind'] == 'first_order_bonus']


def test_first_order_bonus_waits_for_payment_and_is_extra_once(live_setup):
    app, admin, _ = live_setup
    client, _ = account(app)
    assert client.get('/api/catalog').json()['rewards']['first_order_bonus_points'] == 50
    _, result, _ = new_order(app, client=client)
    assert wallet(client)['points'] == 0  # Order and terms acceptance do not earn points.
    session = open_session(app, client, result.json()['job_id'])
    assert wallet(client)['points'] == 0  # Opening checkout is not payment.
    paid = paid_object(app, session)
    assert send_event(app, paid, event_id='evt_first_bonus').status_code == 200
    assert send_event(app, paid, event_id='evt_first_bonus').json()['duplicate']
    assert send_event(app, paid).status_code == 200
    assert wallet(client)['points'] == 110  # $60 merchandise + 50 bonus points.
    first_bonus = bonus_history(client)
    assert len(first_bonus) == 1 and first_bonus[0]['points'] == 50
    pay_order(app, client)
    assert wallet(client)['points'] == 170  # A later $60 order adds only its usual points.
    assert bonus_history(client) == first_bonus


def test_simultaneous_first_payments_share_one_bonus(live_setup):
    app, _, _ = live_setup
    client, _ = account(app)
    paid = []
    for _ in range(2):
        _, result, _ = new_order(app, client=client)
        paid.append(paid_object(app, open_session(app, client, result.json()['job_id'])))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda obj: send_event(app, obj), paid))
    assert [r.status_code for r in responses] == [200, 200]
    assert wallet(client)['points'] == 170
    assert len(bonus_history(client)) == 1


def test_bonus_kept_for_partial_refund_reversed_for_full_refund_and_not_reearned(live_setup):
    app, _, _ = live_setup
    client, _ = account(app)
    _, paid = pay_order(app, client)
    refund = {'payment_intent': paid['payment_intent'], 'amount_refunded': paid['amount_total'] // 2}
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    assert wallet(client)['points'] == 80  # 30 purchase points plus the fixed bonus.
    refund['amount_refunded'] = paid['amount_total']
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    assert wallet(client)['points'] == 0
    pay_order(app, client)
    assert wallet(client)['points'] == 60
    assert len(bonus_history(client)) == 1
    reversals = [r for r in wallet(client)['history'] if r['kind'] == 'first_order_bonus_reversed']
    assert len(reversals) == 1 and reversals[0]['points'] == -50


def test_dispute_reverses_and_restores_the_original_bonus_once(live_setup):
    app, _, _ = live_setup
    client, _ = account(app)
    _, paid = pay_order(app, client)
    dispute = {'payment_intent': paid['payment_intent'], 'status': 'needs_response'}
    assert send_event(app, dispute, kind='charge.dispute.created').status_code == 200
    assert send_event(app, dispute, kind='charge.dispute.created').status_code == 200
    assert wallet(client)['points'] == 0
    dispute['status'] = 'won'
    assert send_event(app, dispute, kind='charge.dispute.closed').status_code == 200
    assert send_event(app, dispute, kind='charge.dispute.closed').status_code == 200
    assert wallet(client)['points'] == 110
    assert len(bonus_history(client)) == 1
    restorations = [r for r in wallet(client)['history'] if r['kind'] == 'first_order_bonus_restored']
    assert len(restorations) == 1 and restorations[0]['points'] == 50


def test_earlier_guest_payment_blocks_bonus_on_new_account_order(live_setup):
    app, _, _ = live_setup
    guest = anonymous(app)
    pay_order(app, guest)
    client, _ = account(app)
    pay_order(app, client)
    assert wallet(client)['points'] == 60
    assert bonus_history(client) == []


def test_matching_account_can_link_its_first_guest_order_once(live_setup):
    app, _, _ = live_setup
    guest = anonymous(app)
    pay_order(app, guest)
    client, _ = account(app)
    guest.cookies.set('signshop_customer', client.cookies.get('signshop_customer'))
    for _ in range(2):
        result = guest.post('/api/portal/rewards/link', json={})
        assert result.status_code == 200, result.text
    assert wallet(client)['points'] == 110
    assert len(bonus_history(client)) == 1


def test_paused_rewards_and_invalid_receipt_cannot_award_bonus(live_setup):
    app, admin, _ = live_setup
    client, _ = account(app)
    _, result, _ = new_order(app, client=client)
    paid = paid_object(app, open_session(app, client, result.json()['job_id']))
    assert send_event(app, paid, signature='invalid').status_code == 400
    assert wallet(client)['points'] == 0
    shop = admin.get('/api/admin/settings').json()
    shop['rewards_enabled'] = False
    assert admin.put('/api/admin/settings', json=shop).status_code == 200
    assert send_event(app, paid).status_code == 200
    assert wallet(client)['points'] == 0
    assert bonus_history(client) == []


def test_existing_payment_rewards_are_not_backfilled_on_retry(live_setup, monkeypatch):
    app, _, _ = live_setup
    client, _ = account(app)
    # Emulate a payment reconciled by the release before the bonus existed.
    with monkeypatch.context() as previous_release:
        previous_release.setattr(rewards, 'sync_first_order_bonus', lambda *args: None)
        _, paid = pay_order(app, client)
    assert wallet(client)['points'] == 60
    assert send_event(app, paid).status_code == 200
    refund = {'payment_intent': paid['payment_intent'], 'amount_refunded': paid['amount_total'] // 2}
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    pay_order(app, client)
    assert wallet(client)['points'] == 90
    assert bonus_history(client) == []


def test_custom_deposits_award_once_and_last_payment_void_reverses_bonus(env):
    app, admin, _ = env
    client, cid = account(app, 'customer@example.test')
    jid = create_banner(admin)
    finalize(admin, jid)
    buyer = portal(app, admin, jid)
    buyer.cookies.set('signshop_customer', client.cookies.get('signshop_customer'))
    accept(buyer)
    assert buyer.post('/api/portal/rewards/link', json={}).status_code == 200
    one = payment(admin, jid, '10', 'FIRST-DEPOSIT')
    two = payment(admin, jid, '5', 'SECOND-DEPOSIT')
    assert one.status_code == two.status_code == 200
    assert payment(admin, jid, '10', 'FIRST-DEPOSIT').json()['already_recorded']
    assert wallet(client)['points'] == 65
    assert len(bonus_history(client)) == 1
    for result, expected in [(one, 55), (two, 0)]:
        pid = result.json()['payment_id']
        assert admin.post(f'/api/staff/payments/{pid}/void', json={'reason': 'Local test correction'}).status_code == 200
        assert wallet(client)['points'] == expected
    with transaction(app.state.database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM customer_reward_ledger WHERE customer_id=? "
                            "AND operation_id=?", (cid, 'first-order-bonus-' + str(cid))).fetchone()[0] == 1
