from pathlib import Path


def test_rigid_sign_product_images_are_real_assets_and_wired_to_product_slugs():
    root = Path(__file__).parents[1]
    aluminum = root / 'app/static/products/aluminum-composite-signs.webp'
    hdu = root / 'app/static/products/high-density-board-signs.webp'
    css = (root / 'app/static/styles.css').read_text()

    assert aluminum.is_file() and aluminum.stat().st_size > 5000
    assert hdu.is_file() and hdu.stat().st_size > 5000
    assert "/static/products/aluminum-composite-signs.webp" in css
    assert "/static/products/high-density-board-signs.webp" in css
