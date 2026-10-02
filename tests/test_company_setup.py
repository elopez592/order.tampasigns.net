import io
import json
from fastapi.testclient import TestClient
from PIL import Image
from app.db import settings, transaction
from app.images import sanitize
from pathlib import Path
import hashlib
from app.platform import CompanyRouter
from tests.test_company_platform import tenant, add_company


def test_mirakol_setup_is_private_quote_only_and_applied_once(env):
    app,admin,_=env
    original_brand=admin.get('/api/brand').json()
    original_icon=admin.get('/brand/app-icon.png').content
    original_products=admin.get('/api/catalog').json()['products']
    response=admin.post('/api/platform/companies',json={'slug':'mirakol','name':'Mirakol Customs',
                        'owner_email':'client@example.test','hostname':'mirakol.tampasigns.net'})
    assert response.status_code==200,response.text
    child=app.state.company_apps.pop('mirakol')
    with transaction(child.state.database,True) as conn:
        shop=settings(conn)|{'contact_phone':'555-0100'}
        conn.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(shop),))
    first=tenant(app,'mirakol.tampasigns.net',response.json())
    brand=first.get('/api/brand').json()
    assert brand['brand_primary']=='#ffa500' and brand['brand_dark']=='#000000'
    assert brand['contact_email']=='client@example.test' and brand['contact_phone']=='555-0100'
    assert brand['brand_logo'] and brand['brand_icon'] and brand['app_short_name']=='Mirakol'
    icon=Image.open(io.BytesIO(first.get('/brand/app-icon.png').content))
    assert icon.size==(180,180) and icon.mode=='RGB'
    assert icon.getpixel((0,0))==(0,0,0)
    assert icon.getpixel((179,179))==(0,0,0)
    assert icon.getpixel((6,90))==(0,0,0)
    assert max(high for low,high in icon.getextrema())>240
    assert first.get('/staff/manifest.webmanifest').json()['icons'][0]['src']=='/brand/app-icon.png?v='+brand['brand_icon'][:16]+'-iphone-1'
    assert 'href="/brand/app-icon.png?v=' in first.get('/').text
    theme=first.get('/brand/theme.css').text
    assert 'color:#000000' in theme
    assert '--brand-teal:#ffa500' in theme and '--brand-yellow:#ffe600' in theme
    assert 'body:has(.public-masthead)' in theme
    assert '/brand/images/'+brand['brand_icon'] in theme
    assert first.get('/staff/manifest.webmanifest').json()['background_color']=='#000000'
    assert '--brand-yellow' not in admin.get('/brand/theme.css').text
    catalog=first.get('/api/catalog').json()
    assert catalog['shop']['storefront_category_order'].startswith('Apparel, Events, Promotional Products')
    assert catalog['shop']['storefront_heading']=='Wear your brand. Make an impression.'
    expected={'Sublimation printing','DTF transfers','DTF printed apparel','Custom embroidery','Engraved pens',
              'Custom name tags','Laser-cut promotional products','Custom table covers','Table runners',
              'Event backdrops','Step-and-repeat backdrops','Retractable banners','Custom tent graphics','Feather flags','Event signage'}
    added=[p for p in catalog['products'] if p['name'] in expected]
    assert {p['name'] for p in added}==expected
    assert all(p['config']['quote_only'] and not p['config']['instant'] for p in added)
    quote=first.post('/api/calculate',json={'items':[{'product_id':added[0]['id'],'width':12,'height':12,'quantity':1}]}).json()
    assert quote['review_required'] and quote['lines'][0]['quote_only']
    assert first.get('/',follow_redirects=False).headers['location']=='/products/embroidered-hats'
    assert 'Wear your brand. Make an impression.' in first.get('/products').text
    assert catalog['shop']['rates_live'] is False
    assert first.get('/api/admin/settings').json()['checkout_enabled'] is False
    # Owner changes and existing product edits survive a subsequent application load.
    child=app.state.company_apps['mirakol']
    with transaction(child.state.database,True) as conn:
        count=conn.execute('SELECT count(*) FROM products').fetchone()[0]
        revisions=conn.execute('SELECT count(*) FROM company_revisions').fetchone()[0]
        shop=settings(conn)|{'brand_primary':'#123456'}
        conn.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(shop),))
    app.state.company_apps.pop('mirakol')
    assert first.get('/api/brand').json()['brand_primary']=='#123456'
    with transaction(child.state.database) as conn:
        assert conn.execute('SELECT count(*) FROM products').fetchone()[0]==count
        assert conn.execute('SELECT count(*) FROM company_revisions').fetchone()[0]==revisions
    assert admin.get('/api/brand').json()==original_brand
    assert admin.get('/brand/app-icon.png').content==original_icon
    assert admin.get('/api/catalog').json()['products']==original_products
    other=tenant(app,'other.example.test',add_company(admin,'another-shop','other.example.test'))
    assert other.get('/brand/images/'+brand['brand_logo']).status_code==404
    assert other.get('/brand/images/'+brand['brand_icon']).status_code==404
    assert not expected.intersection({p['name'] for p in other.get('/api/catalog').json()['products']}) - {'DTF transfers'}
    first.close();other.close()


