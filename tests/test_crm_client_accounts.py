import re

from app import crm as crm_module
from app.db import transaction
from tests.conftest import anonymous, portal, accept


def _crm_contact(admin, email):
    data = admin.get('/api/admin/crm').json()['contacts']
    return next(item for item in data if item['email'].lower() == email.lower())


def test_crm_promotes_real_orders_but_not_open_quotes(env):
    app, admin, employee = env
    email = 'promotion-test@example.test'
    created = admin.post('/api/staff/jobs', json={
        'title': 'Promotion test',
        'customer_name': 'Promotion Test',
        'customer_email': email,
        'phone': '8135550201',
        'items': [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1}],
        'workflow_id': 2,
    })
    assert created.status_code == 200, created.text
    job_id = created.json()['job_id']

    lead = _crm_contact(admin, email)
    assert lead['status'] == 'new_lead'

    # Website checkout jobs are real orders even before payment settles.
    with transaction(app.state.database, True) as conn:
        conn.execute("UPDATE jobs SET source='checkout' WHERE id=?", (job_id,))
    customer = _crm_contact(admin, email)
    assert customer['status'] == 'customer'


def test_accepted_custom_quote_promotes_lead_to_customer(env):
    app, admin, employee = env
    email = 'accepted-client@example.test'
    job = admin.post('/api/staff/jobs', json={
        'title': 'Accepted custom quote',
        'customer_name': 'Accepted Client',
        'customer_email': email,
        'phone': '8135550202',
        'items': [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1}],
        'workflow_id': 2,
    })
    assert job.status_code == 200, job.text
    job_id = job.json()['job_id']

    current = admin.get(f'/api/staff/jobs/{job_id}').json()
    quoted = admin.post(f'/api/staff/jobs/{job_id}/quote', json={
        'version': current['quote_version'], 'charges_verified': True,
        'deposit_percent': '50', 'shipping': '0', 'tax': '0',
    })
    assert quoted.status_code == 200, quoted.text
    current = admin.get(f'/api/staff/jobs/{job_id}').json()
    published = admin.post(f'/api/staff/jobs/{job_id}/publish', json={
        'version': current['quote_version'], 'reviewed': True,
    })
    assert published.status_code == 200, published.text
    assert _crm_contact(admin, email)['status'] != 'customer'

    client = portal(app, admin, job_id)
    accept(client)
    assert _crm_contact(admin, email)['status'] == 'customer'


def test_credit_can_be_added_before_account_claim_and_survives_invitation(env, monkeypatch):
    app, admin, employee = env
    email = 'credit-before-account@example.test'
    created = admin.post('/api/admin/crm', json={
        'name': 'Credit Client',
        'email': email,
        'phone': '8135550203',
        'status': 'customer',
    })
    assert created.status_code == 200, created.text
    contact_id = created.json()['id']

    credited = admin.post(f'/api/admin/crm/{contact_id}/credit', json={
        'credit': '125.00',
        'reason': 'Overpayment credit',
        'operation_id': 'test-overpayment-credit-1',
    })
    assert credited.status_code == 200, credited.text
    assert credited.json()['wallet']['credit_cents'] == 12500

    detail = admin.get(f'/api/admin/crm/{contact_id}').json()
    assert detail['account']['status'] == 'pending'
    assert detail['account']['wallet']['credit_cents'] == 12500

    sent = {}
    def fake_direct(recipient, subject, title, message, action_url=None, action_label='View account'):
        sent.update(recipient=recipient, action_url=action_url, action_label=action_label)
        return True
    monkeypatch.setattr(crm_module, 'notify_direct', fake_direct)

    invited = admin.post(f'/api/admin/crm/{contact_id}/invite-account', json={})
    assert invited.status_code == 200, invited.text
    assert sent['recipient'] == email
    assert sent['action_label'] == 'Create my account'
    token = re.search(r'[?&]claim=([^&]+)', sent['action_url']).group(1)

    client = anonymous(app)
    preview = client.post('/api/customer/claim/preview', json={'token': token})
    assert preview.status_code == 200, preview.text
    assert preview.json()['email'] == email

    claimed = client.post('/api/customer/claim', json={
        'token': token,
        'password': 'ClaimedCustomerPassword2026',
    })
    assert claimed.status_code == 200, claimed.text
    profile = client.get('/api/customer')
    assert profile.status_code == 200, profile.text
    assert profile.json()['customer']['email'] == email
    assert profile.json()['wallet']['credit_cents'] == 12500
    assert admin.get(f'/api/admin/crm/{contact_id}').json()['account']['status'] == 'active'
