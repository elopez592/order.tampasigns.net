from __future__ import annotations
import json
import os
import secrets
from .db import now, transaction
from .security import password_hash, email
from .pricing import validate_config
from .domain import create_job, validate_steps

DEFAULT_SETTINGS = {
 'shop_name': 'Tampa Signs and Stickers', 'contact_email': '', 'contact_phone': '(813) 749-4500',
 'deposit_percent': '50', 'target_margin_percent': '40', 'overhead_percent': '10',
 'labor_cost_per_hour': '35', 'labor_sell_per_hour': '85', 'minimum_order_price': '50', 'rates_live': False,
 'quote_note': 'Order standard-sized prints online. Wraps, installation and custom specifications are quoted by our team. You approve your proof before we print.',
 'checkout_enabled': False, 'checkout_tax_reviewed': False,
 'checkout_pickup_enabled': True, 'checkout_pickup_address': '',
 'checkout_pickup_tax_percent': '0', 'checkout_shipping_enabled': False,
 'checkout_shipping_price': '0',
 'checkout_terms': 'I confirm the product, size and quantity. I will review and approve a proof before production. Tax and any selected delivery charge are shown at secure checkout.',
}


def steps_for(production):
    base = [
      {'title': 'Review measurements and specifications', 'department': 'Intake', 'gate': 'none', 'depends_on': []},
      {'title': 'Order / reserve materials', 'department': 'Purchasing', 'gate': 'deposit', 'depends_on': [1]},
      {'title': 'Design and complete proof package', 'department': 'Design', 'gate': 'quote', 'depends_on': [1]},
    ]
    for i, (title, department) in enumerate(production):
        base.append({'title': title, 'department': department, 'gate': 'production',
                     'depends_on': [2, 3] if i == 0 else [len(base)]})
    base.append({'title': 'Deliver / install and close out', 'department': 'Fulfillment', 'gate': 'delivery', 'depends_on': [len(base)]})
    return validate_steps(base)


