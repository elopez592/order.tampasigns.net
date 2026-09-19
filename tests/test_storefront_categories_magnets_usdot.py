from .conftest import anonymous


def catalog_by_name(client):
    return {p['name']: p for p in client.get('/api/catalog').json()['products']}


def test_storefront_category_metadata_and_duplicates(env):
    app, admin, employee = env
    products = catalog_by_name(anonymous(app))

    assert products['Window Graphics']['config']['storefront_categories'] == ['Storefront']
    assert set(products['Banners']['config']['storefront_categories']) == {'Storefront', 'Signs', 'Events'}
    assert set(products['ACM signs']['config']['storefront_categories']) == {'Storefront', 'Signs'}
    assert set(products['Magnets']['config']['storefront_categories']) == {'Vehicles', 'Fleet Services', 'Signs'}
    assert products['Transfer stickers']['config']['storefront_categories'] == ['Stickers']
    assert set(products['Vehicle Wraps']['config']['storefront_categories']) == {'Vehicles', 'Fleet Services'}
    assert products['Die-cut stickers']['config']['storefront_categories'] == ['Stickers']


def test_magnet_standard_sizes_and_orientation_independent_limit(env):
    app, admin, employee = env
    client = anonymous(app)
    magnet = catalog_by_name(client)['Magnets']
    cfg = magnet['config']
    assert [(x['width'], x['height']) for x in cfg['size_options']] == [
        ('18', '12'), ('24', '12'), ('24', '18')
    ]
    assert cfg['max_short_axis'] == '24'
    assert cfg['max_long_axis'] == '48'
    assert cfg['quantity_presets'][:2] == [1, 2]

    valid = client.post('/api/calculate', json={'items':[{
        'product_id': magnet['id'], 'width': 48, 'height': 24, 'quantity': 1,
        'lamination': 'none'
    }]})
    assert valid.status_code == 200, valid.text

    rotated = client.post('/api/calculate', json={'items':[{
        'product_id': magnet['id'], 'width': 24, 'height': 48, 'quantity': 1,
        'lamination': 'none'
    }]})
    assert rotated.status_code == 200, rotated.text

    too_wide = client.post('/api/calculate', json={'items':[{
        'product_id': magnet['id'], 'width': 25, 'height': 48, 'quantity': 1,
        'lamination': 'none'
    }]})
    assert too_wide.status_code == 422


def test_decals_usdot_and_apparel_listings(env):
    app, admin, employee = env
    client = anonymous(app)
    products = catalog_by_name(client)

    decals = products['Decals']
    assert set(decals['config']['storefront_categories']) == {'Stickers', 'Vehicles', 'Fleet Services'}
    assert decals['config']['self_approve_artwork'] is True

    usdot = products['USDOT Decals']
    assert usdot['config']['storefront_categories'] == ['Vehicles', 'Fleet Services']
    assert usdot['config']['usdot_customizer'] is True
    assert [x['label'] for x in usdot['config']['size_options']] == ['18 x 12 in', '24 x 12 in', '24 x 18 in']
    assert usdot['config']['max_short_axis'] == '24'
    assert usdot['config']['max_long_axis'] == '48'
    assert usdot['config']['quantity_presets'][:2] == [1, 2]

    shirts = products['Custom T-shirts']['config']
    assert shirts['storefront_categories'] == ['Apparel', 'Events']
    assert shirts['finished_apparel'] is True
    assert shirts['shirt_sizes'] == ['S', 'M', 'L', 'XL', '2XL', '3XL']
    assert {'White', 'Black', 'Navy', 'Royal', 'Red', 'Sport Grey'} == set(shirts['shirt_colors'])
    assert 'Gildan Heavy Cotton 5000' in shirts['description']

    hats = products['Embroidered hats']['config']
    polos = products['Embroidered polos']['config']
    assert hats['storefront_categories'] == ['Apparel']
    assert polos['storefront_categories'] == ['Apparel']
    assert hats['instant'] is False and polos['instant'] is False
    assert hats['finished_apparel'] is True and polos['finished_apparel'] is True
    assert hats['shirt_sizes'] == ['Adjustable']
    assert polos['shirt_sizes'] == ['S', 'M', 'L', 'XL', '2XL', '3XL']
    assert set(hats['shirt_colors']) == set(polos['shirt_colors']) == {'White', 'Black', 'Navy', 'Royal', 'Red', 'Sport Grey'}
    assert [x['id'] for x in hats['placement_options']] == ['front']
    assert [x['id'] for x in polos['placement_options']] == ['left_chest', 'right_chest']
    assert hats['digitizing_fee'] == polos['digitizing_fee'] == '35'
    assert 'one-time $35 digitizing fee' in hats['description']
    assert 'one-time $35 digitizing fee' in polos['description']

    shirt_product = products['Custom T-shirts']
    shirt_quote = client.post('/api/calculate', json={'items':[{
        'product_id': shirt_product['id'], 'width': 12, 'height': 12, 'quantity': 1,
        'shirt_color': 'Black', 'size_quantities': {'M': 1}, 'print_locations': ['front']
    }]})
    assert shirt_quote.status_code == 200, shirt_quote.text
    assert shirt_quote.json()['subtotal_cents'] == 3000
    assert shirt_quote.json()['meets_minimum_order'] is True
    assert shirt_quote.json()['lines'][0]['description'].startswith('Gildan 5000 / Black / M: 1 / Full front')

    hat_product = products['Embroidered hats']
    hat_quote = client.post('/api/calculate', json={'items':[{
        'product_id': hat_product['id'], 'width': 4, 'height': 2.25, 'quantity': 5,
        'shirt_color': 'Navy', 'size_quantities': {'Adjustable': 5}, 'print_locations': ['front']
    }]})
    assert hat_quote.status_code == 200, hat_quote.text
    assert hat_quote.json()['subtotal_cents'] == 3500
    assert hat_quote.json()['lines'][0]['digitizing_fee_cents'] == 3500
    assert hat_quote.json()['lines'][0]['quote_only'] is True
    assert hat_quote.json()['review_required'] is True


