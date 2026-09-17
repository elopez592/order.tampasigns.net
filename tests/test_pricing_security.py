import json
import pytest
from concurrent.futures import ThreadPoolExecutor
from .conftest import anonymous, sign_in, create_banner, finalize, portal, image_bytes, task_action


def calculate(client, **overrides):
    item = {'product_id': 1, 'width': '3', 'height': '3', 'quantity': 100}
    item.update(overrides)
    return client.post('/api/calculate', json={'items': [item]})


def test_public_calculator_uses_net_area_and_hides_costs(env):
    app, admin, employee = env
    client = anonymous(app)
    response = calculate(client)
    assert response.status_code == 200
    data = response.json()
    assert data['lines'][0]['net_sqft'] == '6.2500'
    assert data['subtotal_cents'] > 0
    assert 'fingerprint' in data
    for secret in ['cost_cents', 'rate_snapshot', 'material_sqft', 'settings_snapshot']:
        assert secret not in response.text


@pytest.mark.parametrize('overrides', [
    {'width': -1}, {'width': 0}, {'width': 'NaN'}, {'width': 'Infinity'},
    {'quantity': 1.5}, {'quantity': -50}, {'quantity': True}, {'quantity': 100001},
    {'height': 'not-a-number'}, {'product_id': 99999},
])
def test_pricing_rejects_invalid_inputs(env, overrides):
    app, admin, employee = env
    assert calculate(admin, **overrides).status_code == 422


def test_quantity_tiers_are_monotonic(env):
    app, admin, employee = env
    totals = [calculate(admin, quantity=q).json()['subtotal_cents'] for q in [50,99,100,101,499,500,501,999,1000,1001]]
    assert totals == sorted(totals)


def test_frontend_price_cannot_override_server_price(env):
    app, admin, employee = env
    client = anonymous(app)
    quote = calculate(client).json()
    response = client.post('/api/requests', json={
        'title': 'Tamper check', 'customer_name': 'Test', 'customer_email': 'test@example.test',
        'total_cents': 1, 'price_override_cents': 1, 'fingerprint': quote['fingerprint'],
        'items': [{'product_id':1,'width':3,'height':3,'quantity':100,'sell_cents':1}]})
    assert response.status_code == 200, response.text
    job = admin.get('/api/staff/jobs/' + str(response.json()['job_id'])).json()
    assert job['totals']['total_cents'] == quote['subtotal_cents']
    assert not job['published']


def test_rate_changes_preserve_existing_job_snapshot_and_reject_stale_cart(env):
    app, admin, employee = env
    before = admin.get('/api/staff/jobs/2').json()
    client = anonymous(app)
    old_quote = calculate(client).json()
    p = admin.get('/api/admin/products').json()['products'][0]
    p['active'], p['public'] = True, True
    if p['config'].get('quantity_price_table'):
        p['config']['quantity_price_table'] = [
            dict(row, total=str(float(row['total']) + 10)) for row in p['config']['quantity_price_table']
        ]
    else:
        p['config']['sell_per_sqft'] = '99'
    assert admin.put('/api/admin/products/1', json=p).status_code == 200
    after = admin.get('/api/staff/jobs/2').json()
    assert before['quote'] == after['quote']
    assert before['totals'] == after['totals']
    assert calculate(client).json()['subtotal_cents'] > old_quote['subtotal_cents']
    response = client.post('/api/requests', json={
        'title':'Stale quote','customer_name':'Test','customer_email':'a@example.test',
        'items':[{'product_id':1,'width':3,'height':3,'quantity':100}], 'fingerprint':old_quote['fingerprint']})
    assert response.status_code == 409
    assert admin.put('/api/admin/products/1', json=p).status_code == 409


def test_employee_cannot_modify_finances_or_catalog(env):
    app, admin, employee = env
    assert employee.get('/api/admin/products').status_code == 403
    assert employee.put('/api/admin/settings', json={}).status_code == 403
    assert employee.post('/api/staff/jobs/1/quote', json={}).status_code == 403
    assert employee.post('/api/staff/jobs/1/payments', json={}).status_code == 403
    assert employee.get('/api/staff/jobs').status_code == 200
    data = employee.get('/api/staff/jobs/1').text
    assert 'cost_cents' not in data
    assert 'rate_snapshot' not in data


def test_csrf_and_cross_origin_protection(env):
    app, admin, employee = env
    client = anonymous(app)
    client.headers.pop('X-CSRF-Token')
    assert client.post('/api/calculate', json={'items':[]}).status_code == 403
    assert admin.post('/api/calculate', json={'items':[]}, headers={'Origin':'https://attacker.example'}).status_code == 403


