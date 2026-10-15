"""Validated pack specifications for quoting and production jobs."""
from fastapi import HTTPException
from .pricing import number


def normalize_pack(value, packs):
    if not isinstance(value, dict):
        raise HTTPException(422, 'Add the sticker designs for your pack.')
    rows = value.get('stickers')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise HTTPException(422, 'A pack needs 1 to 20 sticker designs.')
    result = {'stickers': []}
    for row in rows:
        if not isinstance(row, dict):
            raise HTTPException(422, 'Invalid sticker design.')
        name = str(row.get('name', '')).strip()[:100]
        if not name:
            raise HTTPException(422, 'Each sticker needs an artwork filename.')
        width = number(row.get('width'), 'Sticker width', '.5', '7')
        height = number(row.get('height'), 'Sticker height', '.5', '7')
        copies = number(row.get('copies', 1), 'Copies per pack', '1', '100')
        if copies != copies.to_integral():
            raise HTTPException(422, 'Copies per pack must be a whole number.')
        result['stickers'].append({'name': name, 'width': str(width), 'height': str(height), 'copies': int(copies)})
    header = value.get('header')
    if header is not None:
        if not isinstance(header, dict) or not str(header.get('name', '')).strip():
            raise HTTPException(422, 'Attach the custom header artwork.')
        result['header'] = {'name': str(header['name'])[:100], 'width': str(number(header.get('width'), 'Header width', '1', '24')), 'height': str(number(header.get('height'), 'Flat header height', '1', '24'))}
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
    description += f" | Header: {h['name']} ({h['width']} x {h['height']} in flat; {packs} headers)" if h else ' | No custom header'
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
    header_unit = 0
    if pack['header']:
        large = number(pack['header']['width']) >= 5
        key, default = ('pack_header_5_price', '2.00') if large else ('pack_header_4_price', '1.50')
        header_unit = cents(config.get(key, default), 'Cardstock header price')
    packaging_unit = cents(config.get('pack_packaging_price', '1.00'), 'Packaging and assembly price')
    header_total, packaging_total = header_unit * packs, packaging_unit * packs
    return {'designs': designs, 'stickers_cents': sticker_sell,
            'header_unit_cents': header_unit, 'headers_cents': header_total,
            'packaging_unit_cents': packaging_unit, 'packaging_cents': packaging_total,
            'total_cents': sticker_sell + header_total + packaging_total,
            'retail_total_cents': sticker_retail + header_total + packaging_total}, sticker_cost
