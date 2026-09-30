"""Turn explicitly reviewed customer uploads into an approved complete proof."""
import hashlib
import io
import json
import textwrap

from fastapi import Body, Depends, HTTPException, Request
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .db import audit, now, transaction
from .domain import get_job, latest_proof, production_started
from .images import save_asset
from .job_terms import APPROVAL_STATEMENT, record_acceptance, validate_version
from .security import text


def survey_pending(conn, job_id):
    row = conn.execute('SELECT status FROM job_site_surveys WHERE job_id=?', (job_id,)).fetchone()
    return bool(row and row['status'] == 'requested')


def request_survey(conn, job_id, location='', note=''):
    conn.execute('''INSERT INTO job_site_surveys(job_id,status,location,note,updated_at)
        VALUES(?,'requested',?,?,?) ON CONFLICT(job_id) DO UPDATE SET
        status='requested',location=excluded.location,note=excluded.note,updated_at=excluded.updated_at''',
        (job_id, location, note, now()))


def package_image(job, lines, assets, uploads):
    """Contact sheet references the complete, hashed source-file manifest."""
    width, row_height = 1200, 260
    canvas = Image.new('RGB', (width, 160 + row_height * len(assets) + 90), 'white')
    draw = ImageDraw.Draw(canvas)
    title, normal, small = [ImageFont.load_default(size=size) for size in (30, 22, 17)]
    draw.rectangle((0, 0, width, 115), fill='#102527')
    draw.text((35, 23), job['number'] + ' / APPROVED UPLOAD PREVIEW', font=title, fill='white')
    draw.text((35, 73), 'Customer approval applies to the exact listed files and ordered dimensions.', font=small, fill='#8ae1de')
    for index, (asset, mapped) in enumerate(assets):
        top = 145 + index * row_height
        draw.rounded_rectangle((25, top, width - 25, top + row_height - 16), radius=12, outline='#becfce', width=2)
        if asset['mime'] == 'image/png':
            with Image.open(uploads / asset['stored_name']) as source:
                thumb = ImageOps.contain(source.convert('RGBA'), (350, 205), Image.Resampling.LANCZOS)
                back = Image.new('RGBA', thumb.size, '#e9eeee')
                back.alpha_composite(thumb)
                canvas.paste(back.convert('RGB'), (40 + (350-thumb.width)//2, top + 16 + (205-thumb.height)//2))
        else:
            draw.text((95, top + 65), 'PDF ARTWORK', font=title, fill='#126b6b')
            draw.text((56, top + 115), 'Review every page in the source PDF.', font=small, fill='#445858')
        for row, label in enumerate(textwrap.wrap(asset['filename'], 57)[:2]):
            draw.text((420, top + 16 + row * 25), label, font=normal, fill='#102527')
        details = '; '.join(f'Item {i+1}: {lines[i]["name"]} / {lines[i]["width"]} x {lines[i]["height"]} in / Qty {lines[i]["quantity"]}' for i in mapped)
        for row, label in enumerate(textwrap.wrap(details, 76)[:5]):
            draw.text((420, top + 77 + row * 23), label, font=small, fill='#314749')
        draw.text((420, top + 209), 'SHA256 ' + asset['sha256'][:32], font=small, fill='#58716f')
    draw.text((35, canvas.height - 60), 'Screen colors may differ from print. Approved artwork is final; changes after printing require a new order.', font=small, fill='#334947')
    out = io.BytesIO()
    canvas.save(out, format='PNG')
    return out.getvalue()


def install(app, database, uploads, portal_job, require_admin, add_proof, actor):
    @app.post('/api/portal/artwork-preview/approve')
    def approve_preview(request: Request, payload: dict = Body(...)):
        signer = text(payload.get('name', ''), 'Full name', 120, True)
        validate_version(payload, required=True)
        if payload.get('confirm') is not True:
            raise HTTPException(422, 'Review and explicitly approve every preview, file and ordered dimension.')
        submitted = payload.get('files')
        if not isinstance(submitted, list) or not 1 <= len(submitted) <= 60:
            raise HTTPException(422, 'An approved preview needs 1 to 60 artwork files.')
        with transaction(database, True) as conn:
            job = portal_job(conn, request)
            if job['archived'] or production_started(conn, job['id']):
                raise HTTPException(409, 'Artwork cannot be changed after production starts. Request a new order.')
            if job['accepted_version'] != job['quote_version'] or payload.get('quote_version') != job['quote_version']:
                raise HTTPException(409, 'The order scope changed. Accept and review the current order first.')
            if survey_pending(conn, job['id']):
                raise HTTPException(409, 'Your requested site survey must be completed before approving sizing for print.')
            quote = json.loads(job['quote_snapshot'])
            lines = quote['lines']
            if quote['review_required'] or any(line.get('design_requested') or line.get('installation_requested') or line.get('is_wrap') for line in lines):
                raise HTTPException(409, 'This custom project needs a shop proof for its verified layout and scope.')
            needed = {i for i, line in enumerate(lines) if not line.get('artwork_upload_disabled')}
            covered, seen, checked, manifest = set(), set(), [], []
            for file in submitted:
                if not isinstance(file, dict) or type(file.get('asset_id')) is not int or file['asset_id'] in seen:
                    raise HTTPException(422, 'Each approved file must appear once.')
                indexes = file.get('line_indices')
                if not isinstance(indexes, list) or not indexes or any(type(i) is not int or i not in needed for i in indexes) or len(set(indexes)) != len(indexes):
                    raise HTTPException(422, 'Assign every approved file to its printed product or products.')
                asset = conn.execute("SELECT * FROM assets WHERE id=? AND job_id=? AND kind='artwork'", (file['asset_id'], job['id'])).fetchone()
                if not asset:
                    raise HTTPException(404, 'The approved artwork must belong to this order.')
                try:
                    fingerprint = hashlib.sha256((uploads / asset['stored_name']).read_bytes()).hexdigest()
                except OSError:
                    raise HTTPException(409, 'An artwork file is unavailable. Upload it again before approval.')
                if fingerprint != asset['sha256'] or file.get('sha256') != fingerprint:
                    raise HTTPException(409, 'An artwork file changed. Review the exact uploaded file again.')
                seen.add(asset['id']); covered.update(indexes)
                checked.append((asset, indexes))
                manifest.append({'asset_id': asset['id'], 'sha256': fingerprint,
                                 'filename': asset['filename'], 'line_indices': sorted(indexes)})
            if covered != needed:
                raise HTTPException(422, 'Approve artwork for every printed product and side in this order.')
            previous = latest_proof(conn, job['id'])
            if previous:
                decision = conn.execute('SELECT * FROM job_terms_acceptances WHERE proof_id=? ORDER BY id DESC LIMIT 1', (previous['id'],)).fetchone()
                if previous['status'] == 'approved' and decision and decision['quote_version'] == job['quote_version'] and json.loads(decision['file_manifest']) == manifest:
                    return {'ok': True, 'proof_id': previous['id'], 'already_approved': True}
                raise HTTPException(409, 'A proof already exists. Review the latest proof or request a revised version from the shop.')
            if len(checked) == 1:
                proof_asset = checked[0][0]['id']
            else:
                raw = package_image(job, lines, checked, uploads)
                proof_asset = save_asset(conn, uploads, job['id'], raw, job['number'] + '-approved-preview-package.png',
                                         'image/png', '.png', 'proof', 'Customer upload preview')
            pid = add_proof(conn, job, proof_asset, 'Customer-approved upload preview',
                            'Exact uploaded artwork and preview approved at checkout. No second approval of the same artwork is required.', signer + ' (private job link)')
            proof_asset_row = conn.execute('SELECT sha256 FROM assets WHERE id=?', (proof_asset,)).fetchone()
            conn.execute('''INSERT INTO proof_decisions
                (proof_id,action,signer_name,comment,statement,quote_version,file_hash,created_at,method)
                VALUES(?,'approve',?,?,?,?,?,?,'customer_upload_preview')''',
                (pid, signer, 'Reviewed uploaded artwork and instant previews at checkout.', APPROVAL_STATEMENT,
                 job['quote_version'], proof_asset_row['sha256'], now()))
            conn.execute("UPDATE proofs SET status='approved' WHERE id=?", (pid,))
            record_acceptance(conn, job, signer, 'customer_upload_preview', proof_id=pid, files=manifest)
            audit(conn, job['id'], signer + ' (private job link)', 'proof.approve',
                  {'proof_version': 1, 'comment': 'Upload previews approved at checkout.'}, True)
            return {'ok': True, 'proof_id': pid}

    @app.post('/api/staff/jobs/{job_id}/site-survey/complete')
    def complete_survey(job_id: int, request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        note = text(payload.get('note', ''), 'Verified measurement / survey notes', 2000, True)
        if payload.get('confirm') is not True:
            raise HTTPException(422, 'Confirm the survey and measurements are complete.')
        with transaction(database, True) as conn:
            job = get_job(conn, job_id)
            if not survey_pending(conn, job_id) or job['archived']:
                raise HTTPException(409, 'No pending site survey exists for this job.')
            conn.execute("UPDATE job_site_surveys SET status='complete',note=?,updated_at=? WHERE job_id=?", (note, now(), job_id))
            audit(conn, job_id, actor(user), 'site_survey.completed', {'note': note}, True)
            return {'ok': True}
