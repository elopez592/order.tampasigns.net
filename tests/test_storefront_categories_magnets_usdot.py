from .conftest import anonymous
import json

from app.db import transaction
from app.seed import bootstrap
from app.storefront import upgrade_catalog


def catalog_by_name(client):
    return {p['name']: p for p in client.get('/api/catalog').json()['products']}


def test_storefront_category_metadata_and_duplicates(env):
    app, admin, employee = env
    products = catalog_by_name(anonymous(app))

    assert products['Window Graphics']['config']['storefront_categories'] == ['Storefront']
    assert set(products['Banners']['config']['storefront_categories']) == {'Storefront', 'Signs', 'Events', 'Construction & Site Signs'}
    assert set(products['Aluminum Composite Signs']['config']['storefront_categories']) == {'Construction & Site Signs', 'Storefront', 'Signs'}
    assert 'ACM signs' not in products
    assert set(products['Magnets']['config']['storefront_categories']) == {'Vehicles', 'Fleet Services', 'Signs'}
    assert products['Transfer stickers']['config']['storefront_categories'] == ['Stickers']
    assert set(products['Vehicle Wraps']['config']['storefront_categories']) == {'Vehicles', 'Fleet Services'}
    assert products['Die-cut stickers']['config']['storefront_categories'] == ['Stickers']


def test_acm_thickness_prices_and_existing_catalog_upgrade(env):
    app, admin, employee = env
    client = anonymous(app)
    product = catalog_by_name(client)['Aluminum Composite Signs']
    cfg = product['config']
    assert [(o['id'], o['sell_per_sqft_adjustment'], o['cost_per_sqft_adjustment'])
            for o in cfg['material_options']] == [('3mm', '0', '0'), ('6mm', '6', '3.5')]
    assert cfg['material_options'][0]['default'] is True

    def price(width, height, material=None, lamination='none'):
        item = {'product_id': product['id'], 'width': width, 'height': height,
                'quantity': 1, 'lamination': lamination}
        if material:
            item['material'] = material
        response = client.post('/api/calculate', json={'items': [item]})
        assert response.status_code == 200, response.text
        return response.json()

    assert price(24, 48)['subtotal_cents'] == 11200
    thicker = price(24, 48, '6mm')
    assert thicker['subtotal_cents'] == 16000
    assert thicker['lines'][0]['material_label'] == '6 mm ACM (+$6/sq ft)'
    assert price(48, 96, '3mm')['subtotal_cents'] == 44800
    assert price(48, 96, '6mm')['subtotal_cents'] == 64000

    # Production already has this product, so verify the startup upgrade path too.
    with transaction(app.state.database, True) as conn:
        row = conn.execute('SELECT config FROM products WHERE id=?', (product['id'],)).fetchone()
        old_cfg = json.loads(row['config'])
        old_cfg['material_options'] = []
        old_cfg['description'] = 'Temporary legacy ACM description.'
        conn.execute('UPDATE products SET config=? WHERE id=?', (json.dumps(old_cfg), product['id']))
    bootstrap(app.state.database)
    upgrade_catalog(app.state.database)
    bootstrap(app.state.database)
    upgrade_catalog(app.state.database)
    upgraded = catalog_by_name(client)['Aluminum Composite Signs']['config']
    assert catalog_by_name(client)['Aluminum Composite Signs']['version'] == product['version'] + 1
    assert [o['id'] for o in upgraded['material_options']] == ['3mm', '6mm']
    assert '3 mm standard or optional 6 mm' in upgraded['description']
    assert price(48, 96, '6mm')['subtotal_cents'] == 64000


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
    assert usdot['config']['usdot_logo_setup_price'] == '20'
    assert 'Full-color' in usdot['config']['description']
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
    assert hats['apparel_unit_price'] == polos['apparel_unit_price'] == '35'
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
    assert hat_quote.json()['subtotal_cents'] == 21000
    assert hat_quote.json()['lines'][0]['digitizing_fee_cents'] == 3500
    assert hat_quote.json()['lines'][0]['quote_only'] is True
    assert hat_quote.json()['review_required'] is True


