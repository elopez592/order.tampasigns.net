"""End-to-end verification on an isolated local app; never submit live orders."""
import io
import json
import os
import sqlite3
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, expect

root = 'http://localhost:8000'
pdf = {'name':'Left Window.pdf','mimeType':'application/pdf','buffer':b'%PDF-1.4\n% Local upload verification\n%%EOF\n'}
image = io.BytesIO()
Image.new('RGB', (32, 32), 'white').save(image, format='PNG')
png = {'name':'Right Window.png','mimeType':'image/png','buffer':image.getvalue()}
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width':1365,'height':900})
    page.on('pageerror', lambda e: errors.append(str(e)))
    try:
        page.goto(root + '/products/window-graphics')
        expect(page.locator('[data-action="window-upload"]')).to_have_count(1)
        expect(page.locator('[data-action="product-canva"]')).to_have_count(0)
        page.locator('[data-action="window-upload"]').click()
        page.locator('#window-upload-input').set_input_files([pdf, png])
        expect(page.locator('#window-upload-files [data-action="window-upload-remove"]')).to_have_count(2)
        page.get_by_role('button', name='Done', exact=True).click()
        expect(page.locator('[data-window-upload-summary]')).to_have_text('2 files attached')
        page.reload()
        expect(page.locator('[data-window-upload-summary]')).to_have_text('2 files attached')
        page.locator('[data-action="add-wrap-dimension"]').click()
        for row in page.locator('[data-wrap-dimension]').all():
            row.locator('input').nth(0).fill('24')
            row.locator('input').nth(1).fill('36')
            row.locator('input').nth(2).fill('1')
            row.locator('input').nth(2).press('Tab')
        expect(page.locator('#continue-btn')).to_be_enabled()
        page.locator('#continue-btn').click()
        page.get_by_role('link', name='View project', exact=True).click()
        expect(page.locator('[data-action="window-upload"]')).to_have_count(2)
        expect(page.locator('[data-window-upload-summary]')).to_have_text(['2 files attached','2 files attached'])
        page.reload()
        expect(page.locator('[data-window-upload-summary]')).to_have_text(['2 files attached','2 files attached'])
        page.locator('[data-action="window-upload"]').first.click()
        expect(page.locator('#modal-content')).to_contain_text('shared by 2 panes')
        page.locator('[data-action="window-upload-remove"]').first.click()
        expect(page.locator('#window-upload-files [data-action="window-upload-remove"]')).to_have_count(1)
        page.locator('#window-upload-input').set_input_files(pdf)
        expect(page.locator('#window-upload-files [data-action="window-upload-remove"]')).to_have_count(2)
        page.screenshot(path='window-upload-desktop.png', full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        expect(page.locator('#window-upload-input')).to_be_visible()
        expect(page.get_by_role('button',name='Done',exact=True)).to_be_visible()
        page.screenshot(path='window-upload-mobile.png', full_page=True)
        page.get_by_role('button',name='Done',exact=True).click()
        page.locator('[data-action="project-checkout"]').click()
        expect(page.locator('#window-upload-checkout-notice')).to_contain_text('2 window design files already attached')
        form = page.locator('form[data-form="public-order"]')
        form.locator('[name="customer_name"]').fill('Window Upload Test')
        form.locator('[name="customer_email"]').fill('window-upload@example.test')
        form.locator('[name="title"]').fill('Local window upload verification')
        if form.locator('[name="confirm"]').count():
            form.locator('[name="confirm"]').check()
        form.locator('button[type="submit"]').click()
        expect(page.locator('#modal-content h2')).to_have_text('Your order is saved', timeout=20000)
        assert 'artwork was not uploaded' not in page.locator('#modal-content').inner_text()
        assert not errors, errors
        db = sqlite3.connect(Path(os.environ['DATA_DIR']) / 'signshop.sqlite3')
        assets = db.execute("SELECT filename FROM assets WHERE job_id=(SELECT id FROM jobs WHERE title='Local window upload verification' ORDER BY id DESC LIMIT 1)").fetchall()
        assert sorted(x[0] for x in assets) == ['items-1-2-Left Window.pdf','items-1-2-Right Window.png'], assets
        print('PASS: browser product upload, multi-pane cart, real IndexedDB reload, shared removal/replacement, desktop/mobile modal, checkout and private backend attachments.')
    except Exception:
        print('BROWSER FAILURE URL:', page.url)
        print('BROWSER FAILURE TEXT:', page.locator('body').inner_text()[-6500:])
        page.screenshot(path='window-upload-failure.png', full_page=True)
        raise
    finally:
        browser.close()
