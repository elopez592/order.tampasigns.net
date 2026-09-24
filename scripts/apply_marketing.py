"""Guarded addition of owner-requested, consent-based website measurement.

The only new public POST is the isolated /api/marketing/event collector. Its
handler independently requires an exact allowed Origin, explicit consent,
strict event fields, public paths, a small body and a request rate limit.
All existing staff, payment, customer and order authorization remains intact.
"""
from pathlib import Path
import re

def patch(name, changes):
    p=Path(name);s=p.read_text()
    for before,after in changes:
        if s.count(before)!=1:raise RuntimeError(f'Unexpected source in {name}: {before[:100]}')
        s=s.replace(before,after,1)
    p.write_text(s)

patch('app/marketing.py',[("marketing_conversions VALUES (?,?,?,?,?,?,?,?,?)", "marketing_conversions VALUES (?,?,?,?,?,?,?,?)")])
patch('app/main.py',[
 ('from . import canva','from . import canva, marketing'),
 ("    app.state.public_url = public_url", "    app.state.public_url = public_url\n    marketing.install(app, database, public_url, production, require_admin)"),
 ("request.url.path != '/api/payments/stripe/webhook'", "request.url.path not in ('/api/payments/stripe/webhook','/api/marketing/event')"),
 ("                job_id = create_job(conn,order_payload,source='checkout',actor='Online customer')", "                job_id = create_job(conn,order_payload,source='checkout',actor='Online customer')\n                marketing.capture_conversion(conn, request, job_id)"),
 ("            job_id = create_job(conn, request_payload, source='customer', actor='Public estimate request')", "            job_id = create_job(conn, request_payload, source='customer', actor='Public estimate request')\n            marketing.capture_conversion(conn, request, job_id)"),
 ("            }, source='custom', actor='Custom quote request')", "            }, source='custom', actor='Custom quote request')\n            marketing.capture_conversion(conn, request, job_id)")])
patch('app/static/app.js',[
 ("import {createShop}","import {createMarketingDashboard} from './marketing-admin.js?v=20260924-1';\nimport {createShop}"),
 ("    if(hash==='reports')return loadReports();", "    if(hash==='reports')return loadReports();\n    if(hash==='conversions')return marketingDashboard.render();"),
 ("['reports','chart','Revenue & reports'],", "['reports','chart','Revenue & reports'],['conversions','chart','Traffic & conversions'],"),
 ('shop=createShop({', 'const marketingDashboard=createMarketingDashboard({api,staffShell,esc,money,forms,toast});\nshop=createShop({'),
 ("state.user=s.user;state.catalog", "state.user=s.user;if(s.user)window.TampaAnalytics?.excludeStaff();state.catalog"),
 ('./shop.js?v=20260924-all-uploads','./shop.js?v=20260924-marketing')])
patch('app/static/shop.js',[
 ('project.push(...items);persist();',"project.push(...items);persist();window.TampaAnalytics?.track('add_to_cart');"),
 ('orderModal();await windowUploads.checkoutHint(project);',"orderModal();window.TampaAnalytics?.track('begin_checkout');await windowUploads.checkoutHint(project);"),
 ('./window-upload.js?v=20260924-all-uploads','./window-upload.js?v=20260924-marketing')])
patch('app/static/window-upload.js',[
 ('          await save(files);',"          await save(files);\n          globalThis.window?.TampaAnalytics?.track('upload_file');")])
p=Path('app/static/index.html');s=p.read_text()
s,n=re.subn(r'/static/app.js\?v=[^"\s]+','/static/app.js?v=20260924-marketing',s)
assert n==1
s=s.replace('</head>','<link rel="stylesheet" href="/static/measure.css?v=1">\n<script defer src="/static/measure.js?v=1"></script>\n</head>')
p.write_text(s)
print('Integrated optional measurement. Existing authorization, prices and payment verification unchanged.')
