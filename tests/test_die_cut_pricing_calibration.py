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
