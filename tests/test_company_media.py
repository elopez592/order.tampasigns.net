from tests.test_company_platform import tenant, add_company


def test_mirakol_catalog_has_complete_private_media(env):
    app,admin,_=env
    root=admin.get('/api/catalog').json()
    info=admin.post('/api/platform/companies',json={
        'slug':'mirakol','name':'Mirakol Customs','owner_email':'client@example.test',
        'hostname':'mirakol.tampasigns.net'}).json()
    app.state.company_apps.pop('mirakol')
    child=tenant(app,'mirakol.tampasigns.net',info)
    catalog=child.get('/api/catalog').json()
    media=catalog['company_media']
    assert set(media['products'])=={product['name'] for product in catalog['products']}
    assert media['instagram']=='https://www.instagram.com/mirakol_designs/'
    assert media['projects']==[]
    assert root['company_media']=={}
    assert admin.get('/api/catalog').json()['products']==root['products']
    other=tenant(app,'other.example.test',add_company(admin,'another-shop','other.example.test'))
    assert other.get('/api/catalog').json()['company_media']=={}
    # The mockups are real public website assets, not broken metadata references.
    image=child.get(media['products']['Custom T-shirts']['image'])
    assert image.status_code==200 and image.content[:4]==b'RIFF'