def test_setup_requires_matching_company_identity(env):
    app,admin,_=env
    response=admin.post('/api/platform/companies',json={'slug':'mirakol','name':'Different Shop',
                        'owner_email':'another@example.test','hostname':'other.example.test'})
    child=app.state.company_apps.pop('mirakol')
    client=tenant(app,'other.example.test',response.json())
    assert client.get('/api/brand').json()['brand_icon']==''
    assert 'Custom table covers' not in {p['name'] for p in client.get('/api/catalog').json()['products']}
    client.close()


def test_reference_icon_update_preserves_owner_settings_draft_and_products(env):
    app,admin,_=env
    created=admin.post('/api/platform/companies',json={'slug':'mirakol','name':'Mirakol Customs',
                       'owner_email':'client@example.test','hostname':'mirakol.tampasigns.net'}).json()
    app.state.company_apps.pop('mirakol')
    client=tenant(app,'mirakol.tampasigns.net',created)
    new_icon=client.get('/api/brand').json()['brand_icon']
    child=app.state.company_apps['mirakol']
    bundle=Path(__file__).parents[1]/'app/company_setups/mirakol'
    clean,_,_,_=sanitize((bundle/'icon.png').read_bytes(),'icon.png')
    previous_icon=hashlib.sha256(clean).hexdigest()+'.png'
    with transaction(child.state.database,True) as conn:
        conn.execute("DELETE FROM company_setup_applied WHERE id='mirakol-reference-icon-20261002-v3'")
        shop=settings(conn)|{'brand_primary':'#123456','contact_phone':'555-0100','brand_icon':previous_icon}
        conn.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(shop),))
        draft=json.loads(conn.execute('SELECT data FROM company_draft WHERE id=1').fetchone()[0])
        draft=draft|{'storefront_heading':'An unpublished owner draft','brand_icon':previous_icon}
        conn.execute('UPDATE company_draft SET data=? WHERE id=1',(json.dumps(draft),))
        products=[dict(r) for r in conn.execute('SELECT * FROM products ORDER BY id')]
    app.state.company_apps.pop('mirakol')
    updated=client.get('/api/brand').json()
    assert updated['brand_icon']==new_icon and new_icon!=previous_icon
    assert updated['brand_primary']=='#123456' and updated['contact_phone']=='555-0100'
    state=client.get('/api/admin/company').json()
    assert state['draft']['data']['storefront_heading']=='An unpublished owner draft'
    assert state['draft']['data']['brand_icon']==new_icon
    with transaction(child.state.database) as conn:
        assert [dict(r) for r in conn.execute('SELECT * FROM products ORDER BY id')]==products
    app.state.company_apps.pop('mirakol')
    assert client.get('/api/admin/company').json()['draft']['version']==state['draft']['version']
    client.close()
