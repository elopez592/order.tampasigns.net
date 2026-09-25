"""Deterministic server-side pricing. Money is persisted in integer cents.

Graduated quantity bands apply only to units inside a band. This prevents
order totals falling when the quantity crosses a discount threshold.
Waste increases estimated material cost, not the customer's net square feet.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_CEILING
import json
import re
from fastapi import HTTPException
from .db import settings

D = Decimal
USDOT_STYLES = {'bold', 'condensed', 'industrial', 'serif', 'rounded', 'highway', 'stencil', 'monospace', 'modern', 'slab'}
USDOT_FONT_SCALES = {D('0.8'), D('1'), D('1.2'), D('1.4')}
USDOT_FONT_DEFAULTS = {'company': 56, 'phone': 30, 'number': 72, 'licenses': 30, 'location': 32}


def usdot_design(value) -> dict:
    if value in (None, ''):
        return {}
    if not isinstance(value, dict):
        raise HTTPException(422, 'USDOT design details must be an object.')
    limits = {'company': 80, 'phone': 40, 'number': 20, 'licenses': 100, 'location': 80}
    result = {key: str(value.get(key, '')).strip()[:limit] for key, limit in limits.items()}
    if not result['company'] or not result['number']:
        raise HTTPException(422, 'Company name and USDOT number are required.')
    result['number'] = re.sub(r'^USDOT\s*', '', result['number'], flags=re.I)
    style = str(value.get('style', 'bold')).strip().lower()
    if style not in USDOT_STYLES:
        raise HTTPException(422, 'Choose a valid USDOT font style.')
    result['style'] = style
    font_scale = number(value.get('font_scale', 1), 'USDOT font size', '0.8', '1.4')
    if 'font_sizes' not in value and font_scale not in USDOT_FONT_SCALES:
        raise HTTPException(422, 'Choose a valid USDOT font size.')
    result['font_scale'] = str(font_scale)
    font_sizes = value.get('font_sizes', {})
    if not isinstance(font_sizes, dict) or set(font_sizes) - set(USDOT_FONT_DEFAULTS):
        raise HTTPException(422, 'USDOT font sizes must match the available text lines.')
    result['font_sizes'] = {
        key: str(number(font_sizes.get(key, default), f'{key.title()} point size', '8', '300'))
        for key, default in USDOT_FONT_DEFAULTS.items()
    }
    color = str(value.get('text_color', '#111111')).strip().lower()
    if not re.fullmatch(r'#[0-9a-f]{6}', color):
        raise HTTPException(422, 'Choose a valid USDOT lettering color.')
    result['text_color'] = color
    return result


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
        ('installation_minutes_per_sqft', '0', '0', '1000'),
        ('installation_setup_minutes', '0', '0', '10000'),
        ('price_table_base_width', '3', '0.1', '10000'),
        ('price_table_base_height', '3', '0.1', '10000'),
        ('price_table_size_weight', '0.45', '0', '1'),
        ('max_short_axis', '10000', '0.1', '10000'), ('max_long_axis', '10000', '0.1', '10000'),
        ('min_width', '0.1', '0.1', '10000'), ('min_height', '0.1', '0.1', '10000'),
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
    for flag in ('requires_installation', 'is_wrap', 'supports_installation', 'supports_multiple_dimensions', 'self_approve_artwork', 'usdot_customizer', 'contour_customizer', 'quantity_only', 'finished_apparel', 'quote_only', 'vehicle_details_required', 'tint_package_selector', 'artwork_upload_disabled'):
        if not isinstance(cfg.get(flag, False), bool):
            raise HTTPException(422, f'{flag} must be true or false.')
        result[flag] = cfg.get(flag, False)
    if result['requires_installation']:
        result['instant'] = False
    installation_workflow = cfg.get('installation_workflow_id')
    if installation_workflow in (None, ''):
        result['installation_workflow_id'] = None
    else:
        workflow_id = number(installation_workflow, 'Installation workflow ID', '1', '100000000')
        if workflow_id != workflow_id.to_integral():
            raise HTTPException(422, 'Installation workflow ID must be a whole number.')
        result['installation_workflow_id'] = int(workflow_id)
    result['description'] = str(cfg.get('description', ''))[:700]
    apparel_kind = str(cfg.get('apparel_kind', '')).strip().lower()
    if apparel_kind not in ('', 'custom_shirt', 'embroidered_hat', 'embroidered_polo',
                            'embroidered_shirt', 'embroidered_hoodie', 'embroidered_jacket'):
        raise HTTPException(422, 'Choose a valid apparel kind.')
    result['apparel_kind'] = apparel_kind
    result['apparel_unit_price'] = str(number(cfg.get('apparel_unit_price', 0), 'Apparel unit price', '0', '10000'))
    result['digitizing_fee'] = str(number(cfg.get('digitizing_fee', 0), 'Digitizing fee', '0', '10000'))
    shirt_colors = cfg.get('shirt_colors', {})
    if not isinstance(shirt_colors, dict) or len(shirt_colors) > 40 or any(not str(k).strip() or len(str(k)) > 50 or not re.fullmatch(r'#[0-9a-fA-F]{6}', str(v)) for k, v in shirt_colors.items()):
        raise HTTPException(422, 'Apparel colors must use names and six-digit hex values.')
    result['shirt_colors'] = {str(k).strip(): str(v).lower() for k, v in shirt_colors.items()}
    shirt_sizes = cfg.get('shirt_sizes', [])
    if not isinstance(shirt_sizes, list) or len(shirt_sizes) > 30:
        raise HTTPException(422, 'Use no more than 30 apparel sizes.')
    result['shirt_sizes'] = [str(size).strip()[:30] for size in shirt_sizes if str(size).strip()]
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

    price_table = cfg.get('quantity_price_table', [])
    if not isinstance(price_table, list) or len(price_table) > 30:
        raise HTTPException(422, 'Quantity price table must contain no more than 30 rows.')
    checked_table, previous_qty, previous_total = [], 0, D('-1')
    for row in price_table:
        if not isinstance(row, dict):
            raise HTTPException(422, 'Invalid quantity price row.')
        qty = number(row.get('quantity'), 'Price-table quantity', '1', '100000')
        total = number(row.get('total'), 'Price-table total', '0', '1000000')
        if qty != qty.to_integral() or int(qty) <= previous_qty or total < previous_total:
            raise HTTPException(422, 'Price-table quantities must increase and totals must not decrease.')
        checked_table.append({'quantity': int(qty), 'total': str(total)})
        previous_qty, previous_total = int(qty), total
    result['quantity_price_table'] = checked_table

    options = cfg.get('lamination_options', [])
    if not isinstance(options, list) or len(options) > 8:
        raise HTTPException(422, 'Use no more than 8 lamination options.')
    checked_options, option_ids, default_count = [], set(), 0
    for option in options:
        if not isinstance(option, dict):
            raise HTTPException(422, 'Invalid lamination option.')
        oid = str(option.get('id', '')).strip().lower()
        if not re.fullmatch(r'[a-z0-9_-]{1,40}', oid) or oid in option_ids:
            raise HTTPException(422, 'Lamination option IDs must be unique letters, numbers, hyphens or underscores.')
        label = str(option.get('label', '')).strip()[:80]
        if not label:
            raise HTTPException(422, 'Lamination option label is required.')
        sell = number(option.get('sell_per_sqft', 0), 'Lamination selling rate', '0', '1000')
        cost = number(option.get('cost_per_sqft', 0), 'Lamination cost rate', '0', '1000')
        is_default = option.get('default', False)
        if not isinstance(is_default, bool):
            raise HTTPException(422, 'Lamination default flag must be true or false.')
        default_count += int(is_default)
        option_ids.add(oid)
        checked_options.append({'id': oid, 'label': label, 'sell_per_sqft': str(sell),
                                'cost_per_sqft': str(cost), 'default': is_default})
    if default_count > 1:
        raise HTTPException(422, 'Choose only one default lamination option.')
    if checked_options and default_count == 0:
        checked_options[0]['default'] = True
    result['lamination_options'] = checked_options

    materials = cfg.get('material_options', [])
    if not isinstance(materials, list) or len(materials) > 12:
        raise HTTPException(422, 'Use no more than 12 material options.')
    checked_materials, material_ids, material_defaults = [], set(), 0
    for option in materials:
        if not isinstance(option, dict):
            raise HTTPException(422, 'Invalid material option.')
        oid = str(option.get('id', '')).strip().lower()
        if not re.fullmatch(r'[a-z0-9_-]{1,40}', oid) or oid in material_ids:
            raise HTTPException(422, 'Material option IDs must be unique letters, numbers, hyphens or underscores.')
        label = str(option.get('label', '')).strip()[:80]
        if not label:
            raise HTTPException(422, 'Material option label is required.')
        sell_adjustment = number(option.get('sell_per_sqft_adjustment', 0), 'Material selling adjustment', '0', '1000')
        cost_adjustment = number(option.get('cost_per_sqft_adjustment', 0), 'Material cost adjustment', '0', '1000')
        is_default = option.get('default', False)
        if not isinstance(is_default, bool):
            raise HTTPException(422, 'Material default flag must be true or false.')
        material_defaults += int(is_default)
        material_ids.add(oid)
        checked_materials.append({
            'id': oid, 'label': label,
            'sell_per_sqft_adjustment': str(sell_adjustment),
            'cost_per_sqft_adjustment': str(cost_adjustment),
            'default': is_default
        })
    if material_defaults > 1:
        raise HTTPException(422, 'Choose only one default material option.')
    if checked_materials and material_defaults == 0:
        checked_materials[0]['default'] = True
    result['material_options'] = checked_materials

    categories = cfg.get('storefront_categories', [])
    if not isinstance(categories, list) or len(categories) > 8:
        raise HTTPException(422, 'Use no more than 8 storefront categories.')
    allowed_categories = {'Storefront','Vehicles','Fleet Services','Trailers / Food Trucks','Construction signs','Stickers','Signs','Apparel','Events'}
    checked_categories = []
    for category in categories:
        label = str(category).strip()
        if label not in allowed_categories:
            raise HTTPException(422, 'Choose a valid storefront category.')
        if label not in checked_categories:
            checked_categories.append(label)
    result['storefront_categories'] = checked_categories

    sizes = cfg.get('size_options', [])
    if not isinstance(sizes, list) or len(sizes) > 12:
        raise HTTPException(422, 'Use no more than 12 standard size options.')
    checked_sizes = []
    for option in sizes:
        if not isinstance(option, dict):
            raise HTTPException(422, 'Invalid standard size option.')
        width = number(option.get('width'), 'Standard size width', '0.1', '10000')
        height = number(option.get('height'), 'Standard size height', '0.1', '10000')
        label = str(option.get('label', f'{width} x {height}')).strip()[:80]
        checked_sizes.append({'width': str(width), 'height': str(height), 'label': label})
    result['size_options'] = checked_sizes

    placements = cfg.get('placement_options', [])
    if not isinstance(placements, list) or len(placements) > 16:
        raise HTTPException(422, 'Use no more than 16 apparel placement options.')
    checked_placements, placement_ids = [], set()
    for option in placements:
        if not isinstance(option, dict):
            raise HTTPException(422, 'Invalid apparel placement option.')
        oid = str(option.get('id', '')).strip().lower()
        if not re.fullmatch(r'[a-z0-9_-]{1,40}', oid) or oid in placement_ids:
            raise HTTPException(422, 'Placement IDs must be unique letters, numbers, hyphens or underscores.')
        label = str(option.get('label', '')).strip()[:100]
        if not label:
            raise HTTPException(422, 'Placement label is required.')
        width = number(option.get('width'), 'Placement width', '0.1', '10000')
        height = number(option.get('height'), 'Placement height', '0.1', '10000')
        placement_ids.add(oid)
        checked_placements.append({'id': oid, 'label': label, 'width': str(width), 'height': str(height)})
    result['placement_options'] = checked_placements

    quantity_presets = cfg.get('quantity_presets', [])
    if not isinstance(quantity_presets, list) or len(quantity_presets) > 12:
        raise HTTPException(422, 'Use no more than 12 quantity presets.')
    checked_quantities = []
    min_q, max_q = int(D(result['min_quantity'])), int(D(result['max_quantity']))
    for value in quantity_presets:
        qty = number(value, 'Quantity preset', str(min_q), str(max_q))
        if qty != qty.to_integral():
            raise HTTPException(422, 'Quantity presets must be whole numbers.')
        qty = int(qty)
        if qty not in checked_quantities:
            checked_quantities.append(qty)
    result['quantity_presets'] = checked_quantities

    coverage = cfg.get('coverage_options', [])
    if not isinstance(coverage, list) or len(coverage) > 12:
        raise HTTPException(422, 'Use no more than 12 wrap coverage options.')
    checked_coverage, coverage_ids = [], set()
    for option in coverage:
        if not isinstance(option, dict):
            raise HTTPException(422, 'Invalid wrap coverage option.')
        oid = str(option.get('id', '')).strip().lower()
        if not re.fullmatch(r'[a-z0-9_-]{1,40}', oid) or oid in coverage_ids:
            raise HTTPException(422, 'Wrap coverage IDs must be unique letters, numbers, hyphens or underscores.')
        label = str(option.get('label', '')).strip()[:80]
        description = str(option.get('description', '')).strip()[:180]
        multiplier = number(option.get('multiplier', 1), 'Wrap coverage multiplier', '0.05', '2')
        if not label:
            raise HTTPException(422, 'Wrap coverage label is required.')
        coverage_ids.add(oid)
        checked_coverage.append({'id': oid, 'label': label, 'description': description, 'multiplier': str(multiplier)})
    result['coverage_options'] = checked_coverage

    vehicle_types = cfg.get('vehicle_type_options', [])
    if not isinstance(vehicle_types, list) or len(vehicle_types) > 12:
        raise HTTPException(422, 'Use no more than 12 vehicle type options.')
    checked_vehicle_types, vehicle_type_ids = [], set()
    for option in vehicle_types:
        if not isinstance(option, dict):
            raise HTTPException(422, 'Invalid vehicle type option.')
        oid = str(option.get('id', '')).strip().lower()
        if not re.fullmatch(r'[a-z0-9_-]{1,40}', oid) or oid in vehicle_type_ids:
            raise HTTPException(422, 'Vehicle type IDs must be unique letters, numbers, hyphens or underscores.')
        label = str(option.get('label', '')).strip()[:80]
        multiplier = number(option.get('multiplier', 1), 'Vehicle type multiplier', '0.5', '3')
        if not label:
            raise HTTPException(422, 'Vehicle type label is required.')
        vehicle_type_ids.add(oid)
        checked_vehicle_types.append({'id': oid, 'label': label, 'multiplier': str(multiplier)})
    result['vehicle_type_options'] = checked_vehicle_types
    result['quantity_only_note'] = str(cfg.get('quantity_only_note', ''))[:300]
    return result


def weighted_quantity(quantity: int, tiers: list) -> Decimal:
    weighted = D(0)
    for i, tier in enumerate(tiers):
        start = tier['from']
        end = tiers[i + 1]['from'] - 1 if i + 1 < len(tiers) else quantity
        count = max(0, min(quantity, end) - start + 1)
        weighted += D(count) * D(tier['multiplier'])
    return weighted


def table_total(quantity: int, table: list) -> Decimal:
    """Piecewise-linear benchmark total. Exact published quantity anchors remain exact."""
    rows = [(int(row['quantity']), D(row['total'])) for row in table]
    if quantity <= rows[0][0]:
        return D(quantity) * rows[0][1] / D(rows[0][0])
    for (q1, t1), (q2, t2) in zip(rows, rows[1:]):
        if quantity <= q2:
            share = D(quantity - q1) / D(q2 - q1)
            return t1 + (t2 - t1) * share
    return D(quantity) * rows[-1][1] / D(rows[-1][0])


def calculate(conn, items: list, staff=False, wholesale_client_id=None) -> dict:
    if not isinstance(items, list) or not 1 <= len(items) <= 30:
        raise HTTPException(422, 'A quote needs 1 to 30 product lines.')
    shop = settings(conn)
    margin = number(shop['target_margin_percent'], 'Target margin', '0', '90') / 100
    overhead = number(shop['overhead_percent'], 'Overhead', '0', '200') / 100
    labor_cost = number(shop['labor_cost_per_hour']) * 100
    labor_sell = number(shop['labor_sell_per_hour']) * 100
    wholesale = None
    product_discounts = {}
    if wholesale_client_id is not None:
        wholesale = conn.execute('SELECT * FROM wholesale_clients WHERE id=? AND active=1', (int(wholesale_client_id),)).fetchone()
        if not wholesale:
            raise HTTPException(422, 'Wholesale pricing profile is no longer active.')
        product_discounts = {
            row['product_id']: number(row['discount_percent'], 'Wholesale product discount', '0', '90')
            for row in conn.execute('SELECT product_id,discount_percent FROM wholesale_product_discounts WHERE client_id=?', (wholesale['id'],))
        }
        wholesale_default = number(wholesale['discount_percent'], 'Wholesale discount', '0', '90')
    else:
        wholesale_default = D(0)
    lines = []
    installation_setup_applied = set()
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
        installation_requested = item.get('installation_requested', False)
        if not isinstance(installation_requested, bool):
            raise HTTPException(422, 'Installation selection must be true or false.')
        if installation_requested and not cfg.get('supports_installation', False):
            raise HTTPException(422, 'Installation is not available for this product.')
        design_requested = item.get('design_requested', False)
        if not isinstance(design_requested, bool):
            raise HTTPException(422, 'Design quote selection must be true or false.')
        if design_requested and not cfg.get('supports_installation', False):
            raise HTTPException(422, 'A design quote is not available for this product.')
        include_roof_wrap = item.get('include_roof_wrap', False)
        if not isinstance(include_roof_wrap, bool):
            raise HTTPException(422, 'Roof wrap selection must be true or false.')
        generated_usdot = usdot_design(item.get('usdot_design')) if cfg.get('usdot_customizer') else {}
        qty = number(item.get('quantity', 1), 'Quantity', cfg['min_quantity'], cfg['max_quantity'])
        if qty != qty.to_integral():
            raise HTTPException(422, 'Quantity must be a whole number.')
        qty = int(qty)
        garment_price = None
        garment_fee = 0
        embroidery_preview = None
        if cfg.get('finished_apparel'):
            from .storefront import garment_selection
            garment_price, garment_fee, garment_description, embroidery_preview = garment_selection(item, qty, cfg, row['name'])
            item = dict(item, width=12, height=12, description=garment_description)
        width = number(item.get('width'), 'Width in inches', cfg.get('min_width', '0.1'), '10000')
        height = number(item.get('height'), 'Height in inches', cfg.get('min_height', '0.1'), '10000')
        short_axis, long_axis = sorted((width, height))
        if short_axis > D(cfg.get('max_short_axis', '10000')) or long_axis > D(cfg.get('max_long_axis', '10000')):
            raise HTTPException(422, f'Finished size cannot exceed {cfg.get("max_short_axis", "10000")} x {cfg.get("max_long_axis", "10000")} inches in either orientation.')
        area = width * height / 144

        coverage_options = cfg.get('coverage_options', [])
        coverage_id = str(item.get('coverage_option', '') or '').strip().lower()
        if coverage_options:
            if not coverage_id:
                coverage_id = coverage_options[0]['id']
            coverage_option = next((o for o in coverage_options if o['id'] == coverage_id), None)
            if not coverage_option:
                raise HTTPException(422, 'Choose a valid wrap coverage option.')
        else:
            if coverage_id:
                raise HTTPException(422, 'Wrap coverage selection is not available for this product.')
            coverage_option = None

        if include_roof_wrap and (not cfg.get('is_wrap') or coverage_id != 'full'):
            raise HTTPException(422, 'Roof coverage can only be added to a full vehicle wrap.')

        vehicle_type_options = cfg.get('vehicle_type_options', [])
        vehicle_type_id = str(item.get('vehicle_type', '') or '').strip().lower()
        if vehicle_type_options:
            if not vehicle_type_id:
                vehicle_type_id = vehicle_type_options[0]['id']
            vehicle_type_option = next((o for o in vehicle_type_options if o['id'] == vehicle_type_id), None)
            if not vehicle_type_option:
                raise HTTPException(422, 'Choose a valid vehicle or trailer type.')
        else:
            if vehicle_type_id:
                raise HTTPException(422, 'Vehicle type selection is not available for this product.')
            vehicle_type_option = None

        coverage_factor = D(coverage_option['multiplier']) if coverage_option else D(1)
        vehicle_factor = D(vehicle_type_option['multiplier']) if vehicle_type_option else D(1)
        pricing_factor = coverage_factor * vehicle_factor

        net_area = area * qty
        material_area = net_area * (1 + D(cfg['waste_percent']) / 100)
        labor_hours = D(cfg['labor_minutes_per_unit']) * qty / 60

        lamination_options = cfg.get('lamination_options', [])
        lamination = str(item.get('lamination', '') or '').strip().lower()
        if lamination_options:
            if not lamination:
                lamination = next((o['id'] for o in lamination_options if o.get('default')), lamination_options[0]['id'])
            lamination_option = next((o for o in lamination_options if o['id'] == lamination), None)
            if not lamination_option:
                raise HTTPException(422, 'Choose a valid lamination option.')
        else:
            if lamination:
                raise HTTPException(422, 'Lamination is not available for this product.')
            lamination_option = None
        lamination_sell = net_area * D(lamination_option['sell_per_sqft']) * 100 if lamination_option else D(0)
        lamination_cost = material_area * D(lamination_option['cost_per_sqft']) * 100 if lamination_option else D(0)

        material_options = cfg.get('material_options', [])
        material = str(item.get('material', '') or '').strip().lower()
        if material_options:
            if not material:
                material = next((o['id'] for o in material_options if o.get('default')), material_options[0]['id'])
            material_option = next((o for o in material_options if o['id'] == material), None)
            if not material_option:
                raise HTTPException(422, 'Choose a valid material option.')
        else:
            if material:
                raise HTTPException(422, 'Material selection is not available for this product.')
            material_option = None
        material_sell = net_area * D(material_option['sell_per_sqft_adjustment']) * 100 if material_option else D(0)
        material_cost = material_area * D(material_option['cost_per_sqft_adjustment']) * 100 if material_option else D(0)

        installation_hours = D(0)
        if installation_requested:
            installation_hours = net_area * D(cfg.get('installation_minutes_per_sqft', '0')) / 60
            if row['id'] not in installation_setup_applied:
                installation_hours += D(cfg.get('installation_setup_minutes', '0')) / 60
                installation_setup_applied.add(row['id'])

        raw_cost = (material_area * D(cfg['cost_per_sqft']) * 100 * pricing_factor + D(cfg['setup_cost']) * 100
                    + labor_hours * labor_cost * pricing_factor + lamination_cost + material_cost + installation_hours * labor_cost * pricing_factor)
        cost = cent_round(raw_cost * (1 + overhead))

        if cfg.get('quantity_price_table'):
            base_total = table_total(qty, cfg['quantity_price_table']) * 100
            base_area = D(cfg['price_table_base_width']) * D(cfg['price_table_base_height']) / 144
            area_ratio = area / base_area
            size_weight = D(cfg['price_table_size_weight'])
            size_factor = (D(1) - size_weight) + size_weight * area_ratio
            calculated = base_total * size_factor * pricing_factor + lamination_sell + material_sell + installation_hours * labor_sell * pricing_factor
        else:
            band_qty = weighted_quantity(qty, cfg['tiers'])
            calculated = (D(cfg['setup_price']) * 100 + area * band_qty * D(cfg['sell_per_sqft']) * 100 * pricing_factor
                          + labor_hours * labor_sell * pricing_factor + lamination_sell + material_sell + installation_hours * labor_sell * pricing_factor)

        floor = 0 if cfg.get('quantity_price_table') else int((D(cost) / (1 - margin)).quantize(D('1'), rounding=ROUND_CEILING))
        sell = max(cent_round(calculated), cents(cfg['minimum_price']), floor)
        if include_roof_wrap:
            sell = cent_round(D(sell) * D('1.20'))
            cost = cent_round(D(cost) * D('1.20'))
        if garment_price is not None:
            sell = cent_round(D(garment_price) * 100 * weighted_quantity(qty, cfg['tiers']) + D(garment_fee) * 100)
        retail_sell = sell
        wholesale_discount = product_discounts.get(row['id'], wholesale_default)
        if wholesale and wholesale_discount > 0:
            protected_fee = min(sell, cents(cfg.get('digitizing_fee', 0) if cfg.get('finished_apparel') else cfg['setup_price']))
            if row['category'] == 'Custom' or any(word in row['name'].lower() for word in ('design', 'digitiz')):
                protected_fee = sell
            discounted = protected_fee + cent_round(D(sell - protected_fee) * (D(1) - wholesale_discount / 100))
            sell = max(discounted, cost)
        if sell > 1_000_000_000:
            raise HTTPException(422, 'This project exceeds the automatic estimating limit. Split the job or request a manual quote.')
        review = (not cfg['instant'] or cfg.get('requires_installation', False) or installation_requested or design_requested
                  or width > D(cfg['max_width']) or height > D(cfg['max_height']))
        workflow_id = cfg.get('installation_workflow_id') if installation_requested else row['workflow_id']
        if installation_requested and not workflow_id:
            raise HTTPException(422, 'Installation workflow is not configured for this product.')
        lines.append({
            'product_id': row['id'], 'product_version': row['version'], 'name': row['name'],
            'finished_apparel': bool(cfg.get('finished_apparel')),
            'artwork_upload_disabled': bool(cfg.get('artwork_upload_disabled')),
            'shirt_color': item.get('shirt_color', '') if garment_price is not None else '',
            'size_quantities': item.get('size_quantities', {}) if garment_price is not None else {},
            'print_locations': item.get('print_locations', []) if garment_price is not None else [],
            'embroidery_preview': embroidery_preview,
            'digitizing_fee_cents': garment_fee * 100,
            'quote_only': bool(cfg.get('quote_only')) or design_requested,
            'category': row['category'], 'description': str(item.get('description', ''))[:200],
            'width': str(width), 'height': str(height), 'quantity': qty, 'unit': cfg['unit'],
            'net_sqft': str(net_area.quantize(D('0.0001'))),
            'material_sqft': str(material_area.quantize(D('0.0001'))),
            'labor_hours': str(labor_hours), 'sell_cents': sell, 'cost_cents': cost,
            'retail_sell_cents': retail_sell, 'wholesale_discount_percent': str(wholesale_discount) if wholesale else '',
            'price_per_item_cents': cent_round(D(sell) / qty), 'review_required': review,
            'installation_requested': installation_requested,
            'design_requested': design_requested,
            'usdot_design': generated_usdot,
            'self_approve_artwork': bool(cfg.get('self_approve_artwork', False)),
            'installation_estimate_cents': cent_round(installation_hours * labor_sell),
            'lamination': lamination_option['id'] if lamination_option else '',
            'lamination_label': lamination_option['label'] if lamination_option else '',
            'lamination_cents': cent_round(lamination_sell),
            'material': material_option['id'] if material_option else '',
            'material_label': material_option['label'] if material_option else '',
            'material_cents': cent_round(material_sell),
            'coverage_option': coverage_option['id'] if coverage_option else '',
            'coverage_label': coverage_option['label'] if coverage_option else '',
            'include_roof_wrap': include_roof_wrap,
            'vehicle_type': vehicle_type_option['id'] if vehicle_type_option else '',
            'vehicle_type_label': vehicle_type_option['label'] if vehicle_type_option else '',
            'workflow_id': workflow_id, 'floor_applied': sell == floor,
            'rate_snapshot': cfg,
        })
    line_subtotal = sum(x['sell_cents'] for x in lines)
    minimum_order = cents(shop.get('minimum_order_price', '50'), 'Minimum order price')
    apply_order_minimum = not all(x['category'] == 'Custom' or x['finished_apparel'] for x in lines)
    return {'lines': lines, 'subtotal_cents': line_subtotal,
            'wholesale': {'name': wholesale['name']} if wholesale else None,
            'minimum_order_adjustment_cents': 0,
            'minimum_order_cents': minimum_order if apply_order_minimum else 0,
            'meets_minimum_order': (not apply_order_minimum) or line_subtotal >= minimum_order,
            'cost_cents': sum(x['cost_cents'] for x in lines),
            'review_required': any(x['review_required'] for x in lines) or not shop['rates_live'],
            'settings_snapshot': {k: shop[k] for k in ['target_margin_percent', 'overhead_percent',
                                                       'labor_cost_per_hour', 'labor_sell_per_hour', 'minimum_order_price']},
            'currency': 'USD', 'pricing_basis': 'Server-calculated product rates, quantity breaks, finishing options and labor; a shop-wide minimum order may apply; waste affects internal cost only.'}


def public_quote(quote: dict) -> dict:
    return {k: v for k, v in quote.items() if k not in ('cost_cents', 'settings_snapshot')} | {
        'lines': [{k: v for k, v in line.items() if k not in
                   ('cost_cents', 'rate_snapshot', 'material_sqft', 'labor_hours', 'floor_applied', 'workflow_id')}
                  for line in quote['lines']]}
