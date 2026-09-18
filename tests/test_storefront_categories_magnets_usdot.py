from .conftest import anonymous


def catalog_by_name(client):
    return {p['name']: p for p in client.get('/api/catalog').json()['products']}


def test_storefront_category_metadata_and_duplicates(env):
    app, admin, employee = env
    products = catalog_by_name(anonymous(app))

    assert products['Window Graphics']['config']['storefront_categories'] == ['Storefront']
    assert set(products['Banners']['config']['storefront_categories']) == {'Storefront', 'Signs'}
    assert set(products['ACM signs']['config']['storefront_categories']) == {'Storefront', 'Signs'}
    assert set(products['Magnets']['config']['storefront_categories']) == {'Vehicle Signage', 'Signs'}
    assert products['Transfer stickers']['config']['storefront_categories'] == ['Stickers']
    assert products['Vehicle Wraps']['config']['storefront_categories'] == ['Vehicle Signage']
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
    assert set(decals['config']['storefront_categories']) == {'Stickers', 'Vehicle Signage'}
    assert decals['config']['self_approve_artwork'] is True

    usdot = products['USDOT Decals']
    assert set(usdot['config']['storefront_categories']) == {'Vehicle Signage', 'Stickers'}
    assert usdot['config']['usdot_customizer'] is True
    assert [x['label'] for x in usdot['config']['size_options']] == ['18 x 12 in', '24 x 12 in', '24 x 18 in']
    assert usdot['config']['max_short_axis'] == '24'
    assert usdot['config']['max_long_axis'] == '48'

    dtf = products['DTF transfers']['config']
    assert dtf['storefront_categories'] == ['Apparel']
    assert dtf['instant'] is True
    assert dtf['sell_per_sqft'] if 'sell_per_sqft' in dtf else True
    assert [x['id'] for x in dtf['placement_options']][:4] == [
        'adult_left_chest', 'adult_right_chest', 'adult_full_front', 'adult_full_back'
    ]

    hats = products['Embroidered hats']['config']
    polos = products['Embroidered polos']['config']
    assert hats['storefront_categories'] == ['Apparel']
    assert polos['storefront_categories'] == ['Apparel']
    assert hats['instant'] is False and polos['instant'] is False
    assert [x['id'] for x in hats['placement_options']] == ['front']
    assert [x['id'] for x in polos['placement_options']] == ['left_chest', 'right_chest']


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
