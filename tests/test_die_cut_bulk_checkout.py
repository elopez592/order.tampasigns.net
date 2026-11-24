import json
import uuid

from app.db import transaction
from app.seed import LEGACY_DIE_CUT_QUANTITY_PRICE_TABLE, bootstrap
from tests.conftest import anonymous
from tests.test_checkout_privacy import live_setup, open_session


def test_old_10000_sticker_quote_requires_repricing(live_setup):
    app, _, _ = live_setup
    db = app.state.database
    client = anonymous(app)
    with transaction(db, True) as conn:
        product = conn.execute("SELECT id,config FROM products WHERE name='Die-cut stickers'").fetchone()
        config = json.loads(product['config'])
        config.update(quantity_price_table=LEGACY_DIE_CUT_QUANTITY_PRICE_TABLE,
                      price_table_base_width='3', price_table_base_height='3')
        conn.execute('UPDATE products SET config=? WHERE id=?', (json.dumps(config), product['id']))
        conn.execute("UPDATE settings SET data=json_remove(data,'$.die_cut_benchmark_product_id') WHERE id=1")

    items = [{'product_id': product['id'], 'width': 3, 'height': 3, 'quantity': 10000, 'lamination': 'none'}]
    old = client.post('/api/calculate', json={'items': items}).json()
    assert old['subtotal_cents'] == 122500
    body = {'items': items, 'fingerprint': old['fingerprint'], 'confirm': True,
            'request_id': str(uuid.uuid4()), 'fulfillment': 'pickup',
            'customer_name': 'Bulk sticker test', 'customer_email': 'stickers@example.test'}

    bootstrap(db, primary_storefront=True)
    for route in ('/api/requests', '/api/orders'):
        stale = client.post(route, json=body)
        assert stale.status_code == 409, stale.text
        assert 'Pricing has changed' in stale.json()['detail']

    fresh = client.post('/api/calculate', json={'items': items}).json()
    assert fresh['subtotal_cents'] >= 225900
    body['fingerprint'] = fresh['fingerprint']
    order = client.post('/api/orders', json=body)
    assert order.status_code == 200, order.text
    client.headers['X-CSRF-Token'] = order.json()['csrf']
    payment = open_session(app, client, order.json()['job_id'])
    assert payment['merchandise_cents'] == fresh['subtotal_cents']
