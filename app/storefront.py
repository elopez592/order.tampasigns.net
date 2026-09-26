"""Customer catalog additions and finished garment pricing."""
import json
import re
from fastapi import HTTPException
from .db import transaction, now

COLORS = {'White': '#ffffff', 'Black': '#252525', 'Navy': '#182b49', 'Royal': '#2453a0', 'Red': '#bd2437', 'Sport Grey': '#a8a8a8'}
SIZES = ['S', 'M', 'L', 'XL', '2XL', '3XL']
EMBROIDERY_KINDS = {
    'embroidered_polo': 'Embroidered polo',
    'embroidered_hat': 'Embroidered hat',
    'embroidered_hoodie': 'Embroidered hoodie',
}
CHEST_PLACEMENTS = [
    {'id': 'left_chest', 'label': 'Left chest — up to 4.5 x 4.5 in', 'width': '4.5', 'height': '4.5'},
    {'id': 'right_chest', 'label': 'Right chest — up to 4.5 x 4.5 in', 'width': '4.5', 'height': '4.5'},
]
HAT_PLACEMENTS = [{'id': 'front', 'label': 'Front — up to 4 x 2.25 in', 'width': '4', 'height': '2.25'}]
PRINTS = {'front': 'Full front', 'back': 'Full back', 'left_chest': 'Left chest'}
PRINT_PRICES = {'front': 30, 'back': 30, 'left_chest': 25}
EMBROIDERY_TEXT_LINE_PRICE = 7


