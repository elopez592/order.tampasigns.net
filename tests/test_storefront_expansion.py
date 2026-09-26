from .conftest import anonymous


def products(client):
    return {p['name']: p for p in client.get('/api/catalog').json()['products']}


def test_events_tinting_foam_boards_and_rollups_are_public(env):
    app, admin, employee = env
    catalog = products(anonymous(app))

    assert catalog['Window Graphics']['config']['storefront_categories'] == ['Storefront']
    assert catalog['Fleet Window Tinting']['config']['storefront_categories'] == ['Fleet Services']
    assert catalog['Storefront Window Tinting']['config']['storefront_categories'] == ['Storefront']
    assert catalog['Roll-up banners']['config']['storefront_categories'] == ['Storefront', 'Events']
    assert catalog['Foam boards']['config']['storefront_categories'] == ['Storefront', 'Events']
    assert catalog['A-Frame inserts']['config']['storefront_categories'] == ['Storefront', 'Events']
    assert set(catalog['Aluminum Composite Signs']['config']['storefront_categories']) == {'Construction signs', 'Signs'}
    assert set(catalog['High-Density Board Signs']['config']['storefront_categories']) == {'Construction signs', 'Signs'}
    assert 'Construction signs' in catalog['Banners']['config']['storefront_categories']
    assert 'Events' in catalog['Banners']['config']['storefront_categories']
    assert 'Events' in catalog['Custom T-shirts']['config']['storefront_categories']
    assert catalog['Roll-up banners']['config']['quote_only'] is False
    assert catalog['Storefront Window Tinting']['config']['artwork_upload_disabled'] is True


def test_new_sign_products_have_prices_sizes_and_material_options(env):
    app, admin, employee = env
    client = anonymous(app)
    catalog = products(client)

    rollup = catalog['Roll-up banners']
    quote = client.post('/api/calculate', json={'items':[{
        'product_id': rollup['id'], 'width': 33, 'height': 80, 'quantity': 1
    }]}).json()
    assert quote['subtotal_cents'] == 15000

    aframe = catalog['A-Frame inserts']
    insert_quote = client.post('/api/calculate', json={'items':[{
        'product_id': aframe['id'], 'width': 24, 'height': 36, 'quantity': 1, 'material': 'inserts'
    }]}).json()
    assert insert_quote['subtotal_cents'] == 4900

    two_insert_quote = client.post('/api/calculate', json={'items':[{
        'product_id': aframe['id'], 'width': 24, 'height': 36, 'quantity': 2, 'material': 'inserts'
    }]}).json()
    assert two_insert_quote['subtotal_cents'] == 8000

    frame_quote = client.post('/api/calculate', json={'items':[{
        'product_id': aframe['id'], 'width': 24, 'height': 36, 'quantity': 1, 'material': 'with_frame'
    }]}).json()
    assert frame_quote['subtotal_cents'] == 14800

    two_insert_frame_quote = client.post('/api/calculate', json={'items':[{
        'product_id': aframe['id'], 'width': 24, 'height': 36, 'quantity': 2, 'material': 'with_frame'
    }]}).json()
    assert two_insert_frame_quote['subtotal_cents'] == 17900

    foam = catalog['Foam boards']
    assert foam['config']['max_width'] == '48' and foam['config']['max_height'] == '96'
    quarter = client.post('/api/calculate', json={'items':[{
        'product_id': foam['id'], 'width': 48, 'height': 96, 'quantity': 1, 'material': 'quarter'
    }]}).json()['subtotal_cents']
    half = client.post('/api/calculate', json={'items':[{
        'product_id': foam['id'], 'width': 48, 'height': 96, 'quantity': 1, 'material': 'half'
    }]}).json()['subtotal_cents']
    assert quarter > 0 and half > quarter

    construction = catalog['Aluminum Composite Signs']['config']
    assert [x['label'] for x in construction['size_options']] == ['2 × 4 ft', '3 × 6 ft', '4 × 8 ft', '5 × 10 ft']
    assert '3mm aluminum composite' in construction['description']
    hdu_product = catalog['High-Density Board Signs']
    hdu = hdu_product['config']
    assert hdu['quote_only'] is False
    assert [x['label'] for x in hdu['size_options']] == ['3 × 4 ft', '4 × 6 ft', '4 × 8 ft']
    assert hdu['min_short_axis'] == '36' and hdu['min_long_axis'] == '48'
    assert '1/2-inch high-density urethane board' in hdu['description']
    standard_hdu = client.post('/api/calculate', json={'items':[{
        'product_id': hdu_product['id'], 'width': 36, 'height': 48, 'quantity': 1
    }]})
    assert standard_hdu.status_code == 200, standard_hdu.text
    assert standard_hdu.json()['subtotal_cents'] == 24000
    landscape_hdu = client.post('/api/calculate', json={'items':[{
        'product_id': hdu_product['id'], 'width': 48, 'height': 36, 'quantity': 1
    }]})
    assert landscape_hdu.status_code == 200, landscape_hdu.text
    too_small_hdu = client.post('/api/calculate', json={'items':[{
        'product_id': hdu_product['id'], 'width': 24, 'height': 48, 'quantity': 1
    }]})
    assert too_small_hdu.status_code == 422


