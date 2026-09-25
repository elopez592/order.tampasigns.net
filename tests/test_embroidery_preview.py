import json

from app.db import transaction, now
from app.storefront import upgrade_catalog
from .conftest import anonymous


def test_embroidery_garments_accept_preview_in_reviewed_quote(env):
    app, _, _ = env
    client = anonymous(app)
    catalog = {p['name']: p for p in client.get('/api/catalog').json()['products']}
    scenarios = [
        ('Embroidered polos', 'right_chest', 'M'),
        ('Embroidered hoodies', 'left_chest', 'L'),
        ('Embroidered hats', 'front', 'Adjustable'),
    ]
    assert {p['config']['apparel_kind'] for p in catalog.values()
            if (p['config'].get('apparel_kind') or '').startswith('embroidered_')} == {
        'embroidered_polo', 'embroidered_hoodie', 'embroidered_hat'}
    assert catalog['Custom T-shirts']['config']['apparel_kind'] == 'custom_shirt'
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


def test_existing_embroidery_shirts_and_jackets_are_retired_without_deleting_records(env):
    app, _, _ = env
    client = anonymous(app)
    retired = []
    with transaction(app.state.database, True) as conn:
        base = conn.execute("SELECT * FROM products WHERE name='Embroidered polos'").fetchone()
        for name, kind in [('Embroidered T-shirts', 'embroidered_shirt'),
                           ('Embroidered jackets', 'embroidered_jacket')]:
            cfg = json.loads(base['config'])
            cfg['apparel_kind'] = kind
            pid = conn.execute(
                'INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,1,1,?,?,?)',
                (name, 'Apparel', base['workflow_id'], json.dumps(cfg), now())).lastrowid
            retired.append(pid)
    upgrade_catalog(app.state.database)
    upgrade_catalog(app.state.database)
    catalog = client.get('/api/catalog').json()['products']
    assert not set(retired) & {p['id'] for p in catalog}
    with transaction(app.state.database) as conn:
        for pid in retired:
            row = conn.execute('SELECT active,public FROM products WHERE id=?', (pid,)).fetchone()
            assert row is not None and not row['active'] and not row['public']
            response = client.post('/api/calculate', json={'items': [
                {'product_id': pid, 'width': 12, 'height': 12, 'quantity': 1}]})
            assert response.status_code == 422
