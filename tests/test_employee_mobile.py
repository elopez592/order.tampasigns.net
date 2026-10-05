import io
import json
import uuid
from decimal import Decimal

from PIL import Image

from app.db import settings, transaction
from app.main import create_app
from .conftest import anonymous, portal, accept, sign_in


def add_client(employee, suffix='one'):
    response = employee.post('/api/staff/clients', json={
        'name': 'Survey Client', 'company': 'Survey Shop',
        'email': f'field-{suffix}@example.test', 'phone': '813-555-0100'})
    assert response.status_code == 200, response.text
    return response.json()['id']


def survey_payload(contact_id, **extra):
    return dict(client_key=str(uuid.uuid4()), contact_id=contact_id, title='Storefront survey',
                address='123 Test Street, Tampa', measurements=[{
                    'label': 'Left window', 'width': '3', 'height': '6', 'unit': 'ft',
                    'quantity': 1, 'product_id': 4, 'notes': 'Top pane only'}], **extra)


def save_survey(employee, contact_id, **extra):
    payload = survey_payload(contact_id, **extra)
    response = employee.post('/api/staff/surveys', json=payload)
    assert response.status_code == 200, response.text
    return response.json(), payload


def live_rates(app, tax='7.5'):
    with transaction(app.state.database, True) as conn:
        shop = settings(conn)
        shop.update(rates_live=True, checkout_tax_reviewed=True, checkout_pickup_tax_percent=tax)
        conn.execute('UPDATE settings SET data=?', (json.dumps(shop),))


def estimate(employee, contact_id, items=None, **extra):
    payload = {'contact_id': contact_id, 'title': 'Field estimate', 'request_key': str(uuid.uuid4()),
               'items': items or [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1}], **extra}
    response = employee.post('/api/staff/estimates/calculate', json=payload)
    assert response.status_code == 200, response.text
    payload['fingerprint'] = response.json()['fingerprint']
    saved = employee.post('/api/staff/estimates', json=payload)
    assert saved.status_code == 200, saved.text
    return saved.json()['job_id'], payload, response.json()


def test_mobile_shell_installation_and_private_apis(env):
    app, admin, employee = env
    visitor = anonymous(app)
    shell = visitor.get('/staff/app')
    assert shell.status_code == 200
    assert '/staff/manifest.webmanifest' in shell.text and 'apple-mobile-web-app-capable' in shell.text
    assert shell.headers['X-Robots-Tag'] == 'noindex, nofollow'
    assert shell.headers['Permissions-Policy'].startswith('camera=(self)')
    worker = visitor.get('/staff/sw.js')
    assert worker.headers['Service-Worker-Allowed'] == '/staff/'
    manifest = visitor.get('/staff/manifest.webmanifest').json()
    assert manifest['start_url'] == '/staff/app' and manifest['display'] == 'standalone'
    icon_path = manifest['icons'][0]['src']
    assert icon_path in shell.text and icon_path in visitor.get('/staff').text
    icon = visitor.get(icon_path)
    assert icon.status_code == 200 and icon.headers['content-type'] == 'image/png'
    image = Image.open(io.BytesIO(icon.content))
    assert image.size == (180, 180)
    image.verify()
    for fallback in ('/apple-touch-icon.png', '/apple-touch-icon-precomposed.png', '/staff/apple-touch-icon.png'):
        assert visitor.get(fallback).content == icon.content
    for url in ('/api/staff/clients', '/api/staff/surveys', '/api/staff/invoices/1'):
        assert visitor.get(url).status_code == 401
    employee.headers.pop('X-CSRF-Token')
    assert employee.post('/api/staff/clients', json={'name': 'CSRF test'}).status_code == 403


def test_employee_crm_is_shared_and_owner_controls_remain_private(env):
    app, admin, employee = env
    cid = add_client(employee)
    assert any(c['id'] == cid for c in admin.get('/api/admin/crm').json()['contacts'])
    assert employee.post('/api/staff/clients', json={'name': 'Duplicate', 'email': 'field-one@example.test'}).status_code == 409
    response = employee.patch(f'/api/staff/clients/{cid}', json={'phone': '813-555-0123', 'notes': 'Door top glass only', 'status': 'lost'})
    assert response.status_code == 200
    client = employee.get(f'/api/staff/clients/{cid}').json()
    assert client['phone'] == '813-555-0123' and client['notes'] == 'Door top glass only'
    assert client['status'] == 'new_lead'
    assert employee.get('/api/admin/crm').status_code == 403
    assert employee.put('/api/admin/settings', json={}).status_code == 403