def upgrade_catalog(database):
    from .pricing import validate_config
    with transaction(database, True) as conn:
        for row in conn.execute('SELECT * FROM products').fetchall():
            cfg = json.loads(row['config'])
            cats = cfg.get('storefront_categories', [])
            name = row['name']
            active, public = row['active'], row['public']
            # Retain old product records for existing jobs while retiring them from sale.
            if (name in ('Embroidered T-shirts', 'Embroidered jackets') or
                    cfg.get('apparel_kind') in ('embroidered_shirt', 'embroidered_jacket')):
                active, public = 0, 0
            if name in ('Die-cut stickers', 'Decals'):
                cfg['contour_customizer'] = True
            if 'banner' in name.lower() or name == 'Custom T-shirts':
                cats = list(dict.fromkeys(cats + ['Events']))
            if name == 'DTF transfers':
                name = 'Custom T-shirts'
                cfg.update(finished_apparel=True, sell_per_sqft='30', setup_price='0', setup_cost='0', cost_per_sqft='0',
                           minimum_price='0', default_width='12', default_height='12', max_width='12', max_height='12',
                           placement_options=[], quantity_only=True, self_approve_artwork=False,
                           description='Custom Gildan Heavy Cotton 5000 shirts. Choose a color, sizes and one print location, then upload your design for proofing.',
                           tiers=[{'from': 1, 'multiplier': '1'}, {'from': 6, 'multiplier': '.9'}, {'from': 12, 'multiplier': '.85'}, {'from': 24, 'multiplier': '.8'}, {'from': 48, 'multiplier': '.75'}])
                cats = ['Apparel', 'Events']
            if name == 'Custom T-shirts':
                cfg.update(finished_apparel=True, shirt_colors=COLORS, shirt_sizes=SIZES,
                           apparel_kind='custom_shirt', digitizing_fee='0',
                           description='Custom Gildan Heavy Cotton 5000 shirts. Choose a color, sizes and one or more print locations, then upload your design for proofing.')
                cats = ['Apparel', 'Events']
            if name == 'Embroidered hats':
                cfg.update(
                    finished_apparel=True, apparel_kind='embroidered_hat', quote_only=True,
                    shirt_colors=COLORS, shirt_sizes=['Adjustable'], digitizing_fee='35',
                    placement_options=HAT_PLACEMENTS,
                    apparel_unit_price=cfg.get('apparel_unit_price') if float(cfg.get('apparel_unit_price') or 0) > 0 else '35',
                    setup_price='0', minimum_price='0', instant=False,
                    description='Choose a hat color and quantity. Product pricing is calculated first, then a one-time $35 digitizing fee is added to the embroidery order.'
                )
                cats = ['Apparel']
            if name == 'Embroidered polos':
                cfg.update(
                    finished_apparel=True, apparel_kind='embroidered_polo', quote_only=True,
                    shirt_colors=COLORS, shirt_sizes=SIZES, digitizing_fee='35',
                    placement_options=CHEST_PLACEMENTS,
                    apparel_unit_price=cfg.get('apparel_unit_price') if float(cfg.get('apparel_unit_price') or 0) > 0 else '35',
                    setup_price='0', minimum_price='0', instant=False,
                    description='Choose polo colors, sizes and chest placement. Product pricing is calculated first, then a one-time $35 digitizing fee is added to the embroidery order.'
                )
                cats = ['Apparel']
            if name == 'Window Graphics':
                cfg.update(
                    storefront_categories=['Storefront'], supports_multiple_dimensions=True,
                    material_options=[
                        {'id':'opaque','label':'Standard opaque vinyl','sell_per_sqft_adjustment':'0','cost_per_sqft_adjustment':'0','default':True},
                        {'id':'perforated','label':'Perforated window vinyl','sell_per_sqft_adjustment':'3','cost_per_sqft_adjustment':'1.5','default':False},
                    ],
                    description='Window graphics priced by material. Standard opaque vinyl is the base rate; perforated window vinyl costs more. Add each window or panel separately.'
                )
                cats = ['Storefront']
            if name == 'Fleet Window Tinting':
                cfg.update(
                    sell_per_sqft='200', minimum_price='200', instant=False, quote_only=False,
                    quantity_only=True, requires_installation=True, vehicle_details_required=True,
                    tint_package_selector=True, artwork_upload_disabled=True, material_options=[],
                    coverage_options=[
                        {'id':'full_ceramic','label':'Full ceramic — 4 side windows + front and rear windshields','description':'Standard vehicle package. Larger or additional windows cost extra.','multiplier':'3'},
                        {'id':'windshield','label':'Windshield only','description':'Ceramic tint for the front windshield.','multiplier':'1'},
                        {'id':'windshield_fronts','label':'Windshield + 2 front windows','description':'Ceramic tint for the windshield and two front side windows.','multiplier':'1.5'},
                    ],
                    description='Ceramic vehicle tint packages: windshield only $200, windshield plus two front windows $300, or full standard-vehicle tint $600. Larger or additional windows cost extra after review.',
                    quantity_only_note='Choose a ceramic tint package. Vehicle year, make and model are required; larger glass or additional windows are confirmed after review.'
                )
                cats = ['Fleet Services']
            if name == 'Storefront Window Tinting':
                cfg.update(
                    unit='sqft', sell_per_sqft='10.5', cost_per_sqft='4.25', minimum_price='75',
                    default_width='44', default_height='92', min_width='1', min_height='1',
                    max_width='54', max_height='1200', instant=False, quote_only=False,
                    supports_multiple_dimensions=True, requires_installation=True,
                    artwork_upload_disabled=True, material_options=[], lamination_options=[],
                    description='Storefront window tinting priced by measured glass area. Add each window or panel separately; installation and film selection are confirmed after review.'
                )
                cats = ['Storefront']
            if name == 'Banners':
                cats = list(dict.fromkeys(cats + ['Construction signs']))
            if name in ('Construction signs', 'Aluminum Composite Signs'):
                name = 'Aluminum Composite Signs'
                cfg.update(
                    unit='sqft', sell_per_sqft='14', cost_per_sqft='5',
                    setup_price='0', setup_cost='0', waste_percent='15',
                    labor_minutes_per_unit='0', minimum_price='65',
                    default_width='24', default_height='48',
                    min_width='24', min_height='48', max_width='60', max_height='120',
                    max_short_axis='60', max_long_axis='120', instant=True,
                    quote_only=False,
                    size_options=[
                        {'label':'2 × 4 ft','width':'24','height':'48'},
                        {'label':'3 × 6 ft','width':'36','height':'72'},
                        {'label':'4 × 8 ft','width':'48','height':'96'},
                        {'label':'5 × 10 ft','width':'60','height':'120'},
                    ],
                    description='Durable 3mm aluminum composite signs with common construction and property-sign sizes from 2 × 4 through 5 × 10 feet.'
                )
                cats = ['Construction signs', 'Signs']
            if name == 'Roll-up banners':
                cfg.update(
                    unit='sqft', sell_per_sqft='8.181818', cost_per_sqft='0', minimum_price='150',
                    default_width='33', default_height='80', min_width='33', min_height='80',
                    max_width='33', max_height='80', instant=True, quote_only=False, quantity_only=True,
                    quantity_only_note='$150 each, including the 33 × 80 inch printed banner and roll-up stand.',
                    size_options=[], material_options=[], lamination_options=[],
                    description='One 33 × 80 inch roll-up banner with the printed banner and retractable stand included. Starts at $150.'
                )
                cats = ['Storefront', 'Events']
            if name == 'A-Frame inserts':
                cfg.update(
                    unit='sqft', sell_per_sqft='0', cost_per_sqft='0', setup_price='0', setup_cost='0',
                    waste_percent='0', labor_minutes_per_unit='0', minimum_price='0',
                    default_width='24', default_height='36', min_width='24', min_height='36',
                    max_width='24', max_height='36', instant=True, quote_only=False,
                    quantity_only=True,
                    quantity_only_note='Standard 24 x 36 inch inserts. One insert is $49, two inserts are $80. Add an A-frame stand for $99.',
                    quantity_presets=[1, 2],
                    quantity_price_table=[
                        {'quantity': 1, 'total': '49'},
                        {'quantity': 2, 'total': '80'},
                    ],
                    price_table_base_width='24', price_table_base_height='36', price_table_size_weight='1',
                    material_options=[
                        {'id':'inserts','label':'Printed inserts only','sell_per_sqft_adjustment':'0','cost_per_sqft_adjustment':'0','flat_price_adjustment':'0','flat_cost_adjustment':'0','default':True},
                        {'id':'with_frame','label':'Add A-frame stand — +$99','sell_per_sqft_adjustment':'0','cost_per_sqft_adjustment':'0','flat_price_adjustment':'99','flat_cost_adjustment':'0','default':False},
                    ],
                    description='Standard 24 x 36 inch printed A-frame inserts. One insert is $49, two inserts are $80, and the A-frame stand is an extra $99.'
                )
                cats = ['Storefront', 'Events']
            if name in ('1/4 inch foam board', 'Foam boards'):
                name = 'Foam boards'
                cfg.update(
                    unit='sqft', sell_per_sqft='4', cost_per_sqft='2', minimum_price='25',
                    default_width='24', default_height='36', min_width='1', min_height='1',
                    max_width='48', max_height='96', max_short_axis='48', max_long_axis='96',
                    instant=True, quote_only=False, quantity_only=False,
                    material_options=[
                        {'id':'quarter','label':'1/4 inch foam board — $4/sq ft','sell_per_sqft_adjustment':'0','cost_per_sqft_adjustment':'0','default':True},
                        {'id':'half','label':'1/2 inch foam board — $6/sq ft','sell_per_sqft_adjustment':'2','cost_per_sqft_adjustment':'1','default':False},
                    ],
                    size_options=[
                        {'label':'18 × 24 in','width':'18','height':'24'},
                        {'label':'24 × 36 in','width':'24','height':'36'},
                        {'label':'36 × 48 in','width':'36','height':'48'},
                        {'label':'48 × 96 in','width':'48','height':'96'},
                    ],
                    description='Printed foam board in 1/4-inch or 1/2-inch thickness. Maximum finished sheet size is 4 × 8 feet.'
                )
                cats = ['Storefront', 'Events']
            if name == '1/2 inch foam board':
                active, public = 0, 0
            cfg['storefront_categories'] = cats
            if (cfg != json.loads(row['config']) or name != row['name']
                    or active != row['active'] or public != row['public']):
                conn.execute('UPDATE products SET name=?,active=?,public=?,config=?,version=version+1,updated_at=? WHERE id=?',
                             (name, active, public, json.dumps(cfg), now(), row['id']))
        workflow = conn.execute('SELECT id FROM workflows ORDER BY id LIMIT 1').fetchone()['id']
        additions = {
            'Roll-up banners': dict(
                category='Events', storefront_categories=['Storefront','Events'], unit='sqft',
                sell_per_sqft='8.181818', cost_per_sqft='0', setup_price='0', setup_cost='0',
                waste_percent='0', labor_minutes_per_unit='0', minimum_price='150',
                default_width='33', default_height='80', min_width='33', min_height='80', max_width='33', max_height='80',
                instant=True, quantity_only=True,
                quantity_only_note='$150 each, including the 33 × 80 inch printed banner and roll-up stand.',
                description='One 33 × 80 inch roll-up banner with the printed banner and retractable stand included. Starts at $150.'
            ),
            'Foam boards': dict(
                category='Storefront', storefront_categories=['Storefront','Events'], unit='sqft',
                sell_per_sqft='4', cost_per_sqft='2', setup_price='0', setup_cost='0',
                waste_percent='0', labor_minutes_per_unit='0', minimum_price='25',
                default_width='24', default_height='36', min_width='1', min_height='1', max_width='48', max_height='96',
                max_short_axis='48', max_long_axis='96', instant=True,
                material_options=[
                    {'id':'quarter','label':'1/4 inch foam board — $4/sq ft','sell_per_sqft_adjustment':'0','cost_per_sqft_adjustment':'0','default':True},
                    {'id':'half','label':'1/2 inch foam board — $6/sq ft','sell_per_sqft_adjustment':'2','cost_per_sqft_adjustment':'1','default':False},
                ],
                size_options=[
                    {'label':'18 × 24 in','width':'18','height':'24'},
                    {'label':'24 × 36 in','width':'24','height':'36'},
                    {'label':'36 × 48 in','width':'36','height':'48'},
                    {'label':'48 × 96 in','width':'48','height':'96'},
                ],
                description='Printed foam board in 1/4-inch or 1/2-inch thickness. Maximum finished sheet size is 4 × 8 feet.'
            ),
            'Storefront Window Tinting': dict(
                category='Storefront', storefront_categories=['Storefront'], unit='sqft',
                sell_per_sqft='10.5', cost_per_sqft='4.25', setup_price='0', setup_cost='0',
                waste_percent='0', labor_minutes_per_unit='0', minimum_price='75',
                default_width='44', default_height='92', min_width='1', min_height='1', max_width='54', max_height='1200',
                instant=False, supports_multiple_dimensions=True, requires_installation=True,
                artwork_upload_disabled=True,
                description='Storefront window tinting priced by measured glass area. Add each window or panel separately; installation and film selection are confirmed after review.'
            ),
            'A-Frame inserts': dict(
                category='Storefront', storefront_categories=['Storefront','Events'], unit='sqft',
                sell_per_sqft='0', cost_per_sqft='0', setup_price='0', setup_cost='0',
                waste_percent='0', labor_minutes_per_unit='0', minimum_price='0',
                default_width='24', default_height='36', min_width='24', min_height='36', max_width='24', max_height='36',
                instant=True, quantity_only=True,
                quantity_only_note='Standard 24 x 36 inch inserts. One insert is $49, two inserts are $80. Add an A-frame stand for $99.',
                quantity_presets=[1, 2],
                quantity_price_table=[
                    {'quantity': 1, 'total': '49'},
                    {'quantity': 2, 'total': '80'},
                ],
                price_table_base_width='24', price_table_base_height='36', price_table_size_weight='1',
                material_options=[
                    {'id':'inserts','label':'Printed inserts only','sell_per_sqft_adjustment':'0','cost_per_sqft_adjustment':'0','flat_price_adjustment':'0','flat_cost_adjustment':'0','default':True},
                    {'id':'with_frame','label':'Add A-frame stand — +$99','sell_per_sqft_adjustment':'0','cost_per_sqft_adjustment':'0','flat_price_adjustment':'99','flat_cost_adjustment':'0','default':False},
                ],
                description='Standard 24 x 36 inch printed A-frame inserts. One insert is $49, two inserts are $80, and the A-frame stand is an extra $99.'
            ),
            'Aluminum Composite Signs': dict(
                category='Construction signs', storefront_categories=['Construction signs','Signs'], unit='sqft',
                sell_per_sqft='14', cost_per_sqft='5', setup_price='0', setup_cost='0',
                waste_percent='15', labor_minutes_per_unit='0', minimum_price='65',
                default_width='24', default_height='48', min_width='24', min_height='48', max_width='60', max_height='120',
                max_short_axis='60', max_long_axis='120', instant=True,
                size_options=[
                    {'label':'2 × 4 ft','width':'24','height':'48'},
                    {'label':'3 × 6 ft','width':'36','height':'72'},
                    {'label':'4 × 8 ft','width':'48','height':'96'},
                    {'label':'5 × 10 ft','width':'60','height':'120'},
                ],
                description='Durable 3mm aluminum composite signs with common construction and property-sign sizes from 2 × 4 through 5 × 10 feet.'
            ),
            'High-Density Board Signs': dict(
                category='Construction signs', storefront_categories=['Construction signs','Signs'], unit='sqft',
                sell_per_sqft='20', cost_per_sqft='6', setup_price='0', setup_cost='0',
                waste_percent='15', labor_minutes_per_unit='0', minimum_price='240',
                default_width='36', default_height='48', min_width='36', min_height='36',
                min_short_axis='36', min_long_axis='48',
                max_width='96', max_height='96', max_short_axis='48', max_long_axis='96',
                instant=True, quote_only=False, self_approve_artwork=False,
                size_options=[
                    {'label':'3 × 4 ft','width':'36','height':'48'},
                    {'label':'4 × 6 ft','width':'48','height':'72'},
                    {'label':'4 × 8 ft','width':'48','height':'96'},
                ],
                description='Flat printed outdoor sign on standard 1/2-inch high-density urethane board. Standard sizes start at 3 × 4 feet at $20/sq ft. Routed, carved, dimensional, painted or specialty-finished HDU work is quoted separately.'
            ),
        }
        for name, kind in (('Embroidered hoodies', 'embroidered_hoodie'),):
            additions[name] = dict(
                category='Apparel', storefront_categories=['Apparel'], unit='piece',
                sell_per_sqft='0', cost_per_sqft='0', setup_price='0', setup_cost='0',
                waste_percent='0', labor_minutes_per_unit='0', minimum_price='0',
                default_width='3.5', default_height='3.5', min_width='1', min_height='1',
                max_width='12', max_height='12', instant=False, quote_only=True,
                finished_apparel=True, apparel_kind=kind, apparel_unit_price='35',
                digitizing_fee='35', shirt_colors=COLORS, shirt_sizes=SIZES,
                placement_options=CHEST_PLACEMENTS, self_approve_artwork=False,
                description=f'Choose {name.lower()}, color, sizes and chest placement. Upload a logo for a digital embroidery preview. Garment and stitch pricing is confirmed by the shop; a one-time $35 digitizing fee applies.'
            )
        for product_name, values in additions.items():
            if conn.execute('SELECT id FROM products WHERE name=?', (product_name,)).fetchone():
                continue
            category = values.pop('category')
            cfg = validate_config(values)
            conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,1,1,?,?,?)',
                         (product_name, category, workflow, json.dumps(cfg), now()))


