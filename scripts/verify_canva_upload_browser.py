"""Check artwork choices everywhere; submit only to an isolated local test app."""
import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image
from playwright.sync_api import sync_playwright, expect

live = '--live' in sys.argv
root = os.getenv('VERIFY_BASE_URL', 'http://localhost:8000').rstrip('/')
if not live and root != 'http://localhost:8000':
    raise RuntimeError('Order submission is permitted only on the isolated local app.')
image = io.BytesIO()
Image.new('RGB', (24, 24), 'white').save(image, format='PNG')
pdf_bytes = b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 72 72]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n'
fixture_dir = Path(tempfile.mkdtemp(prefix='canva-upload-fixtures-'))
errors, blocked, checked, added = [], [], [], []
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={'width':1365, 'height':1000})
    page.on('pageerror', lambda error: errors.append(str(error)))
    if live:
        def read_only(route):
            req = route.request
            if req.method not in ('GET', 'HEAD', 'OPTIONS') and urlparse(req.url).path != '/api/calculate':
                blocked.append(req.method + ' ' + req.url)
                route.abort()
            else:
                route.continue_()
        page.route('**/api/**', read_only)
    try:
        page.goto(root + '/products')
        expect(page.locator('.product-catalog-card').first).to_be_visible()
        entries = page.locator('.product-catalog-card').evaluate_all("cards => cards.map(card => ({id:Number(card.querySelector('[data-action=browse-product]').dataset.id),name:card.querySelector('h2').textContent,path:card.querySelector('h2 a').getAttribute('href')}))")
        catalog = page.request.get(root + '/api/catalog').json()
        configs = {p['id']: p['config'] for p in catalog['products']}
        ordinary = []
        for entry in entries:
            cfg = configs[entry['id']]
            page.goto(root + entry['path'])
            expect(page.locator('h1.product-page-title')).to_be_visible()
            canva = page.locator('[data-action="product-canva"]')
            upload = page.locator('[data-action="window-upload"]')
            if cfg.get('artwork_upload_disabled') or cfg.get('contour_customizer'):
                expect(canva).to_have_count(0)
                expect(upload).to_have_count(0)
                checked.append({'product':entry['name'], 'artwork':'excluded/preserved'})
                continue
            if cfg.get('is_wrap') or cfg.get('supports_multiple_dimensions'):
                expect(canva).to_have_count(0)
                expect(upload).to_have_text('Upload Design')
                expect(page.locator('.public-grid [data-action="design-quote"]')).to_have_count(1)
                checked.append({'product':entry['name'], 'artwork':'direct options preserved'})
                continue
            ordinary.append(entry)
            expect(canva).to_have_count(1)
            expect(upload).to_have_text('Upload File')
            upload.click()
            expect(page.locator('#modal-content h2')).to_have_text('Upload File')
            expect(page.locator('#modal-content')).not_to_contain_text('Left Window')
            expect(page.locator('#modal-content')).not_to_contain_text('Driver Side')
            front = fixture_dir / f'product-{entry["id"]}-Front.pdf'
            back = fixture_dir / f'product-{entry["id"]}-Back.png'
            front.write_bytes(pdf_bytes)
            back.write_bytes(image.getvalue())
            page.locator('#window-upload-input').set_input_files([front, back])
            expect(page.locator('#window-upload-files [data-action="window-upload-remove"]')).to_have_count(2)
            if len(ordinary) == 1:
                page.locator('#window-upload-input').set_input_files(front)
                expect(page.locator('#window-upload-files [data-action="window-upload-remove"]')).to_have_count(2)
            page.get_by_role('button', name='Done', exact=True).click()
            expect(page.locator('[data-window-upload-summary]')).to_have_text('2 files attached')
            page.reload()
            expect(page.locator('[data-window-upload-summary]')).to_have_text('2 files attached')
            page.set_viewport_size({'width':390,'height':844})
            expect(canva).to_be_visible()
            expect(upload).to_be_visible()
            if len(ordinary) == 1:
                page.screenshot(path='canva-upload-product-mobile.png', full_page=True)
            page.set_viewport_size({'width':1365,'height':1000})
            if len(added) < 2 and not cfg.get('finished_apparel') and not cfg.get('usdot_customizer'):
                quantity = page.locator('#calculator [name="quantity"]')
                if page.locator('#continue-btn').is_disabled() and quantity.count():
                    quantity.fill(str(min(max(100,cfg.get('min_quantity',1)),cfg.get('max_quantity',100000))))
                    quantity.press('Tab')
                expect(page.locator('#continue-btn')).to_be_enabled(timeout=15000)
                page.screenshot(path=f'canva-upload-product-{len(added)+1}-desktop.png', full_page=True)
                page.locator('#continue-btn').click()
                page.get_by_role('link',name='View project',exact=True).click()
                added.append(entry)
                expect(page.locator('[data-action="window-upload"]')).to_have_count(len(added))
                expect(page.locator('[data-action="canva-open"]')).to_have_count(len(added))
            checked.append({'product':entry['name'], 'artwork':'Canva plus Upload File; two files persist after reload on desktop/mobile'})
        assert len(ordinary) >= 5, 'Expected several ordinary products to verify.'
        assert len(added) == 2, 'Expected two different printed products in the test project.'
        page.goto(root + '/project')
        expect(page.locator('[data-window-upload-summary]')).to_have_text(['2 files attached','2 files attached'])
        page.locator('[data-action="window-upload"]').first.click()
        page.locator('[data-action="window-upload-remove"]').first.click()
        expect(page.locator('#window-upload-files [data-action="window-upload-remove"]')).to_have_count(1)
        replacement = fixture_dir / 'replacement-Front.pdf'
        replacement.write_bytes(pdf_bytes)
        page.locator('#window-upload-input').set_input_files(replacement)
        expect(page.locator('#window-upload-files [data-action="window-upload-remove"]')).to_have_count(2)
        page.get_by_role('button',name='Done',exact=True).click()
        page.reload()
        expect(page.locator('[data-window-upload-summary]')).to_have_text(['2 files attached','2 files attached'])
        page.screenshot(path='canva-upload-cart-desktop.png', full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.locator('[data-action="project-checkout"]').click()
        expect(page.locator('#window-upload-checkout-notice')).to_contain_text('4 design files already attached')
        expect(page.locator('#window-upload-checkout-notice')).not_to_contain_text('window design')
        page.screenshot(path='canva-upload-checkout-mobile.png', full_page=True)
        if not live:
            form = page.locator('form[data-form="public-order"]')
            form.locator('[name="customer_name"]').fill('Local Upload Test')
            form.locator('[name="customer_email"]').fill('local-upload@example.test')
            form.locator('[name="title"]').fill('Local Canva plus upload verification')
            if form.locator('[name="confirm"]').count():
                form.locator('[name="confirm"]').check()
            form.locator('button[type="submit"]').click()
            expect(page.locator('#modal-content h2')).to_have_text('Your order is saved', timeout=20000)
            assert 'artwork was not uploaded' not in page.locator('#modal-content').inner_text()
            db = sqlite3.connect(Path(os.environ['DATA_DIR']) / 'signshop.sqlite3')
            assets = db.execute("SELECT filename FROM assets WHERE job_id=(SELECT id FROM jobs WHERE title='Local Canva plus upload verification' ORDER BY id DESC LIMIT 1)").fetchall()
            expected = [f'items-1-product-{added[0]["id"]}-Back.png','items-1-replacement-Front.pdf',f'items-2-product-{added[1]["id"]}-Front.pdf',f'items-2-product-{added[1]["id"]}-Back.png']
            assert sorted(row[0] for row in assets) == sorted(expected), assets
        assert not errors, errors
        assert not blocked, blocked
        report = {'mode':'live read-only' if live else 'local end-to-end','all_passed':True,'products':checked,'canva_products':len(ordinary),'cart_files':4,'live_orders_submitted':0}
        Path('canva-upload-verification.json').write_text(json.dumps(report,indent=2))
        print('PASS:',json.dumps(report),flush=True)
    except Exception:
        print('FAILED URL:',page.url)
        print(page.locator('body').inner_text()[-7000:])
        page.screenshot(path='canva-upload-failure.png', full_page=True)
        raise
    finally:
        browser.close()
