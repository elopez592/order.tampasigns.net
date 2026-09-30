"""Money, permissions and proof/sizing regressions; all payments use a fake gateway."""
import json
import sqlite3
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor

from app.db import initialize, transaction
from app.domain import gate_reason, get_job
from app.job_terms import CHECKOUT_CONFIRMATION
from app import job_terms
from .conftest import anonymous, image_bytes, create_banner, finalize, portal, accept, payment, proof, approve
from .test_checkout_privacy import live_setup, new_order, open_session, paid_object, send_event


def account(app, address='checkout@example.test'):
    client = anonymous(app)
    response = client.post('/api/customer/register', json={
        'name': 'Rewards customer', 'email': address, 'password': 'LocalRewardsTestPassword2026'})
    assert response.status_code == 200, response.text
    return client, response.json()['customer']['id']


def grant(admin, customer_id, credit='10', points=300, **extra):
    payload = {'action': 'add', 'credit': credit, 'points': points,
               'reason': 'Local goodwill example', 'operation_id': str(uuid.uuid4())} | extra
    result = admin.post(f'/api/admin/rewards/customers/{customer_id}/adjust', json=payload)
    assert result.status_code == 200, result.text
    return payload


def apply(client, credit='5', points=200):
    return client.post('/api/portal/rewards/apply', json={
        'credit': credit, 'points': points, 'quote_version': 1, 'confirm': True})


def test_manual_adjustments_permissions_idempotency_and_available_balance(live_setup):
    app, admin, employee = live_setup
    client, cid = account(app)
    payload = grant(admin, cid)
    assert employee.get('/api/admin/rewards/customers').status_code == 403
    assert client.post(f'/api/admin/rewards/customers/{cid}/adjust', json=payload).status_code == 401
    retry = admin.post(f'/api/admin/rewards/customers/{cid}/adjust', json=payload)
    assert retry.status_code == 200 and retry.json()['already_recorded']
    changed = admin.post(f'/api/admin/rewards/customers/{cid}/adjust', json=payload | {'credit': '11'})
    assert changed.status_code == 409
    insufficient = admin.post(f'/api/admin/rewards/customers/{cid}/adjust', json=payload | {
        'operation_id': str(uuid.uuid4()), 'action': 'deduct', 'credit': '11'})
    assert insufficient.status_code == 422
    wallet = client.get('/api/customer').json()['wallet']
    assert (wallet['credit_cents'], wallet['points'], len(wallet['history'])) == (1000, 300, 1)
    assert 'actor' not in wallet['history'][0]


def test_redemption_payment_and_full_refund_are_reconciled_once(live_setup):
    app, admin, employee = live_setup
    client, cid = account(app)
    grant(admin, cid)
    client, result, _ = new_order(app, client=client)
    assert result.status_code == 200, result.text
    before = client.get('/api/portal/job').json()['totals']
    assert apply(client).status_code == 200
    discounted = client.get('/api/portal/job').json()['totals']
    assert discounted['merchandise_cents'] == before['merchandise_cents'] - 700
    assert discounted['rewards_discount_cents'] == 700
    assert discounted['tax_cents'] == 398  # $53 merchandise at 7.5%, rounded half-up.
    assert apply(client).status_code == 409
    session = open_session(app, client, result.json()['job_id'])
    paid = paid_object(app, session)
    # Fake helper uses Python round; production uses Decimal half-up.
    paid['total_details']['amount_tax'] = discounted['tax_cents']
    paid['amount_total'] = discounted['total_cents']
    assert send_event(app, paid, event_id='evt_rewards_paid').status_code == 200
    assert send_event(app, paid, event_id='evt_rewards_paid').json()['duplicate']
    assert send_event(app, paid, event_id='evt_rewards_paid_again').status_code == 200
    wallet = client.get('/api/customer').json()['wallet']
    assert (wallet['credit_cents'], wallet['points']) == (500, 153)
    assert client.get('/api/portal/job').json()['totals']['balance_cents'] == 0
    refund = {'payment_intent': paid['payment_intent'], 'amount_refunded': paid['amount_total']}
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    restored = client.get('/api/customer').json()['wallet']
    assert (restored['credit_cents'], restored['points']) == (1000, 300)