def garment_selection(item, qty, cfg, product_name):
    color = item.get('shirt_color')
    sizes = item.get('size_quantities')
    placements = item.get('print_locations')
    colors = cfg.get('shirt_colors') or COLORS
    allowed_sizes = cfg.get('shirt_sizes') or SIZES
    if color not in colors or not isinstance(sizes, dict) or not sizes or set(sizes) - set(allowed_sizes):
        raise HTTPException(422, 'Choose an apparel color and size quantities.')
    if any(type(q) is not int or q < 0 or q > 100000 for q in sizes.values()) or sum(sizes.values()) != qty:
        raise HTTPException(422, 'Apparel size quantities must add up to the total quantity.')
    kind = cfg.get('apparel_kind', 'custom_shirt')
    if kind == 'custom_shirt':
        if not isinstance(placements, list) or not 1 <= len(placements) <= len(PRINTS) or len(set(placements)) != len(placements) or any(p not in PRINTS for p in placements):
            raise HTTPException(422, 'Choose one or more valid print locations.')
        unit_price = sum(PRINT_PRICES[p] for p in placements)
        garment = 'Gildan 5000'
        placement_labels = [PRINTS[p] for p in placements]
    else:
        options = {p['id']: p['label'].split(' — ')[0] for p in cfg.get('placement_options', [])}
        if not isinstance(placements, list) or len(placements) != 1 or placements[0] not in options:
            raise HTTPException(422, 'Choose a valid embroidery placement.')
        unit_price = float(cfg.get('apparel_unit_price') or cfg.get('setup_price') or 0)
        garment = EMBROIDERY_KINDS.get(kind, product_name)
        placement_labels = [options[placements[0]]]
    description = garment + ' / ' + color + ' / ' + ', '.join(f'{s}: {q}' for s, q in sizes.items() if q) + ' / ' + ', '.join(placement_labels)
    preview = None
    text_line_count = 0
    if kind != 'custom_shirt' and item.get('embroidery_preview') is not None:
        preview = validate_embroidery_preview(item['embroidery_preview'], cfg, placements[0])
        description += f' / embroidery {preview["width"]:g} x {preview["height"]:g} in'
        if preview.get('text'):
            text_line_count = sum(bool(str(preview['text'].get(key) or '').strip()) for key in ('line1', 'line2'))
            description += (f' / {preview["text"]["placement"].replace("_", " ")} text'
                            f' / {text_line_count} personalized line{"s" if text_line_count != 1 else ""}'
                            f' @ ${EMBROIDERY_TEXT_LINE_PRICE} each per garment')
    return unit_price, int(float(cfg.get('digitizing_fee', 0))), description, preview, text_line_count


