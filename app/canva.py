from __future__ import annotations

import base64
import hashlib
import math
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from .db import now

AUTH_URL = 'https://www.canva.com/api/oauth/authorize'
TOKEN_URL = 'https://api.canva.com/rest/v1/oauth/token'
DESIGNS_URL = 'https://api.canva.com/rest/v1/designs'
SCOPE = 'design:content:write'
MAX_DIMENSION = 8000
MAX_AREA = 25_000_000
TARGET_DPI = 150


def config(public_url: str) -> dict:
    client_id = os.getenv('CANVA_CLIENT_ID', '').strip()
    client_secret = os.getenv('CANVA_CLIENT_SECRET', '').strip()
    redirect_uri = os.getenv('CANVA_REDIRECT_URI', '').strip() or f'{public_url.rstrip("/")}/api/canva/callback'
    return {
        'configured': bool(client_id and client_secret),
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
    }


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def code_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode('ascii')).digest())


def begin_oauth(conn, token_hash: str, public_url: str, return_path: str = '/') -> str:
    cfg = config(public_url)
    if not cfg['configured']:
        raise HTTPException(503, 'Canva is not configured yet. Add CANVA_CLIENT_ID and CANVA_CLIENT_SECRET in Railway.')
    state = secrets.token_urlsafe(72)
    verifier = secrets.token_urlsafe(72)
    safe_return = return_path if isinstance(return_path, str) and return_path.startswith('/') and not return_path.startswith('//') else '/'
    expires = time.time() + 15 * 60
    conn.execute('DELETE FROM canva_oauth_states WHERE expires_at<?', (time.time(),))
    conn.execute(
        '''INSERT INTO canva_oauth_states(state,token_hash,code_verifier,return_path,expires_at,created_at)
           VALUES(?,?,?,?,?,?)''',
        (state, token_hash, verifier, safe_return, expires, now())
    )
    params = {
        'code_challenge': code_challenge(verifier),
        'code_challenge_method': 'S256',
        'scope': SCOPE,
        'response_type': 'code',
        'client_id': cfg['client_id'],
        'state': state,
        'redirect_uri': cfg['redirect_uri'],
    }
    return AUTH_URL + '?' + urlencode(params)


def auth_headers(public_url: str) -> dict:
    cfg = config(public_url)
    credentials = f'{cfg["client_id"]}:{cfg["client_secret"]}'.encode('utf-8')
    return {
        'Authorization': 'Basic ' + base64.b64encode(credentials).decode('ascii'),
        'Content-Type': 'application/x-www-form-urlencoded',
    }


def exchange_code(conn, state: str, code: str, public_url: str) -> str:
    cfg = config(public_url)
    if not cfg['configured']:
        raise HTTPException(503, 'Canva is not configured yet.')
    row = conn.execute('SELECT * FROM canva_oauth_states WHERE state=? AND expires_at>?', (state, time.time())).fetchone()
    if not row:
        raise HTTPException(400, 'Canva authorization expired. Try connecting again.')
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'code_verifier': row['code_verifier'],
        'redirect_uri': cfg['redirect_uri'],
    }
    token = _token_request(public_url, data)
    store_token(conn, row['token_hash'], token)
    conn.execute('DELETE FROM canva_oauth_states WHERE state=? OR expires_at<?', (state, time.time()))
    return row['return_path'] or '/'


def store_token(conn, token_hash: str, token: dict) -> None:
    expires_in = max(60, int(token.get('expires_in') or 3600))
    expires_at = time.time() + expires_in - 60
    conn.execute(
        '''INSERT INTO canva_tokens(token_hash,access_token,refresh_token,scope,expires_at,updated_at)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(token_hash) DO UPDATE SET
             access_token=excluded.access_token,
             refresh_token=excluded.refresh_token,
             scope=excluded.scope,
             expires_at=excluded.expires_at,
             updated_at=excluded.updated_at''',
        (
            token_hash,
            str(token.get('access_token') or ''),
            str(token.get('refresh_token') or ''),
            str(token.get('scope') or SCOPE),
            expires_at,
            now(),
        )
    )


def _token_request(public_url: str, data: dict) -> dict:
    try:
        response = httpx.post(TOKEN_URL, headers=auth_headers(public_url), data=data, timeout=20)
    except httpx.HTTPError as exc:
        raise HTTPException(502, 'Canva did not respond. Try again in a moment.') from exc
    if response.status_code >= 400:
        raise HTTPException(502, 'Canva authorization failed. Check the Canva app credentials and redirect URL.')
    token = response.json()
    if not token.get('access_token') or not token.get('refresh_token'):
        raise HTTPException(502, 'Canva did not return usable credentials.')
    return token


def access_token(conn, token_hash: str, public_url: str) -> str | None:
    row = conn.execute('SELECT * FROM canva_tokens WHERE token_hash=?', (token_hash,)).fetchone()
    if not row:
        return None
    if row['expires_at'] > time.time() + 30:
        return row['access_token']
    if not row['refresh_token']:
        return None
    token = _token_request(public_url, {'grant_type': 'refresh_token', 'refresh_token': row['refresh_token']})
    store_token(conn, token_hash, token)
    return str(token.get('access_token') or '')


def canva_pixels(width_in: float, height_in: float) -> dict:
    width = max(0.1, min(10_000.0, float(width_in)))
    height = max(0.1, min(10_000.0, float(height_in)))
    raw_w = max(40, round(width * TARGET_DPI))
    raw_h = max(40, round(height * TARGET_DPI))
    scale = min(1.0, MAX_DIMENSION / raw_w, MAX_DIMENSION / raw_h, math.sqrt(MAX_AREA / max(1, raw_w * raw_h)))
    px_w = max(40, min(MAX_DIMENSION, round(raw_w * scale)))
    px_h = max(40, min(MAX_DIMENSION, round(raw_h * scale)))
    return {
        'width_px': px_w,
        'height_px': px_h,
        'dpi': TARGET_DPI,
        'scale': scale,
        'scale_label': 'full size' if scale > 0.995 else f'1:{round(1 / scale, 1):g} scale',
    }


def create_design(conn, token_hash: str, public_url: str, title: str, width_in: float, height_in: float) -> dict:
    token = access_token(conn, token_hash, public_url)
    if not token:
        raise HTTPException(401, 'Connect Canva first.')
    size = canva_pixels(width_in, height_in)
    payload = {
        'type': 'type_and_asset',
        'design_type': {
            'type': 'custom',
            'width': size['width_px'],
            'height': size['height_px'],
        },
        'title': str(title or 'Tampa Signs artwork')[:255],
    }
    try:
        response = httpx.post(
            DESIGNS_URL,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            json=payload,
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(502, 'Canva did not respond. Try again in a moment.') from exc
    if response.status_code == 401:
        conn.execute('DELETE FROM canva_tokens WHERE token_hash=?', (token_hash,))
        raise HTTPException(401, 'Connect Canva again.')
    if response.status_code >= 400:
        raise HTTPException(502, 'Canva could not create this design.')
    design = response.json().get('design') or {}
    urls = design.get('urls') or {}
    return {
        'design_id': design.get('id'),
        'edit_url': urls.get('edit_url'),
        'view_url': urls.get('view_url'),
        'width_px': size['width_px'],
        'height_px': size['height_px'],
        'scale_label': size['scale_label'],
    }
