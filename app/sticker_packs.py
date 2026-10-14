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

