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


def test_sticker_dimensions_cannot_exceed_seven_inches():
    with pytest.raises(HTTPException):
        normalize_pack({'stickers':[{'name':'large.png','width':7.01,'height':2,'copies':1}]}, 1)


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
    assert q['lines'][0]['quote_only']
    assert q['lines'][0]['sticker_pack']['total_stickers']==150
    assert 'Gloss; assemble in bags' in q['lines'][0]['description']
    item['quantity']=75
    q=admin.post('/api/calculate',json={'items':[item]}).json()
    assert q['lines'][0]['sticker_pack']['total_stickers']==225
    del item['sticker_pack']
    assert admin.post('/api/calculate',json={'items':[item]}).status_code==422


def test_quote_request_keeps_production_specs_and_blocks_instant_checkout(env):
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



@pytest.mark.parametrize('packs,header_width,header_unit', [(1,4,150),(50,4,150),(75,5,200),(50,None,0)])
def test_pack_price_is_individual_sticker_totals_plus_header_and_packaging(env,packs,header_width,header_unit):
    app,admin,_=env
    catalog=admin.get('/api/catalog').json()['products']
    product=next(p for p in catalog if p['name']=='Sticker packs')
    sticker=next(p for p in catalog if p['name']=='Die-cut stickers')
    spec=specification()
    if header_width is None:
        spec['header']=None
    else:
        spec['header']['width']=header_width
    separate=admin.post('/api/calculate',json={'items':[
        {'product_id':sticker['id'],'quantity':s['copies']*packs,'width':s['width'],'height':s['height']}
        for s in spec['stickers']]}).json()
    response=admin.post('/api/calculate',json={'items':[{
        'product_id':product['id'],'quantity':packs,'sticker_pack':spec,
        'sell_cents':1,'sticker_pack_pricing':{'total_cents':1}}]})
    assert response.status_code==200,response.text
    line=response.json()['lines'][0]
    expected=separate['subtotal_cents']+(header_unit+100)*packs
    assert line['sell_cents']==expected
    assert line['sticker_pack_pricing']['total_cents']==expected
    assert line['sticker_pack_pricing']['headers_cents']==header_unit*packs
    assert line['sticker_pack_pricing']['packaging_cents']==100*packs
    assert 'cost_cents' not in line
    assert 'cost_cents' not in line['sticker_pack_pricing']
    assert line['quote_only']


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
    assert second['sell_cents']>first['sell_cents']
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
        assert bundle['subtotal_cents']==separate['subtotal_cents']+12500
        assert bundle['cost_cents']==separate['cost_cents']
