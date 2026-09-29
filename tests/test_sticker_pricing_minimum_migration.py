import json

import pytest

from app.db import initialize, now, transaction


@pytest.mark.parametrize('legacy_floor', ['50', '60'])
def test_existing_sticker_floor_and_order_minimum_migrate_once(tmp_path, legacy_floor):
    database = tmp_path / 'legacy.sqlite'
    initialize(database)
    with transaction(database, True) as conn:
        conn.execute('INSERT INTO settings(id,data) VALUES(1,?)',
                     (json.dumps({'minimum_order_price': '50'}),))
        conn.execute("INSERT INTO workflows(id,name,steps,version) VALUES(1,'Test','[]',1)")
        for product_id, name in ((1, 'Die-cut stickers'), (2, 'Magnets')):
            cfg = {'minimum_price': legacy_floor, 'quantity_price_table': [
                {'quantity': 50, 'total': '60'}]}
            conn.execute('INSERT INTO products(id,name,category,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?)',
                         (product_id, name, 'Stickers', 1, json.dumps(cfg), now()))
        conn.execute('DELETE FROM schema_version WHERE version=9')

    initialize(database)
    with transaction(database) as conn:
        shop = json.loads(conn.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
        stickers, magnets = conn.execute('SELECT config,version FROM products ORDER BY id').fetchall()
        assert shop['minimum_order_price'] == '35'
        assert json.loads(stickers['config'])['minimum_price'] == '0'
        assert stickers['version'] == 2
        assert json.loads(magnets['config'])['minimum_price'] == legacy_floor
        assert magnets['version'] == 1

    with transaction(database, True) as conn:
        shop['minimum_order_price'] = '42'
        conn.execute('UPDATE settings SET data=? WHERE id=1', (json.dumps(shop),))
        updated = json.loads(stickers['config'])
        updated['minimum_price'] = '20'
        conn.execute('UPDATE products SET config=?,version=version+1 WHERE id=1', (json.dumps(updated),))
    initialize(database)
    with transaction(database) as conn:
        assert json.loads(conn.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])['minimum_order_price'] == '42'
        sticker = conn.execute('SELECT config,version FROM products WHERE id=1').fetchone()
        assert json.loads(sticker['config'])['minimum_price'] == '20'
        assert sticker['version'] == 3
