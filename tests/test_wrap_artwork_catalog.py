from .conftest import anonymous


def test_public_catalog_exposes_wrap_artwork_classification(env):
    app, admin, employee = env
    products = {p['name']: p for p in anonymous(app).get('/api/catalog').json()['products']}
    for name in ('Partial Vehicle Wraps', 'Trailer / Food Truck Wraps'):
        matches = [p for p in products.values() if p['name'].lower() == name.lower()]
        assert len(matches) == 1, list(products)
        assert matches[0]['config']['is_wrap'] is True
        assert matches[0]['config']['artwork_upload_disabled'] is False
    assert products['Window Graphics']['config']['is_wrap'] is False
    assert products['Window Graphics']['config']['supports_multiple_dimensions'] is True
    assert all(isinstance(p['config']['is_wrap'], bool) for p in products.values())
