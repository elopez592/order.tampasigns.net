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
 'labor_cost_per_hour': '35', 'labor_sell_per_hour': '85', 'rates_live': False,
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
            cfg['description'] = 'Premium cast wrap film, printed and laminated. Choose print only for ready-to-print files, or request installation for a reviewed vehicle wrap quote.'
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
              ('Die-cut stickers', 'Stickers', 1, 'piece', '24', '4', '25', '8', '35', 50, 3, 3, 24, 48, True, 'Printed vinyl stickers with laminate. One design per line.'),
              ('Roll / sheet labels', 'Labels', 1, 'piece', '18', '3', '30', '10', '45', 50, 2, 2, 12, 12, True, 'Example label configuration; confirm roll direction and packaging.'),
              ('Custom magnets', 'Magnets', 1, 'piece', '18', '5', '20', '8', '40', 10, 3, 3, 24, 48, True, 'Printed magnetic stock. Thickness and suitability require confirmation.'),
              ('Vinyl banner', 'Banners', 2, 'sqft', '5', '1.5', '10', '4', '45', 1, 72, 36, 120, 1200, True, 'Single-sided banner, standard hem and grommets.'),
              ('ACM sign - single sided', 'Signs', 3, 'sqft', '14', '5', '20', '8', '65', 1, 24, 18, 48, 96, True, 'Printed graphic on 3mm ACM. Installation priced separately.'),
              ('Yard sign - single sided', 'Signs', 3, 'piece', '8', '2.5', '15', '5', '30', 1, 24, 18, 48, 96, True, '4mm corrugated plastic; hardware and installation not included.'),
              ('Storefront perforated graphics', 'Windows', 3, 'sqft', '10.5', '4.25', '0', '0', '75', 1, 44, 92, 54, 1200, False, 'Budget allowance for printed, laminated and installed perf. Verify approved film/laminate and site access.'),
              ('Acrylic sign face replacement', 'Signs', 3, 'sqft', '22', '12', '0', '0', '150', 1, 120, 30.5, 120, 96, False, 'Review thickness, full-sheet purchase, print type, retainers and installation labor.'),
              ('Cast wrap film - print and laminate', 'Wrap print', 5, 'sqft', '10', '5.5', '20', '8', '85', 1, 54, 120, 54, 1200, True, 'Print-only example rate, not installed. Confirm film and laminate selection.'),
              ('Vehicle wrap - installed estimate', 'Wraps', 4, 'sqft', '16', '7', '200', '75', '650', 1, 180, 120, 1000, 1000, False, 'Budget estimate only. Vehicle, coverage, removal, condition and installation must be reviewed.'),
            ]
            for name, category, workflow, unit, sell, cost, setup, setup_cost, minimum, minqty, width, height, maxw, maxh, instant, description in entries:
                cfg = validate_config({'unit': unit, 'sell_per_sqft': sell, 'cost_per_sqft': cost,
                    'setup_price': setup, 'setup_cost': setup_cost, 'minimum_price': minimum,
                    'min_quantity': minqty, 'default_width': width, 'default_height': height,
                    'max_width': maxw, 'max_height': maxh, 'instant': instant and 'wrap' not in category.lower(), 'description': description,
                    'is_wrap': 'wrap' in category.lower(), 'requires_installation': not instant,
                    'tiers': [{'from': 1, 'multiplier': '1'}, {'from': 100, 'multiplier': '.90'},
                              {'from': 500, 'multiplier': '.80'}, {'from': 1000, 'multiplier': '.70'}] if unit == 'piece'
                              else [{'from': 1, 'multiplier': '1'}]})
                conn.execute('INSERT INTO products(name,category,workflow_id,config,updated_at) VALUES(?,?,?,?,?)',
                             (name, category, workflow, json.dumps(cfg), now()))
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