def test_expiration_returns_reservations_and_retry_uses_restored_price(live_setup):
    app, admin, employee = live_setup
    client, cid = account(app)
    grant(admin, cid)
    client, result, _ = new_order(app, client=client)
    original = client.get('/api/portal/job').json()['totals']
    assert apply(client).status_code == 200
    session = open_session(app, client, result.json()['job_id'])
    obj = {'id': session['stripe_id'], 'metadata': {'checkout_id': session['id']}}
    app.state.gateway.sessions[session['stripe_id']]['status'] = 'expired'
    assert send_event(app, obj, kind='checkout.session.expired').status_code == 200
    assert send_event(app, obj, kind='checkout.session.expired').status_code == 200
    assert client.get('/api/portal/job').json()['totals'] == original
    assert client.get('/api/customer').json()['wallet']['credit_cents'] == 1000
    retry = open_session(app, client, result.json()['job_id'])
    assert retry['merchandise_cents'] == original['merchandise_cents']


def test_explicit_release_expires_provider_checkout_first(live_setup):
    app, admin, employee = live_setup
    client, cid = account(app)
    grant(admin, cid)
    client, result, _ = new_order(app, client=client)
    assert apply(client).status_code == 200
    session = open_session(app, client, result.json()['job_id'])
    response = client.post('/api/portal/rewards/release', json={'confirm': True})
    assert response.status_code == 200, response.text
    assert app.state.gateway.sessions[session['stripe_id']]['status'] == 'expired'
    assert client.get('/api/customer').json()['wallet']['credit_cents'] == 1000


def test_owner_can_release_only_unpaid_balances_and_employee_cannot(live_setup):
    app, admin, employee = live_setup
    client, cid = account(app)
    grant(admin, cid)
    client, result, _ = new_order(app, client=client)
    jid = result.json()['job_id']
    assert apply(client).status_code == 200
    session = open_session(app, client, jid)
    route = f'/api/admin/rewards/jobs/{jid}/release'
    assert employee.post(route, json={'confirm': True}).status_code == 403
    assert admin.post(route, json={'confirm': False}).status_code == 422
    assert admin.post(route, json={'confirm': True}).json()['released']
    assert app.state.gateway.sessions[session['stripe_id']]['status'] == 'expired'
    assert apply(client).status_code == 200
    session = open_session(app, client, jid)
    paid = paid_object(app, session)
    job = client.get('/api/portal/job').json()
    paid['amount_total'] = job['totals']['total_cents']
    paid['total_details']['amount_tax'] = job['totals']['tax_cents']
    assert send_event(app, paid).status_code == 200
    assert admin.post(route, json={'confirm': True}).status_code == 409
    assert client.get('/api/customer').json()['wallet']['credit_cents'] == 500


