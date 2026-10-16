import json
import pytest
from fastapi import HTTPException
from app.sticker_packs import normalize_pack
from app.db import transaction
from app.checkout import eligible_quote
from tests.conftest import anonymous


def specification():
    return {'stickers': [{'name':'van.png','width':3,'height':2,'copies':2},
                         {'name':'logo.pdf','width':1.5,'height':1.5,'copies':1}],
            'header': {'name':'header.pdf','width':5.25,'height':4}, 'notes':'Gloss; assemble in bags'}


def test_totals_and_production_description():
    pack, description = normalize_pack(specification(), 50)
    assert pack['stickers_per_pack'] == 3
    assert pack['total_stickers'] == 150
    assert '100 total' in description and '50 headers' in description
    assert '5.25 x 4' in description


@pytest.mark.parametrize('rows', [[], [{}], [{'name':'x.png','width':-1,'height':3}],
    [{'name':'x.png','width':3,'height':3,'copies':1.5}], [dict(name='x',width=3,height=3)]*21])
def test_invalid_designs(rows):
    with pytest.raises(HTTPException):
        normalize_pack({'stickers':rows}, 50)


def test_sticker_dimensions_cannot_exceed_four_inches():
    with pytest.raises(HTTPException):
        normalize_pack({'stickers':[{'name':'large.png','width':4.01,'height':2,'copies':1}]}, 1)


def test_catalog_and_quote_preserve_bundle(env):
    app, admin, _ = env
    catalog=admin.get('/api/catalog').json()
    product=next(p for p in catalog['products'] if p['name']=='Sticker packs')
    assert product['config']['sticker_pack']
    item={'product_id':product['id'],'quantity':50,'width':1,'height':1,'sticker_pack':specification()}
    quote=admin.post('/api/calculate',json={'items':[item]})
    assert quote.status_code==200,quote.text
    q=quote.json()
    assert q['review_required']
    assert q['lines'][0]['quote_only'] is False
    assert q['lines'][0]['sticker_pack']['total_stickers']==150
    assert 'Gloss; assemble in bags' in q['lines'][0]['description']
    item['quantity']=75
    q=admin.post('/api/calculate',json={'items':[item]}).json()
    assert q['lines'][0]['sticker_pack']['total_stickers']==225
    del item['sticker_pack']
    assert admin.post('/api/calculate',json={'items':[item]}).status_code==422


def test_quote_request_keeps_specs_and_unapproved_shop_rates_block_checkout(env):
    app, admin, _ = env
    client = anonymous(app)
    product = next(p for p in client.get('/api/catalog').json()['products'] if p['name'] == 'Sticker packs')
    items = [{'product_id': product['id'], 'quantity': 50, 'sticker_pack': specification()}]
    quote = client.post('/api/calculate', json={'items': items}).json()
    response = client.post('/api/requests', json={
        'items': items, 'fingerprint': quote['fingerprint'], 'title': 'Custom sticker pack',
        'customer_name': 'Pack test', 'customer_email': 'packs@example.test'})
    assert response.status_code == 200, response.text
    with transaction(app.state.database) as conn:
        saved = json.loads(conn.execute('SELECT quote_snapshot FROM jobs WHERE id=?',
                                       (response.json()['job_id'],)).fetchone()[0])
        assert saved['lines'][0]['sticker_pack']['header']['width'] == '5.25'
        assert saved['lines'][0]['sticker_pack']['total_stickers'] == 150
        assert '100 total' in saved['lines'][0]['description']
        with pytest.raises(HTTPException) as error:
            eligible_quote(conn, items)
        assert error.value.status_code == 422


def test_staff_pricing_preserves_large_pack_and_updates_totals(env):
    from app.main import revised_quote_snapshot
    app, admin, _ = env
    product = next(p for p in admin.get('/api/catalog').json()['products'] if p['name'] == 'Sticker packs')
    spec = specification()
    spec['stickers'] *= 10
    quote = admin.post('/api/calculate', json={'items': [{'product_id': product['id'], 'quantity': 50, 'sticker_pack': spec}]}).json()
    assert len(quote['lines'][0]['description']) > 500
    revised = revised_quote_snapshot(quote, [{'source_index': 0, 'quantity': 75, 'sell_total': 400}])
    assert revised['lines'][0]['sticker_pack']['total_stickers'] == 2250
    assert '75 packs' in revised['lines'][0]['description']
    assert revised['lines'][0]['sell_cents'] == 40000



@pytest.mark.parametrize('packs', [50, 100, 1000])
def test_benchmark_pack_price_remains_stable_after_50(env, packs):
    app, admin, _=env
    product=next(p for p in admin.get('/api/catalog').json()['products'] if p['name']=='Sticker packs')
    spec={'stickers':[{'name':'A','width':3,'height':2,'copies':2},
                      {'name':'B','width':3,'height':2,'copies':1}]}
    line=admin.post('/api/calculate',json={'items':[{'product_id':product['id'],'quantity':packs,'sticker_pack':spec}]}).json()['lines'][0]
    assert line['sell_cents']==packs*350
    assert line['sticker_pack_pricing']['bundle_unit_cents']==350