def test_finished_shirts_validate_options_and_reward_quantity(env):
    app, admin, employee = env
    client = anonymous(app)
    shirt = products(client)['Custom T-shirts']

    bulk = client.post('/api/calculate', json={'items': [{
        'product_id': shirt['id'], 'width': 12, 'height': 12, 'quantity': 12,
        'shirt_color': 'Royal', 'size_quantities': {'M': 6, 'L': 6},
        'print_locations': ['back'],
    }]})
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()['lines'][0]['price_per_item_cents'] < 3000

    invalid = client.post('/api/calculate', json={'items': [{
        'product_id': shirt['id'], 'width': 12, 'height': 12, 'quantity': 2,
        'shirt_color': 'Royal', 'size_quantities': {'M': 1},
        'print_locations': ['front'],
    }]})
    assert invalid.status_code == 422

    chest = client.post('/api/calculate', json={'items': [{
        'product_id': shirt['id'], 'width': 12, 'height': 12, 'quantity': 1,
        'shirt_color': 'White', 'size_quantities': {'M': 1},
        'print_locations': ['left_chest'],
    }]})
    assert chest.status_code == 200, chest.text
    assert chest.json()['subtotal_cents'] == 2500

    back_and_chest = client.post('/api/calculate', json={'items': [{
        'product_id': shirt['id'], 'width': 12, 'height': 12, 'quantity': 1,
        'shirt_color': 'Navy', 'size_quantities': {'L': 1},
        'print_locations': ['back', 'left_chest'],
    }]})
    assert back_and_chest.status_code == 200, back_and_chest.text
    assert back_and_chest.json()['subtotal_cents'] == 5500
    assert back_and_chest.json()['lines'][0]['print_locations'] == ['back', 'left_chest']


def test_customer_account_register_login_and_logout(env):
    app, admin, employee = env
    client = anonymous(app)

    created = client.post('/api/customer/register', json={
        'name': 'Customer Test', 'email': 'customer@example.test',
        'password': 'safe-password-123',
    })
    assert created.status_code == 200, created.text
    assert created.json()['customer']['email'] == 'customer@example.test'
    assert client.get('/api/customer').json()['customer']['name'] == 'Customer Test'

    assert client.post('/api/customer/logout', json={}).status_code == 200
    assert client.get('/api/customer').json()['customer'] is None
    signed_in = client.post('/api/customer/login', json={
        'email': 'customer@example.test', 'password': 'safe-password-123',
    })
    assert signed_in.status_code == 200, signed_in.text


def test_wholesale_discount_does_not_reduce_digitizing_fee(env):
    app, admin, employee = env
    public = anonymous(app)
    hat = products(public)['Embroidered hats']
    created = admin.post('/api/admin/wholesale', json={
        'name': 'Protected Fees Co', 'username': 'protectedfees',
        'email': 'fees@example.test', 'discount_percent': 50,
    })
    password = created.json()['temporary_password']
    token = public.post('/api/wholesale/activate', json={
        'username': 'protectedfees', 'password': password,
    }).json()['token']
    item = {'product_id': hat['id'], 'width': 4, 'height': 2.25, 'quantity': 10,
            'shirt_color': 'Black', 'size_quantities': {'Adjustable': 10}, 'print_locations': ['front']}
    retail = public.post('/api/calculate', json={'items': [item]}).json()
    wholesale = public.post('/api/calculate', json={'items': [item], 'wholesale_token': token}).json()
    assert retail['subtotal_cents'] == 38500
    assert wholesale['subtotal_cents'] == 21000
    assert retail['lines'][0]['digitizing_fee_cents'] == 3500
    assert wholesale['lines'][0]['digitizing_fee_cents'] == 3500