def test_shipping_discount_and_partial_refund_exclude_tax_and_delivery(live_setup):
    app, admin, employee = live_setup
    client, cid = account(app)
    grant(admin, cid)
    client, result, _ = new_order(app, client=client, fulfillment='shipping')
    assert apply(client).status_code == 200
    session = open_session(app, client, result.json()['job_id'])
    body = json.loads(session['request_body'])
    assert body['line_items[0][price_data][unit_amount]'] == '5300'
    assert body['shipping_options[0][shipping_rate_data][fixed_amount][amount]'] == '1200'
    assert body['automatic_tax[enabled]'] == 'true'
    paid = paid_object(app, session)
    assert send_event(app, paid).status_code == 200
    wallet = client.get('/api/customer').json()['wallet']
    assert (wallet['credit_cents'], wallet['points']) == (500, 153)
    refund = {'payment_intent': paid['payment_intent'], 'amount_refunded': paid['amount_total'] // 2}
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    wallet = client.get('/api/customer').json()['wallet']
    assert (wallet['credit_cents'], wallet['points']) == (750, 226)
    refund['amount_refunded'] = paid['amount_total']
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    wallet = client.get('/api/customer').json()['wallet']
    assert (wallet['credit_cents'], wallet['points']) == (1000, 300)


def test_refund_reverses_spent_points_and_keeps_original_earning_rate(live_setup):
    app, admin, employee = live_setup
    client, cid = account(app)
    client, first, _ = new_order(app, client=client)
    session = open_session(app, client, first.json()['job_id'])
    paid = paid_object(app, session)
    assert send_event(app, paid).status_code == 200
    assert client.get('/api/customer').json()['wallet']['points'] == 60
    client, second, _ = new_order(app, client=client)
    assert apply(client, credit='0', points=60).status_code == 200
    shop = admin.get('/api/admin/settings').json()
    shop['rewards_points_per_dollar'] = '5'
    assert admin.put('/api/admin/settings', json=shop).status_code == 200
    refund = {'payment_intent': paid['payment_intent'], 'amount_refunded': paid['amount_total'] // 2}
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    wallet = client.get('/api/customer').json()['wallet']
    assert wallet['points'] == 0 and wallet['points_adjustment_due'] == 30
    refund['amount_refunded'] = paid['amount_total']
    assert send_event(app, refund, kind='charge.refunded').status_code == 200
    assert client.get('/api/customer').json()['wallet']['points_adjustment_due'] == 60
    assert client.post('/api/portal/rewards/release', json={'confirm': True}).status_code == 200
    wallet = client.get('/api/customer').json()['wallet']
    assert wallet['points'] == wallet['points_adjustment_due'] == 0


def test_zero_due_order_is_covered_without_creating_a_card_charge(live_setup):
    app, admin, employee = live_setup
    client, cid = account(app)
    grant(admin, cid, credit='100', points=0)
    client, result, _ = new_order(app, client=client)
    amount = client.get('/api/portal/job').json()['totals']['merchandise_cents'] / 100
    assert apply(client, credit=str(amount), points=0).status_code == 200
    payment = client.post('/api/portal/checkout', json={})
    assert payment.status_code == 200 and payment.json()['paid']
    assert client.get('/api/portal/job').json()['checkout']['status'] == 'paid'
    assert not app.state.gateway.creates


def test_account_balance_cannot_be_spent_concurrently(live_setup):
    app, admin, employee = live_setup
    first, cid = account(app)
    second = anonymous(app)
    assert second.post('/api/customer/login', json={'email': 'checkout@example.test',
        'password': 'LocalRewardsTestPassword2026'}).status_code == 200
    grant(admin, cid, credit='50', points=0)
    for client in (first, second):
        assert new_order(app, client=client)[1].status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda client: apply(client, credit='40', points=0), (first, second)))
    assert sorted(result.status_code for result in results) == [200, 422]
    assert first.get('/api/customer').json()['wallet']['credit_cents'] == 1000


def test_order_email_must_match_signed_in_wallet_and_other_accounts_cannot_redeem(live_setup):
    app, admin, employee = live_setup
    client, cid = account(app, 'other@example.test')
    assert new_order(app, client=client)[1].status_code == 422
    guest, result, _ = new_order(app)
    # Possessing a job link still does not grant access to a different wallet.
    guest.cookies.set('signshop_customer', client.cookies.get('signshop_customer'))
    assert apply(guest).status_code == 403