def test_fleet_window_tint_is_fleet_only_and_retail_first(env):
    app, admin, employee = env
    client = anonymous(app)
    products = catalog_by_name(client)
    tint = products['Fleet Window Tinting']
    cfg = tint['config']
    assert cfg['storefront_categories'] == ['Fleet Services']
    assert cfg['quantity_only'] is True
    assert cfg['quantity_presets'][:4] == [1, 2, 5, 10]
    assert cfg['instant'] is False
    assert cfg['vehicle_details_required'] is True
    assert '$600' in cfg['description']

    single = client.post('/api/calculate', json={'items':[{
        'product_id': tint['id'], 'width': 12, 'height': 12, 'quantity': 1
    }]})
    assert single.status_code == 200, single.text
    assert single.json()['subtotal_cents'] == 60000
    assert single.json()['review_required'] is True

    windshield = client.post('/api/calculate', json={'items':[{
        'product_id': tint['id'], 'width': 12, 'height': 12, 'quantity': 1,
        'coverage_option': 'windshield'
    }]})
    fronts = client.post('/api/calculate', json={'items':[{
        'product_id': tint['id'], 'width': 12, 'height': 12, 'quantity': 1,
        'coverage_option': 'windshield_fronts'
    }]})
    assert windshield.json()['subtotal_cents'] == 20000
    assert fronts.json()['subtotal_cents'] == 30000
    assert cfg['artwork_upload_disabled'] is True

    bulk = client.post('/api/calculate', json={'items':[{
        'product_id': tint['id'], 'width': 12, 'height': 12, 'quantity': 10
    }]})
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()['subtotal_cents'] < 60000 * 10


def test_usdot_quote_preserves_generated_preview_copy(env):
    app, admin, employee = env
    client = anonymous(app)
    usdot = catalog_by_name(client)['USDOT Decals']
    description = 'Company: BAY AREA LOGISTICS | USDOT 1234567 | Tampa, FL | Style: industrial'
    response = client.post('/api/calculate', json={'items':[{
        'product_id': usdot['id'], 'width': 18, 'height': 12, 'quantity': 2,
        'description': description, 'lamination': 'none'
    }]})
    assert response.status_code == 200, response.text
    assert response.json()['lines'][0]['description'] == description

    design = {
        'company': 'Bay Area Logistics', 'phone': '(813) 555-0123',
        'number': 'USDOT 1234567', 'licenses': 'MC 7654321',
        'location': 'Tampa, FL', 'style': 'stencil',
        'text_color': '#ffffff', 'background_color': '#123456'
    }
    generated = client.post('/api/calculate', json={'items':[{
        'product_id': usdot['id'], 'width': 24, 'height': 12, 'quantity': 2,
        'usdot_design': design, 'lamination': 'none'
    }]})
    assert generated.status_code == 200, generated.text
    saved = generated.json()['lines'][0]['usdot_design']
    assert saved['phone'] == '(813) 555-0123'
    assert saved['licenses'] == 'MC 7654321'
    assert saved['number'] == '1234567'
    assert saved['style'] == 'stencil'
    assert saved['text_color'] == '#ffffff'
    assert saved['background_color'] == '#123456'

    invalid = client.post('/api/calculate', json={'items':[{
        'product_id': usdot['id'], 'width': 18, 'height': 12, 'quantity': 1,
        'usdot_design': design | {'style': 'comic-sans'}, 'lamination': 'none'
    }]})
    assert invalid.status_code == 422
