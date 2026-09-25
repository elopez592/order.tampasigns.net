from datetime import datetime, timedelta, timezone

from app.db import transaction
from tests.conftest import create_banner, finalize, portal, accept, proof, approve


def test_crm_backfills_jobs_and_is_admin_only(env):
    app, admin, employee = env
    response = admin.get('/api/admin/crm')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['totals']['contacts'] >= 1
    assert any(contact['order_count'] >= 1 for contact in data['contacts'])
    assert employee.get('/api/admin/crm').status_code == 403


def test_crm_create_update_dedupe_and_job_linking(env):
    app, admin, employee = env
    created = admin.post('/api/admin/crm', json={
        'name': 'Vanguard Contact',
        'company': 'Vanguard Commercial Flooring',
        'email': 'crm-vanguard@example.test',
        'phone': '(813) 252-5198',
        'status': 'new_lead',
        'source': 'Website',
        'tags': 'Storefront, Repeat Customer',
        'notes': 'Door graphics lead',
        'follow_up_date': '2026-09-29',
    })
    assert created.status_code == 200, created.text
    contact = created.json()
    assert contact['company'] == 'Vanguard Commercial Flooring'
    assert contact['tags'] == ['Storefront', 'Repeat Customer']

    duplicate = admin.post('/api/admin/crm', json={
        'name': 'Duplicate',
        'email': 'CRM-VANGUARD@example.test',
        'phone': '8135550100',
    })
    assert duplicate.status_code == 409

    job = admin.post('/api/staff/jobs', json={
        'title': 'CRM storefront job',
        'customer_name': 'Vanguard Contact',
        'customer_email': 'crm-vanguard@example.test',
        'phone': '(813) 252-5198',
        'items': [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1}],
        'workflow_id': 2,
    })
    assert job.status_code == 200, job.text

    detail = admin.get(f"/api/admin/crm/{contact['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()['order_count'] == 1
    assert detail.json()['jobs'][0]['title'] == 'CRM storefront job'

    updated = admin.patch(f"/api/admin/crm/{contact['id']}", json={
        'status': 'quote_sent',
        'tags': ['Storefront', 'Commercial'],
        'notes': 'Quote sent; follow up Tuesday.',
        'follow_up_date': '2026-09-30',
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()['status'] == 'quote_sent'
    assert updated.json()['tags'] == ['Storefront', 'Commercial']
    assert updated.json()['follow_up_date'] == '2026-09-30'

    csv_response = admin.get('/api/admin/crm.csv')
    assert csv_response.status_code == 200
    assert 'Vanguard Commercial Flooring' in csv_response.text



def test_crm_project_reminder_uses_open_job_and_cooldown(env, monkeypatch):
    app, admin, employee = env
    created = admin.post('/api/admin/crm', json={
        'name': 'Reminder Customer',
        'email': 'reminder@example.test',
        'phone': '8135550199',
        'status': 'quote_sent',
    })
    assert created.status_code == 200, created.text
    contact = created.json()

    job = admin.post('/api/staff/jobs', json={
        'title': 'Storefront door graphics',
        'customer_name': 'Reminder Customer',
        'customer_email': 'reminder@example.test',
        'phone': '8135550199',
        'items': [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1}],
        'workflow_id': 2,
    })
    assert job.status_code == 200, job.text

    sent = {}
    from app import crm as crm_module

    def fake_notify(database, job_id, event_key, recipient, audience, subject, title,
                    message, action_url=None, action_label='View order', force=False):
        sent.update({
            'job_id': job_id,
            'recipient': recipient,
            'subject': subject,
            'title': title,
            'message': message,
            'action_url': action_url,
            'action_label': action_label,
        })
        return True

    monkeypatch.setattr(crm_module, 'notify_one', fake_notify)

    response = admin.post(f"/api/admin/crm/{contact['id']}/remind", json={})
    assert response.status_code == 200, response.text
    assert sent['recipient'] == 'reminder@example.test'
    assert sent['title'] == 'Don’t forget about your project'
    assert 'Storefront door graphics' in sent['message']
    assert sent['action_label'] == 'Continue my project'
    assert '/portal#token=' in sent['action_url']

    detail = admin.get(f"/api/admin/crm/{contact['id']}")
    assert detail.status_code == 200
    assert detail.json()['reminders'][0]['status'] == 'sent'
    assert detail.json()['can_remind'] is True

    repeated = admin.post(f"/api/admin/crm/{contact['id']}/remind", json={})
    assert repeated.status_code == 429


def test_crm_reminder_blocks_completed_or_missing_email(env):
    app, admin, employee = env
    completed = admin.post('/api/admin/crm', json={
        'name': 'Completed Customer',
        'email': 'completed-reminder@example.test',
        'phone': '8135550188',
        'status': 'completed',
    })
    assert completed.status_code == 200
    response = admin.post(f"/api/admin/crm/{completed.json()['id']}/remind", json={})
    assert response.status_code == 409



def _age(timestamp_days):
    return (datetime.now(timezone.utc) - timedelta(days=timestamp_days)).isoformat(timespec='seconds')


def _capture_reminders(monkeypatch):
    sent = []
    from app import crm as crm_module

    def fake_notify(database, job_id, event_key, recipient, audience, subject, title,
                    message, action_url=None, action_label='View order', force=False):
        sent.append({
            'job_id': job_id, 'event_key': event_key, 'recipient': recipient,
            'subject': subject, 'title': title, 'message': message,
            'action_url': action_url, 'action_label': action_label,
        })
        return True

    monkeypatch.setattr(crm_module, 'notify_one', fake_notify)
    return sent


def test_automatic_quote_reminder_after_three_days_only_once(env, monkeypatch):
    app, admin, employee = env
    job_id = admin.post('/api/staff/jobs', json={
        'title': 'Automatic quote follow-up',
        'customer_name': 'Quote Reminder',
        'customer_email': 'auto-quote@example.test',
        'phone': '8135550111',
        'items': [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1}],
        'workflow_id': 2,
    }).json()['job_id']
    finalize(admin, job_id)
    with transaction(app.state.database, True) as conn:
        conn.execute("UPDATE events SET created_at=? WHERE job_id=? AND action='quote.published'",
                     (_age(4), job_id))

    sent = _capture_reminders(monkeypatch)
    response = admin.post('/api/admin/crm/reminders/run', json={})
    assert response.status_code == 200, response.text
    assert response.json()['sent'] == 1
    assert response.json()['items'][0]['kind'] == 'quote'
    assert sent[0]['title'] == 'Don’t forget about your project'
    assert sent[0]['action_label'] == 'Review my quote'

    repeated = admin.post('/api/admin/crm/reminders/run', json={})
    assert repeated.status_code == 200
    assert repeated.json()['sent'] == 0
    assert len(sent) == 1


def test_automatic_proof_reminder_after_three_days(env, monkeypatch):
    app, admin, employee = env
    job_id = admin.post('/api/staff/jobs', json={
        'title': 'Automatic proof follow-up',
        'customer_name': 'Proof Reminder',
        'customer_email': 'auto-proof@example.test',
        'phone': '8135550112',
        'items': [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1}],
        'workflow_id': 2,
    }).json()['job_id']
    finalize(admin, job_id)
    customer = portal(app, admin, job_id)
    accept(customer)
    proof_id = proof(admin, job_id)
    with transaction(app.state.database, True) as conn:
        conn.execute('UPDATE proofs SET created_at=? WHERE id=?', (_age(4), proof_id))

    sent = _capture_reminders(monkeypatch)
    response = admin.post('/api/admin/crm/reminders/run', json={})
    assert response.status_code == 200, response.text
    assert response.json()['sent'] == 1
    assert response.json()['items'][0]['kind'] == 'proof'
    assert sent[0]['title'] == 'Your proof is waiting for approval'
    assert sent[0]['action_label'] == 'Review my proof'


