from .conftest import anonymous


def test_transfer_stickers_are_second_and_allow_single_unit(env):
    app, admin, employee = env
    client = anonymous(app)
    products = client.get('/api/catalog').json()['products']
    names = [p['name'] for p in products]
    assert names[0] == 'Die-cut stickers'
    assert names[1] == 'Transfer stickers'
    transfer = products[1]
    assert transfer['config']['min_quantity'] == '1'
    assert transfer['config']['min_width'] == '3'
    assert transfer['config']['min_height'] == '3'

    quote = client.post('/api/calculate', json={'items':[{
        'product_id': transfer['id'], 'width': 3, 'height': 3, 'quantity': 1,
        'lamination': 'none'
    }]})
    assert quote.status_code == 200, quote.text
    data = quote.json()
    assert data['subtotal_cents'] < 5000
    assert data['minimum_order_cents'] == 5000
    assert data['meets_minimum_order'] is False


def test_storefront_windows_accept_multiple_panels(env):
    app, admin, employee = env
    client = anonymous(app)
    windows = next(p for p in client.get('/api/catalog').json()['products'] if p['category'] == 'Windows')
    assert windows['config']['supports_multiple_dimensions'] is True

    r = client.post('/api/calculate', json={'items':[
        {'product_id': windows['id'], 'width': 44, 'height': 92, 'quantity': 1, 'lamination': 'none'},
        {'product_id': windows['id'], 'width': 43.75, 'height': 92, 'quantity': 1, 'lamination': 'none'},
    ]})
    assert r.status_code == 200, r.text
    assert len(r.json()['lines']) == 2


def test_wholesale_profile_can_apply_default_and_product_discount(env):
    app, admin, employee = env
    public = anonymous(app)
    sticker = next(p for p in public.get('/api/catalog').json()['products'] if p['name'] == 'Die-cut stickers')

    created = admin.post('/api/admin/wholesale', json={
        'name': 'Wholesale Test Co',
        'email': 'wholesale@example.test',
        'discount_percent': 10,
        'product_discounts': {str(sticker['id']): 25}
    })
    assert created.status_code == 200, created.text
    code = created.json()['access_code']

    activated = public.post('/api/wholesale/activate', json={
        'email': 'wholesale@example.test',
        'code': code
    })
    assert activated.status_code == 200, activated.text
    token = activated.json()['token']

    retail = public.post('/api/calculate', json={'items':[{
        'product_id': sticker['id'], 'width': 3, 'height': 3, 'quantity': 50,
        'lamination': 'none'
    }]}).json()
    wholesale = public.post('/api/calculate', json={
        'wholesale_token': token,
        'items':[{
            'product_id': sticker['id'], 'width': 3, 'height': 3, 'quantity': 50,
            'lamination': 'none'
        }]
    })
    assert wholesale.status_code == 200, wholesale.text
    body = wholesale.json()
    assert body['wholesale']['name'] == 'Wholesale Test Co'
    assert body['subtotal_cents'] < retail['subtotal_cents']
    assert body['lines'][0]['wholesale_discount_percent'] == '25'

    profiles = admin.get('/api/admin/wholesale')
    assert profiles.status_code == 200
    assert profiles.json()['clients'][0]['product_discounts'][0]['product_id'] == sticker['id']