def test_survey_units_retries_conflicts_and_other_employee(env):
    app, admin, employee = env
    cid = add_client(employee)
    saved, payload = save_survey(employee, cid)
    assert Decimal(saved['measurements'][0]['width_inches']) == 36
    assert Decimal(saved['measurements'][0]['height_inches']) == 72
    again = employee.post('/api/staff/surveys', json=payload)
    assert again.json()['id'] == saved['id'] and again.json()['version'] == 1
    payload.update(id=saved['id'], version=1, title='Updated site visit')
    assert employee.post('/api/staff/surveys', json=payload).json()['version'] == 2
    payload['title'] = 'Stale overwrite'
    assert employee.post('/api/staff/surveys', json=payload).status_code == 409
    user = admin.post('/api/admin/users', json={'name': 'Another Employee', 'email': 'other-field@example.test', 'role': 'employee'}).json()
    other = sign_in(app, 'other-field@example.test', user['temporary_password'])
    payload['version'] = 2
    assert other.post('/api/staff/surveys', json=payload).status_code == 403


def test_survey_validates_sizes_and_contact_project_relationship(env):
    app, admin, employee = env
    cid = add_client(employee)
    payload = survey_payload(cid)
    payload['measurements'][0]['width'] = 'NaN'
    assert employee.post('/api/staff/surveys', json=payload).status_code == 422
    payload['measurements'][0]['width'] = '-1'
    assert employee.post('/api/staff/surveys', json=payload).status_code == 422
    jid, _, _ = estimate(employee, cid)
    other = add_client(employee, 'two')
    assert employee.post('/api/staff/surveys', json=survey_payload(other, job_id=jid)).status_code == 422


def test_photos_are_idempotent_staff_only_and_not_portal_artwork(env):
    app, admin, employee = env
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    saved, _ = save_survey(employee, cid, job_id=jid)
    data = io.BytesIO()
    Image.new('RGB', (20, 20), 'teal').save(data, format='PNG')
    upload = {'files': {'file': ('window.png', data.getvalue(), 'image/png')}, 'data': {'client_key': 'photo-one'}}
    url = f'/api/staff/surveys/{saved["id"]}/files'
    first = employee.post(url, **upload)
    assert first.status_code == 200, first.text
    assert employee.post(url, **upload).json()['id'] == first.json()['id']
    assert len(employee.get(f'/api/staff/surveys/{saved["id"]}').json()['files']) == 1
    file_url = url + '/' + str(first.json()['id'])
    assert employee.get(file_url).status_code == 200
    customer = portal(app, admin, jid)
    assert customer.get(file_url).status_code == 401
    assert not customer.get('/api/portal/job').json()['assets']


def panel_image(color='teal'):
    data = io.BytesIO()
    Image.new('RGB', (35, 25), color).save(data, format='PNG')
    return data.getvalue()


def test_panel_photo_follows_survey_panel_into_quote_and_document(env):
    app, admin, employee = env
    live_rates(app)
    cid = add_client(employee)
    saved, _ = save_survey(employee, cid)
    key = saved['measurements'][0]['panel_key']
    url = f'/api/staff/surveys/{saved["id"]}/files'
    upload = dict(files={'file': ('left.png', panel_image(), 'image/png')}, data={'client_key': 'panel-left', 'panel_key': key})
    first = employee.post(url, **upload)
    assert first.status_code == 200, first.text
    fid = first.json()['id']
    assert employee.post(url, **upload).json()['id'] == fid
    assert employee.get(f'/api/staff/surveys/{saved["id"]}').json()['files'][0]['panel_key'] == key
    assert employee.post(url, files=upload['files'], data={'client_key': 'other', 'panel_key': 'missing'}).status_code == 422
    assert employee.post(url, files=upload['files'], data={'client_key': 'duplicate', 'panel_key': key}).status_code == 409
    jid, _, price = estimate(employee, cid, items=[{'product_id': 4, 'width': 36, 'height': 72, 'quantity': 1, 'survey_file_id': fid}], survey_id=saved['id'])
    job = employee.get(f'/api/staff/jobs/{jid}').json()
    assert job['totals']['total_cents'] == price['totals']['total_cents']
    assert job['panel_photos'][0]['line_index'] == 0 and not job['proofs'] and not job['assets']
    photo_url = f'/api/quote-photos/{job["panel_photos"][0]["id"]}'
    assert photo_url in employee.get(f'/api/staff/jobs/{jid}/estimate-document').text
    assert employee.get(photo_url).status_code == 200
    assert employee.post(f'/api/staff/estimates/{jid}/send', json={'version': 1, 'reviewed': True}).status_code == 200
    customer = portal(app, admin, jid)
    assert customer.get(photo_url).status_code == 200
    assert customer.get('/api/portal/job').json()['panel_photos'][0]['id'] == job['panel_photos'][0]['id']
    assert customer.get(url+'/'+str(fid)).status_code == 401
    assert employee.delete(url+'/'+str(fid)).status_code == 200
    assert employee.get(photo_url).status_code == 200  # The quote keeps its reference file.


