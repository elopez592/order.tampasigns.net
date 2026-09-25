import json

from app.db import initialize, now, transaction


def test_legacy_decal_minimum_migrates_once_without_overwriting_owner_edits(tmp_path):
    database = tmp_path / 'legacy.sqlite'
    initialize(database)
    legacy = {'minimum_price': '50', 'setup_price': '10', 'sell_per_sqft': '18'}
    with transaction(database, True) as conn:
        conn.execute("INSERT INTO workflows(id,name,steps,version) VALUES(1,'Test','[]',1)")
        for product_id, name in ((1, 'Decals'), (2, 'Magnets')):
            conn.execute('INSERT INTO products(id,name,category,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?)',
                         (product_id, name, 'Stickers', 1, json.dumps(legacy), now()))
        conn.execute('DELETE FROM schema_version WHERE version=8')

    initialize(database)
    with transaction(database) as conn:
        decals, magnets = conn.execute('SELECT config,version FROM products ORDER BY id').fetchall()
        assert json.loads(decals['config'])['minimum_price'] == '0'
        assert decals['version'] == 2
        assert json.loads(magnets['config'])['minimum_price'] == '50'
        assert magnets['version'] == 1

    with transaction(database, True) as conn:
        updated = json.loads(conn.execute('SELECT config FROM products WHERE id=1').fetchone()[0])
        updated['minimum_price'] = '50'
        conn.execute('UPDATE products SET config=?,version=version+1 WHERE id=1', (json.dumps(updated),))
    initialize(database)
    with transaction(database) as conn:
        decal = conn.execute('SELECT config,version FROM products WHERE id=1').fetchone()
        assert json.loads(decal['config'])['minimum_price'] == '50'
        assert decal['version'] == 3
