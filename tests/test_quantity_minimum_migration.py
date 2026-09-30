import json

from app.db import initialize, now, transaction
from app.pricing import validate_config


def test_existing_product_quantities_migrate_once_and_future_edits_stay_at_one(tmp_path):
    database = tmp_path / 'legacy.sqlite'
    initialize(database)
    with transaction(database, True) as conn:
        conn.execute("INSERT INTO workflows(id,name,steps,version) VALUES(1,'Test','[]',1)")
        for product_id, name, minimum in ((1, 'Die-cut stickers', '50'),
                                          (2, 'Custom labels', '25'), (3, 'Banners', '1')):
            conn.execute('INSERT INTO products(id,name,category,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?)',
                         (product_id, name, 'Stickers', 1,
                          json.dumps({'min_quantity': minimum, 'max_quantity': '1000'}), now()))
        conn.execute('DELETE FROM schema_version WHERE version>=10')

    initialize(database)
    with transaction(database) as conn:
        products = conn.execute('SELECT config,version FROM products ORDER BY id').fetchall()
        assert [json.loads(p['config'])['min_quantity'] for p in products] == ['1', '1', '1']
        assert [p['version'] for p in products] == [2, 2, 1]

    initialize(database)
    with transaction(database) as conn:
        assert [p['version'] for p in conn.execute('SELECT version FROM products ORDER BY id')] == [2, 2, 1]
    assert validate_config({'min_quantity': '50'})['min_quantity'] == '1'
