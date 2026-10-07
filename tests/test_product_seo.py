from .conftest import anonymous


def test_product_page_has_indexable_metadata_and_fallback(env):
    app, _, _ = env
    client = anonymous(app)
    response = client.get('/products/usdot-decals')
    assert response.status_code == 200
    assert '<title>USDOT Decals | Tampa Signs and Stickers</title>' in response.text
    assert '<link rel="canonical" href="http://testserver/products/usdot-decals">' in response.text
    assert '<meta name="robots" content="index,follow,max-image-preview:large">' in response.text
    assert '"@type": "Service"' in response.text
    assert '"@type": "BreadcrumbList"' in response.text
    assert '<h1>USDOT Decals</h1>' in response.text
    assert 'Related custom products' in response.text
    assert '/static/products/client-jobs/usdot-decals.webp' in response.text


def test_unknown_product_page_is_not_served(env):
    app, _, _ = env
    assert anonymous(app).get('/products/not-a-real-product').status_code == 404


def test_sitemap_and_robots_expose_public_product_pages(env):
    app, _, _ = env
    client = anonymous(app)
    sitemap = client.get('/sitemap.xml')
    assert sitemap.status_code == 200
    assert sitemap.headers['content-type'].startswith('application/xml')
    assert '<loc>http://testserver/products/usdot-decals</loc>' in sitemap.text
    assert '<loc>http://testserver/products/vehicle-wraps</loc>' in sitemap.text
    robots = client.get('/robots.txt')
    assert 'Sitemap: http://testserver/sitemap.xml' in robots.text
    assert 'Disallow: /staff' in robots.text
    assert client.get('/staff').headers['x-robots-tag'] == 'noindex, nofollow'


def test_all_products_page_has_its_own_canonical_metadata(env):
    app, _, _ = env
    response = anonymous(app).get('/products')
    assert response.status_code == 200
    assert '<link rel="canonical" href="http://testserver/products">' in response.text
    assert '<title>Custom Signs, Wraps, Decals and Apparel | Tampa Signs</title>' in response.text
    assert '<h1>Shop Custom Signs, Wraps, Stickers &amp; Apparel</h1>' in response.text
    assert '"@type": "ItemList"' in response.text
    assert '/products/usdot-decals' in response.text


def test_homepage_has_server_rendered_h1_and_catalog_links(env):
    app, _, _ = env
    response = anonymous(app).get('/')
    assert response.status_code == 200
    assert '<h1>Custom Signs, Vehicle Wraps, Stickers &amp; Printing in Tampa</h1>' in response.text
    assert '/products/die-cut-stickers' in response.text


def test_sitemap_deduplicates_public_slugs(env):
    app, _, _ = env
    response = anonymous(app).get('/sitemap.xml')
    assert response.status_code == 200
    assert response.text.count('<loc>http://testserver/products/vehicle-wraps</loc>') == 1
