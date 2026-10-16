"""Validated pack specifications for quoting and production jobs."""
from fastapi import HTTPException
from .pricing import number


def normalize_pack(value, packs):
    if not isinstance(value, dict):
        raise HTTPException(422, 'Add the sticker designs for your pack.')
    rows = value.get('stickers')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise HTTPException(422, 'A pack needs 1 to 20 sticker designs.')
    result = {'stickers': [], 'header_included': True}
    for row in rows:
        if not isinstance(row, dict):
            raise HTTPException(422, 'Invalid sticker design.')
        name = str(row.get('name', '')).strip()[:100]
        if not name:
            raise HTTPException(422, 'Give each sticker design a name.')
        width = number(row.get('width'), 'Sticker width', '.5', '4')
        height = number(row.get('height'), 'Sticker height', '.5', '4')
        copies = number(row.get('copies', 1), 'Copies per pack', '1', '100')
        if copies != copies.to_integral():
            raise HTTPException(422, 'Copies per pack must be a whole number.')
        design_requested = row.get('design_requested', False)
        if not isinstance(design_requested, bool):
            raise HTTPException(422, 'Design assistance must be selected for each sticker design.')
        design_service = row.get('design_service')
        if design_service is None:
            design_service = 'manual' if design_requested else 'artwork'
        if design_service not in ('artwork', 'generated', 'manual'):
            raise HTTPException(422, 'Choose a valid design service.')
        result['stickers'].append({'name': name, 'width': str(width), 'height': str(height),
                                   'copies': int(copies), 'design_requested': design_service != 'artwork',
                                   'design_service': design_service})
    header = value.get('header')
    if header is not None:
        if not isinstance(header, dict) or not str(header.get('name', '')).strip():
            raise HTTPException(422, 'Attach the custom header artwork.')
        result['header'] = {'name': str(header['name'])[:100]}
        # Retain dimensions from older saved projects; new artwork is sized by the shop.
        if header.get('width') is not None or header.get('height') is not None:
            result['header'].update(width=str(number(header.get('width'), 'Header width', '1', '24')), height=str(number(header.get('height'), 'Flat header height', '1', '24')))
    else:
        result['header'] = None
    result['stickers_per_pack'] = sum(s['copies'] for s in result['stickers'])
    result['total_stickers'] = result['stickers_per_pack'] * packs
    if result['total_stickers'] > 100000:
        raise HTTPException(422, 'Please request a custom quote for more than 100,000 stickers.')
    result['notes'] = str(value.get('notes', '')).strip()[:1000]
    description = f"{packs} packs; {result['stickers_per_pack']} stickers per pack; {result['total_stickers']} total. "
    description += ' | '.join(f"Design {i}: {s['name']} ({s['width']} x {s['height']} in), {s['copies']} per pack / {s['copies'] * packs} total" for i, s in enumerate(result['stickers'], 1))
    h = result['header']
    if h:
        size = f"{h['width']} x {h['height']} in flat; " if 'width' in h else ''
        description += f" | Custom header artwork: {h['name']} ({size}{packs} headers)"
    else:
        description += f' | Standard cardstock header included ({packs} headers)'
    generated_count = sum(s['design_service'] == 'generated' for s in result['stickers'])
    manual_count = sum(s['design_service'] == 'manual' for s in result['stickers'])
    if generated_count:
        description += f' | Sticker generation requested for {generated_count} design(s).'
    if manual_count:
        description += f' | Manual artwork creation requested for {manual_count} design(s).'
    description += ' | Package size may vary. Shop proof follows payment; approval is required before printing.'
    if result['notes']:
        description += ' | Notes: ' + result['notes']
    return result, description



