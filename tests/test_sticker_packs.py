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