def validate_embroidery_preview(value, cfg, placement):
    """Only placement instructions are accepted here; artwork remains a private job upload."""
    if not isinstance(value, dict):
        raise HTTPException(422, 'Invalid embroidery preview.')
    option = next((p for p in cfg.get('placement_options', []) if p['id'] == placement), None)
    if not option:
        raise HTTPException(422, 'Choose a valid embroidery placement.')
    try:
        width, height = float(value['width']), float(value['height'])
        x, y = float(value['offset_x']), float(value['offset_y'])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, 'Enter valid embroidery dimensions and position.')
    import math
    limit = 0.35 if placement == 'front' else 0.75
    if (not all(math.isfinite(v) for v in (width, height, x, y)) or
            width < 0.5 or height < 0.2 or width > float(option['width']) or
            height > float(option['height']) or abs(x) > limit or abs(y) > limit):
        raise HTTPException(422, 'Embroidery size or placement exceeds the garment area.')
    colors = value.get('thread_colors')
    if (not isinstance(colors, list) or not 1 <= len(colors) <= 8 or
            any(not isinstance(c, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', c) for c in colors)):
        raise HTTPException(422, 'Choose 1 to 8 thread colors.')
    result = {'width': round(width, 2), 'height': round(height, 2),
              'offset_x': round(x, 2), 'offset_y': round(y, 2),
              'thread_colors': [c.lower() for c in colors]}
    text = value.get('text') or {}
    if isinstance(text, dict) and text.get('enabled'):
        other = {'left_chest': 'right_chest', 'right_chest': 'left_chest'}.get(placement)
        other_option = next((p for p in cfg.get('placement_options', []) if p['id'] == other), None)
        if not other_option:
            raise HTTPException(422, 'Second-side text embroidery is only available for chest placements.')
        line1 = str(text.get('line1') or '').strip()
        line2 = str(text.get('line2') or '').strip()
        if not line1 and not line2:
            raise HTTPException(422, 'Enter text for the second embroidery side.')
        if any(len(line) > 40 or re.search(r'[\x00-\x1f\x7f]', line) for line in (line1, line2)):
            raise HTTPException(422, 'Embroidery text must be 40 characters or fewer per line.')
        try:
            text_width = float(text.get('width', 3))
        except (ValueError, TypeError):
            raise HTTPException(422, 'Enter a valid embroidery text width.')
        text_color = str(text.get('thread_color') or result['thread_colors'][0]).lower()
        if (not math.isfinite(text_width) or text_width < 0.75 or
                text_width > float(other_option['width']) or
                not re.fullmatch(r'#[0-9a-fA-F]{6}', text_color)):
            raise HTTPException(422, 'Second-side embroidery text exceeds the garment area.')
        result['text'] = {'enabled': True, 'placement': other, 'line1': line1[:40],
                          'line2': line2[:40], 'width': round(text_width, 2),
                          'thread_color': text_color}
    return result
