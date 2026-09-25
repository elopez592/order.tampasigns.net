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
