"""Local isolated browser test; production mode only reads public pages."""
import json
import os
from playwright.sync_api import sync_playwright, expect
root=os.getenv('VERIFY_BASE_URL','http://localhost:8000')
live=root.startswith('https://')
with sync_playwright() as pw:
    browser=pw.chromium.launch()
    context=browser.new_context(viewport={'width':1365,'height':950})
    page=context.new_page();errors=[];requests=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:requests.append(r) if '/api/marketing/event' in r.url else None)
    page.goto(root+'/products/banners')
    expect(page.locator('#ts-measure-banner')).to_be_visible()
    assert not requests,'No measurement before consent'
    page.get_by_role('button',name='No thanks',exact=True).click()
    page.reload();expect(page.locator('#ts-measure-banner')).to_have_count(0)
    assert not requests,'No measurement after decline'
    if live:
        assert page.request.get(root+'/api/admin/marketing').status==401
        assert page.request.get(root+'/api/admin/marketing.csv').status==401
        page.screenshot(path='marketing-live-product.png',full_page=True)
    else:
        page.get_by_role('button',name='Privacy choices',exact=True).click()
        page.get_by_role('button',name='Allow measurement',exact=True).click()
        page.wait_for_timeout(800)
        assert any(json.loads(r.post_data)['event']=='page_view' for r in requests)
        for r in requests:
            assert set(json.loads(r.post_data))<={'sid','event_id','event','path','consent','source','medium','campaign'}
        page.goto(root+'/staff')
        page.locator('input[name="email"]').fill(os.environ['ADMIN_EMAIL'])
        page.locator('input[name="password"]').fill(os.environ['ADMIN_PASSWORD'])
        page.get_by_role('button',name='Sign in',exact=True).click()
        page.get_by_role('link',name='Traffic & conversions',exact=True).click()
        expect(page.locator('h1')).to_have_text('Traffic & conversions')
        expect(page.get_by_text('Sources & campaigns',exact=True)).to_be_visible()
        page.screenshot(path='marketing-owner-desktop.png',full_page=True)
        count=len(requests)
        page.set_viewport_size({'width':390,'height':844})
        expect(page.locator('h1')).to_have_text('Traffic & conversions')
        page.screenshot(path='marketing-owner-mobile.png',full_page=True)
        assert count==len(requests),'Staff screens must not send events'
        result=page.request.get(root+'/api/admin/marketing.csv')
        assert result.status==200 and 'Measured sessions' in result.text()
    assert not errors,errors
    browser.close()
print('PASS: '+('live public script, decline and owner-only report access' if live else 'opt-in consent, no tracking before/after decline, safe event fields, staff exclusion, owner desktop/mobile dashboard and CSV'))
