"""Sanitized image uploads and deterministic dimensioned panel proof generation.
No AI imagery, bleed, ICC conversion, RIP output or full-scale cutting files.
"""
from __future__ import annotations
import hashlib
import io
import json
import math
import secrets
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from fastapi import HTTPException
from .db import now

Image.MAX_IMAGE_PIXELS = 50_000_000
MAX_UPLOAD = 50 * 1024 * 1024


def sanitize(raw: bytes, filename: str):
    if not raw or len(raw) > MAX_UPLOAD:
        raise HTTPException(413, 'Files must be non-empty and no larger than 50 MB.')
    name = Path(filename.replace('\\', '/')).name[:180] or 'artwork'
    suffix = Path(name).suffix.lower()
    if suffix == '.pdf' and raw.startswith(b'%PDF-'):
        return raw, name, 'application/pdf', '.pdf'
    if suffix not in ('.png', '.jpg', '.jpeg'):
        raise HTTPException(422, 'Upload a PNG, JPEG or PDF. SVG, HTML and executable formats are not accepted.')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('JPEG', 'PNG') or image.width * image.height > Image.MAX_IMAGE_PIXELS:
                raise ValueError('Unsupported or oversized image.')
            image.load()
            clean = ImageOps.exif_transpose(image).convert('RGBA')
            out = io.BytesIO()
            clean.save(out, format='PNG')
            return out.getvalue(), Path(name).stem + '.png', 'image/png', '.png'
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, 'The image is invalid or exceeds the 50-megapixel limit.') from exc


def save_asset(conn, directory: Path, job_id: int, raw: bytes, name: str, mime: str, suffix: str, kind: str, actor: str):
    stored = secrets.token_hex(24) + suffix
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / stored
    path.write_bytes(raw)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    asset_id = conn.execute('INSERT INTO assets(job_id,filename,stored_name,mime,sha256,size,kind,created_at,uploaded_by) VALUES(?,?,?,?,?,?,?,?,?)',
        (job_id, name, stored, mime, hashlib.sha256(raw).hexdigest(), len(raw), kind, now(), actor)).lastrowid
    return asset_id


