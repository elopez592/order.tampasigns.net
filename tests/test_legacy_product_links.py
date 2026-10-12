"""Regression tests for public links to renamed catalog products."""

from .conftest import anonymous


def test_legacy_acm_links_redirect_to_the_current_product(env):
    app, _, _ = env
    client = anonymous(app)
    current = client.get('/products/aluminum-composite-signs')
    assert current.status_code == 200, current.text
    assert 'Aluminum Composite Signs' in current.text

    for old_slug in ('acm-signs', 'acm-sign-single-sided', 'construction-signs'):
        response = client.get('/products/' + old_slug, follow_redirects=False)
        assert response.status_code == 301, response.text
        assert response.headers['location'] == '/products/aluminum-composite-signs'
        final = client.get('/products/' + old_slug)
        assert final.status_code == 200
        assert 'Aluminum Composite Signs' in final.text

    with_query = client.get('/products/acm-signs?utm_source=customer', follow_redirects=False)
    assert with_query.headers['location'] == '/products/aluminum-composite-signs?utm_source=customer'


def test_retired_acrylic_face_link_uses_current_product(env):
    app, _, _ = env
    client = anonymous(app)
    response = client.get('/products/acrylic-sign-face-replacement', follow_redirects=False)
    assert response.status_code == 301
    assert response.headers['location'] == '/products/illuminated-sign-faces'


def test_unknown_public_product_returns_readable_html_not_api_json(env):
    app, _, _ = env
    client = anonymous(app)
    response = client.get('/products/this-product-does-not-exist')
    assert response.status_code == 404
    assert response.headers['content-type'].startswith('text/html')
    assert 'Browse current products' in response.text
    assert '{"detail":"Product not found."}' not in response.text