def test_estimate_cannot_attach_a_different_surveys_photo(env):
    app, admin, employee = env
    cid = add_client(employee)
    source, _ = save_survey(employee, cid)
    other, _ = save_survey(employee, add_client(employee, 'different'))
    response = employee.post(f'/api/staff/surveys/{other["id"]}/files',
                             files={'file': ('other.png', panel_image(), 'image/png')}, data={'client_key': 'other-client-photo'})
    payload = dict(contact_id=cid, survey_id=source['id'], title='Wrong photo', request_key='wrong-photo',
                   items=[{'product_id': 4, 'width': 36, 'height': 72, 'quantity': 1, 'survey_file_id': response.json()['id']}])
    payload['fingerprint'] = employee.post('/api/staff/estimates/calculate', json=payload).json()['fingerprint']
    assert employee.post('/api/staff/estimates', json=payload).status_code == 422


def test_quote_photos_retry_privacy_replacement_and_invoice_snapshot(env):
    app, admin, employee = env
    live_rates(app)
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    url = f'/api/staff/jobs/{jid}/panel-photos'
    first_upload = dict(files={'file': ('front.png', panel_image(), 'image/png')},
                        data={'client_key': 'front-photo', 'line_index': 0, 'version': 1})
    response = employee.post(url, **first_upload)
    assert response.status_code == 200, response.text
    first = response.json()['id']
    assert employee.post(url, **first_upload).json()['id'] == first
    assert anonymous(app).get(f'/api/quote-photos/{first}').status_code == 401
    invoice = employee.post(f'/api/staff/jobs/{jid}/invoices', json={'version': 1, 'confirm': True}).json()
    invoice_url = f'/api/staff/invoices/{invoice["invoice_id"]}'
    snapshot = employee.get(invoice_url).text
    assert f'/api/quote-photos/{first}' in snapshot
    second_upload = dict(files={'file': ('replacement.png', panel_image('orange'), 'image/png')},
                         data={'client_key': 'replacement-photo', 'line_index': 0, 'version': 1})
    second = employee.post(url, **second_upload).json()['id']
    assert first != second and employee.get(f'/api/staff/jobs/{jid}').json()['panel_photos'][0]['id'] == second
    assert employee.get(invoice_url).text == snapshot and employee.get(f'/api/quote-photos/{first}').status_code == 200
    assert employee.post(url, **first_upload).json()['id'] == first
    assert employee.get(f'/api/staff/jobs/{jid}').json()['panel_photos'][0]['id'] == second
    assert employee.request('DELETE', url+f'/{second}', json={'version': 1}).status_code == 200
    assert employee.get(f'/api/staff/jobs/{jid}').json()['panel_photos'] == []
    other, _, _ = estimate(employee, add_client(employee, 'other'))
    customer = portal(app, admin, other)
    assert customer.get(f'/api/quote-photos/{first}').status_code == 404
    assert employee.post(f'/api/staff/estimates/{jid}/send', json={'version': 1, 'reviewed': True}).status_code == 200
    own = portal(app, admin, jid)
    accept(own)
    assert employee.post(url, **second_upload).json()['id'] == second
    assert employee.post(url, files=first_upload['files'], data={'client_key': 'after-acceptance', 'line_index': 0, 'version': 1}).status_code == 409


def test_quote_photos_validate_images_panel_indices_and_versions(env):
    app, admin, employee = env
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    url = f'/api/staff/jobs/{jid}/panel-photos'
    upload = {'file': ('panel.png', panel_image(), 'image/png')}
    for index, version in ((-1, 1), (1, 1), (0, 2)):
        assert employee.post(url, files=upload, data={'client_key': 'invalid', 'line_index': index, 'version': version}).status_code in (409, 422)
    assert employee.post(url, files={'file': ('not-photo.pdf', b'%PDF-1.4\n%%EOF', 'application/pdf')},
                         data={'client_key': 'pdf', 'line_index': 0, 'version': 1}).status_code == 422
    employee.headers.pop('X-CSRF-Token')
    assert employee.post(url, files=upload, data={'client_key': 'no-csrf', 'line_index': 0, 'version': 1}).status_code == 403