def test_size_and_sticker_count_change_bundle_price(env):
    app,admin,_=env
    product=next(p for p in admin.get('/api/catalog').json()['products'] if p['name']=='Sticker packs')
    def quote(width,height,copies,qty=50):
        spec={'stickers':[{'name':'A','width':width,'height':height,'copies':copies}]}
        return admin.post('/api/calculate',json={'items':[{'product_id':product['id'],'quantity':qty,'sticker_pack':spec}]}).json()['lines'][0]['sell_cents']
    assert quote(2,2,3)<quote(3,2,3)<quote(4,4,3)
    assert quote(3,2,5)>quote(3,2,3)
    assert quote(3,2,3,49)>49*350


def test_generated_design_charge_is_one_time(env):
    app,admin,_=env
    product=next(p for p in admin.get('/api/catalog').json()['products'] if p['name']=='Sticker packs')
    spec={'stickers':[{'name':'A','width':3,'height':2,'copies':3,'design_service':'generated'}]}
    for packs in (50,100):
        line=admin.post('/api/calculate',json={'items':[{'product_id':product['id'],'quantity':packs,'sticker_pack':spec}]}).json()['lines'][0]
        assert line['sell_cents']==packs*350+1200


def test_pack_configured_fees_and_live_sticker_rates_are_used(env):
    app,admin,_=env
    from app.pricing import validate_config
    with transaction(app.state.database,True) as conn:
        product=conn.execute("SELECT * FROM products WHERE name='Sticker packs'").fetchone()
        cfg=json.loads(product['config'])
        cfg.update(pack_header_4_price='1.75',pack_packaging_price='1.25')
        conn.execute('UPDATE products SET config=? WHERE id=?',(json.dumps(validate_config(cfg)),product['id']))
    spec=specification();spec['header']['width']=4
    item={'product_id':product['id'],'quantity':50,'sticker_pack':spec}
    first=admin.post('/api/calculate',json={'items':[item]}).json()['lines'][0]
    assert first['sticker_pack_pricing']['headers_cents']==8750
    assert first['sticker_pack_pricing']['packaging_cents']==6250
    with transaction(app.state.database,True) as conn:
        sticker=conn.execute("SELECT * FROM products WHERE name='Die-cut stickers'").fetchone()
        cfg=json.loads(sticker['config']);cfg.update(quantity_price_table=[],sell_per_sqft='100',minimum_price='0')
        conn.execute('UPDATE products SET config=?,version=version+1 WHERE id=?',(json.dumps(validate_config(cfg)),sticker['id']))
    second=admin.post('/api/calculate',json={'items':[item]}).json()['lines'][0]
    assert second['sell_cents']==first['sell_cents']  # bundled sell rates are independent of individual die-cut retail prices
    assert second['sticker_pack_pricing']['designs'][0]['product_version']==sticker['version']+1


def test_pack_wholesale_stickers_are_discounted_once_and_fees_stay_fixed(env):
    app,_,_=env
    from app.pricing import calculate
    with transaction(app.state.database,True) as conn:
        result=conn.execute("INSERT INTO wholesale_clients(name,email,username,code_hash,discount_percent,created_at,updated_at) VALUES('Trade','trade@example.test','pack-trade','unused','20','2026-10-15','2026-10-15')")
        client=result.lastrowid
        product=conn.execute("SELECT id FROM products WHERE name='Sticker packs'").fetchone()['id']
        sticker=conn.execute("SELECT id FROM products WHERE name='Die-cut stickers'").fetchone()['id']
        spec=specification();spec['header']['width']=4
        separate=calculate(conn,[{'product_id':sticker,'quantity':s['copies']*50,'width':s['width'],'height':s['height']} for s in spec['stickers']],staff=True,wholesale_client_id=client)
        bundle=calculate(conn,[{'product_id':product,'quantity':50,'sticker_pack':spec}],staff=True,wholesale_client_id=client)
        assert bundle['subtotal_cents']==50*(80+2*90+34)  # two 3x2 and one 1.5x1.5 design
        assert bundle['cost_cents']==separate['cost_cents']


@pytest.mark.parametrize('width,height',[(4.01,3),(3,4.01),(5,5)])
def test_four_inch_limit_is_enforced_on_both_sides(env,width,height):
    app,admin,_=env
    product=next(p for p in admin.get('/api/catalog').json()['products'] if p['name']=='Sticker packs')
    spec={'stickers':[{'name':'sticker.png','width':width,'height':height,'copies':1}]}
    response=admin.post('/api/calculate',json={'items':[{'product_id':product['id'],'quantity':50,'sticker_pack':spec}]})
    assert response.status_code==422


def test_header_artwork_is_optional_and_package_size_is_not_required(env):
    app,admin,_=env
    product=next(p for p in admin.get('/api/catalog').json()['products'] if p['name']=='Sticker packs')
    spec={'stickers':[{'name':'sticker.png','width':4,'height':4,'copies':1}]}
    item={'product_id':product['id'],'quantity':50,'sticker_pack':spec}
    standard=admin.post('/api/calculate',json={'items':[item]}).json()['lines'][0]
    assert standard['sticker_pack']['header_included'] is True
    assert 'Standard cardstock header included' in standard['description']
    assert 'Package size may vary' in standard['description']
    assert standard['sticker_pack_pricing']['headers_cents']==7500
    spec['header']={'name':'custom-header.pdf'}
    custom=admin.post('/api/calculate',json={'items':[item]}).json()['lines'][0]
    assert custom['sell_cents']==standard['sell_cents']
    assert custom['sticker_pack']['header']=={'name':'custom-header.pdf'}
    assert 'Custom header artwork: custom-header.pdf' in custom['description']
