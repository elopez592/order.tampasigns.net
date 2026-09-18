"""Customer catalog additions and finished garment pricing."""
import json
from fastapi import HTTPException
from .db import transaction, now

COLORS = {'White': '#ffffff', 'Black': '#252525', 'Navy': '#182b49', 'Royal': '#2453a0', 'Red': '#bd2437', 'Sport Grey': '#a8a8a8'}
SIZES = ['S', 'M', 'L', 'XL', '2XL', '3XL']
PRINTS = {'front': 'Full front', 'back': 'Full back', 'left_chest': 'Left chest'}


def upgrade_catalog(database):
    from .pricing import validate_config
    with transaction(database, True) as conn:
        for row in conn.execute('SELECT * FROM products').fetchall():
            cfg = json.loads(row['config'])
            cats = cfg.get('storefront_categories', [])
            name = row['name']
            if 'banner' in name.lower() or name == 'Custom T-shirts':
                cats = list(dict.fromkeys(cats + ['Events']))
            if name == 'DTF transfers':
                name = 'Custom T-shirts'
                cfg.update(finished_apparel=True, sell_per_sqft='30', setup_price='0', setup_cost='0', cost_per_sqft='0',
                           minimum_price='0', default_width='12', default_height='12', max_width='12', max_height='12',
                           placement_options=[], quantity_only=True, self_approve_artwork=False,
                           description='Finished Gildan Heavy Cotton 5000 shirts, including your printed artwork. One shirt with a full front OR back print is $30. Quantity savings apply. Color availability is confirmed before production.',
                           tiers=[{'from': 1, 'multiplier': '1'}, {'from': 6, 'multiplier': '.9'}, {'from': 12, 'multiplier': '.85'}, {'from': 24, 'multiplier': '.8'}, {'from': 48, 'multiplier': '.75'}])
                cats = ['Apparel', 'Events']
            if name == 'Custom T-shirts':
                cfg.update(finished_apparel=True, shirt_colors=COLORS, shirt_sizes=SIZES)
            cfg['storefront_categories'] = cats
            if cfg != json.loads(row['config']) or name != row['name']:
                conn.execute('UPDATE products SET name=?,config=?,version=version+1,updated_at=? WHERE id=?', (name, json.dumps(cfg), now(), row['id']))
        workflow = conn.execute('SELECT id FROM workflows ORDER BY id LIMIT 1').fetchone()['id']
        additions = [
            ('Roll-up banners', ['Events'], 'Retractable banner with stand. Choose your size; hardware and final pricing are confirmed in your quote.', 33, 80),
            ('1/4 inch foam board', ['Storefront', 'Events'], 'Printed quarter-inch foam board for indoor displays and events. Pricing confirmed by the shop.', 24, 36),
            ('1/2 inch foam board', ['Storefront', 'Events'], 'Printed half-inch foam board for indoor displays and events. Pricing confirmed by the shop.', 24, 36),
            ('Storefront Window Tinting', ['Storefront'], 'Architectural window tinting for storefronts. Film choice, measurements and installation are quoted after review.', 36, 48),
        ]
        for name, cats, description, width, height in additions:
            if conn.execute('SELECT id FROM products WHERE name=?', (name,)).fetchone():
                continue
            cfg = validate_config(dict(storefront_categories=cats, description=description, default_width=width, default_height=height,
                                       sell_per_sqft=0, cost_per_sqft=0, setup_price=0, setup_cost=0, minimum_price=0, instant=False))
            cfg['quote_only'] = True
            conn.execute('INSERT INTO products(name,category,active,public,workflow_id,config,updated_at) VALUES(?,?,1,1,?,?,?)',
                         (name, cats[0], workflow, json.dumps(cfg), now()))


def garment_selection(item, qty):
    color = item.get('shirt_color')
    sizes = item.get('size_quantities')
    placements = item.get('print_locations')
    if color not in COLORS or not isinstance(sizes, dict) or not sizes or set(sizes) - set(SIZES):
        raise HTTPException(422, 'Choose a shirt color and size quantities.')
    if any(type(q) is not int or q < 0 or q > 100000 for q in sizes.values()) or sum(sizes.values()) != qty:
        raise HTTPException(422, 'Shirt size quantities must add up to the total quantity.')
    if not isinstance(placements, list) or not placements or any(p not in PRINTS for p in placements) or len(set(placements)) != len(placements):
        raise HTTPException(422, 'Choose valid print locations.')
    if 'front' in placements and 'left_chest' in placements:
        raise HTTPException(422, 'Choose full front or left chest, plus an optional back print.')
    description = 'Gildan 5000 / ' + color + ' / ' + ', '.join(f'{s}: {q}' for s, q in sizes.items() if q) + ' / ' + ', '.join(PRINTS[p] for p in placements)
    # Base garment + one print = $30; additional location uses the same $15 decoration allowance.
    return 15 + 15 * len(placements), description
