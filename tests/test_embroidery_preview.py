from .conftest import anonymous


def test_embroidery_garments_accept_preview_in_reviewed_quote(env):
    app, _, _ = env
    client = anonymous(app)
    catalog = {p['name']: p for p in client.get('/api/catalog').json()['products']}
    scenarios = [
        ('Embroidered T-shirts', 'left_chest', 'M'),
        ('Embroidered polos', 'right_chest', 'M'),
        ('Embroidered hoodies', 'left_chest', 'L'),
        ('Embroidered jackets', 'right_chest', 'L'),
        ('Embroidered hats', 'front', 'Adjustable'),
    ]
    for name, placement, size in scenarios:
        p = catalog[name]
        assert p['config']['quote_only']
        item = {
            'product_id': p['id'], 'width': 12, 'height': 12, 'quantity': 2,
            'shirt_color': 'Navy', 'size_quantities': {size: 2},
            'print_locations': [placement],
            'embroidery_preview': {
                'width': 3, 'height': 2, 'offset_x': 0.2, 'offset_y': -0.1,
                'thread_colors': ['#ffffff', '#2453a0'],
            },
        }
        response = client.post('/api/calculate', json={'items': [item]})
        assert response.status_code == 200, (name, response.text)
        line = response.json()['lines'][0]
        assert line['embroidery_preview']['thread_colors'] == ['#ffffff', '#2453a0']
        assert 'embroidery 3 x 2 in' in line['description']
        assert line['quote_only'] and line['digitizing_fee_cents'] == 3500


def test_embroidery_preview_rejects_size_position_and_palette_outside_placement(env):
    app, _, _ = env
    client = anonymous(app)
    hat = next(p for p in client.get('/api/catalog').json()['products'] if p['name'] == 'Embroidered hats')
    item = {
        'product_id': hat['id'], 'width': 12, 'height': 12, 'quantity': 1,
        'shirt_color': 'Black', 'size_quantities': {'Adjustable': 1},
        'print_locations': ['front'],
        'embroidery_preview': {'width': 3, 'height': 2, 'offset_x': 0, 'offset_y': 0,
                               'thread_colors': ['#ffffff']},
    }
    for change in ({'width': 4.5}, {'height': 3}, {'offset_x': 1},
                   {'thread_colors': ['#ffffff; background: url(https://elsewhere.test)']}):
        bad = dict(item, embroidery_preview={**item['embroidery_preview'], **change})
        response = client.post('/api/calculate', json={'items': [bad]})
        assert response.status_code == 422, (change, response.text)
