"""Check product photo gallery assets, company-owned work, and branding compatibility."""
import json

from .conftest import anonymous
from app.db import settings, transaction


def test_product_gallery_is_available_and_built_into_product_pages(env):
    app, _, _ = env
    client = anonymous(app)
    js = client.get('/static/app.js').text
    gallery = client.get('/static/product-photo-gallery.js').text
    css = client.get('/static/styles.css').text

    assert "setupProductPhotoGallery(app);" in js
    assert "productGalleryMarkup(productSlug(product)" in js
    assert "const galleryImages=state.catalog.is_primary_storefront?realWorkPhotosFor(productSlug(product)):[];" in js
    assert "const galleryImages=identity.brand_custom?" not in js
    assert "'aluminum-composite-signs':" in gallery or '"aluminum-composite-signs":' in gallery
    assert "'vehicle-wraps':" in gallery or '"vehicle-wraps":' in gallery
    assert "data-gallery-previous" in gallery
    assert "data-gallery-next" in gallery
    assert "data-gallery-thumb" in gallery
    assert "aria-pressed" in gallery
    assert "product-gallery-preview" in css
    assert "product-gallery-stage" in css

    response = client.get('/products/aluminum-composite-signs')
    assert response.status_code == 200
    assert "https://lh3.googleusercontent.com" in response.headers['content-security-policy']


def test_custom_branding_does_not_hide_primary_storefront_gallery(env):
    app, _, _ = env
    with transaction(app.state.database, True) as conn:
        shop = settings(conn)
        shop['brand_custom'] = True
        conn.execute('UPDATE settings SET data=? WHERE id=1', (json.dumps(shop),))
    client = anonymous(app)
    catalog = client.get('/api/catalog').json()
    assert catalog['shop']['brand_custom'] is True
    assert catalog['is_primary_storefront'] is True
    assert "is_primary_storefront?realWorkPhotosFor" in client.get('/static/app.js').text


def test_product_gallery_source_is_company_work_only(env):
    app, _, _ = env
    client = anonymous(app)
    gallery = client.get('/static/product-photo-gallery.js').text
    assert '/static/projects/real-work/directional-sign.webp' in gallery
    assert '/static/products/client-jobs/acm-signs.webp' in gallery
    assert 'https://lh3.googleusercontent.com/' in gallery
    assert 'Tampa Signs and Stickers jobs, not stock images' in gallery
