from .conftest import anonymous


def by_name(client):
    return {p['name']: p for p in client.get('/api/catalog').json()['products']}


def test_partial_vehicle_wraps_have_visual_coverage_options(env):
    app, admin, employee = env
    client = anonymous(app)
    products = by_name(client)
    partial = products['Partial Vehicle Wraps']
    cfg = partial['config']

    assert set(cfg['storefront_categories']) == {'Vehicles', 'Fleet Services'}
    assert cfg['quantity_only'] is True
    assert cfg['supports_installation'] is True
    assert [x['id'] for x in cfg['coverage_options']] == [
        'spot', 'doors', 'hood', 'roof', 'half', 'three_quarter', 'full'
    ]
    assert [x['id'] for x in cfg['vehicle_type_options']] == [
        'car', 'suv', 'pickup', 'cargo_van'
    ]

    spot = client.post('/api/calculate', json={'items':[{
        'product_id': partial['id'], 'width': 12, 'height': 12, 'quantity': 1,
        'coverage_option': 'spot', 'vehicle_type': 'car',
        'installation_requested': False, 'lamination': 'cast_gloss'
    }]})
    full = client.post('/api/calculate', json={'items':[{
        'product_id': partial['id'], 'width': 12, 'height': 12, 'quantity': 1,
        'coverage_option': 'full', 'vehicle_type': 'car',
        'installation_requested': False, 'lamination': 'cast_gloss'
    }]})
    installed = client.post('/api/calculate', json={'items':[{
        'product_id': partial['id'], 'width': 12, 'height': 12, 'quantity': 1,
        'coverage_option': 'half', 'vehicle_type': 'suv',
        'installation_requested': True, 'lamination': 'cast_gloss'
    }]})
    assert spot.status_code == 200, spot.text
    assert full.status_code == 200, full.text
    assert installed.status_code == 200, installed.text
    assert spot.json()['subtotal_cents'] < full.json()['subtotal_cents']
    assert installed.json()['review_required'] is True
    assert installed.json()['lines'][0]['coverage_label'] == 'Half wrap'
    assert installed.json()['lines'][0]['vehicle_type_label'] == 'SUV / crossover'


def test_trailer_food_truck_wraps_category_and_coverage(env):
    app, admin, employee = env
    client = anonymous(app)
    products = by_name(client)
    trailer = products['Trailer / Food Truck Wraps']
    cfg = trailer['config']

    assert set(cfg['storefront_categories']) == {'Trailers / Food Trucks', 'Fleet Services'}
    assert [x['id'] for x in cfg['coverage_options']] == [
        'lettering', 'partial', 'sides', 'sides_rear', 'three_quarter', 'full'
    ]
    assert [x['id'] for x in cfg['vehicle_type_options']] == [
        'small_trailer', 'large_trailer', 'food_truck', 'box_truck'
    ]
    assert cfg['quantity_only'] is True
    assert cfg['instant'] is False

    lettering = client.post('/api/calculate', json={'items':[{
        'product_id': trailer['id'], 'width': 12, 'height': 12, 'quantity': 1,
        'coverage_option': 'lettering', 'vehicle_type': 'small_trailer',
        'installation_requested': False, 'lamination': 'cast_gloss'
    }]})
    food_truck = client.post('/api/calculate', json={'items':[{
        'product_id': trailer['id'], 'width': 12, 'height': 12, 'quantity': 1,
        'coverage_option': 'full', 'vehicle_type': 'food_truck',
        'installation_requested': True, 'lamination': 'cast_gloss'
    }]})
    assert lettering.status_code == 200, lettering.text
    assert food_truck.status_code == 200, food_truck.text
    assert lettering.json()['subtotal_cents'] < food_truck.json()['subtotal_cents']
    assert food_truck.json()['review_required'] is True


def test_wrap_coverage_storefront_ui_is_present(env):
    app, admin, employee = env
    client = anonymous(app)
    js = client.get('/static/app.js')
    assert js.status_code == 200
    text = js.text
    assert "Trailers / Food Trucks" in text
    assert "Choose wrap coverage" in text
    assert "coverage-card" in text
    assert "key==='partial vehicle wraps'" in text
    assert "return 'Trailer / Food Truck Wraps'" in text
    assert "storefrontProductsFor" in text
    assert "hasCoverageWrap" in text
    assert 'input[name="coverage_option"]:checked' in text
    assert "Approximate dimensions" in text
    assert "Trailer / truck type" in text
    assert "Vehicle year" in text
    assert "Tint package" in text
    assert "vehicleType==='car'?'sedan'" in text
    assert "vehicleType==='cargo_van'?'van'" in text
    assert "find(o=>o.id==='cargo_van')" in text
    assert 'updateCoverageVisuals();' in text
    assert "option.value==='hood'||option.value==='roof'" in text
    assert "largeDecals?'Large decals'" in text
    assert "Large individual graphics across the van side panels." in text
    assert "multiple" in text

    css = client.get('/static/styles.css').text
    assert 'sedan-coverage-blue.webp' in css
    assert 'van-coverage-blue.webp' in css
