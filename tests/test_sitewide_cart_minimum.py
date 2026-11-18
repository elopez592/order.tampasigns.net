"""Sitewide cart minimum vs specialty-signage line minimums."""
from .conftest import anonymous
from app.pricing import normalize_product_minimum, cart_minimum_only_product


def test_standard_products_have_no_line_minimum():
    for name, category in [
        ('Transfer stickers', 'Stickers'),
        ('Die-cut stickers', 'Stickers'),
        ('Labels', 'Labels'),
        ('Magnets', 'Vehicles'),
        ('Banners', 'Signs'),
        ('Window Graphics', 'Windows'),
        ('Yard signs', 'Signs'),
        ('Foam boards', 'Storefront'),
    ]:
        assert cart_minimum_only_product(name, category)
        assert normalize_product_minimum(name, category, {'minimum_price': '60'})['minimum_price'] == '0'


def test_specialty_signage_and_fixed_services_keep_their_floors():
    for name, category in [
        ('High-Density Board Signs', 'Construction & Site Signs'),
        ('Aluminum Composite Signs', 'Construction & Site Signs'),
        ('Acrylic Signs', 'Storefront'),
        ('Illuminated Sign Faces', 'Signs'),
        ('Fleet Window Tinting', 'Vehicles'),
    ]:
        assert not cart_minimum_only_product(name, category)
        assert normalize_product_minimum(name, category, {'minimum_price': '240'})['minimum_price'] == '240'


def test_transfer_sticker_price_is_not_cart_minimum(env):
    app, admin, employee = env
    client = anonymous(app)
    catalog = client.get('/api/catalog').json()
    transfer = next(p for p in catalog['products'] if p['name'] == 'Transfer stickers')
    assert transfer['config']['minimum_price'] == '0'

    def quote(size, qty):
        response = client.post('/api/calculate', json={'items': [{
            'product_id': transfer['id'], 'width': size, 'height': size,
            'quantity': qty, 'lamination': 'none'
        }]})
        assert response.status_code == 200, response.text
        return response.json()

    single = quote(3, 1)
    fifty = quote(3, 50)
    hundred = quote(3, 100)
    large = quote(6, 50)

    assert single['subtotal_cents'] < 3500
    assert single['minimum_order_cents'] == 3500
    assert not single['meets_minimum_order']
    assert fifty['subtotal_cents'] == 6000
    assert hundred['subtotal_cents'] == 7300
    assert large['subtotal_cents'] > fifty['subtotal_cents']
    assert large['meets_minimum_order']


def test_standard_products_share_one_cart_minimum(env):
    app, admin, employee = env
    client = anonymous(app)
    catalog = client.get('/api/catalog').json()
    transfer = next(p for p in catalog['products'] if p['name'] == 'Transfer stickers')
    decals = next(p for p in catalog['products'] if p['name'] == 'Decals')
    response = client.post('/api/calculate', json={'items': [
        {'product_id': transfer['id'], 'width': 3, 'height': 3, 'quantity': 1},
        {'product_id': decals['id'], 'width': 6, 'height': 6, 'quantity': 1},
    ]})
    assert response.status_code == 200, response.text
    quote = response.json()
    assert quote['minimum_order_cents'] == 3500
    assert quote['subtotal_cents'] < 3500
    assert not quote['meets_minimum_order']
