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


def test_customer_favicon_uses_tenant_icon_without_changing_platform_shop(env):
    app,admin,_=env
    first=tenant(app,'icon.example.test',add_company(admin,'icon-shop','icon.example.test'))
    second=tenant(app,'other.example.test',add_company(admin,'other-shop','other.example.test'))
    root_before=admin.get('/static/brand/favicon.png').content
    icon=io.BytesIO()
    Image.new('RGB',(180,180),'#ffa500').save(icon,format='PNG')
    upload=first.post('/api/admin/company/image',files={'file':('star.png',icon.getvalue(),'image/png')})
    assert upload.status_code==200,upload.text
    draft=first.get('/api/admin/company').json()['draft']
    data=draft['data']|{'brand_icon':upload.json()['image']}
    saved=first.put('/api/admin/company/draft',json={'version':draft['version'],'data':data})
    assert first.post('/api/admin/company/publish',json={'version':saved.json()['version']}).status_code==200
    page=first.get('/').text
    assert 'rel="icon" type="image/png" href="/brand/app-icon.png?v=' in page
    assert 'rel="shortcut icon" type="image/png" href="/brand/app-icon.png?v=' in page
    assert '/static/brand/favicon.png' not in page
    assert Image.open(io.BytesIO(first.get('/brand/app-icon.png').content)).getpixel((90,90))[:3]==(255,165,0)
    assert first.get('/brand/app-icon.png').content!=second.get('/brand/app-icon.png').content
    assert second.get(upload.json()['url']).status_code==404
    assert '/static/brand/favicon.png' in admin.get('/').text
    assert admin.get('/static/brand/favicon.png').content==root_before
    first.close();second.close()


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


def support_client(app,host):
    client=TestClient(CompanyRouter(app),base_url='https://'+host)
    client.headers['X-CSRF-Token']=client.get('/api/session').json()['csrf']
    return client


def test_platform_support_is_one_use_company_scoped_and_audited(env):
    from urllib.parse import urlsplit,parse_qs
    app,admin,employee=env
    add_company(admin,'support-shop','support.example.test')
    add_company(admin,'other-shop','other.example.test')
    assert employee.post('/api/platform/companies/support-shop/support',json={}).status_code==403
    issued=admin.post('/api/platform/companies/support-shop/support',json={})
    assert issued.status_code==200,issued.text
    token=parse_qs(urlsplit(issued.json()['url']).fragment)['support'][0]
    wrong=support_client(app,'other.example.test')
    assert wrong.post('/api/auth/platform-support',json={'token':token}).status_code==401
    company=support_client(app,'support.example.test')
    # The exchange retains normal CSRF checks.
    assert company.post('/api/auth/platform-support',json={'token':token},headers={'X-CSRF-Token':'wrong'}).status_code==403
    result=company.post('/api/auth/platform-support',json={'token':token})
    assert result.status_code==200,result.text
    company.headers['X-CSRF-Token']=result.json()['csrf']
    user=company.get('/api/session').json()['user']
    assert user['support_company']=='support-shop' and not user['platform_owner']
    assert user['email']=='owner@example.test'
    assert user['support_return']=='http://testserver/platform'
    assert company.get('/api/staff/jobs').status_code==200
    assert company.post('/api/auth/password',json={}).status_code==403
    assert company.post('/api/auth/platform-support',json={'token':token}).status_code==401
    # The owner account/password and seat count have not changed.
    child=app.state.company_apps['support-shop']
    with transaction(child.state.database) as conn:
        assert conn.execute('SELECT count(*) FROM users').fetchone()[0]==1
        event=conn.execute("SELECT actor FROM events WHERE action='platform.support_started'").fetchone()
        assert event['actor']=='owner@example.test'
    with transaction(app.state.database) as conn:
        assert token not in str([dict(r) for r in conn.execute('SELECT * FROM platform_support_grants')])
    # Revoking the root owner session revokes company support immediately.
    assert admin.post('/api/auth/logout',json={}).status_code==200
    assert company.get('/api/staff/jobs').status_code==401
    company.close();wrong.close()


def test_platform_support_requires_connected_active_company_and_live_grant(env):
    from urllib.parse import urlsplit,parse_qs
    app,admin,_=env
    add_company(admin,'unconnected-shop','')
    assert admin.post('/api/platform/companies/unconnected-shop/support',json={}).status_code==422
    add_company(admin,'paused-shop','paused.example.test')
    row=next(c for c in admin.get('/api/platform/companies').json()['companies'] if c['slug']=='paused-shop')
    assert admin.patch('/api/platform/companies/paused-shop',json={'revision':row['revision'],'status':'suspended'}).status_code==200
    assert admin.post('/api/platform/companies/paused-shop/support',json={}).status_code==403
    add_company(admin,'expired-shop','expired.example.test')
    url=admin.post('/api/platform/companies/expired-shop/support',json={}).json()['url']
    token=parse_qs(urlsplit(url).fragment)['support'][0]
    with transaction(app.state.database,True) as conn:
        conn.execute('UPDATE platform_support_grants SET expires_at=0')
    company=support_client(app,'expired.example.test')
    assert company.post('/api/auth/platform-support',json={'token':token}).status_code==401
    company.close()
