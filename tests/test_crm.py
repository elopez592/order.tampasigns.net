from tests.conftest import create_banner


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