def test_vehicle_window_tint_is_separate_from_storefront_tint(env):
    app, admin, employee = env
    client = anonymous(app)
    products = catalog_by_name(client)
    tint = products['Fleet Window Tinting']
    cfg = tint['config']
    assert cfg['storefront_categories'] == ['Vehicles', 'Fleet Services']
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
        'location': 'Tampa, FL', 'style': 'stencil', 'font_scale': '1.2',
        'font_sizes': {'company': 64, 'phone': 28, 'number': 80, 'licenses': 26, 'location': 30},
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
    assert saved['font_scale'] == '1.2'
    assert saved['font_sizes'] == {'company': '64', 'phone': '28', 'number': '80', 'licenses': '26', 'location': '30'}
    assert saved['text_color'] == '#ffffff'
    assert 'background_color' not in saved

    lettering = client.post('/api/calculate', json={'items':[{
        'product_id': usdot['id'], 'width': 18, 'height': 12, 'quantity': 1,
        'usdot_design': design | {'identity': 'text'}, 'lamination': 'none'
    }]})
    logo = client.post('/api/calculate', json={'items':[{
        'product_id': usdot['id'], 'width': 18, 'height': 12, 'quantity': 1,
        'usdot_design': design | {
            'identity': 'logo', 'company': '', 'logo_id': 'test-logo',
            'logo_name': 'company-logo.png', 'logo_width': 42
        }, 'lamination': 'none'
    }]})
    assert lettering.status_code == 200, lettering.text
    assert logo.status_code == 200, logo.text
    assert lettering.json()['lines'][0]['usdot_logo_fee_cents'] == 0
    assert logo.json()['lines'][0]['usdot_logo_fee_cents'] == 2000
    assert logo.json()['subtotal_cents'] - lettering.json()['subtotal_cents'] == 2000

    invalid = client.post('/api/calculate', json={'items':[{
        'product_id': usdot['id'], 'width': 18, 'height': 12, 'quantity': 1,
        'usdot_design': design | {'style': 'comic-sans'}, 'lamination': 'none'
    }]})
    assert invalid.status_code == 422

    custom = client.post('/api/calculate', json={'items':[{
        'product_id': usdot['id'], 'width': 37.5, 'height': 18.25, 'quantity': 1,
        'usdot_design': design | {'font_scale': '1.4'}, 'lamination': 'none'
    }]})
    assert custom.status_code == 200, custom.text
    assert custom.json()['lines'][0]['width'] == '37.5'
    assert custom.json()['lines'][0]['height'] == '18.25'

    too_large = client.post('/api/calculate', json={'items':[{
        'product_id': usdot['id'], 'width': 48, 'height': 25, 'quantity': 1,
        'usdot_design': design, 'lamination': 'none'
    }]})
    assert too_large.status_code == 422

    invalid_font_size = client.post('/api/calculate', json={'items':[{
        'product_id': usdot['id'], 'width': 24, 'height': 12, 'quantity': 1,
        'usdot_design': {k: v for k, v in design.items() if k != 'font_sizes'} | {'font_scale': '1.3'},
        'lamination': 'none'
    }]})
    assert invalid_font_size.status_code == 422

    invalid_point_size = client.post('/api/calculate', json={'items':[{
        'product_id': usdot['id'], 'width': 24, 'height': 12, 'quantity': 1,
        'usdot_design': design | {'font_sizes': design['font_sizes'] | {'number': 301}}, 'lamination': 'none'
    }]})
    assert invalid_point_size.status_code == 422


def test_usdot_custom_measurements_and_font_size_ui(env):
    app, admin, employee = env
    client = anonymous(app)
    js = client.get('/static/app.js').text
    shop = client.get('/static/shop.js').text
    assert 'Custom measurements (up to ' in js
    assert "pointSize('usdot_company_points',56)" in js
    assert "pointSize('usdot_number_points',72)" in js
    assert "const paired=(field,size)" in js
    assert "font_sizes:{company:f.elements.usdot_company_points?.value||'56'" in js
    assert 'd.font_sizes||' in shop
    assert 'TRUE-SIZE ARTBOARD' in shop
    assert 'Shapes & clipart' in shop
    assert 'data-studio="art.width"' in shop
    assert 'dimensioned-proof-${width}x${height}in.png' in shop
    assert "c.rect(view.x,view.y,view.width,view.height);c.clip()" in shop
    assert "c.imageSmoothingQuality='high'" in shop
    assert 'ratio>=1?1600' in shop
    assert '4096/Math.max(image.width,image.height)' in shop
    assert "input('usdot_text_color','Letter color'" in js
    assert 'usdot_background_color' not in js
    assert 'background_color' not in shop
    assert 'strokeRect' not in shop[shop.index('async function usdotPrintFile'):shop.index('async function designFiles')]
    assert 'const location=(form.elements.location_line?.value||\'\')' in js
    assert "['phone','licenses','location'].includes(key)&&!value" in js
