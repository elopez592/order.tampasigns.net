"""Browser checks that never submit orders or mutate production data."""
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

root = os.getenv('VERIFY_BASE_URL', 'http://localhost:8000').rstrip('/')
paths = ['/products/storefront-window-tinting', '/products/fleet-window-tinting']
artwork_actions = '[data-action="window-upload"], [data-action="design-quote"], [data-action="product-canva"], [data-action="canva-open"]'
errors, blocked = [], []

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={'width':1365,'height':1000})
    page.on('pageerror', lambda e: errors.append(str(e)))
    def read_only(route):
        request = route.request
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and urlparse(request.url).path != '/api/calculate':
            blocked.append(request.method+' '+request.url)
            route.abort()
        else:
            route.continue_()
    page.route('**/api/**', read_only)
    try:
        for i, path in enumerate(paths):
            page.goto(root + path)
            expect(page.locator('h1.product-page-title')).to_contain_text('Tinting')
            expect(page.locator(artwork_actions)).to_have_count(0)
            expect(page.get_by_text('Need design?', exact=True)).to_have_count(0)
            expect(page.locator('.public-grid')).not_to_contain_text(re.compile(r'artwork|canva|design|proof', re.I))
            if page.locator('[data-wrap-dimension]').count():
                for row in page.locator('[data-wrap-dimension]').all():
                    row.locator('input').nth(0).fill('24')
                    row.locator('input').nth(1).fill('36')
            for field, value in [('vehicle_year','2024'), ('vehicle_make','Ford'), ('vehicle_model','Transit')]:
                locator = page.locator(f'#calculator [name="{field}"]')
                if locator.count(): locator.fill(value)
            if page.locator('#calculator [name="quantity"]').count():
                page.locator('#calculator [name="quantity"]').fill('1')
            page.locator('#calculator input').last.press('Tab')
            expect(page.locator('#continue-btn')).to_be_enabled(timeout=15000)
            expect(page.locator('#estimate-total')).not_to_have_text('--')
            page.screenshot(path=f'tint-no-design-{i+1}-desktop.png', full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            expect(page.locator(artwork_actions)).to_have_count(0)
            page.screenshot(path=f'tint-no-design-{i+1}-mobile.png', full_page=True)
            page.locator('#continue-btn').click()
            page.get_by_role('link', name='View project', exact=True).click()
            expect(page.locator('.project-layout')).to_be_visible()
            expect(page.locator(artwork_actions)).to_have_count(0)
            page.locator('[data-action="project-checkout"]').click()
            expect(page.locator('form[data-form="public-order"]')).to_be_visible()
            expect(page.locator('form[data-form="public-order"] input[type="file"]')).to_have_count(0)
            expect(page.locator('form[data-form="public-order"]')).not_to_contain_text(re.compile(r'artwork|canva|design|proof', re.I))
            page.locator('#modal-content .close-btn').click()
            page.set_viewport_size({'width':1365,'height':1000})

        # Existing artwork choices must still render after moving away from tinting.
        page.goto(root + '/products/window-graphics')
        expect(page.locator('[data-action="window-upload"]')).to_have_count(1)
        expect(page.locator('.public-grid [data-action="design-quote"]')).to_have_count(1)
        expect(page.get_by_text('Need design?', exact=True)).to_have_count(1)
        page.locator('[data-action="window-upload"]').click()
        expect(page.locator('#window-upload-input')).to_be_visible()
        page.get_by_role('button',name='Done',exact=True).click()
        for path in ['/products/vehicle-wraps', '/products/trailer-food-truck-wraps']:
            page.goto(root + path)
            expect(page.locator('[data-action="window-upload"]')).to_have_count(1)
            expect(page.locator('.public-grid [data-action="design-quote"]')).to_have_count(1)
            expect(page.locator('[data-action="product-canva"], [data-action="canva-open"]')).to_have_count(0)
        # Mixed projects still accept artwork for the printed item, not for tinting.
        page.goto(root + '/products/window-graphics')
        for row in page.locator('[data-wrap-dimension]').all():
            row.locator('input').nth(0).fill('24')
            row.locator('input').nth(1).fill('36')
        page.locator('#calculator input').last.press('Tab')
        expect(page.locator('#continue-btn')).to_be_enabled(timeout=15000)
        page.locator('#continue-btn').click()
        page.get_by_role('link', name='View project', exact=True).click()
        expect(page.locator('[data-action="window-upload"]')).to_have_count(1)
        page.locator('[data-action="project-checkout"]').click()
        expect(page.locator('form[data-form="public-order"] input[type="file"]')).to_have_count(1)
        assert not blocked, blocked
        assert not errors, errors
        print('PASS:', root, 'both tinting pages show no artwork/design buttons or prompts; tint-only cart and checkout need no artwork; window graphics, wraps and mixed-project uploads preserved. Desktop and mobile checked. No orders submitted.')
    except Exception:
        print('Failure page:', page.url)
        print(page.locator('body').inner_text()[-8000:])
        page.screenshot(path='tint-no-design-failure.png', full_page=True)
        raise
    finally:
        browser.close()
