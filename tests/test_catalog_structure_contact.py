from .conftest import anonymous


def test_orders_contact_page_is_routable_and_linked(env):
    app, admin, employee = env
    client = anonymous(app)

    assert client.get('/contact').status_code == 200
    js = client.get('/static/app.js').text
    assert '<a href="/contact">Contact</a>' in js
    assert "path==='/contact'||path==='/contact.html'" in js
    assert '9236 Lazy Ln' in js
    assert 'Need help with an order or custom project?' in js


def test_catalog_uses_broad_categories_and_reassigned_acrylic_photos(env):
    app, admin, employee = env
    client = anonymous(app)
    js = client.get('/static/app.js').text
    css = client.get('/static/styles.css').text

    assert "const storefrontCategories=['Storefront','Vehicles','Fleet Services','Construction & Site Signs','Events','Stickers','Signs','Apparel']" in js
    assert "Trailers / Food Trucks" not in js
    assert "return 'Vehicle Window Tinting'" in js
    assert "return 'Storefront Window Tinting'" in js
    assert "return 'Acrylic Signs'" in js
    assert "return 'Illuminated Sign Faces'" in js
    assert '.product-photo-acrylic-signs .product-example-photo' in css
    assert "client-jobs/acm-signs.webp" in css
    assert '.product-photo-illuminated-sign-faces .product-example-photo' in css
    assert "client-jobs/acrylic-sign-face-replacement.webp" in css