def price_pack(conn, pack, packs, config, staff=False, wholesale_client_id=None):
    """Use the same live die-cut rates as separately ordered sticker designs."""
    import json
    from .pricing import calculate, cents
    sticker = conn.execute("SELECT * FROM products WHERE name='Die-cut stickers' AND active=1 ORDER BY id LIMIT 1").fetchone()
    if not sticker or (not staff and not sticker['public']) or json.loads(sticker['config']).get('sticker_pack'):
        raise HTTPException(422, 'Sticker pricing is unavailable. Please contact the shop for a quote.')
    designs = []
    sticker_sell = sticker_retail = sticker_cost = 0
    for design in pack['stickers']:
        line = calculate(conn, [{'product_id': sticker['id'], 'quantity': design['copies'] * packs,
                                'width': design['width'], 'height': design['height']}],
                         staff=staff, wholesale_client_id=wholesale_client_id)['lines'][0]
        designs.append({'name': design['name'], 'width': design['width'], 'height': design['height'],
                        'quantity': line['quantity'], 'sell_cents': line['sell_cents'],
                        'product_id': sticker['id'], 'product_version': sticker['version']})
        sticker_sell += line['sell_cents']
        sticker_retail += line['retail_sell_cents']
        sticker_cost += line['cost_cents']
    header_unit = cents(config.get('pack_header_4_price', '1.50'), 'Cardstock header price')
    packaging_unit = cents(config.get('pack_packaging_price', '1.00'), 'Packaging and assembly price')
    header_total, packaging_total = header_unit * packs, packaging_unit * packs
    generated_count = sum(s.get('design_service') == 'generated' for s in pack['stickers'])
    manual_count = sum(s.get('design_service', 'manual' if s.get('design_requested') else 'artwork') == 'manual' for s in pack['stickers'])
    design_count = generated_count + manual_count
    design_unit = cents(config.get('pack_design_price', '25.00'), 'Manual sticker design price')
    generation_unit = cents(config.get('pack_generation_price', '12.00'), 'Sticker generation price')
    design_fee = manual_count * design_unit + generated_count * generation_unit
    # Finished-pack bundle rates are editable in the product config.
    # Benchmark: three 3x2-inch stickers = $3.50 per pack at 50+ packs,
    # including the printed header, bag and assembly (excluding design fees).
    from decimal import Decimal, ROUND_HALF_UP
    base_unit = cents(config.get('pack_bundle_base_price', '0.80'), 'Bundle packaging base')
    sticker_unit = cents(config.get('pack_bundle_sticker_price', '0.90'), 'Bundle sticker base')
    base_area = Decimal('6')
    area_price = 0
    for design in pack['stickers']:
        area = Decimal(design['width']) * Decimal(design['height'])
        # Area-based pricing remains proportional to material usage.
        unit = (Decimal(sticker_unit) * area / base_area).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        area_price += int(unit) * design['copies']
    standard_unit = base_unit + area_price
    # Small runs carry a surcharge. 50+ retain a stable per-pack rate.
    minimum_run = int(config.get('pack_bundle_standard_quantity', 50))
    if minimum_run < 1:
        minimum_run = 50
    short_run_multiplier = Decimal(str(config.get('pack_bundle_short_run_multiplier', '1.20')))
    if short_run_multiplier < 1:
        short_run_multiplier = Decimal('1')
    unit_price = standard_unit if packs >= minimum_run else int(
        (Decimal(standard_unit) * short_run_multiplier).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    bundle_total = unit_price * packs
    return {'designs': designs, 'stickers_cents': sticker_sell,
            'header_unit_cents': header_unit, 'headers_cents': header_total,
            'packaging_unit_cents': packaging_unit, 'packaging_cents': packaging_total,
            'design_fee_cents': design_fee, 'design_unit_cents': design_unit, 'design_count': design_count,
            'manual_design_count': manual_count, 'generation_count': generated_count,
            'generation_unit_cents': generation_unit,
            'bundle_unit_cents': unit_price, 'bundle_min_quantity': minimum_run,
            'total_cents': bundle_total + design_fee,
            'retail_total_cents': bundle_total + design_fee}, sticker_cost
