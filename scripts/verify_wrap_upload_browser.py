"""Verify wrap artwork on local test orders, or read-only on the live site."""
import io
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.request import urlopen
from PIL import Image
from playwright.sync_api import sync_playwright, expect

live = '--live' in sys.argv
root = os.getenv('VERIFY_BASE_URL', 'http://localhost:8000').rstrip('/')
if not live and root != 'http://localhost:8000':
    raise RuntimeError('Order submission is restricted to the isolated local server.')
with urlopen(root + '/api/catalog', timeout=30) as response:
    catalog = json.load(response)
products = catalog['products']
wraps = [item for item in products if item['config'].get('is_wrap')]
if any(item['name'].lower() == 'partial vehicle wraps' for item in wraps):
    wraps = [item for item in wraps if item['name'].lower() != 'vehicle wraps']
assert any('vehicle' in item['name'].lower() for item in wraps), [item['name'] for item in wraps]
assert any('trailer' in item['name'].lower() for item in wraps), [item['name'] for item in wraps]

def slug(item):
    name = item['name'].lower()
    if name == 'partial vehicle wraps': name = 'vehicle wraps'
    return re.sub(r'[^a-z0-9]+', '-', name.replace('&',' and ')).strip('-')

buf = io.BytesIO()
Image.new('RGB',(32,32),'white').save(buf,format='PNG')
errors=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch()
    page=browser.new_page(viewport={'width':1365,'height':900})
    page.on('pageerror',lambda e:errors.append(str(e)))
    if live:
        def read_only(route):
            request=route.request
            if request.method not in ('GET','HEAD','OPTIONS') and not request.url.startswith(root+'/api/calculate'):
                raise RuntimeError('Unexpected live mutation blocked: '+request.url)
            route.continue_()
        page.route('**/api/**',read_only)
    try:
        for index,item in enumerate(wraps):
            page.goto(root+'/products/'+slug(item))
            expect(page.locator('[data-action="window-upload"]')).to_have_count(1)
            expect(page.locator('[data-action="product-canva"], [data-action="canva-open"]')).to_have_count(0)
            expect(page.locator('.public-grid [data-action="design-quote"]')).to_have_count(1)
            expect(page.locator('.public-grid')).not_to_contain_text('Design in Canva')
            for radio in page.locator('input[name="coverage_option"]').all():
                radio.check()
                expect(page.locator('[data-action="product-canva"], [data-action="canva-open"]')).to_have_count(0)
            page.locator('.public-grid [data-action="design-quote"]').click()
            expect(page.locator('form[data-form="design-quote"]')).to_be_visible()
            page.locator('#modal-content .close-btn').click()
            page.locator('[data-action="window-upload"]').click()
            expect(page.locator('#modal-content')).to_contain_text('Driver Side, Passenger Side and Rear')
            expect(page.locator('#modal-content')).not_to_contain_text('Canva')
            pdf={'name':f'wrap-{index+1}-Driver Side.pdf','mimeType':'application/pdf','buffer':b'%PDF-1.4\n% upload verification\n%%EOF\n'}
            png={'name':f'wrap-{index+1}-Rear.png','mimeType':'image/png','buffer':buf.getvalue()}
            page.locator('#window-upload-input').set_input_files([pdf,png])
            expect(page.locator('#window-upload-files [data-action="window-upload-remove"]')).to_have_count(2)
            page.get_by_role('button',name='Done',exact=True).click()
            expect(page.locator('[data-window-upload-summary]')).to_have_text('2 files attached')
            page.reload()
            expect(page.locator('[data-window-upload-summary]')).to_have_text('2 files attached')
            expect(page.locator('#continue-btn')).to_be_enabled(timeout=15000)
            page.screenshot(path=f'wrap-upload-{slug(item)}-desktop.png',full_page=True)
            page.locator('#continue-btn').click()
            page.get_by_role('link',name='View project',exact=True).click()
            expect(page.locator('[data-action="window-upload"]')).to_have_count(index+1)
            expect(page.locator('[data-action="product-canva"], [data-action="canva-open"]')).to_have_count(0)
        page.reload()
        expect(page.locator('[data-window-upload-summary]')).to_have_text(['2 files attached']*len(wraps))
        page.set_viewport_size({'width':390,'height':844})
        page.locator('[data-action="window-upload"]').last.click()
        expect(page.locator('#window-upload-input')).to_be_visible()
        expect(page.get_by_role('button',name='Done',exact=True)).to_be_visible()
        page.locator('[data-action="window-upload-remove"]').first.click()
        expect(page.locator('#window-upload-files [data-action="window-upload-remove"]')).to_have_count(1)
        page.locator('#window-upload-input').set_input_files(pdf)
        expect(page.locator('#window-upload-files [data-action="window-upload-remove"]')).to_have_count(2)
        page.screenshot(path='wrap-upload-mobile.png',full_page=True)
        page.get_by_role('button',name='Done',exact=True).click()
        page.locator('[data-action="project-checkout"]').click()
        expect(page.locator('#window-upload-checkout-notice')).to_contain_text(f'{2*len(wraps)} design files already attached')
        if not live:
            form=page.locator('form[data-form="public-order"]')
            form.locator('[name="customer_name"]').fill('Wrap Upload Test')
            form.locator('[name="customer_email"]').fill('wrap-upload@example.test')
            form.locator('[name="title"]').fill('Local wrap upload verification')
            if form.locator('[name="confirm"]').count():form.locator('[name="confirm"]').check()
            form.locator('button[type="submit"]').click()
            expect(page.locator('#modal-content h2')).to_have_text('Your order is saved',timeout=20000)
            assert 'artwork was not uploaded' not in page.locator('#modal-content').inner_text()
            db=sqlite3.connect(Path(os.environ['DATA_DIR'])/'signshop.sqlite3')
            assets=db.execute("SELECT filename FROM assets WHERE job_id=(SELECT id FROM jobs WHERE title='Local wrap upload verification' ORDER BY id DESC LIMIT 1)").fetchall()
            expected=[f'items-{i+1}-wrap-{i+1}-{name}' for i in range(len(wraps)) for name in ('Driver Side.pdf','Rear.png')]
            assert sorted(row[0] for row in assets)==sorted(expected),assets
        page.goto(root+'/products/window-graphics')
        expect(page.locator('[data-action="window-upload"]')).to_have_count(1)
        unchanged=next(item for item in products if not any(item['config'].get(flag) for flag in ('is_wrap','supports_multiple_dimensions','artwork_upload_disabled','contour_customizer','finished_apparel','usdot_customizer')))
        page.goto(root+'/products/'+slug(unchanged))
        expect(page.locator('[data-action="product-canva"]')).to_have_count(1)
        assert not errors,errors
        print('PASS:', 'LIVE read-only' if live else 'LOCAL end-to-end', 'wrap upload choices, all coverage options, design help, persisted files, cart, mobile, checkout attachments and unchanged other-product choices.')
        print('Verified wrap products:', ', '.join(item['name'] for item in wraps))
    except Exception:
        print('FAILURE URL:',page.url)
        print('FAILURE TEXT:',page.locator('body').inner_text()[-7000:])
        page.screenshot(path='wrap-upload-failure.png',full_page=True)
        raise
    finally:
        browser.close()