def test_verified_custom_payment_earns_points_and_void_reverses_them(env):
    app, admin, employee = env
    client, cid = account(app, 'customer@example.test')
    jid = create_banner(admin)
    finalize(admin, jid)
    buyer = portal(app, admin, jid)
    buyer.cookies.set('signshop_customer', client.cookies.get('signshop_customer'))
    accept(buyer)
    assert buyer.post('/api/portal/rewards/link', json={}).status_code == 200
    result = payment(admin, jid, '10')
    assert result.status_code == 200, result.text
    assert client.get('/api/customer').json()['wallet']['points'] == 10
    pid = result.json()['payment_id']
    assert admin.post(f'/api/staff/payments/{pid}/void', json={'reason': 'Local correction'}).status_code == 200
    assert client.get('/api/customer').json()['wallet']['points'] == 0


def upload(client, jid, name='ready.png'):
    response = client.post(f'/api/jobs/{jid}/artwork', files={'file': (name, image_bytes(), 'image/png')})
    assert response.status_code == 200, response.text
    return response.json()


def approve_preview(client, files, version=1, **extra):
    return client.post('/api/portal/artwork-preview/approve', json={
        'name': 'Preview customer', 'confirm': True, 'quote_version': version,
        'terms_version': '2026-09-30', 'files': files} | extra)


def manifest(asset, indexes):
    return {'asset_id': asset['asset_id'], 'sha256': asset['sha256'], 'line_indices': indexes}


def test_uploaded_preview_is_approved_proof_before_payment(live_setup):
    app, admin, employee = live_setup
    client, result, _ = new_order(app)
    jid = result.json()['job_id']
    uploaded = upload(client, jid)
    response = approve_preview(client, [manifest(uploaded, [0])])
    assert response.status_code == 200, response.text
    assert approve_preview(client, [manifest(uploaded, [0])]).json()['already_approved']
    job = client.get('/api/portal/job').json()
    assert job['totals']['paid_cents'] == 0
    assert job['proofs'][0]['status'] == 'approved'
    assert job['proofs'][0]['decisions'][0]['method'] == 'customer_upload_preview'
    assert job['proofs'][0]['approved_files'][0]['sha256'] == uploaded['sha256']
    terms = job['proofs'][0]['terms_acceptance']
    assert terms['version'] == '2026-09-30' and terms['accepted_at']
    assert terms['signer_name'] == 'Preview customer' and terms['terms']['sections']
    assert job['checkout']['can_pay']
    with transaction(app.state.database) as conn:
        acceptance = conn.execute('SELECT * FROM job_terms_acceptances WHERE proof_id=?', (response.json()['proof_id'],)).fetchone()
        assert acceptance['terms_version'] == '2026-09-30'
        assert json.loads(acceptance['terms_snapshot'])['sections']
    open_session(app, client, jid)


def test_preview_approval_requires_explicit_consent_current_scope_and_exact_hash(live_setup):
    app, admin, employee = live_setup
    client, result, _ = new_order(app)
    asset = upload(client, result.json()['job_id'])
    files = [manifest(asset, [0])]
    assert approve_preview(client, files, confirm=False).status_code == 422
    assert approve_preview(client, files, version=99).status_code == 409
    assert approve_preview(client, files, terms_version='old').status_code == 409
    assert client.post('/api/portal/artwork-preview/approve', json={
        'name': 'Preview customer', 'confirm': True, 'quote_version': 1, 'files': files}).status_code == 409
    assert approve_preview(client, [files[0] | {'sha256': 'forged'}]).status_code == 409
    assert not client.get('/api/portal/job').json()['proofs']


def test_versioned_terms_acceptance_is_only_recorded_when_the_version_is_submitted(live_setup):
    app, admin, employee = live_setup
    client, result, body = new_order(app)
    first = result.json()['job_id']
    with transaction(app.state.database) as conn:
        assert not conn.execute('SELECT 1 FROM job_terms_acceptances WHERE job_id=?', (first,)).fetchone()
    body.update(request_id=str(uuid.uuid4()), terms_version='2026-09-30')
    response = client.post('/api/orders', json=body)
    assert response.status_code == 200, response.text
    with transaction(app.state.database) as conn:
        terms = conn.execute('SELECT * FROM job_terms_acceptances WHERE job_id=?', (response.json()['job_id'],)).fetchone()
        assert terms['terms_version'] == '2026-09-30' and terms['method'] == 'online_checkout'