def usdot_proof_pdf(raw: bytes, job_number: str, item_number: int, line: dict) -> bytes:
    """Make a dimensioned shop draft from the exact generated USDOT artwork."""
    page = Image.new('RGB', (1650, 1275), 'white')  # 11 x 8.5 in at 150 dpi
    draw = ImageDraw.Draw(page)
    title = ImageFont.load_default(size=39)
    normal = ImageFont.load_default(size=25)
    small = ImageFont.load_default(size=19)
    ink, muted, teal = '#112225', '#51676a', '#007f83'
    draw.text((75, 65), f'{job_number}  /  USDOT DESIGN DRAFT', font=title, fill=ink)
    draw.text((75, 124), f'Item {item_number}  |  {line["width"]} x {line["height"]} in  |  Qty {line["quantity"]}', font=normal, fill=teal)
    draw.rectangle((75, 190, 1575, 1090), outline='#b8c9ca', width=3)
    with Image.open(io.BytesIO(raw)) as source:
        artwork = ImageOps.contain(source.convert('RGBA'), (1450, 850), method=Image.Resampling.LANCZOS)
    color = line.get('usdot_design', {}).get('text_color', '#111111').lstrip('#')
    rgb = tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    backdrop = '#546166' if sum(rgb) / 3 > 170 else 'white'
    preview = Image.new('RGBA', artwork.size, backdrop)
    preview.alpha_composite(artwork)
    page.paste(preview.convert('RGB'), (825 - artwork.width // 2, 640 - artwork.height // 2))
    draw.text((75, 1125), 'Check spelling, USDOT number, positioning, color and finished size.', font=normal, fill=ink)
    draw.text((75, 1170), 'Preview backdrop is for contrast only; it is not printed.', font=small, fill=muted)
    draw.text((75, 1205), 'Shop review required. This draft is not an approved proof or a production file.', font=small, fill=muted)
    output = io.BytesIO()
    page.save(output, format='PDF', resolution=150.0)
    return output.getvalue()


def panel_sheet(conn, directory: Path, job, mappings: dict, fit='contain') -> bytes:
    if fit not in ('contain', 'cover'):
        raise HTTPException(422, 'Fit must be contain or cover.')
    all_lines = json.loads(job['quote_snapshot'])['lines']
    indexed_lines = [(i, line) for i, line in enumerate(all_lines)
                     if line.get('artwork_required', not line.get('artwork_upload_disabled', False))
                     and line.get('width') not in (None, '') and line.get('height') not in (None, '')]
    if not indexed_lines:
        raise HTTPException(422, 'This quote has no product lines that require an artwork layout.')
    lines = [line for _, line in indexed_lines]
    columns = min(3, len(lines))
    tilew, tileh = 540, 450
    canvas = Image.new('RGB', (columns * tilew + 64, math.ceil(len(lines) / columns) * tileh + 180), '#f0f3f6')
    draw = ImageDraw.Draw(canvas)
    title = ImageFont.load_default(size=26)
    normal = ImageFont.load_default(size=17)
    small = ImageFont.load_default(size=13)
    draw.text((32, 25), f'{job["number"]} | DIMENSIONED PANEL LAYOUT', font=title, fill='#112536')
    draw.text((32, 67), 'Visual reference only. No bleed or print scale. Each panel uses the same relative scale.', font=small, fill='#536578')
    maxw = max(float(line['width']) for line in lines)
    maxh = max(float(line['height']) for line in lines)
    scale = min(420 / maxw, 320 / maxh)
    for i, line in enumerate(lines):
        left = 32 + (i % columns) * tilew
        top = 105 + (i // columns) * tileh
        draw.rounded_rectangle((left, top, left + tilew - 18, top + tileh - 18), radius=12, fill='white')
        label = line['description'] or line['name']
        draw.text((left + 18, top + 14), label[:49], font=normal, fill='#112536')
        w, h = max(1, round(float(line['width']) * scale)), max(1, round(float(line['height']) * scale))
        x, y = left + (tilew - 18 - w) // 2, top + 48 + (320 - h) // 2
        draw.rectangle((x, y, x + w, y + h), fill='#e6eef3', outline='#112536', width=2)
        source_index = indexed_lines[i][0]
        aid = mappings.get(str(source_index))
        if aid is not None:
            asset = conn.execute('SELECT * FROM assets WHERE id=? AND job_id=?', (aid, job['id'])).fetchone()
            if not asset or asset['mime'] != 'image/png':
                raise HTTPException(422, 'Generated layouts require a PNG/JPEG artwork asset belonging to this job.')
            with Image.open(directory / asset['stored_name']) as art:
                art = art.convert('RGBA')
                if fit == 'cover':
                    placed = ImageOps.fit(art, (w, h), method=Image.Resampling.LANCZOS)
                else:
                    resized = ImageOps.contain(art, (w, h), method=Image.Resampling.LANCZOS)
                    placed = Image.new('RGBA', (w, h), 'white')
                    placed.alpha_composite(resized, ((w - resized.width) // 2, (h - resized.height) // 2))
                canvas.paste(placed, (x, y), placed)
            draw.rectangle((x, y, x + w, y + h), outline='#112536', width=2)
        else:
            draw.text((x + 6, y + max(4, h // 2 - 8)), 'ARTWORK AREA', font=small, fill='#536578')
        draw.text((left + 18, top + 383), f'{line["width"]} in W x {line["height"]} in H   |   Qty {line["quantity"]}', font=normal, fill='#112536')
        draw.text((left + 18, top + 408), f'Panel {i + 1}   |   {line["name"][:47]}', font=small, fill='#536578')
    draw.text((32, canvas.height - 42), f'Check every panel. Fit: {fit}. Screen colors are not a print-color guarantee.', font=small, fill='#536578')
    output = io.BytesIO()
    canvas.save(output, format='PNG')
    return output.getvalue()