def test_panel_photo_migration_preserves_existing_survey_attachment(env):
    app, admin, employee = env
    saved, _ = save_survey(employee, add_client(employee))
    response = employee.post(f'/api/staff/surveys/{saved["id"]}/files',
                             files={'file': ('old.png', panel_image(), 'image/png')}, data={'client_key': 'old-file'})
    fid = response.json()['id']
    with transaction(app.state.database, True) as conn:
        conn.execute('DROP INDEX employee_survey_photo_panel')
        conn.execute('ALTER TABLE employee_survey_files DROP COLUMN panel_key')
    restarted = create_app(app.state.database.parent, demo=False)
    with transaction(restarted.state.database) as conn:
        row = conn.execute('SELECT id,panel_key FROM employee_survey_files WHERE id=?', (fid,)).fetchone()
        assert row['id'] == fid and row['panel_key'] == ''
    assert employee.get(f'/api/staff/surveys/{saved["id"]}/files/{fid}').status_code == 200


def test_survey_submission_requires_owner_verification_and_survives_restart(env):
    app, admin, employee = env
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    saved, _ = save_survey(employee, cid, job_id=jid)
    url = f'/api/staff/surveys/{saved["id"]}/action'
    submitted = employee.post(url, json={'action': 'submit', 'version': 1})
    assert submitted.status_code == 200, submitted.text
    assert employee.get(f'/api/staff/jobs/{jid}').json()['site_survey']['status'] == 'requested'
    assert employee.post(url, json={'action': 'verify', 'version': 2, 'confirm': True}).status_code == 403
    verified = admin.post(url, json={'action': 'verify', 'version': 2, 'confirm': True})
    assert verified.status_code == 200, verified.text
    assert employee.get(f'/api/staff/jobs/{jid}').json()['site_survey']['status'] == 'complete'
    second_app = create_app(app.state.database.parent, demo=False)
    with transaction(second_app.state.database) as conn:
        assert conn.execute('SELECT status FROM employee_surveys WHERE id=?', (saved['id'],)).fetchone()['status'] == 'verified'
    assert admin.post(url, json={'action': 'reopen', 'version': 3}).status_code == 200
    assert employee.get(f'/api/staff/jobs/{jid}').json()['site_survey']['status'] == 'requested'


def test_another_pending_survey_keeps_print_blocked(env):
    app, admin, employee = env
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    first, _ = save_survey(employee, cid, job_id=jid)
    second, _ = save_survey(employee, cid, job_id=jid)
    for s in (first, second):
        employee.post(f'/api/staff/surveys/{s["id"]}/action', json={'action': 'submit', 'version': 1})
    admin.post(f'/api/staff/surveys/{first["id"]}/action', json={'action': 'verify', 'version': 2, 'confirm': True})
    assert employee.get(f'/api/staff/jobs/{jid}').json()['site_survey']['status'] == 'requested'
    admin.post(f'/api/staff/surveys/{second["id"]}/action', json={'action': 'verify', 'version': 2, 'confirm': True})
    assert employee.get(f'/api/staff/jobs/{jid}').json()['site_survey']['status'] == 'complete'


def test_legacy_completion_cannot_bypass_structured_measurement_review(env):
    from app.artwork_approval import survey_pending
    app, admin, employee = env
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    saved, payload = save_survey(employee, cid, job_id=jid)
    response = admin.post(f'/api/staff/jobs/{jid}/site-survey/complete', json={'confirm': True, 'note': 'Legacy completion attempt'})
    assert response.status_code == 409
    with transaction(app.state.database, True) as conn:
        conn.execute("UPDATE job_site_surveys SET status='complete' WHERE job_id=?", (jid,))
        assert survey_pending(conn, jid)
    payload['user_id'] = employee.get('/api/session').json()['user']['id'] + 999
    assert employee.post('/api/staff/surveys', json=payload).status_code == 403


def test_employee_estimate_uses_catalog_tax_and_retries_do_not_duplicate(env):
    app, admin, employee = env
    live_rates(app)
    cid = add_client(employee)
    jid, payload, price = estimate(employee, cid)
    public = employee.post('/api/calculate', json={'items': payload['items']}).json()
    assert price['quote']['subtotal_cents'] == public['subtotal_cents']
    assert price['totals']['total_cents'] == public['subtotal_cents'] + price['totals']['tax_cents']
    assert 'cost_cents' not in price['quote'] and 'rate_snapshot' not in price['quote']['lines'][0]
    saved = employee.get(f'/api/staff/jobs/{jid}').json()
    assert saved['charges_verified'] and saved['assignee_id'] == employee.get('/api/session').json()['user']['id']
    assert saved['totals']['total_cents'] == price['totals']['total_cents']
    assert employee.post('/api/staff/estimates', json=payload).json()['job_id'] == jid
    payload['title'] = 'A different estimate'
    assert employee.post('/api/staff/estimates', json=payload).status_code == 409
    assert any(j['id'] == jid for j in admin.get('/api/admin/crm/'+str(cid)).json()['jobs'])