def test_complete_multi_product_preview_covers_every_printed_item(live_setup):
    app, admin, employee = live_setup
    client = anonymous(app)
    items = [{'product_id': 1, 'width': 3, 'height': 3, 'quantity': 50},
             {'product_id': 4, 'width': 72, 'height': 36, 'quantity': 1}]
    quote = client.post('/api/calculate', json={'items': items}).json()
    result = client.post('/api/orders', json={'items': items, 'fingerprint': quote['fingerprint'],
        'request_id': str(uuid.uuid4()), 'customer_name': 'Preview customer',
        'customer_email': 'preview@example.test', 'title': 'Multi-product preview',
        'fulfillment': 'pickup', 'confirm': True})
    assert result.status_code == 200, result.text
    client.headers['X-CSRF-Token'] = result.json()['csrf']
    jid = result.json()['job_id']
    first, second = upload(client, jid, 'item-1-stickers.png'), upload(client, jid, 'item-2-banner.png')
    assert approve_preview(client, [manifest(first, [0])]).status_code == 422
    approved = approve_preview(client, [manifest(first, [0]), manifest(second, [1])])
    assert approved.status_code == 200, approved.text
    proof = client.get('/api/portal/job').json()['proofs'][0]
    assert len(proof['approved_files']) == 2 and len(proof['specs']) == 2
    assert proof['filename'].endswith('approved-preview-package.png')


def test_site_survey_has_extra_fee_disclosure_and_blocks_artwork_approval(live_setup):
    app, admin, employee = live_setup
    client, result, _ = new_order(app)
    jid = result.json()['job_id']
    asset = upload(client, jid)
    request = client.post('/api/portal/appointment-request', json={'kind': 'site_survey',
        'requested_date': '2026-10-05', 'window': 'Morning', 'location': 'Local test address'})
    assert request.status_code == 200, request.text
    assert approve_preview(client, [manifest(asset, [0])]).status_code == 409
    assert employee.post(f'/api/staff/jobs/{jid}/site-survey/complete', json={'confirm': True, 'note': 'Measured'}).status_code == 403
    assert admin.post(f'/api/staff/jobs/{jid}/site-survey/complete', json={'confirm': True,
        'note': 'Measurements verified against current order scope.'}).status_code == 200
    assert approve_preview(client, [manifest(asset, [0])]).status_code == 200


def test_changed_sizing_requires_new_proof_but_price_only_changes_do_not(env):
    app, admin, employee = env
    jid = create_banner(admin)
    finalize(admin, jid)
    buyer = portal(app, admin, jid)
    accept(buyer)
    approve(buyer, proof(admin, jid))
    # A zero deposit isolates the artwork gate from payment prerequisites.
    with transaction(app.state.database, True) as conn:
        conn.execute("UPDATE jobs SET deposit_percent='0' WHERE id=?", (jid,))
        task = {'dependencies': '[]', 'gate': 'production'}
        assert not gate_reason(conn, get_job(conn, jid), task)
        conn.execute('UPDATE jobs SET extra_price_cents=1000,quote_version=quote_version+1,'
                     'accepted_version=quote_version+1 WHERE id=?', (jid,))
        assert not gate_reason(conn, get_job(conn, jid), task)
        scope = json.loads(get_job(conn, jid)['quote_snapshot'])
        scope['lines'][0]['width'] = '96'
        conn.execute('UPDATE jobs SET quote_snapshot=? WHERE id=?', (json.dumps(scope), jid))
        assert 'sizing or scope differs' in gate_reason(conn, get_job(conn, jid), task)


