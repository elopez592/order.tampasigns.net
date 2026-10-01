import io
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from PIL import Image
from app.platform import CompanyRouter
from app.db import transaction, settings
from app.runtime import configuration
from app.mailer import _brand_html


def add_company(admin, slug, hostname):
    response=admin.post('/api/platform/companies',json={'slug':slug,'name':slug.title(),'owner_email':slug+'@example.test','hostname':hostname})
    assert response.status_code==200,response.text
    assert response.json()['temporary_password']
    return response.json()


def tenant(root,host,credentials):
    client=TestClient(CompanyRouter(root),base_url='https://'+host)
    session=client.get('/api/session').json()
    client.headers['X-CSRF-Token']=session['csrf']
    login=client.post('/api/auth/login',json={'email':credentials['owner_email'],'password':credentials['temporary_password']})
    assert login.status_code==200,login.text
    client.headers['X-CSRF-Token']=login.json()['csrf']
    return client


def test_platform_owner_only_and_credentials_not_listed(env):
    app,admin,employee=env
    assert employee.get('/api/platform/companies').status_code==403
    c=add_company(admin,'first-shop','first.example.test')
    response=admin.get('/api/platform/companies')
    assert c['temporary_password'] not in response.text
    assert response.json()['billing_mode']=='manual'
    owner_id=admin.get('/api/session').json()['user']['id']
    with transaction(app.state.database,True) as conn:
        conn.execute("UPDATE users SET email='another@example.test' WHERE id=?",(owner_id,))
    assert admin.get('/api/platform/companies').status_code==403


def test_company_isolation_sessions_records_integrations_and_concurrent_requests(env,monkeypatch):
    app,admin,_=env
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_live_root_secret')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_root')
    monkeypatch.setenv('RESEND_API_KEY','root_email_secret')
    monkeypatch.setenv('EMAIL_FROM','root@example.test')
    a=add_company(admin,'alpha-shop','alpha.example.test')
    b=add_company(admin,'beta-shop','beta.example.test')
    first=tenant(app,'alpha.example.test',a);second=tenant(app,'beta.example.test',b)
    assert first.get('/api/admin/settings').json()['checkout_connection']['configured'] is False
    assert first.get('/api/catalog').json()['notifications']['enabled'] is False
    assert first.get('/api/platform/companies').status_code==404
    assert not first.get('/api/session').json()['user']['platform_owner']
    assert first.get('/api/staff/jobs').json()['jobs']==[]
    added=first.post('/api/staff/clients',json={'name':'Alpha private','email':'private@example.test'})
    assert added.status_code==200,added.text
    assert 'Alpha private' not in second.get('/api/staff/clients').text
    stolen=TestClient(CompanyRouter(app),base_url='https://beta.example.test')
    stolen.headers['Cookie']='signshop_session='+first.cookies.get('signshop_session')
    assert stolen.get('/api/staff/jobs').status_code==401
    assert TestClient(CompanyRouter(app),base_url='https://unknown.example.test').get('/').status_code==404
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda i:(first if i%2==0 else second).get('/api/brand').json()['shop_name'],range(12)))
    assert results==['Alpha-Shop','Beta-Shop']*6
    assert configuration.get() is None
    first.close();second.close();stolen.close()


def test_brand_draft_publish_conflict_restore_and_private_images(env):
    app,admin,employee=env
    original=admin.get('/api/admin/company').json()
    data=original['draft']['data']|{'shop_name':'New Shop','app_short_name':'NS Staff','brand_primary':'#2468ab'}
    version=original['draft']['version']
    saved=admin.put('/api/admin/company/draft',json={'version':version,'data':data})
    assert saved.status_code==200,saved.text
    assert admin.put('/api/admin/company/draft',json={'version':version,'data':data}).status_code==409
    assert admin.get('/api/brand').json()['shop_name']=='Tampa Signs and Stickers'
    assert employee.post('/api/admin/company/publish',json={'version':saved.json()['version']}).status_code==403
    assert admin.post('/api/admin/company/publish',json={'version':saved.json()['version']}).status_code==200
    assert admin.get('/api/brand').json()['shop_name']=='New Shop'
    assert admin.get('/staff/manifest.webmanifest').json()['name']=='New Shop Staff'
    assert '#2468ab' in admin.get('/brand/theme.css').text
    assert Image.open(io.BytesIO(admin.get('/brand/app-icon.png').content)).size==(180,180)
    latest=admin.get('/api/admin/company').json()
    assert admin.post('/api/admin/company/restore/'+str(original['history'][0]['id']),json={'version':latest['draft']['version']}).status_code==200
    assert admin.get('/api/brand').json()['shop_name']=='New Shop'
    assert admin.get('/api/admin/company').json()['draft']['data']['shop_name']=='Tampa Signs and Stickers'


def test_seats_status_and_revocation(env):
    app,admin,employee=env
    first=add_company(admin,'limited-shop','limited.example.test')
    row=admin.get('/api/platform/companies').json()['companies'][0]
    assert admin.patch('/api/platform/companies/limited-shop',json={'revision':row['revision'],'seats':1}).status_code==200
    owner=tenant(app,'limited.example.test',first)
    assert owner.post('/api/admin/users',json={'name':'Extra','email':'extra@example.test'}).status_code==403
    row=admin.get('/api/platform/companies').json()['companies'][0]
    assert admin.patch('/api/platform/companies/limited-shop',json={'revision':row['revision'],'status':'suspended'}).status_code==200
    assert owner.get('/api/staff/jobs').status_code==403
    employee_id=employee.get('/api/session').json()['user']['id']
    assert admin.put('/api/admin/company/access/'+str(employee_id),json={'profile':'read_only'}).status_code==200
    assert employee.get('/api/staff/jobs').status_code==401
    owner.close()


def test_restricted_profiles_enforced_server_side(env):
    app,admin,employee=env
    employee_id=employee.get('/api/session').json()['user']['id']
    with transaction(app.state.database,True) as conn:
        conn.execute("INSERT INTO company_access VALUES(?,'designer')",(employee_id,))
    assert employee.post('/api/staff/clients',json={'name':'Unauthorized'}).status_code==403
    assert employee.post('/api/staff/estimates/calculate',json={}).status_code==403
    # Allowed designer action reaches normal record validation, not profile rejection.
    response=employee.post('/api/staff/jobs/999/proofs',data={})
    assert response.status_code in (404,422)


def test_connections_are_not_inherited_and_secrets_not_returned(env):
    app,admin,_=env
    add_company(admin,'secret-shop','secret.example.test')
    response=admin.put('/api/platform/companies/secret-shop/connections',json={'RESEND_API_KEY':'tenant-secret','EMAIL_FROM':'shop@example.test'})
    assert response.status_code==200,response.text
    listed=admin.get('/api/platform/companies')
    assert 'tenant-secret' not in listed.text
    assert listed.json()['companies'][0]['connections']['RESEND_API_KEY']
    assert admin.put('/api/platform/companies/secret-shop/connections',json={'PUBLIC_URL':'bad'}).status_code==422
    token=configuration.set({'SHOP_NAME':'Tenant Shop','SHOP_PHONE':'555-0100'})
    try:
        rendered=_brand_html('Hello','World')
        assert 'Tenant Shop' in rendered and '555-0100' in rendered and 'Tampa Signs' not in rendered
    finally: configuration.reset(token)