def test_estimate_fingerprint_rejects_stale_rates_and_manual_price_injection(env):
    app, admin, employee = env
    live_rates(app)
    cid = add_client(employee)
    payload = {'contact_id': cid, 'items': [{'product_id': 4, 'width': '72', 'height': '36', 'quantity': 1,
                                           'sell_cents': 1, 'price': 0.01}], 'title': 'No client pricing override', 'request_key': 'stale-price'}
    price = employee.post('/api/staff/estimates/calculate', json=payload).json()
    assert price['quote']['subtotal_cents'] > 1
    payload['fingerprint'] = price['fingerprint']
    live_rates(app, '8')
    assert employee.post('/api/staff/estimates', json=payload).status_code == 409
    assert employee.post('/api/staff/jobs', json=payload).status_code == 403


def test_staff_wholesale_uses_existing_client_profile(env):
    app, admin, employee = env
    cid = add_client(employee)
    with transaction(app.state.database, True) as conn:
        conn.execute("INSERT INTO wholesale_clients(name,email,username,code_hash,discount_percent,created_at,updated_at) VALUES('Trade','field-one@example.test','field-trade','unused','20','2026-09-30','2026-09-30')")
    jid, payload, price = estimate(employee, cid)
    retail = employee.post('/api/calculate', json={'items': payload['items']}).json()['subtotal_cents']
    assert price['quote']['wholesale']['name'] == 'Trade'
    assert price['quote']['subtotal_cents'] < retail
    assert employee.get(f'/api/staff/jobs/{jid}').json()['quote']['subtotal_cents'] == price['quote']['subtotal_cents']


def test_survey_estimate_links_scope_and_mixed_workflows(env):
    app, admin, employee = env
    cid = add_client(employee)
    saved, _ = save_survey(employee, cid)
    jid, _, _ = estimate(employee, cid, items=[{'product_id': 4, 'width': '36', 'height': '72', 'quantity': 1},
                                             {'product_id': 1, 'width': '3', 'height': '3', 'quantity': 50}], survey_id=saved['id'])
    survey = employee.get(f'/api/staff/surveys/{saved["id"]}').json()
    assert survey['job_id'] == jid
    job = employee.get(f'/api/staff/jobs/{jid}').json()
    assert job['site_survey']['status'] == 'requested'
    with transaction(app.state.database) as conn:
        p = conn.execute('SELECT workflow_id FROM products WHERE id=4').fetchone()
        primary_count = len(json.loads(conn.execute('SELECT steps FROM workflows WHERE id=?', (p['workflow_id'],)).fetchone()['steps']))
    assert len(job['tasks']) > primary_count


def test_draft_and_issued_invoices_are_immutable_and_private(env):
    app, admin, employee = env
    live_rates(app)
    cid = add_client(employee)
    jid, _, price = estimate(employee, cid, title='<script>unsafe</script>')
    job = employee.get(f'/api/staff/jobs/{jid}').json()
    url = f'/api/staff/jobs/{jid}/invoices'
    payload = {'version': job['quote_version'], 'confirm': True}
    draft = employee.post(url, json=payload).json()
    assert draft['status'] == 'draft'
    assert employee.post(url, json=payload).json()['invoice_id'] == draft['invoice_id']
    doc = employee.get('/api/staff/invoices/'+str(draft['invoice_id']))
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in doc.text
    assert '<script>unsafe</script>' not in doc.text
    assert 'Draft' in doc.text and f'${price["totals"]["total_cents"]/100:,.2f}' in doc.text
    sent = employee.post(f'/api/staff/estimates/{jid}/send', json={'version': job['quote_version'], 'reviewed': True})
    assert sent.status_code == 200, sent.text
    assert sent.json()['email_sent'] is False
    customer = portal(app, admin, jid)
    accept(customer)
    issued = employee.post(url, json=payload).json()
    assert issued['status'] == 'issued' and issued['invoice_id'] != draft['invoice_id']
    assert customer.get('/api/staff/invoices/'+str(issued['invoice_id'])).status_code == 401
    original_document = employee.get('/api/staff/invoices/'+str(issued['invoice_id'])).text
    with transaction(app.state.database, True) as conn:
        conn.execute('UPDATE jobs SET tax_cents=99999 WHERE id=?', (jid,))
    assert employee.get('/api/staff/invoices/'+str(issued['invoice_id'])).text == original_document
    assert f'${price["totals"]["total_cents"]/100:,.2f}' in employee.get('/api/staff/invoices/'+str(issued['invoice_id'])).text


