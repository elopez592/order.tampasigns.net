"""Check product photo gallery assets and external work image policy."""
from .conftest import anonymous


def test_product_gallery_is_available_and_built_into_product_pages(env):
    app, _, _ = env
    client = anonymous(app)
    js = client.get('/static/app.js').text
    gallery = client.get('/static/product-photo-gallery.js').text
    css = client.get('/static/styles.css').text

    assert "setupProductPhotoGallery(app);" in js
    assert "productGalleryMarkup(productSlug(product)" in js
    assert "const galleryImages=identity.brand_custom?[]:realWorkPhotosFor(productSlug(product));" in js
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


def test_product_gallery_source_is_company_work_only(env):
    app, _, _ = env
    client = anonymous(app)
    gallery = client.get('/static/product-photo-gallery.js').text
    assert '/static/projects/real-work/directional-sign.webp' in gallery
    assert '/static/products/client-jobs/acm-signs.webp' in gallery
    assert 'https://lh3.googleusercontent.com/' in gallery
    assert 'Tampa Signs and Stickers jobs, not stock images' in gallery