def test_private_portal_is_job_scoped_and_rotatable(env):
    app, admin, employee = env
    client = portal(app, admin, 1)
    assert client.get('/api/staff/jobs').status_code == 401
    assert client.post('/api/portal/accept-quote', json={'name':'Test','confirm':True,'version':1}).status_code == 409
    upload = admin.post('/api/jobs/2/artwork', files={'file':('art.png',image_bytes(),'image/png')})
    assert upload.status_code == 200
    asset_id = upload.json()['asset_id']
    assert client.get(f'/api/assets/{asset_id}').status_code == 404
    data = client.get('/api/portal/job').text
    for key in ['cost_cents','extra_cost_cents','rate_snapshot','portal_hash','password_hash']:
        assert key not in data
    admin.post('/api/staff/jobs/1/share')
    assert client.get('/api/portal/job').status_code == 401


@pytest.mark.parametrize('url', ['http://intuit.com/test','https://intuit.com.attacker.example/a',
                               'https://intuit.com@attacker.example/a','javascript:alert(1)',
                               'https://attacker.example','https://intuit.com:8443/a'])
def test_rejects_unsafe_payment_urls(env, url):
    app, admin, employee = env
    response = admin.post('/api/staff/jobs/1/payment-link', json={'url':url,'invoice_reference':'TEST'})
    assert response.status_code == 422


def test_upload_types_and_authenticated_downloads(env):
    app, admin, employee = env
    response = admin.post('/api/jobs/1/artwork', files={'file':('bad.svg', b'<svg onload="alert(1)"/>','image/svg+xml')})
    assert response.status_code == 422
    response = admin.post('/api/jobs/1/artwork', files={'file':('fake.jpg', b'<html>bad</html>','image/jpeg')})
    assert response.status_code == 422
    response = admin.post('/api/jobs/1/artwork', files={'file':('../../proof.png',image_bytes(),'image/png')})
    assert response.status_code == 200
    aid = response.json()['asset_id']
    client = anonymous(app)
    assert client.get(f'/api/assets/{aid}').status_code == 401
    downloaded = admin.get(f'/api/assets/{aid}')
    assert downloaded.status_code == 200
    assert downloaded.headers['x-content-type-options'] == 'nosniff'
    assert 'no-store' in downloaded.headers['cache-control']


def test_concurrent_employee_claim_has_one_winner(env):
    app, admin, employee = env
    created = admin.post('/api/admin/users', json={'name':'Second Employee','email':'second@example.test','role':'employee'}).json()
    second = sign_in(app, 'second@example.test', created['temporary_password'])
    task_id = admin.get('/api/staff/jobs/1').json()['tasks'][0]['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda client: task_action(client, task_id, 'claim').status_code, [employee, second]))
    assert sorted(results) == [200,409]


def test_deactivated_employee_session_is_revoked(env):
    app, admin, employee = env
    uid = next(u['id'] for u in admin.get('/api/staff/users').json()['users'] if u['role']=='employee')
    assert admin.patch(f'/api/admin/users/{uid}', json={'active':False}).status_code == 200
    assert employee.get('/api/staff/jobs').status_code == 401


def test_workflow_update_does_not_change_existing_tasks(env):
    app, admin, employee = env
    before=admin.get('/api/staff/jobs/1').json()['tasks']
    workflow=next(w for w in admin.get('/api/staff/workflows').json()['workflows'] if w['id']==3)
    workflow['steps'][0]['title']='Changed intake task'
    assert admin.put('/api/admin/workflows/3', json=workflow).status_code == 200
    after=admin.get('/api/staff/jobs/1').json()['tasks']
    assert [t['title'] for t in before] == [t['title'] for t in after]
    assert admin.put('/api/admin/workflows/3', json=workflow).status_code == 409


def test_seed_measurements_are_preserved(env):
    app, admin, employee=env
    j=admin.get('/api/staff/jobs/1').json()
    assert [(x['width'],x['height']) for x in j['quote']['lines']]==[('43.75','92'),('30.5','72'),('44','92'),('120','30.5')]
    assert j['totals']['total_cents']==140000
    assert not j['charges_verified']


def test_product_id_must_not_silently_truncate(env):
    app,admin,employee=env
    response=admin.post('/api/calculate',json={'items':[{'product_id':1.5,'width':3,'height':3,'quantity':50}]})
    assert response.status_code==422