def test_employee_cannot_send_unreviewed_installation_estimate(env):
    app, admin, employee = env
    live_rates(app)
    cid = add_client(employee)
    installed_product = next(p for p in employee.get('/api/catalog').json()['products'] if p['config'].get('supports_installation'))
    jid, _, price = estimate(employee, cid, items=[{'product_id': installed_product['id'], 'width': '72', 'height': '36', 'quantity': 1, 'installation_requested': True}])
    assert price['totals']['owner_review_required']
    assert employee.post(f'/api/staff/estimates/{jid}/send', json={'version': 1, 'reviewed': True}).status_code == 409


def test_survey_removal_requires_owner_scope_pricing_review(env):
    app, admin, employee = env
    live_rates(app)
    cid = add_client(employee)
    survey, _ = save_survey(employee, cid, removal_required=True)
    jid, _, price = estimate(employee, cid, survey_id=survey['id'])
    assert price['totals']['owner_review_required']
    assert not employee.get(f'/api/staff/jobs/{jid}').json()['charges_verified']


def test_queue_scope_claim_and_another_staff_timer(env):
    app, admin, employee = env
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    task = employee.get(f'/api/staff/jobs/{jid}').json()['tasks'][0]
    assert not employee.get('/api/staff/task-queue?scope=mine').json()['tasks']
    assert employee.post(f'/api/staff/tasks/{task["id"]}/action', json={'action': 'claim'}).status_code == 200
    assert task['id'] in [t['id'] for t in employee.get('/api/staff/task-queue?scope=mine').json()['tasks']]
    assert task['id'] not in [t['id'] for t in employee.get('/api/staff/task-queue?scope=available').json()['tasks']]
    assert employee.post(f'/api/staff/tasks/{task["id"]}/action', json={'action': 'start'}).status_code == 200
    assert employee.post(f'/api/staff/tasks/{task["id"]}/action', json={'action': 'complete'}).status_code == 200
    assert not employee.get('/api/staff/task-queue?scope=mine').json()['tasks']
    assert employee.get('/api/staff/task-queue?scope=invalid').status_code == 422


def test_mobile_active_jobs_hide_finished_but_preserve_history(env):
    app, admin, employee = env
    cid = add_client(employee)
    finished, _, _ = estimate(employee, cid)
    active, _, _ = estimate(employee, cid)
    no_tasks, _, _ = estimate(employee, cid)
    with transaction(app.state.database, True) as conn:
        conn.execute("UPDATE tasks SET status='done' WHERE job_id=?", (finished,))
        conn.execute('DELETE FROM tasks WHERE job_id=?', (no_tasks,))
    for staff in (employee, admin):
        ids = {j['id'] for j in staff.get('/api/staff/jobs?active_only=true').json()['jobs']}
        assert finished not in ids
        assert {active, no_tasks} <= ids
        assert finished in {j['id'] for j in staff.get('/api/staff/jobs').json()['jobs']}
        assert staff.get(f'/api/staff/jobs/{finished}').json()['stage'] == 'complete'
    assert all(t['job_id'] != finished for t in employee.get('/api/staff/task-queue').json()['tasks'])
    # Reopening work makes the project active again.
    with transaction(app.state.database, True) as conn:
        conn.execute("UPDATE tasks SET status='todo' WHERE id=(SELECT MIN(id) FROM tasks WHERE job_id=?)", (finished,))
    assert finished in {j['id'] for j in employee.get('/api/staff/jobs?active_only=true').json()['jobs']}


def on_site_payload(employee, jid, **extra):
    job = employee.get(f'/api/staff/jobs/{jid}').json()
    return {'version': job['quote_version'], 'total_cents': job['totals']['total_cents'],
            'recipient': job['customer_email'], 'customer_name': 'Client at site', 'confirm': True, **extra}


def invoice_customer(app, result):
    from urllib.parse import urlsplit, parse_qs
    client = anonymous(app)
    token = parse_qs(urlsplit(result['portal_url']).fragment)['token'][0]
    exchanged = client.post('/api/portal/exchange', json={'token': token})
    assert exchanged.status_code == 200, exchanged.text
    client.headers['X-CSRF-Token'] = exchanged.json()['csrf']
    return client


