import json

from app.db import transaction
from app.seed import (
    LEGACY_DIE_CUT_QUANTITY_PRICE_TABLE,
    _upgrade_legacy_die_cut_pricing,
    bootstrap,
)


def test_migrates_only_untouched_legacy_die_cut_pricing():
    original = {
        'unit': 'piece', 'quantity_price_table': list(LEGACY_DIE_CUT_QUANTITY_PRICE_TABLE),
        'sell_per_sqft': '24', 'setup_price': '0', 'labor_minutes_per_unit': '0',
        'minimum_price': '0', 'price_table_size_weight': '.45',
    }
    custom = dict(original, setup_price='12')
    assert not _upgrade_legacy_die_cut_pricing(custom)
    assert custom['quantity_price_table'] == LEGACY_DIE_CUT_QUANTITY_PRICE_TABLE

    assert _upgrade_legacy_die_cut_pricing(original)
    assert original['quantity_price_table'] == []
    assert original['setup_price'] == '30'
    assert original['minimum_price'] == '50'
    assert not _upgrade_legacy_die_cut_pricing(original)


def test_bootstrap_retains_new_die_cut_rates_on_restart(env):
    app, admin, employee = env
    with transaction(app.state.database) as conn:
        before = conn.execute("SELECT config, version FROM products WHERE name='Die-cut stickers'").fetchone()
        cfg = json.loads(before['config'])
        assert cfg['quantity_price_table'] == []
    bootstrap(app.state.database)
    with transaction(app.state.database) as conn:
        after = conn.execute("SELECT config, version FROM products WHERE name='Die-cut stickers'").fetchone()
        assert json.loads(after['config'])['quantity_price_table'] == []
        assert json.loads(after['config'])['setup_price'] == '30'
        assert json.loads(after['config'])['labor_minutes_per_unit'] == '0.02625'
        assert after['version'] == before['version']


def test_sticker_mule_floor_on_retail_wholesale_and_checkout(env):
    from app.checkout import eligible_quote
    from app.pricing import calculate

    app, admin, _employee = env
    account = admin.post('/api/admin/wholesale', json={
        'name': 'Sticker retailer', 'username': 'stickerretailer',
        'email': 'retailer@example.test', 'discount_percent': 80,
        'product_discounts': {},
    })
    assert account.status_code == 200, account.text
    with transaction(app.state.database, True) as conn:
        conn.execute("UPDATE settings SET data=json_set(data,'$.rates_live',json('true')) WHERE id=1")
        product = conn.execute("SELECT id,config FROM products WHERE name='Die-cut stickers'").fetchone()
        client_id = conn.execute("SELECT id FROM wholesale_clients WHERE username='stickerretailer'").fetchone()[0]
        # Simulate an existing catalog with custom rates below the competitor.
        cfg = json.loads(product['config'])
        cfg.update(quantity_price_table=[{'quantity': 1, 'total': '0.01'}],
                   cost_per_sqft='0', setup_cost='0', labor_minutes_per_unit='0')
        conn.execute('UPDATE products SET config=? WHERE id=?', (json.dumps(cfg), product['id']))
        for w, h, qty, expected in [(2, 2, 50, 6300), (2, 2, 100, 7700), (3, 3, 50, 7600),
                                    (1.4, 1.7, 700, 15500), (1, 9, 100, 9900)]:
            items = [{'product_id': product['id'], 'width': w, 'height': h, 'quantity': qty}]
            assert calculate(conn, items)['subtotal_cents'] == expected
            assert eligible_quote(conn, items, wholesale_client_id=client_id)['subtotal_cents'] == expected

        cfg.update(quantity_price_table=[{'quantity': 100, 'total': '200'}])
        conn.execute('UPDATE products SET config=? WHERE id=?', (json.dumps(cfg), product['id']))
        items = [{'product_id': product['id'], 'width': 3, 'height': 3, 'quantity': 100}]
        assert calculate(conn, items)['subtotal_cents'] == 20000
        assert eligible_quote(conn, items, wholesale_client_id=client_id)['subtotal_cents'] == 9900


def test_sticker_mule_custom_runs_round_up_to_verified_benchmarks():
    from decimal import Decimal
    from app.pricing import die_cut_benchmark_cents

    assert die_cut_benchmark_cents(Decimal('2.01'), 2, 101) == die_cut_benchmark_cents(Decimal('2.25'), 2, 110)
    assert die_cut_benchmark_cents(2, 2, 9) == 0