def test_terms_upgrade_preserves_custom_settings_and_existing_order_snapshots(live_setup):
    app, admin, employee = live_setup
    client, result, _ = new_order(app)
    with transaction(app.state.database, True) as conn:
        frozen = dict(conn.execute('SELECT * FROM checkout_orders WHERE job_id=?', (result.json()['job_id'],)).fetchone())
        shop = json.loads(conn.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
        shop.update(checkout_terms='Owner-customized contract language.', rewards_points_per_dollar='2')
        shop.pop('rewards_point_value_cents', None)
        conn.execute('UPDATE settings SET data=? WHERE id=1', (json.dumps(shop),))
        conn.execute('DELETE FROM schema_version WHERE version>=11')
    initialize(app.state.database)
    with transaction(app.state.database) as conn:
        current = json.loads(conn.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
        assert current['checkout_terms'] == 'Owner-customized contract language.'
        assert current['rewards_points_per_dollar'] == '2'
        assert current['rewards_point_value_cents'] == '1'
        assert dict(conn.execute('SELECT * FROM checkout_orders WHERE job_id=?', (result.json()['job_id'],)).fetchone()) == frozen
    legacy = 'I confirm the product, size and quantity. I will review and approve a proof before production. Tax and any selected delivery charge are shown at secure checkout.'
    with transaction(app.state.database, True) as conn:
        current['checkout_terms'] = legacy
        conn.execute('UPDATE settings SET data=? WHERE id=1', (json.dumps(current),))
        conn.execute('DELETE FROM schema_version WHERE version>=11')
    initialize(app.state.database)
    with transaction(app.state.database) as conn:
        assert json.loads(conn.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])['checkout_terms'] == CHECKOUT_CONFIRMATION
    terms = client.get('/terms')
    assert terms.status_code == 200 and 'additional fee' in terms.text and 'Once printed' in terms.text


def test_full_terms_are_accessible_as_a_public_website_page(env):
    app, admin, employee = env
    visitor = anonymous(app)
    response = visitor.get('/terms')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert '<main' in response.text and '<article' in response.text
    assert 'your private order page' in response.text
    for index, (heading, _) in enumerate(job_terms.SECTIONS, 1):
        assert heading in response.text
        assert f'href="#term-{index}"' in response.text
        assert f'id="term-{index}"' in response.text
    assert visitor.get('/api/job-terms').json()['version'] == job_terms.VERSION


def test_shop_artwork_approval_accepts_and_retains_the_exact_terms(env, monkeypatch):
    app, admin, employee = env
    jid = create_banner(admin)
    finalize(admin, jid)
    buyer = portal(app, admin, jid)
    accept(buyer)
    pid = proof(admin, jid)
    url = f'/api/portal/proofs/{pid}/decision'
    consent = {'name': 'Saved approval example', 'action': 'approve',
               'confirm': True, 'terms_version': job_terms.VERSION}
    assert buyer.post(url, json=consent | {'confirm': False}).status_code == 422
    assert buyer.post(url, json=consent | {'terms_version': 'outdated'}).status_code == 409
    assert not buyer.get('/api/portal/job').json()['proofs'][0]['terms_acceptance']
    assert buyer.post(url, json=consent).status_code == 200
    approved = buyer.get('/api/portal/job').json()['proofs'][0]
    saved = approved['terms_acceptance']
    assert approved['status'] == 'approved'
    assert saved['signer_name'] == consent['name'] and saved['accepted_at']
    assert saved['terms'] == job_terms.public_terms()
    with transaction(app.state.database) as conn:
        record = conn.execute('SELECT * FROM job_terms_acceptances WHERE proof_id=?', (pid,)).fetchone()
        assert record['method'] == 'shop_proof'
        assert json.loads(record['file_manifest'])[0]['sha256'] == approved['sha256']
    # The order keeps what was accepted even if the public terms later change.
    monkeypatch.setattr(job_terms, 'VERSION', '2026-10-01')
    monkeypatch.setattr(job_terms, 'SECTIONS', [('New public version', 'New example wording.')])
    refreshed = buyer.get('/api/portal/job').json()
    assert refreshed['job_terms']['version'] == '2026-10-01'
    assert refreshed['proofs'][0]['terms_acceptance'] == saved
    visitor = anonymous(app)
    assert visitor.get('/api/portal/job').status_code in (401, 403)
    assert consent['name'] not in visitor.get('/terms').text


def test_all_portal_proof_notifications_include_the_combined_review_terms(env, monkeypatch):
    app, admin, employee = env
    sent = []
    monkeypatch.setattr('app.main.notify_customer', lambda *args, **kwargs: sent.append(args) or True)
    jid = create_banner(admin)
    finalize(admin, jid)
    pid = proof(admin, jid)
    assert employee.post(f'/api/staff/jobs/{jid}/proofs/{pid}/send', json={}).status_code == 200
    artwork = admin.post(f'/api/jobs/{jid}/artwork', files={
        'file': ('layout-source.png', image_bytes(), 'image/png')})
    assert artwork.status_code == 200, artwork.text
    layout = admin.post(f'/api/staff/jobs/{jid}/layout', json={
        'artwork': {'0': artwork.json()['asset_id']}, 'publish_as_proof': True})
    assert layout.status_code == 200, layout.text
    proof_messages = [args for args in sent if args[2].startswith('proof_pending_')]
    assert len(proof_messages) == 3  # Uploaded proof, resend, generated proof.
    for args in proof_messages:
        assert args[4] == 'Review your artwork & terms'
        assert args[5] == job_terms.PROOF_REVIEW_NOTICE
        assert 'dimensions' in args[5] and 'additional quoted fee' in args[5]
        assert 'new paid order' in args[5]
        assert '/portal#token=' in args[6]


def test_v11_upgrade_keeps_a_restorable_database_and_artwork_backup(tmp_path):
    database = tmp_path / 'data' / 'signshop.sqlite3'
    initialize(database)
    uploads = database.parent / 'uploads'
    uploads.mkdir()
    (uploads / 'proof.png').write_bytes(image_bytes())
    with transaction(database, True) as conn:
        conn.execute('DELETE FROM schema_version WHERE version=11')
        conn.execute('INSERT INTO settings(id,data) VALUES(1,?)',
                     (json.dumps({'checkout_terms': 'Owner custom terms'}),))
    initialize(database)
    backups = list((database.parent / 'backups').glob('pre-v11-*.zip'))
    assert len(backups) == 1
    assert backups[0].stat().st_mode & 0o777 == 0o600
    with zipfile.ZipFile(backups[0]) as archive:
        assert archive.read('uploads/proof.png') == image_bytes()
        restored = tmp_path / 'restored.sqlite3'
        restored.write_bytes(archive.read('signshop.sqlite3'))
    with sqlite3.connect(restored) as conn:
        assert conn.execute('SELECT max(version) FROM schema_version').fetchone()[0] == 10
        assert json.loads(conn.execute('SELECT data FROM settings').fetchone()[0]) == {
            'checkout_terms': 'Owner custom terms'}
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    initialize(database)
    assert list((database.parent / 'backups').glob('pre-v11-*.zip')) == backups


def test_failed_v11_backup_stops_the_upgrade_before_schema_changes(tmp_path, monkeypatch):
    database = tmp_path / 'data' / 'signshop.sqlite3'
    initialize(database)
    with transaction(database, True) as conn:
        conn.execute('DELETE FROM schema_version WHERE version=11')
        conn.execute('DROP TABLE job_terms_acceptances')
    def fail_backup(*args):
        raise OSError('Test backup destination unavailable')
    monkeypatch.setattr('app.db._backup_before_v11', fail_backup)
    import pytest
    with pytest.raises(OSError, match='backup destination unavailable'):
        initialize(database)
    with transaction(database) as conn:
        assert conn.execute('SELECT max(version) FROM schema_version').fetchone()[0] == 10
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='job_terms_acceptances'").fetchone()