def test_owner_completes_all_saved_surveys_from_project_review(env):
    app, admin, employee = env
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    first, _ = save_survey(employee, cid, job_id=jid)
    second, _ = save_survey(employee, cid, job_id=jid)
    employee.post(f'/api/staff/surveys/{second["id"]}/action', json={'action': 'submit', 'version': second['version']})
    review_url = f'/api/staff/jobs/{jid}/site-survey/review'
    assert employee.get(review_url).status_code == 403
    assert anonymous(app).get(review_url).status_code == 401
    review = admin.get(review_url).json()
    assert review['quote_version'] == 1 and len(review['surveys']) == 2
    payload = {'confirm': True, 'note': 'Checked both saved surveys against the order.', 'quote_version': 1,
               'reviewed_surveys': [{'id': s['id'], 'version': s['version'], 'confirm': True} for s in review['surveys']]}
    complete = f'/api/staff/jobs/{jid}/site-survey/complete'
    assert employee.post(complete, json=payload).status_code == 403
    assert admin.post(complete, json={**payload, 'reviewed_surveys': payload['reviewed_surveys'][:1]}).status_code == 409
    assert admin.post(complete, json={**payload, 'quote_version': 99}).status_code == 409
    bad = [dict(s) for s in payload['reviewed_surveys']]; bad[0]['version'] += 1
    assert admin.post(complete, json={**payload, 'reviewed_surveys': bad}).status_code == 409
    bad = [dict(s) for s in payload['reviewed_surveys']]; bad[1]['confirm'] = False
    assert admin.post(complete, json={**payload, 'reviewed_surveys': bad}).status_code == 422
    assert admin.get(review_url).json()['surveys'][0]['status'] == 'draft'
    saved = admin.post(complete, json=payload)
    assert saved.status_code == 200, saved.text
    assert employee.get(f'/api/staff/jobs/{jid}').json()['site_survey']['status'] == 'complete'
    assert all(s['status'] == 'verified' for s in admin.get(review_url).json()['surveys'])
    with transaction(app.state.database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events WHERE job_id=? AND action='employee_survey.verify'", (jid,)).fetchone()[0] == 2


def test_project_survey_review_files_are_private_and_job_bound(env):
    app, admin, employee = env
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    saved, _ = save_survey(employee, cid, job_id=jid)
    stream = io.BytesIO(); Image.new('RGB', (20, 20), (0, 120, 120)).save(stream, 'PNG')
    uploaded = employee.post(f'/api/staff/surveys/{saved["id"]}/files', data={'client_key': 'review-photo'}, files={'file': ('site.png', stream.getvalue(), 'image/png')})
    assert uploaded.status_code == 200, uploaded.text
    review = admin.get(f'/api/staff/jobs/{jid}/site-survey/review').json()
    file = review['surveys'][0]['files'][0]
    assert 'stored_name' not in file
    assert admin.get(file['url']).status_code == 200
    assert employee.get(file['url']).status_code == 403
    other, _, _ = estimate(employee, cid, title='Other project')
    assert admin.get(f'/api/staff/jobs/{other}/site-survey/files/{file["id"]}').status_code == 404


def test_on_site_approval_issues_invoice_without_clearing_survey_or_artwork_holds(env, monkeypatch):
    app, admin, employee = env
    live_rates(app)
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    save_survey(employee, cid, job_id=jid)
    sent = []
    monkeypatch.setattr('app.mailer.enabled', lambda: True)
    monkeypatch.setattr('app.mailer._send', lambda *args: sent.append(args) or (True, ''))
    payload = on_site_payload(employee, jid)
    response = employee.post(f'/api/staff/jobs/{jid}/on-site-invoice', json=payload)
    assert response.status_code == 200, response.text
    invoice = response.json()
    assert invoice['status'] == 'issued' and invoice['email_sent'] is True
    assert invoice['recipient'] == payload['recipient'] and len(sent) == 1
    assert invoice['number'] in sent[0][1] and 'View invoice' in sent[0][2]
    assert f'&invoice={invoice["invoice_id"]}' in invoice['portal_url']
    repeated = employee.post(f'/api/staff/jobs/{jid}/on-site-invoice', json=payload).json()
    assert repeated['invoice_id'] == invoice['invoice_id'] and len(sent) == 1
    job = employee.get(f'/api/staff/jobs/{jid}').json()
    assert job['published'] and job['accepted_version'] == 1 and job['accepted_name'] == 'Client at site'
    assert job['site_survey']['status'] == 'requested' and not job['proofs'] and job['totals']['paid_cents'] == 0
    with transaction(app.state.database) as conn:
        events = conn.execute("SELECT details FROM events WHERE job_id=? AND action='quote.accepted'", (jid,)).fetchall()
        assert len(events) == 1 and json.loads(events[0]['details'])['method'] == 'in_person'
    customer = invoice_customer(app, invoice)
    document = customer.get(f'/api/invoices/{invoice["invoice_id"]}')
    assert document.status_code == 200 and invoice['number'] in document.text and 'View order &amp; payment' in document.text
    assert 'no-store' in document.headers['cache-control']
    assert customer.get('/api/portal/job').json()['invoices'][0]['id'] == invoice['invoice_id']
    assert customer.get(f'/api/staff/invoices/{invoice["invoice_id"]}').status_code == 401


def test_on_site_invoice_rejects_stale_price_email_unconfirmed_and_restricted_staff(env):
    app, admin, employee = env
    live_rates(app)
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    url = f'/api/staff/jobs/{jid}/on-site-invoice'
    payload = on_site_payload(employee, jid)
    for change, status in [({'version': 9}, 409), ({'total_cents': payload['total_cents']+1}, 409),
                           ({'recipient': 'someone-else@example.test'}, 409), ({'confirm': False}, 422)]:
        assert employee.post(url, json={**payload, **change}).status_code == status
    assert not employee.get(f'/api/staff/jobs/{jid}').json()['published']
    uid = employee.get('/api/session').json()['user']['id']
    with transaction(app.state.database, True) as conn:
        conn.execute("INSERT OR REPLACE INTO company_access(user_id,profile) VALUES(?,'survey_install')", (uid,))
    assert employee.post(url, json=payload).status_code == 403
    assert employee.post('/api/staff/invoices/999/send', json=payload).status_code == 403
    assert anonymous(app).post(url, json=payload).status_code == 401
    assert not employee.get(f'/api/staff/jobs/{jid}/invoices').json()['invoices']


def test_only_owner_can_review_charges_during_on_site_invoicing(env):
    app, admin, employee = env
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    with transaction(app.state.database, True) as conn:
        conn.execute('UPDATE jobs SET charges_verified=0 WHERE id=?', (jid,))
    payload = on_site_payload(employee, jid)
    url = f'/api/staff/jobs/{jid}/on-site-invoice'
    assert employee.post(url, json={**payload, 'charges_reviewed': True}).status_code == 403
    assert admin.post(url, json=payload).status_code == 422
    result = admin.post(url, json={**payload, 'charges_reviewed': True})
    assert result.status_code == 200 and result.json()['status'] == 'issued'
    assert employee.get(f'/api/staff/jobs/{jid}').json()['charges_verified']


def test_failed_invoice_email_can_retry_without_new_invoice_or_approval(env, monkeypatch):
    app, admin, employee = env
    live_rates(app)
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    calls = []
    monkeypatch.setattr('app.mailer.enabled', lambda: True)
    def delivery(*args):
        calls.append(args)
        return (len(calls)>1, 'Temporary test delivery failure' if len(calls)==1 else '')
    monkeypatch.setattr('app.mailer._send', delivery)
    payload = on_site_payload(employee, jid)
    first = employee.post(f'/api/staff/jobs/{jid}/on-site-invoice', json=payload).json()
    assert first['status'] == 'issued' and first['email_sent'] is False
    url = f'/api/staff/invoices/{first["invoice_id"]}/send'
    retried = employee.post(url, json=payload)
    assert retried.status_code == 200 and retried.json()['email_sent'] is True and len(calls) == 2
    assert employee.post(url, json=payload).json()['email_sent'] is True and len(calls) == 2
    assert employee.post(url, json={**payload, 'resend': True}).json()['email_sent'] is True and len(calls) == 3
    assert len(employee.get(f'/api/staff/jobs/{jid}/invoices').json()['invoices']) == 1
    assert employee.get(f'/api/staff/jobs/{jid}').json()['accepted_name'] == 'Client at site'


def test_invoice_customer_access_and_sending_old_or_draft_invoice(env):
    app, admin, employee = env
    live_rates(app)
    cid = add_client(employee)
    jid, _, _ = estimate(employee, cid)
    draft = employee.post(f'/api/staff/jobs/{jid}/invoices', json={'version': 1, 'confirm': True}).json()
    payload = on_site_payload(employee, jid)
    assert employee.post(f'/api/staff/invoices/{draft["invoice_id"]}/send', json=payload).status_code == 409
    issued = employee.post(f'/api/staff/jobs/{jid}/on-site-invoice', json=payload).json()
    visitor = anonymous(app)
    assert visitor.get(f'/api/invoices/{issued["invoice_id"]}').status_code == 401
    customer = invoice_customer(app, issued)
    assert customer.get(f'/api/invoices/{draft["invoice_id"]}').status_code == 404
    other, _, _ = estimate(employee, cid, title='Another order')
    wrong_customer = portal(app, admin, other)
    assert wrong_customer.get(f'/api/invoices/{issued["invoice_id"]}').status_code == 404
    with transaction(app.state.database, True) as conn:
        conn.execute('UPDATE jobs SET tax_cents=tax_cents+10 WHERE id=?', (jid,))
    new_payload = on_site_payload(employee, jid)
    assert employee.post(f'/api/staff/invoices/{issued["invoice_id"]}/send', json=new_payload).status_code == 409
    assert employee.post(f'/api/staff/jobs/{jid}/on-site-invoice', json=new_payload).status_code == 409
    assert customer.get(f'/api/invoices/{issued["invoice_id"]}').status_code == 200