def bootstrap(db_path, demo=False, admin_email=None, admin_password=None):
    credentials = []
    with transaction(db_path, True) as conn:
        conn.execute('INSERT OR IGNORE INTO settings VALUES(1,?)', (json.dumps(DEFAULT_SETTINGS),))
        saved = json.loads(conn.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
        merged = DEFAULT_SETTINGS | saved
        if merged['shop_name'] == 'SignShop OS':
            merged['shop_name'] = DEFAULT_SETTINGS['shop_name']
        if str(merged.get('labor_sell_per_hour', '85')) == '85':
            merged['labor_sell_per_hour'] = '100'
        conn.execute('UPDATE settings SET data=? WHERE id=1', (json.dumps(merged),))
        # Clean up legacy demo-facing product names without touching custom products.
        for old_name, new_name in {
            'Roll / sheet labels': 'Labels',
            'Custom magnets': 'Magnets',
            'Vinyl banner': 'Banners',
            'ACM sign - single sided': 'ACM signs',
            'Yard sign - single sided': 'Yard signs',
        }.items():
            conn.execute('UPDATE products SET name=? WHERE name=?', (new_name, old_name))
        # Normalize legacy products and consolidate vehicle wraps into one public product.
        wrap_install_workflow = conn.execute("SELECT id FROM workflows WHERE name='Vehicle wraps'").fetchone()
        wrap_print_workflow = conn.execute("SELECT id FROM workflows WHERE name='Print-only wrap panels'").fetchone()
        for old in conn.execute('SELECT id,name,category,config,workflow_id,active,public FROM products').fetchall():
            cfg = json.loads(old['config'])
            cfg.setdefault('requires_installation', old['id'] in (7, 8, 10))
            cfg.setdefault('is_wrap', 'wrap' in (old['name']+' '+old['category']).lower())
            cfg.setdefault('supports_installation', False)
            cfg.setdefault('installation_workflow_id', None)
            cfg.setdefault('lamination_options', [])
            cfg.setdefault('quantity_price_table', [])
            cfg.setdefault('installation_minutes_per_sqft', '0')
            cfg.setdefault('installation_setup_minutes', '0')
            cfg.setdefault('price_table_base_width', cfg.get('default_width', '3'))
            cfg.setdefault('price_table_base_height', cfg.get('default_height', '3'))
            cfg.setdefault('price_table_size_weight', '0.45')
            cfg.setdefault('min_width', '0.1')
            cfg.setdefault('min_height', '0.1')
            cfg.setdefault('self_approve_artwork', False)

            lname = (old['name'] + ' ' + old['category']).lower()
            if any(x in lname for x in ('sticker', 'transfer')):
                cfg['min_width'] = '1'
                cfg['min_height'] = '1'
            if any(x in lname for x in ('die-cut sticker', 'transfer sticker', 'magnet', 'banner')):
                cfg['self_approve_artwork'] = True
            if 'die-cut sticker' in lname:
                cfg['min_quantity'] = '1'
                if str(cfg.get('minimum_price', '')) in ('60', '60.0', '60.00'):
                    cfg['minimum_price'] = '50'
            if 'magnet' in lname and str(cfg.get('min_quantity', '10')) == '10':
                cfg['min_quantity'] = '1'
            # Public benchmark profile: Sticker Mule-style 3x3 quantity anchors.
            if 'die-cut sticker' in lname and len(cfg.get('quantity_price_table', [])) == 5 and [r.get('quantity') for r in cfg.get('quantity_price_table', [])] == [50,100,200,500,1000]:
                cfg['quantity_price_table'] = [
                    {'quantity': 50, 'total': '60'}, {'quantity': 100, 'total': '73'},
                    {'quantity': 200, 'total': '95'}, {'quantity': 300, 'total': '115'},
                    {'quantity': 500, 'total': '152'}, {'quantity': 1000, 'total': '232'},
                    {'quantity': 2000, 'total': '371'}, {'quantity': 3000, 'total': '496'},
                    {'quantity': 5000, 'total': '723'}, {'quantity': 10000, 'total': '1225'}
                ]
                cfg['lamination_options'] = [
                    {'id':'standard_matte','label':'Standard matte — no laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'premium_matte','label':'Premium matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                    {'id':'gloss_laminate','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}
                ]
            if 'die-cut sticker' in lname and not cfg.get('quantity_price_table'):
                cfg['quantity_price_table'] = [
                    {'quantity': 50, 'total': '60'}, {'quantity': 100, 'total': '73'},
                    {'quantity': 200, 'total': '95'}, {'quantity': 300, 'total': '115'},
                    {'quantity': 500, 'total': '152'}, {'quantity': 1000, 'total': '232'},
                    {'quantity': 2000, 'total': '371'}, {'quantity': 3000, 'total': '496'},
                    {'quantity': 5000, 'total': '723'}, {'quantity': 10000, 'total': '1225'}
                ]
                cfg['price_table_base_width'] = '3'
                cfg['price_table_base_height'] = '3'
                cfg['price_table_size_weight'] = '0.45'
                cfg['minimum_price'] = '60'
                cfg['lamination_options'] = [
                    {'id':'standard_matte','label':'Standard matte — no laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'premium_matte','label':'Premium matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                    {'id':'gloss_laminate','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}
                ]

            # Common large-format laminate add-ons, based on public trade-shop finishing rates.
            if any(x in lname for x in ('label','magnet','acm','yard sign','acrylic')) and not cfg.get('lamination_options'):
                cfg['lamination_options'] = [
                    {'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'gloss','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                    {'id':'premium_matte','label':'Premium matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}
                ]
            if ('perforated' in lname or 'window' in lname) and not cfg.get('lamination_options'):
                cfg['lamination_options'] = [
                    {'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'optically_clear','label':'Optically clear laminate','sell_per_sqft':'3.5','cost_per_sqft':'2','default':False}
                ]
            conn.execute('UPDATE products SET config=? WHERE id=?', (json.dumps(cfg), old['id']))
        print_wrap = conn.execute("SELECT * FROM products WHERE name IN ('Cast wrap film - print and laminate','Vehicle Wraps') ORDER BY id LIMIT 1").fetchone()
        installed_wrap = conn.execute("SELECT * FROM products WHERE name='Vehicle wrap - installed estimate' ORDER BY id LIMIT 1").fetchone()
        if print_wrap:
            cfg = json.loads(print_wrap['config'])
            cfg['instant'] = True
            cfg['is_wrap'] = True
            cfg['requires_installation'] = False
            cfg['supports_installation'] = True
            cfg['installation_workflow_id'] = wrap_install_workflow['id'] if wrap_install_workflow else 4
            if str(cfg.get('sell_per_sqft', '10')) == '10':
                cfg['sell_per_sqft'] = '5.27'
                cfg['setup_price'] = '0'
                cfg['minimum_price'] = '5.27'
            if str(cfg.get('cost_per_sqft', '5.5')) == '5.5':
                cfg['cost_per_sqft'] = '0'
                cfg['setup_cost'] = '0'
            cfg['installation_minutes_per_sqft'] = '4'
            cfg['installation_setup_minutes'] = '60'
            cfg['lamination_options'] = [
                {'id':'cast_gloss','label':'Cast gloss laminate (included)','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                {'id':'cast_matte','label':'Cast matte laminate (included)','sell_per_sqft':'0','cost_per_sqft':'0','default':False}
            ]
            cfg['description'] = 'Premium cast wrap film printed and laminated at the current WePrintWraps benchmark rate. Installation can be estimated instantly but is always reviewed before production.'
            conn.execute("UPDATE products SET name='Vehicle Wraps',category='Vehicle Wraps',workflow_id=?,config=?,active=1,public=1 WHERE id=?",
                         ((wrap_print_workflow['id'] if wrap_print_workflow else print_wrap['workflow_id']), json.dumps(cfg), print_wrap['id']))
        if installed_wrap and (not print_wrap or installed_wrap['id'] != print_wrap['id']):
            conn.execute('UPDATE products SET active=0,public=0 WHERE id=?', (installed_wrap['id'],))
        if not conn.execute('SELECT id FROM workflows LIMIT 1').fetchone():
            workflow_map = [
                ('Stickers and labels', [('Preflight and print', 'Production'), ('Laminate / cure', 'Finishing'), ('Contour cut / weed', 'Finishing'), ('Quality check and pack', 'Quality')]),
                ('Banners', [('Preflight and print', 'Production'), ('Trim, hem and grommet', 'Finishing'), ('Quality check and pack', 'Quality')]),
                ('Signs and storefronts', [('Preflight and print', 'Production'), ('Laminate printed graphics', 'Finishing'), ('Cut substrate / fabricate sign face', 'Fabrication'), ('Mount and finish graphics', 'Finishing'), ('Quality check and site preparation', 'Quality')]),
                ('Vehicle wraps', [('Design preflight and panel plan', 'Production'), ('Print color-managed wrap panels', 'Production'), ('Cure / laminate to material specification', 'Finishing'), ('Contour cut, label and kit panels', 'Finishing'), ('Prepare vehicle and install wrap', 'Installation'), ('Post-install quality check', 'Quality')]),
                ('Print-only wrap panels', [('Preflight and print wrap panels', 'Production'), ('Cure / laminate to material specification', 'Finishing'), ('Trim, label and quality check', 'Quality')]),
            ]
            for name, production in workflow_map:
                conn.execute('INSERT INTO workflows(name,steps) VALUES(?,?)', (name, json.dumps(steps_for(production))))
        if not conn.execute('SELECT id FROM products LIMIT 1').fetchone():
            # Demonstration inputs only. Not competitor prices or supplier quotations.
            entries = [
              ('Die-cut stickers', 'Stickers', 1, 'piece', '24', '4', '0', '8', '50', 1, 3, 3, 24, 48, True, 'Die-cut vinyl stickers with quantity-break pricing benchmarked to current Sticker Mule public pricing.'),
              ('Labels', 'Labels', 1, 'piece', '18', '3', '30', '10', '45', 50, 2, 2, 12, 12, True, 'Example label configuration; confirm roll direction and packaging.'),
              ('Magnets', 'Magnets', 1, 'piece', '18', '5', '20', '8', '50', 1, 3, 3, 24, 48, True, 'Printed magnetic stock. Thickness and suitability require confirmation.'),
              ('Banners', 'Banners', 2, 'sqft', '5', '1.5', '10', '4', '45', 1, 72, 36, 120, 1200, True, 'Single-sided banner, standard hem and grommets.'),
              ('ACM signs', 'Signs', 3, 'sqft', '14', '5', '20', '8', '65', 1, 24, 18, 48, 96, True, 'Printed graphic on 3mm ACM. Installation priced separately.'),
              ('Yard signs', 'Signs', 3, 'piece', '8', '2.5', '15', '5', '30', 1, 24, 18, 48, 96, True, '4mm corrugated plastic; hardware and installation not included.'),
              ('Storefront perforated graphics', 'Windows', 3, 'sqft', '10.5', '4.25', '0', '0', '75', 1, 44, 92, 54, 1200, False, 'Budget allowance for printed, laminated and installed perf. Verify approved film/laminate and site access.'),
              ('Acrylic sign face replacement', 'Signs', 3, 'sqft', '22', '12', '0', '0', '150', 1, 120, 30.5, 120, 96, False, 'Review thickness, full-sheet purchase, print type, retainers and installation labor.'),
              ('Vehicle Wraps', 'Vehicle Wraps', 5, 'sqft', '5.27', '0', '0', '0', '5.27', 1, 54, 120, 54, 1200, True, 'Premium cast wrap film printed and laminated at the current WePrintWraps benchmark rate. Installation is estimated instantly and reviewed before production.'),
            ]
            for name, category, workflow, unit, sell, cost, setup, setup_cost, minimum, minqty, width, height, maxw, maxh, instant, description in entries:
                cfg = validate_config({'unit': unit, 'sell_per_sqft': sell, 'cost_per_sqft': cost,
                    'setup_price': setup, 'setup_cost': setup_cost, 'minimum_price': minimum,
                    'min_quantity': minqty, 'default_width': width, 'default_height': height,
                    'max_width': maxw, 'max_height': maxh, 'instant': instant, 'description': description,
                    'is_wrap': 'wrap' in category.lower(), 'requires_installation': not instant,
                    'supports_installation': 'vehicle wrap' in name.lower(),
                    'installation_workflow_id': 4 if 'vehicle wrap' in name.lower() else None,
                    'min_width': '1' if 'sticker' in name.lower() else '0.1',
                    'min_height': '1' if 'sticker' in name.lower() else '0.1',
                    'self_approve_artwork': any(x in name.lower() for x in ('sticker','magnet','banner')),
                    'installation_minutes_per_sqft': '4' if 'vehicle wrap' in name.lower() else '0',
                    'installation_setup_minutes': '60' if 'vehicle wrap' in name.lower() else '0',
                    'quantity_price_table': [
                        {'quantity':50,'total':'60'},{'quantity':100,'total':'73'},{'quantity':200,'total':'95'},
                        {'quantity':300,'total':'115'},{'quantity':500,'total':'152'},{'quantity':1000,'total':'232'},
                        {'quantity':2000,'total':'371'},{'quantity':3000,'total':'496'},
                        {'quantity':5000,'total':'723'},{'quantity':10000,'total':'1225'}
                    ] if 'die-cut sticker' in name.lower() else [],
                    'price_table_base_width': '3', 'price_table_base_height': '3', 'price_table_size_weight': '0.45',
                    'lamination_options': (
                        [{'id':'standard_matte','label':'Standard matte — no laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                         {'id':'premium_matte','label':'Premium matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                         {'id':'gloss_laminate','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}]
                        if 'die-cut sticker' in name.lower() else
                        [{'id':'cast_gloss','label':'Cast gloss laminate (included)','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                         {'id':'cast_matte','label':'Cast matte laminate (included)','sell_per_sqft':'0','cost_per_sqft':'0','default':False}]
                        if 'vehicle wrap' in name.lower() else
                        [{'id':'optically_clear','label':'Optically clear laminate','sell_per_sqft':'3.5','cost_per_sqft':'2','default':False},
                         {'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True}]
                        if 'storefront perforated' in name.lower() else
                        [{'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                         {'id':'gloss','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                         {'id':'premium_matte','label':'Premium matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}]
                        if any(x in name.lower() for x in ('label','magnet','acm','yard sign','acrylic')) else []
                    ),
                    'tiers': [{'from': 1, 'multiplier': '1'}, {'from': 100, 'multiplier': '.90'},
                              {'from': 500, 'multiplier': '.80'}, {'from': 1000, 'multiplier': '.70'}] if unit == 'piece'
                              else [{'from': 1, 'multiplier': '1'}]})
                conn.execute('INSERT INTO products(name,category,workflow_id,config,updated_at) VALUES(?,?,?,?,?)',
                             (name, category, workflow, json.dumps(cfg), now()))
        for custom in conn.execute("SELECT id,config FROM products WHERE category='Custom'").fetchall():
            cfg = json.loads(custom['config'])
            if str(cfg.get('max_quantity', '1')) == '1':
                cfg['max_quantity'] = '100000'
                conn.execute('UPDATE products SET config=? WHERE id=?', (json.dumps(cfg), custom['id']))
        if not conn.execute("SELECT id FROM products WHERE lower(name)='transfer stickers' LIMIT 1").fetchone():
            sticker_workflow = conn.execute("SELECT id FROM workflows WHERE name='Stickers and labels'").fetchone()
            transfer_cfg = validate_config({
                'unit':'piece','sell_per_sqft':'24','cost_per_sqft':'4','setup_price':'0','setup_cost':'8',
                'minimum_price':'50','waste_percent':'15','labor_minutes_per_unit':'0',
                'min_quantity':1,'max_quantity':100000,'default_width':3,'default_height':3,
                'min_width':1,'min_height':1,'max_width':24,'max_height':48,'instant':True,
                'description':'Precision-cut transfer stickers for lettering and graphics without a printed background. Minimum finished size is 1 x 1 inch.',
                'is_wrap':False,'requires_installation':False,'supports_installation':False,
                'self_approve_artwork':True,
                'quantity_price_table':[
                    {'quantity':50,'total':'60'},{'quantity':100,'total':'73'},{'quantity':200,'total':'95'},
                    {'quantity':300,'total':'115'},{'quantity':500,'total':'152'},{'quantity':1000,'total':'232'},
                    {'quantity':2000,'total':'371'},{'quantity':3000,'total':'496'},
                    {'quantity':5000,'total':'723'},{'quantity':10000,'total':'1225'}
                ],
                'price_table_base_width':'3','price_table_base_height':'3','price_table_size_weight':'0.45',
                'lamination_options':[
                    {'id':'standard_matte','label':'Standard matte — no laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'premium_matte','label':'Premium matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                    {'id':'gloss_laminate','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}
                ],
                'tiers':[{'from':1,'multiplier':'1'}]
            })
            conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?,?)',
                         ('Transfer stickers','Stickers',1,1,sticker_workflow['id'] if sticker_workflow else 1,json.dumps(transfer_cfg),now()))
        if not conn.execute("SELECT id FROM products WHERE category='Custom' LIMIT 1").fetchone():
            custom_cfg = validate_config({
                'unit': 'piece', 'sell_per_sqft': '0', 'cost_per_sqft': '0',
                'setup_price': '0', 'setup_cost': '0', 'minimum_price': '0',
                'min_quantity': 1, 'max_quantity': 100000, 'default_width': 12, 'default_height': 12,
                'max_width': 10000, 'max_height': 10000, 'instant': False,
                'description': 'Custom fabrication, specialty signage, bulk orders, fleet projects and other work quoted by the shop.',
                'is_wrap': False, 'requires_installation': False,
                'supports_installation': False, 'installation_workflow_id': None,
                'tiers': [{'from': 1, 'multiplier': '1'}]
            })
            conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?,?)',
                         ('Custom project quote', 'Custom', 1, 0, 3, json.dumps(custom_cfg), now()))
        if not conn.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone():
            address = email(admin_email or os.getenv('ADMIN_EMAIL', 'owner@example.test'))
            password = admin_password or os.getenv('ADMIN_PASSWORD') or secrets.token_urlsafe(18)
            conn.execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                         ('Shop owner', address, password_hash(password), 'admin', now()))
            credentials.append(('Owner', address, password))
        if demo and not conn.execute("SELECT id FROM users WHERE role='employee' LIMIT 1").fetchone():
            password = secrets.token_urlsafe(18)
            conn.execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                         ('Alex - Production', 'employee@example.test', password_hash(password), 'employee', now()))
            credentials.append(('Employee', 'employee@example.test', password))
        if demo and not conn.execute('SELECT id FROM jobs LIMIT 1').fetchone():
            job_id = create_job(conn, {'title': 'Storefront perf + acrylic face',
                'customer_name': 'Storefront customer (sample)', 'customer_email': 'storefront@example.test',
                'workflow_id': 3, 'notes': 'Measured job: 59 in from right edge of left window to left edge of door; 49 in from right edge of door to left edge of right window. Vertical offsets and frame coverage still need verification. Sale agreed at $1,400; tax inclusion, actual material costs, removal and sign-face installation require review.',
                'items': [{'product_id': 7, 'description': 'Left window', 'width': '43.75', 'height': '92', 'quantity': 1},
                          {'product_id': 7, 'description': 'Door', 'width': '30.5', 'height': '72', 'quantity': 1},
                          {'product_id': 7, 'description': 'Right window', 'width': '44', 'height': '92', 'quantity': 1},
                          {'product_id': 8, 'description': 'Acrylic sign face', 'width': '120', 'height': '30.5', 'quantity': 1}]}, actor='Demo setup')
            conn.execute('UPDATE jobs SET price_override_cents=140000,adjustment_note=? WHERE id=?',
                         ('Recorded agreed price. Tax inclusion and unquoted labor must be confirmed; not a verified profit calculation.', job_id))
            for title, name, product_id, width, height, qty in [
                ('250 die-cut brand stickers', 'Sample Coffee Co.', 1, 3, 3, 250),
                ('Grand opening banner', 'Sample Market', 4, 96, 36, 1),
                ('Delivery van wrap inquiry', 'Sample Fleet', 10, 180, 120, 1)]:
                create_job(conn, {'title': title, 'customer_name': name, 'customer_email': 'customer@example.test',
                           'items': [{'product_id': product_id, 'width': width, 'height': height, 'quantity': qty}]}, actor='Demo setup')
    return credentials
