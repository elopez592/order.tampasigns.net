"""Deterministic server-side pricing. Money is persisted in integer cents.

Graduated quantity bands apply only to units inside a band. This prevents
order totals falling when the quantity crosses a discount threshold.
Waste increases estimated material cost, not the customer's net square feet.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_CEILING
import json
from fastapi import HTTPException
from .db import settings

D = Decimal


def number(value, name='Number', minimum='0', maximum='10000000') -> Decimal:
    if isinstance(value, bool):
        raise HTTPException(422, f'{name} must be a number.')
    try:
        val = D(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(422, f'{name} must be a number.')
    if not val.is_finite() or val < D(minimum) or val > D(maximum):
        raise HTTPException(422, f'{name} must be between {minimum} and {maximum}.')
    return val


def cents(value, name='Amount') -> int:
    return int((number(value, name) * 100).quantize(D('1'), rounding=ROUND_HALF_UP))


def cent_round(value: Decimal) -> int:
    return int(value.quantize(D('1'), rounding=ROUND_HALF_UP))


def dollars(value: int) -> str:
    return f'{D(value) / 100:.2f}'


def validate_config(cfg: dict) -> dict:
    if not isinstance(cfg, dict):
        raise HTTPException(422, 'Product configuration must be an object.')
    result = {}
    for key, default, lo, hi in [
        ('sell_per_sqft', '8', '0', '10000'), ('cost_per_sqft', '2', '0', '10000'),
        ('setup_price', '15', '0', '100000'), ('setup_cost', '5', '0', '100000'),
        ('minimum_price', '25', '0', '100000'), ('waste_percent', '15', '0', '200'),
        ('labor_minutes_per_unit', '0', '0', '10000'),
        ('max_width', '120', '0.1', '10000'), ('max_height', '1200', '0.1', '10000'),
        ('min_quantity', '1', '1', '100000'), ('max_quantity', '100000', '1', '100000'),
        ('default_width', '3', '0.1', '10000'), ('default_height', '3', '0.1', '10000')]:
        result[key] = str(number(cfg.get(key, default), key, lo, hi))
    for field in ('min_quantity', 'max_quantity'):
        if D(result[field]) != D(result[field]).to_integral():
            raise HTTPException(422, 'Quantity limits must be whole numbers.')
    if D(result['max_quantity']) < D(result['min_quantity']):
        raise HTTPException(422, 'Maximum quantity must not be below minimum quantity.')
    if not isinstance(cfg.get('instant', True), bool):
        raise HTTPException(422, 'instant must be true or false.')
    result['instant'] = cfg.get('instant', True)
    for flag in ('requires_installation', 'is_wrap'):
        if not isinstance(cfg.get(flag, False), bool):
            raise HTTPException(422, f'{flag} must be true or false.')
        result[flag] = cfg.get(flag, False)
    if result['requires_installation'] or result['is_wrap']:
        result['instant'] = False
    result['description'] = str(cfg.get('description', ''))[:700]
    result['unit'] = cfg.get('unit', 'piece')
    if result['unit'] not in ('piece', 'sqft'):
        raise HTTPException(422, 'Unit must be piece or sqft.')
    tiers = cfg.get('tiers', [{'from': 1, 'multiplier': '1'}])
    if not isinstance(tiers, list) or not tiers or len(tiers) > 12:
        raise HTTPException(422, 'Use 1 to 12 quantity bands.')
    checked, previous, previous_multiplier = [], 0, D('2')
    for tier in tiers:
        if not isinstance(tier, dict):
            raise HTTPException(422, 'Invalid quantity band.')
        start = number(tier.get('from'), 'Band start', '1', '100000')
        mult = number(tier.get('multiplier'), 'Band multiplier', '0.05', '1')
        if start != start.to_integral() or start <= previous or mult > previous_multiplier:
            raise HTTPException(422, 'Bands must have increasing whole-number starts and non-increasing multipliers.')
        checked.append({'from': int(start), 'multiplier': str(mult)})
        previous, previous_multiplier = int(start), mult
    if checked[0]['from'] != 1:
        raise HTTPException(422, 'The first quantity band must start at 1.')
    result['tiers'] = checked
    return result


def weighted_quantity(quantity: int, tiers: list) -> Decimal:
    weighted = D(0)
    for i, tier in enumerate(tiers):
        start = tier['from']
        end = tiers[i + 1]['from'] - 1 if i + 1 < len(tiers) else quantity
        count = max(0, min(quantity, end) - start + 1)
        weighted += D(count) * D(tier['multiplier'])
    return weighted


def calculate(conn, items: list, staff=False) -> dict:
    if not isinstance(items, list) or not 1 <= len(items) <= 30:
        raise HTTPException(422, 'A quote needs 1 to 30 product lines.')
    shop = settings(conn)
    margin = number(shop['target_margin_percent'], 'Target margin', '0', '90') / 100
    overhead = number(shop['overhead_percent'], 'Overhead', '0', '200') / 100
    labor_cost = number(shop['labor_cost_per_hour']) * 100
    labor_sell = number(shop['labor_sell_per_hour']) * 100
    lines = []
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(422, 'Invalid quote line.')
        pid = number(item.get('product_id'), 'Product ID', '1', '100000000')
        if pid != pid.to_integral():
            raise HTTPException(422, 'Product ID must be a whole number.')
        row = conn.execute('SELECT * FROM products WHERE id=? AND active=1', (int(pid),)).fetchone()
        if not row or (not staff and not row['public']):
            raise HTTPException(422, 'Product is unavailable.')
        cfg = json.loads(row['config'])
        qty = number(item.get('quantity', 1), 'Quantity', cfg['min_quantity'], cfg['max_quantity'])
        if qty != qty.to_integral():
            raise HTTPException(422, 'Quantity must be a whole number.')
        qty = int(qty)
        width = number(item.get('width'), 'Width in inches', '0.1', '10000')
        height = number(item.get('height'), 'Height in inches', '0.1', '10000')
        area = width * height / 144
        net_area = area * qty
        material_area = net_area * (1 + D(cfg['waste_percent']) / 100)
        labor_hours = D(cfg['labor_minutes_per_unit']) * qty / 60
        raw_cost = material_area * D(cfg['cost_per_sqft']) * 100 + D(cfg['setup_cost']) * 100 + labor_hours * labor_cost
        cost = cent_round(raw_cost * (1 + overhead))
        band_qty = weighted_quantity(qty, cfg['tiers'])
        calculated = D(cfg['setup_price']) * 100 + area * band_qty * D(cfg['sell_per_sqft']) * 100 + labor_hours * labor_sell
        floor = int((D(cost) / (1 - margin)).quantize(D('1'), rounding=ROUND_CEILING))
        sell = max(cent_round(calculated), cents(cfg['minimum_price']), floor)
        if sell > 1_000_000_000:
            raise HTTPException(422, 'This project exceeds the automatic estimating limit. Split the job or request a manual quote.')
        review = (not cfg['instant'] or cfg.get('requires_installation', False) or cfg.get('is_wrap', False)
                  or 'wrap' in (row['name']+' '+row['category']).lower()) or width > D(cfg['max_width']) or height > D(cfg['max_height'])
        lines.append({
            'product_id': row['id'], 'product_version': row['version'], 'name': row['name'],
            'category': row['category'], 'description': str(item.get('description', ''))[:200],
            'width': str(width), 'height': str(height), 'quantity': qty, 'unit': cfg['unit'],
            'net_sqft': str(net_area.quantize(D('0.0001'))),
            'material_sqft': str(material_area.quantize(D('0.0001'))),
            'labor_hours': str(labor_hours), 'sell_cents': sell, 'cost_cents': cost,
            'price_per_item_cents': cent_round(D(sell) / qty), 'review_required': review,
            'workflow_id': row['workflow_id'], 'floor_applied': sell == floor,
            'rate_snapshot': cfg,
        })
    return {'lines': lines, 'subtotal_cents': sum(x['sell_cents'] for x in lines),
            'cost_cents': sum(x['cost_cents'] for x in lines),
            'review_required': any(x['review_required'] for x in lines) or not shop['rates_live'],
            'settings_snapshot': {k: shop[k] for k in ['target_margin_percent', 'overhead_percent',
                                                       'labor_cost_per_hour', 'labor_sell_per_hour']},
            'currency': 'USD', 'pricing_basis': 'Net rectangular area; graduated quantity bands; waste in cost only.'}


def public_quote(quote: dict) -> dict:
    return {k: v for k, v in quote.items() if k not in ('cost_cents', 'settings_snapshot')} | {
        'lines': [{k: v for k, v in line.items() if k not in
                   ('cost_cents', 'rate_snapshot', 'material_sqft', 'labor_hours', 'floor_applied', 'workflow_id')}
                  for line in quote['lines']]}