def test_automatic_deposit_reminder_after_seven_days(env, monkeypatch):
    app, admin, employee = env
    job_id = admin.post('/api/staff/jobs', json={
        'title': 'Automatic deposit follow-up',
        'customer_name': 'Deposit Reminder',
        'customer_email': 'auto-deposit@example.test',
        'phone': '8135550113',
        'items': [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1}],
        'workflow_id': 2,
    }).json()['job_id']
    finalize(admin, job_id)
    customer = portal(app, admin, job_id)
    accept(customer)
    proof_id = proof(admin, job_id)
    approve(customer, proof_id)
    with transaction(app.state.database, True) as conn:
        conn.execute("UPDATE proof_decisions SET created_at=? WHERE proof_id=? AND action='approve'",
                     (_age(8), proof_id))

    sent = _capture_reminders(monkeypatch)
    response = admin.post('/api/admin/crm/reminders/run', json={})
    assert response.status_code == 200, response.text
    assert response.json()['sent'] == 1
    assert response.json()['items'][0]['kind'] == 'payment'
    assert sent[0]['title'] == 'Ready to keep your project moving?'
    assert 'required deposit' in sent[0]['message'].lower()


def test_automatic_reminders_can_be_paused_per_contact(env, monkeypatch):
    app, admin, employee = env
    job_id = admin.post('/api/staff/jobs', json={
        'title': 'Paused follow-up',
        'customer_name': 'Paused Reminder',
        'customer_email': 'paused-reminder@example.test',
        'phone': '8135550114',
        'items': [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1}],
        'workflow_id': 2,
    }).json()['job_id']
    finalize(admin, job_id)
    with transaction(app.state.database, True) as conn:
        conn.execute("UPDATE events SET created_at=? WHERE job_id=? AND action='quote.published'",
                     (_age(4), job_id))

    contacts = admin.get('/api/admin/crm').json()['contacts']
    contact = next(x for x in contacts if x['email'] == 'paused-reminder@example.test')
    updated = admin.patch(f"/api/admin/crm/{contact['id']}", json={'auto_reminders': False})
    assert updated.status_code == 200
    assert updated.json()['auto_reminders'] is False

    sent = _capture_reminders(monkeypatch)
    response = admin.post('/api/admin/crm/reminders/run', json={})
    assert response.status_code == 200
    assert response.json()['sent'] == 0
    assert sent == []


def test_internal_reminder_endpoint_requires_scheduler_secret(env, monkeypatch):
    app, admin, employee = env
    monkeypatch.setenv('REMINDER_CRON_SECRET', 'test-reminder-cron-secret')
    missing = admin.post('/api/internal/crm-reminders/run', json={})
    assert missing.status_code == 401
    good = admin.post('/api/internal/crm-reminders/run', json={},
                      headers={'Authorization': 'Bearer test-reminder-cron-secret'})
    assert good.status_code == 200, good.text
