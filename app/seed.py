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
            cfg.setdefault('supports_multiple_dimensions', False)
            cfg.setdefault('material_options', [])
            cfg.setdefault('storefront_categories', [])
            cfg.setdefault('size_options', [])
            cfg.setdefault('placement_options', [])
            cfg.setdefault('quantity_presets', [])
            cfg.setdefault('max_short_axis', '10000')
            cfg.setdefault('max_long_axis', '10000')
            cfg.setdefault('usdot_customizer', False)
            cfg.setdefault('quantity_only', False)
            cfg.setdefault('coverage_options', [])
            cfg.setdefault('vehicle_type_options', [])
            cfg.setdefault('quantity_only_note', '')
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
            product_name = old['name'].lower()
            category_map = []
            if any(x in lname for x in ('window','storefront','acrylic sign face','banner','acm')):
                category_map.append('Storefront')
            if any(x in lname for x in ('vehicle','wrap','magnet')) or product_name in ('decals','usdot decals'):
                category_map.append('Vehicles')
            if any(x in lname for x in ('vehicle','wrap','magnet','fleet')) or product_name in ('decals','usdot decals'):
                category_map.append('Fleet Services')
            if any(x in lname for x in ('sticker','label')) or product_name == 'decals':
                category_map.append('Stickers')
            if any(x in lname for x in ('acm','yard sign','banner','acrylic sign','magnet')):
                category_map.append('Signs')
            if old['category'].lower() == 'apparel' or any(x in lname for x in ('dtf','embroider','polo','hat')):
                category_map.append('Apparel')
            if product_name == 'transfer stickers':
                category_map = ['Stickers']
            elif product_name == 'usdot decals':
                category_map = ['Vehicles','Fleet Services']
            elif product_name == 'fleet window tinting':
                category_map = ['Fleet Services']
            elif product_name == 'partial vehicle wraps':
                category_map = ['Vehicles','Fleet Services']
            elif product_name == 'trailer / food truck wraps':
                category_map = ['Trailers / Food Trucks','Fleet Services']
            if category_map:
                cfg['storefront_categories'] = list(dict.fromkeys(category_map))
            if any(x in lname for x in ('sticker', 'transfer')):
                cfg['min_width'] = '1'
                cfg['min_height'] = '1'
            if 'transfer sticker' in lname:
                cfg['storefront_categories'] = ['Stickers']
                cfg['min_quantity'] = '1'
                cfg['min_width'] = '3'
                cfg['min_height'] = '3'
                cfg['description'] = 'Precision-cut transfer stickers for lettering and graphics without a printed background. Minimum finished size is 3 x 3 inches.'
                if str(cfg.get('minimum_price', '')) in ('50', '50.0', '50.00'):
                    cfg['minimum_price'] = '0'
            if any(x in lname for x in ('die-cut sticker', 'transfer sticker', 'magnet', 'banner')):
                cfg['self_approve_artwork'] = True
            if 'die-cut sticker' in lname:
                cfg['min_quantity'] = '50'
            if 'magnet' in lname:
                if str(cfg.get('min_quantity', '10')) == '10':
                    cfg['min_quantity'] = '1'
                cfg['size_options'] = [
                    {'label':'18 x 12 in','width':'18','height':'12'},
                    {'label':'24 x 12 in','width':'24','height':'12'},
                    {'label':'24 x 18 in','width':'24','height':'18'}
                ]
                cfg['default_width'] = '18'
                cfg['default_height'] = '12'
                cfg['max_short_axis'] = '24'
                cfg['max_long_axis'] = '48'
                cfg['max_width'] = '48'
                cfg['max_height'] = '48'
                cfg['quantity_presets'] = [1,2,5,10,25,50]
                cfg['tiers'] = [
                    {'from':1,'multiplier':'1'},
                    {'from':5,'multiplier':'0.95'},
                    {'from':10,'multiplier':'0.90'},
                    {'from':25,'multiplier':'0.85'},
                    {'from':50,'multiplier':'0.80'}
                ]
            if 'usdot decal' in lname:
                cfg['storefront_categories'] = ['Vehicles','Fleet Services']
                cfg['size_options'] = [
                    {'label':'18 x 12 in','width':'18','height':'12'},
                    {'label':'24 x 12 in','width':'24','height':'12'},
                    {'label':'24 x 18 in','width':'24','height':'18'}
                ]
                cfg['default_width'] = '18'
                cfg['default_height'] = '12'
                cfg['max_short_axis'] = '24'
                cfg['max_long_axis'] = '48'
                cfg['max_width'] = '48'
                cfg['max_height'] = '48'
                cfg['quantity_presets'] = [1,2,5,10,25,50]
                cfg['tiers'] = [
                    {'from':1,'multiplier':'1'},
                    {'from':5,'multiplier':'0.95'},
                    {'from':10,'multiplier':'0.90'},
                    {'from':25,'multiplier':'0.85'},
                    {'from':50,'multiplier':'0.80'}
                ]
            if old['name'].lower() == 'fleet window tinting':
                cfg['storefront_categories'] = ['Fleet Services']
                cfg['unit'] = 'piece'
                cfg['sell_per_sqft'] = '350'
                cfg['cost_per_sqft'] = '0'
                cfg['setup_price'] = '0'
                cfg['setup_cost'] = '0'
                cfg['minimum_price'] = '350'
                cfg['min_quantity'] = '1'
                cfg['max_quantity'] = '500'
                cfg['default_width'] = '12'
                cfg['default_height'] = '12'
                cfg['min_width'] = '12'
                cfg['min_height'] = '12'
                cfg['max_width'] = '12'
                cfg['max_height'] = '12'
                cfg['instant'] = False
                cfg['requires_installation'] = True
                cfg['quantity_only'] = True
                cfg['self_approve_artwork'] = False
                cfg['quantity_presets'] = [1,2,5,10,25,50]
                cfg['tiers'] = [
                    {'from':1,'multiplier':'1'},
                    {'from':5,'multiplier':'0.95'},
                    {'from':10,'multiplier':'0.90'},
                    {'from':25,'multiplier':'0.85'},
                    {'from':50,'multiplier':'0.80'}
                ]
                cfg['description'] = 'Fleet window tinting starting at a retail single-vehicle baseline. Final pricing is reviewed by vehicle, glass coverage, film choice and access. Larger fleets receive progressively better volume pricing.'
            if old['name'].lower() == 'decals':
                cfg['storefront_categories'] = ['Vehicles','Fleet Services','Stickers']
                cfg['quantity_presets'] = [1,2,5,10,25,50,100]
                cfg['tiers'] = [
                    {'from':1,'multiplier':'1'},
                    {'from':10,'multiplier':'0.95'},
                    {'from':25,'multiplier':'0.90'},
                    {'from':50,'multiplier':'0.85'},
                    {'from':100,'multiplier':'0.80'}
                ]
            if old['name'].lower() == 'dtf transfers':
                cfg['storefront_categories'] = ['Apparel']
                cfg['sell_per_sqft'] = '8.64'
                cfg['cost_per_sqft'] = '0'
                cfg['setup_price'] = '0'
                cfg['setup_cost'] = '0'
                cfg['minimum_price'] = '0'
                cfg['instant'] = True
                cfg['self_approve_artwork'] = True
                cfg['default_width'] = '3.5'
                cfg['default_height'] = '3.5'
                cfg['min_width'] = '1'
                cfg['min_height'] = '1'
                cfg['max_width'] = '14'
                cfg['max_height'] = '14'
                cfg['max_short_axis'] = '12'
                cfg['max_long_axis'] = '14'
                cfg['placement_options'] = [
                    {'id':'adult_left_chest','label':'Adult left chest — 3.5 x 3.5 in','width':'3.5','height':'3.5'},
                    {'id':'adult_right_chest','label':'Adult right chest — 3.5 x 3.5 in','width':'3.5','height':'3.5'},
                    {'id':'adult_full_front','label':'Adult full front — 11 x 11 in','width':'11','height':'11'},
                    {'id':'adult_full_back','label':'Adult full back — 11 x 11 in','width':'11','height':'11'},
                    {'id':'youth_full_front','label':'Youth full front — 10.5 x 10.5 in','width':'10.5','height':'10.5'},
                    {'id':'youth_full_back','label':'Youth full back — 10.5 x 10.5 in','width':'10.5','height':'10.5'},
                    {'id':'youth_small_front','label':'Youth small full front — 8.5 x 8.5 in','width':'8.5','height':'8.5'},
                    {'id':'toddler_front','label':'Toddler full front — 5.5 x 5.5 in','width':'5.5','height':'5.5'}
                ]
                cfg['size_options'] = []
                cfg['description'] = 'Ready-to-press DTF transfers priced by print area. Choose a standard apparel placement size or use Custom size. Garments and pressing are not included.'
            if old['name'].lower() == 'embroidered polos':
                cfg['storefront_categories'] = ['Apparel']
                cfg['setup_price'] = '35'
                cfg['minimum_price'] = '35'
                cfg['instant'] = False
                cfg['default_width'] = '3.5'
                cfg['default_height'] = '3.5'
                cfg['placement_options'] = [
                    {'id':'left_chest','label':'Left chest — 3.5 x 3.5 in','width':'3.5','height':'3.5'},
                    {'id':'right_chest','label':'Right chest — 3.5 x 3.5 in','width':'3.5','height':'3.5'}
                ]
                cfg['size_options'] = []
                cfg['description'] = '$35 digitizing charge for every embroidery order. Choose left chest or right chest. Garment and stitch-count pricing is reviewed before quoting. Over-complex artwork may be rejected or simplified for an additional design fee.'
            if old['name'].lower() == 'embroidered hats':
                cfg['storefront_categories'] = ['Apparel']
                cfg['setup_price'] = '35'
                cfg['minimum_price'] = '35'
                cfg['instant'] = False
                cfg['default_width'] = '4'
                cfg['default_height'] = '2.25'
                cfg['placement_options'] = [
                    {'id':'front','label':'Front — up to 4 x 2.25 in','width':'4','height':'2.25'}
                ]
                cfg['size_options'] = []
                cfg['description'] = '$35 digitizing charge for every embroidery order. Hat embroidery is front placement only. Garment and stitch-count pricing is reviewed before quoting. Over-complex artwork may be rejected or simplified for an additional design fee.'

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
                    {'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'gloss','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                    {'id':'premium_matte','label':'Matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}
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
                    {'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'gloss','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                    {'id':'premium_matte','label':'Matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}
                ]

            if any(x in lname for x in ('die-cut sticker','transfer sticker')):
                cfg['lamination_options'] = [
                    {'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'gloss','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                    {'id':'premium_matte','label':'Matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}
                ]

            # Common large-format laminate add-ons, based on public trade-shop finishing rates.
            if any(x in lname for x in ('label','magnet','acm','yard sign','acrylic')) and not cfg.get('lamination_options'):
                cfg['lamination_options'] = [
                    {'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'gloss','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                    {'id':'premium_matte','label':'Matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}
                ]
            if 'storefront perforated' in lname or old['category'].lower() == 'windows':
                cfg['supports_multiple_dimensions'] = True
                cfg['lamination_options'] = []
                cfg['material_options'] = [
                    {'id':'perforated','label':'Perforated window vinyl','sell_per_sqft_adjustment':'0','cost_per_sqft_adjustment':'0','default':True},
                    {'id':'opaque','label':'Standard opaque vinyl','sell_per_sqft_adjustment':'0','cost_per_sqft_adjustment':'0','default':False}
                ]
                cfg['description'] = 'Window graphics with your choice of perforated window vinyl or standard opaque vinyl. Add each window or panel size separately. Lamination is not included.'
            if old['category'].lower() == 'windows' and old['name'] != 'Window Graphics':
                conn.execute("UPDATE products SET name='Window Graphics' WHERE id=?", (old['id'],))
            conn.execute('UPDATE products SET config=? WHERE id=?', (json.dumps(cfg), old['id']))
        print_wrap = conn.execute("SELECT * FROM products WHERE name IN ('Cast wrap film - print and laminate','Vehicle Wraps') ORDER BY id LIMIT 1").fetchone()
        installed_wrap = conn.execute("SELECT * FROM products WHERE name='Vehicle wrap - installed estimate' ORDER BY id LIMIT 1").fetchone()
        if print_wrap:
            cfg = json.loads(print_wrap['config'])
            cfg['instant'] = True
            cfg['is_wrap'] = True
            cfg['requires_installation'] = False
            cfg['supports_installation'] = True
            cfg['supports_multiple_dimensions'] = True
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
              ('Die-cut stickers', 'Stickers', 1, 'piece', '24', '4', '0', '8', '50', 50, 3, 3, 24, 48, True, 'Die-cut vinyl stickers with quantity-break pricing benchmarked to current Sticker Mule public pricing.'),
              ('Labels', 'Labels', 1, 'piece', '18', '3', '30', '10', '45', 50, 2, 2, 12, 12, True, 'Example label configuration; confirm roll direction and packaging.'),
              ('Magnets', 'Magnets', 1, 'piece', '18', '5', '20', '8', '50', 1, 18, 12, 48, 48, True, 'Printed magnetic stock. Thickness and suitability require confirmation.'),
              ('Banners', 'Banners', 2, 'sqft', '5', '1.5', '10', '4', '45', 1, 72, 36, 120, 1200, True, 'Single-sided banner, standard hem and grommets.'),
              ('ACM signs', 'Signs', 3, 'sqft', '14', '5', '20', '8', '65', 1, 24, 18, 48, 96, True, 'Printed graphic on 3mm ACM. Installation priced separately.'),
              ('Yard signs', 'Signs', 3, 'piece', '8', '2.5', '15', '5', '30', 1, 24, 18, 48, 96, True, '4mm corrugated plastic; hardware and installation not included.'),
              ('Window Graphics', 'Windows', 3, 'sqft', '10.5', '4.25', '0', '0', '75', 1, 44, 92, 54, 1200, False, 'Window graphics with your choice of perforated window vinyl or standard opaque vinyl. Add each window or panel size separately. Lamination is not included.'),
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
                    'supports_multiple_dimensions': ('vehicle wrap' in name.lower() or category.lower() == 'windows'),
                    'storefront_categories': (
                        ['Storefront'] if category.lower() == 'windows' else
                        ['Vehicles','Fleet Services'] if 'vehicle wrap' in name.lower() else
                        ['Vehicles','Fleet Services','Signs'] if 'magnet' in name.lower() else
                        ['Stickers'] if 'transfer sticker' in name.lower() else
                        ['Stickers'] if any(x in name.lower() for x in ('sticker','label')) else
                        ['Storefront','Signs'] if any(x in name.lower() for x in ('acrylic sign face','banner','acm')) else
                        ['Signs'] if 'yard sign' in name.lower() else []
                    ),
                    'size_options': (
                        [{'label':'18 x 12 in','width':'18','height':'12'},
                         {'label':'24 x 12 in','width':'24','height':'12'},
                         {'label':'24 x 18 in','width':'24','height':'18'}]
                        if 'magnet' in name.lower() else []
                    ),
                    'quantity_presets': [1,2,5,10,25,50] if 'magnet' in name.lower() else [],
                    'max_short_axis': '24' if 'magnet' in name.lower() else '10000',
                    'max_long_axis': '48' if 'magnet' in name.lower() else '10000',
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
                        [{'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                         {'id':'gloss','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                         {'id':'premium_matte','label':'Matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}]
                        if 'die-cut sticker' in name.lower() else
                        [{'id':'cast_gloss','label':'Cast gloss laminate (included)','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                         {'id':'cast_matte','label':'Cast matte laminate (included)','sell_per_sqft':'0','cost_per_sqft':'0','default':False}]
                        if 'vehicle wrap' in name.lower() else
                        []
                        if category.lower() == 'windows' else
                        [{'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                         {'id':'gloss','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                         {'id':'premium_matte','label':'Matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}]
                        if any(x in name.lower() for x in ('label','magnet','acm','yard sign','acrylic')) else []
                    ),
                    'material_options': (
                        [{'id':'perforated','label':'Perforated window vinyl','sell_per_sqft_adjustment':'0','cost_per_sqft_adjustment':'0','default':True},
                         {'id':'opaque','label':'Standard opaque vinyl','sell_per_sqft_adjustment':'0','cost_per_sqft_adjustment':'0','default':False}]
                        if category.lower() == 'windows' else []
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
                'minimum_price':'0','waste_percent':'15','labor_minutes_per_unit':'0',
                'min_quantity':1,'max_quantity':100000,'default_width':3,'default_height':3,
                'min_width':3,'min_height':3,'max_width':24,'max_height':48,'instant':True,
                'description':'Precision-cut transfer stickers for lettering and graphics without a printed background. Minimum finished size is 3 x 3 inches.',
                'is_wrap':False,'requires_installation':False,'supports_installation':False,
                'supports_multiple_dimensions':False,'self_approve_artwork':True,'usdot_customizer':False,
                'storefront_categories':['Stickers'],'size_options':[],'placement_options':[],'quantity_presets':[],'material_options':[],
                'quantity_price_table':[
                    {'quantity':50,'total':'60'},{'quantity':100,'total':'73'},{'quantity':200,'total':'95'},
                    {'quantity':300,'total':'115'},{'quantity':500,'total':'152'},{'quantity':1000,'total':'232'},
                    {'quantity':2000,'total':'371'},{'quantity':3000,'total':'496'},
                    {'quantity':5000,'total':'723'},{'quantity':10000,'total':'1225'}
                ],
                'price_table_base_width':'3','price_table_base_height':'3','price_table_size_weight':'0.45',
                'lamination_options':[
                    {'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'gloss','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                    {'id':'premium_matte','label':'Matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}
                ],
                'tiers':[{'from':1,'multiplier':'1'}]
            })
            conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?,?)',
                         ('Transfer stickers','Stickers',1,1,sticker_workflow['id'] if sticker_workflow else 1,json.dumps(transfer_cfg),now()))
        sticker_workflow_for_decals = conn.execute("SELECT id FROM workflows WHERE name='Stickers and labels'").fetchone()
        if not conn.execute("SELECT id FROM products WHERE lower(name)='decals' LIMIT 1").fetchone():
            decal_cfg = validate_config({
                'unit':'piece','sell_per_sqft':'18','cost_per_sqft':'4','setup_price':'10','setup_cost':'6',
                'minimum_price':'0','waste_percent':'15','labor_minutes_per_unit':'0','min_quantity':1,
                'max_quantity':100000,'default_width':6,'default_height':6,'min_width':1,'min_height':1,
                'max_width':48,'max_height':48,'instant':True,
                'description':'Custom printed vinyl decals for windows, equipment, vehicles and general signage.',
                'is_wrap':False,'requires_installation':False,'supports_installation':False,
                'supports_multiple_dimensions':False,'self_approve_artwork':True,'usdot_customizer':False,
                'storefront_categories':['Vehicles','Fleet Services','Stickers'],'size_options':[],'quantity_presets':[1,2,5,10,25,50],
                'material_options':[],
                'lamination_options':[
                    {'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'gloss','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                    {'id':'premium_matte','label':'Matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}
                ],
                'tiers':[{'from':1,'multiplier':'1'},{'from':10,'multiplier':'.95'},{'from':25,'multiplier':'.90'},{'from':50,'multiplier':'.85'},{'from':100,'multiplier':'.80'}]
            })
            conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?,?)',
                         ('Decals','Stickers',1,1,sticker_workflow_for_decals['id'] if sticker_workflow_for_decals else 1,json.dumps(decal_cfg),now()))
        if not conn.execute("SELECT id FROM products WHERE lower(name)='usdot decals' LIMIT 1").fetchone():
            usdot_cfg = validate_config({
                'unit':'piece','sell_per_sqft':'20','cost_per_sqft':'4','setup_price':'12','setup_cost':'6',
                'minimum_price':'0','waste_percent':'15','labor_minutes_per_unit':'0','min_quantity':1,
                'max_quantity':1000,'default_width':18,'default_height':12,'min_width':3,'min_height':3,
                'max_width':48,'max_height':48,'max_short_axis':24,'max_long_axis':48,'instant':True,
                'description':'Basic USDOT identification decals with an instant text preview. Enter your company information and choose a lettering style before ordering.',
                'is_wrap':False,'requires_installation':False,'supports_installation':False,
                'supports_multiple_dimensions':False,'self_approve_artwork':True,'usdot_customizer':True,
                'storefront_categories':['Vehicles','Fleet Services'],'quantity_presets':[1,2,5,10,25,50],'size_options':[
                    {'label':'18 x 12 in','width':'18','height':'12'},
                    {'label':'24 x 12 in','width':'24','height':'12'},
                    {'label':'24 x 18 in','width':'24','height':'18'}
                ],
                'material_options':[],
                'lamination_options':[
                    {'id':'none','label':'No laminate','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'gloss','label':'Gloss laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False},
                    {'id':'premium_matte','label':'Matte laminate','sell_per_sqft':'2','cost_per_sqft':'1','default':False}
                ],
                'tiers':[{'from':1,'multiplier':'1'},{'from':5,'multiplier':'.95'},{'from':10,'multiplier':'.90'},{'from':25,'multiplier':'.85'},{'from':50,'multiplier':'.80'}]
            })
            conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?,?)',
                         ('USDOT Decals','Stickers',1,1,sticker_workflow_for_decals['id'] if sticker_workflow_for_decals else 1,json.dumps(usdot_cfg),now()))
        vehicle_workflow_for_fleet = conn.execute("SELECT id FROM workflows WHERE name='Vehicle wraps'").fetchone()
        partial_coverage = [
            {'id':'spot','label':'Spot graphics / logos','description':'Logos, names, numbers and smaller branded areas.','multiplier':'0.18'},
            {'id':'doors','label':'Door graphics','description':'Driver and passenger door coverage.','multiplier':'0.25'},
            {'id':'hood','label':'Hood wrap','description':'Hood-focused color or printed graphic coverage.','multiplier':'0.20'},
            {'id':'roof','label':'Roof wrap','description':'Roof-focused coverage or color change.','multiplier':'0.20'},
            {'id':'half','label':'Half wrap','description':'Approximately half of the visible body area.','multiplier':'0.55'},
            {'id':'three_quarter','label':'3/4 wrap','description':'High-impact coverage on most visible body panels.','multiplier':'0.78'},
            {'id':'full','label':'Full wrap','description':'Full exterior wrap coverage, subject to vehicle review.','multiplier':'1'}
        ]
        vehicle_types = [
            {'id':'car','label':'Car / sedan','multiplier':'1'},
            {'id':'suv','label':'SUV / crossover','multiplier':'1.15'},
            {'id':'pickup','label':'Pickup truck','multiplier':'1.2'},
            {'id':'cargo_van','label':'Cargo / service van','multiplier':'1.35'}
        ]
        if not conn.execute("SELECT id FROM products WHERE lower(name)='partial vehicle wraps' LIMIT 1").fetchone():
            partial_wrap_cfg = validate_config({
                'unit':'piece','sell_per_sqft':'2200','cost_per_sqft':'700','setup_price':'0','setup_cost':'0',
                'minimum_price':'450','waste_percent':'10','labor_minutes_per_unit':'0',
                'installation_minutes_per_sqft':'600','installation_setup_minutes':'0',
                'min_quantity':1,'max_quantity':200,'default_width':12,'default_height':12,
                'min_width':12,'min_height':12,'max_width':12,'max_height':12,'instant':False,'quantity_only':True,
                'quantity_only_note':'Starting wrap estimate by coverage and vehicle type. Final pricing is reviewed for exact body shape, prep, removals, access and installation conditions.',
                'description':'Choose a visual coverage option for a fast partial-wrap estimate. Upload multiple artwork/reference files with your request. Installation and final panel plan are reviewed before production.',
                'is_wrap':True,'requires_installation':False,'supports_installation':True,
                'installation_workflow_id':vehicle_workflow_for_fleet['id'] if vehicle_workflow_for_fleet else 4,
                'supports_multiple_dimensions':False,'self_approve_artwork':False,'usdot_customizer':False,
                'storefront_categories':['Vehicles','Fleet Services'],'size_options':[],'placement_options':[],
                'quantity_presets':[1,2,5,10,25,50],'coverage_options':partial_coverage,
                'vehicle_type_options':vehicle_types,'material_options':[],
                'lamination_options':[
                    {'id':'cast_gloss','label':'Cast gloss laminate (included)','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'cast_matte','label':'Cast matte laminate (included)','sell_per_sqft':'0','cost_per_sqft':'0','default':False}
                ],
                'tiers':[
                    {'from':1,'multiplier':'1'},
                    {'from':5,'multiplier':'0.96'},
                    {'from':10,'multiplier':'0.92'},
                    {'from':25,'multiplier':'0.88'},
                    {'from':50,'multiplier':'0.84'}
                ]
            })
            conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?,?)',
                         ('Partial Vehicle Wraps','Vehicle Wraps',1,1,vehicle_workflow_for_fleet['id'] if vehicle_workflow_for_fleet else 4,json.dumps(partial_wrap_cfg),now()))
        trailer_coverage = [
            {'id':'lettering','label':'Lettering / decals only','description':'Logos, menus, contact info and smaller branded areas.','multiplier':'0.18'},
            {'id':'partial','label':'Partial wrap','description':'Focused branded sections with substantial original surface showing.','multiplier':'0.50'},
            {'id':'sides','label':'Sides only','description':'Primary left and right side coverage.','multiplier':'0.65'},
            {'id':'sides_rear','label':'Sides + rear','description':'Both sides plus rear door / rear panel coverage.','multiplier':'0.80'},
            {'id':'three_quarter','label':'3/4 wrap','description':'Most visible surfaces covered, with selective uncovered areas.','multiplier':'0.88'},
            {'id':'full','label':'Full wrap','description':'Full exterior wrap coverage, subject to body and access review.','multiplier':'1'}
        ]
        trailer_types = [
            {'id':'small_trailer','label':'Small enclosed trailer','multiplier':'0.8'},
            {'id':'large_trailer','label':'Large enclosed trailer','multiplier':'1'},
            {'id':'food_truck','label':'Food truck','multiplier':'1.35'},
            {'id':'box_truck','label':'Box truck','multiplier':'1.45'}
        ]
        if not conn.execute("SELECT id FROM products WHERE lower(name)='trailer / food truck wraps' LIMIT 1").fetchone():
            trailer_wrap_cfg = validate_config({
                'unit':'piece','sell_per_sqft':'3000','cost_per_sqft':'950','setup_price':'0','setup_cost':'0',
                'minimum_price':'650','waste_percent':'10','labor_minutes_per_unit':'0',
                'installation_minutes_per_sqft':'720','installation_setup_minutes':'0',
                'min_quantity':1,'max_quantity':100,'default_width':12,'default_height':12,
                'min_width':12,'min_height':12,'max_width':12,'max_height':12,'instant':False,'quantity_only':True,
                'quantity_only_note':'Starting wrap estimate by coverage and trailer / truck type. Final pricing is reviewed for exact dimensions, doors, windows, rivets, equipment, prep and installation access.',
                'description':'Trailer and food-truck wrap estimates from lettering through full coverage. Choose the coverage visually, add optional approximate dimensions, and upload multiple artwork/reference files with your request.',
                'is_wrap':True,'requires_installation':False,'supports_installation':True,
                'installation_workflow_id':vehicle_workflow_for_fleet['id'] if vehicle_workflow_for_fleet else 4,
                'supports_multiple_dimensions':False,'self_approve_artwork':False,'usdot_customizer':False,
                'storefront_categories':['Trailers / Food Trucks','Fleet Services'],'size_options':[],'placement_options':[],
                'quantity_presets':[1,2,5,10,25],'coverage_options':trailer_coverage,
                'vehicle_type_options':trailer_types,'material_options':[],
                'lamination_options':[
                    {'id':'cast_gloss','label':'Cast gloss laminate (included)','sell_per_sqft':'0','cost_per_sqft':'0','default':True},
                    {'id':'cast_matte','label':'Cast matte laminate (included)','sell_per_sqft':'0','cost_per_sqft':'0','default':False}
                ],
                'tiers':[
                    {'from':1,'multiplier':'1'},
                    {'from':5,'multiplier':'0.96'},
                    {'from':10,'multiplier':'0.92'},
                    {'from':25,'multiplier':'0.88'}
                ]
            })
            conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?,?)',
                         ('Trailer / Food Truck Wraps','Vehicle Wraps',1,1,vehicle_workflow_for_fleet['id'] if vehicle_workflow_for_fleet else 4,json.dumps(trailer_wrap_cfg),now()))
        if not conn.execute("SELECT id FROM products WHERE lower(name)='fleet window tinting' LIMIT 1").fetchone():
            fleet_tint_cfg = validate_config({
                'unit':'piece','sell_per_sqft':'350','cost_per_sqft':'0','setup_price':'0','setup_cost':'0',
                'minimum_price':'350','waste_percent':'0','labor_minutes_per_unit':'0',
                'min_quantity':1,'max_quantity':500,'default_width':12,'default_height':12,
                'min_width':12,'min_height':12,'max_width':12,'max_height':12,
                'instant':False,'quantity_only':True,
                'description':'Fleet window tinting starting at a retail single-vehicle baseline. Final pricing is reviewed by vehicle, glass coverage, film choice and access. Larger fleets receive progressively better volume pricing.',
                'is_wrap':False,'requires_installation':True,'supports_installation':False,
                'supports_multiple_dimensions':False,'self_approve_artwork':False,'usdot_customizer':False,
                'storefront_categories':['Fleet Services'],'size_options':[],'placement_options':[],
                'quantity_presets':[1,2,5,10,25,50],'material_options':[],'lamination_options':[],
                'tiers':[
                    {'from':1,'multiplier':'1'},
                    {'from':5,'multiplier':'0.95'},
                    {'from':10,'multiplier':'0.90'},
                    {'from':25,'multiplier':'0.85'},
                    {'from':50,'multiplier':'0.80'}
                ]
            })
            conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?,?)',
                         ('Fleet Window Tinting','Fleet Services',1,1,vehicle_workflow_for_fleet['id'] if vehicle_workflow_for_fleet else 4,json.dumps(fleet_tint_cfg),now()))
        apparel_workflow = conn.execute("SELECT id FROM workflows WHERE name='Signs and storefronts'").fetchone()
        apparel_profiles = {
            'DTF transfers': {
                'sell_per_sqft':'8.64','setup_price':'0','minimum_price':'0','instant':True,
                'default_width':3.5,'default_height':3.5,'min_width':1,'min_height':1,
                'max_width':14,'max_height':14,'max_short_axis':12,'max_long_axis':14,
                'self_approve_artwork':True,
                'description':'Ready-to-press DTF transfers priced by print area. Choose a standard apparel placement size or use Custom size. Garments and pressing are not included.',
                'placement_options':[
                    {'id':'adult_left_chest','label':'Adult left chest — 3.5 x 3.5 in','width':'3.5','height':'3.5'},
                    {'id':'adult_right_chest','label':'Adult right chest — 3.5 x 3.5 in','width':'3.5','height':'3.5'},
                    {'id':'adult_full_front','label':'Adult full front — 11 x 11 in','width':'11','height':'11'},
                    {'id':'adult_full_back','label':'Adult full back — 11 x 11 in','width':'11','height':'11'},
                    {'id':'youth_full_front','label':'Youth full front — 10.5 x 10.5 in','width':'10.5','height':'10.5'},
                    {'id':'youth_full_back','label':'Youth full back — 10.5 x 10.5 in','width':'10.5','height':'10.5'},
                    {'id':'youth_small_front','label':'Youth small full front — 8.5 x 8.5 in','width':'8.5','height':'8.5'},
                    {'id':'toddler_front','label':'Toddler full front — 5.5 x 5.5 in','width':'5.5','height':'5.5'}
                ]
            },
            'Embroidered hats': {
                'sell_per_sqft':'0','setup_price':'35','minimum_price':'35','instant':False,
                'default_width':4,'default_height':2.25,'min_width':1,'min_height':1,'max_width':5,'max_height':3,
                'self_approve_artwork':False,
                'description':'$35 digitizing charge for every embroidery order. Hat embroidery is front placement only. Garment and stitch-count pricing is reviewed before quoting. Over-complex artwork may be rejected or simplified for an additional design fee.',
                'placement_options':[{'id':'front','label':'Front — up to 4 x 2.25 in','width':'4','height':'2.25'}]
            },
            'Embroidered polos': {
                'sell_per_sqft':'0','setup_price':'35','minimum_price':'35','instant':False,
                'default_width':3.5,'default_height':3.5,'min_width':1,'min_height':1,'max_width':4.5,'max_height':4.5,
                'self_approve_artwork':False,
                'description':'$35 digitizing charge for every embroidery order. Choose left chest or right chest. Garment and stitch-count pricing is reviewed before quoting. Over-complex artwork may be rejected or simplified for an additional design fee.',
                'placement_options':[
                    {'id':'left_chest','label':'Left chest — 3.5 x 3.5 in','width':'3.5','height':'3.5'},
                    {'id':'right_chest','label':'Right chest — 3.5 x 3.5 in','width':'3.5','height':'3.5'}
                ]
            }
        }
        for apparel_name, profile in apparel_profiles.items():
            if not conn.execute('SELECT id FROM products WHERE lower(name)=lower(?) LIMIT 1', (apparel_name,)).fetchone():
                apparel_cfg = validate_config({
                    'unit':'piece','sell_per_sqft':profile['sell_per_sqft'],'cost_per_sqft':'0',
                    'setup_price':profile['setup_price'],'setup_cost':'0','minimum_price':profile['minimum_price'],
                    'waste_percent':'0','labor_minutes_per_unit':'0','min_quantity':1,'max_quantity':100000,
                    'default_width':profile['default_width'],'default_height':profile['default_height'],
                    'min_width':profile['min_width'],'min_height':profile['min_height'],
                    'max_width':profile['max_width'],'max_height':profile['max_height'],
                    'max_short_axis':profile.get('max_short_axis',10000),'max_long_axis':profile.get('max_long_axis',10000),
                    'instant':profile['instant'],'description':profile['description'],
                    'is_wrap':False,'requires_installation':False,'supports_installation':False,
                    'supports_multiple_dimensions':False,'self_approve_artwork':profile['self_approve_artwork'],
                    'storefront_categories':['Apparel'],'size_options':[],'placement_options':profile['placement_options'],
                    'material_options':[],'lamination_options':[],'tiers':[{'from':1,'multiplier':'1'}]
                })
                conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,?,?,?,?,?)',
                             (apparel_name,'Apparel',1,1,apparel_workflow['id'] if apparel_workflow else 3,json.dumps(apparel_cfg),now()))
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
            wrap_demo = conn.execute("SELECT id FROM products WHERE name='Vehicle Wraps' AND active=1 ORDER BY id LIMIT 1").fetchone()
            for title, name, product_id, width, height, qty in [
                ('250 die-cut brand stickers', 'Sample Coffee Co.', 1, 3, 3, 250),
                ('Grand opening banner', 'Sample Market', 4, 96, 36, 1),
                ('Delivery van wrap inquiry', 'Sample Fleet', wrap_demo['id'] if wrap_demo else 9, 180, 120, 1)]:
                create_job(conn, {'title': title, 'customer_name': name, 'customer_email': 'customer@example.test',
                           'items': [{'product_id': product_id, 'width': width, 'height': height, 'quantity': qty}]}, actor='Demo setup')
    return credentials
