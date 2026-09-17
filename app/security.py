from __future__ import annotations
import hashlib
import hmac
import re
import secrets
import time
from urllib.parse import urlsplit
from fastapi import HTTPException


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str) -> str:
    if not isinstance(password, str) or len(password) < 12 or len(password) > 128:
        raise HTTPException(422, 'Passwords must contain 12 to 128 characters.')
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1,
                         maxmem=64 * 1024 * 1024, dklen=32)
    return f'scrypt$32768$8$1${salt.hex()}${key.hex()}'


def password_matches(password: str, stored: str) -> bool:
    if not isinstance(password, str) or len(password) > 128:
        return False
    try:
        _, n, r, p, salt, expected = stored.split('$')
        key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                             maxmem=64 * 1024 * 1024, dklen=32)
        return hmac.compare_digest(key.hex(), expected)
    except (ValueError, TypeError):
        return False


def text(value, name: str, maxlen=500, required=False) -> str:
    if not isinstance(value, str):
        raise HTTPException(422, f'{name} must be text.')
    value = value.strip()
    if (required and not value) or len(value) > maxlen:
        raise HTTPException(422, f'{name} is required and must fit within {maxlen} characters.' if required
                            else f'{name} must fit within {maxlen} characters.')
    return value


def email(value: str) -> str:
    value = text(value, 'Email', 254, True).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise HTTPException(422, 'Enter a valid email address.')
    return value


def payment_url(value: str) -> str:
    value = text(value, 'Payment link', 3000, True)
    try:
        url = urlsplit(value)
        hostname = (url.hostname or '').lower()
        valid_host = any(hostname == root or hostname.endswith('.' + root)
                         for root in ('intuit.com', 'quickbooks.com'))
        if url.scheme != 'https' or not valid_host or url.username or url.password or url.port not in (None, 443):
            raise ValueError()
        if any(ch.isspace() for ch in value) or '\\' in value:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, 'Use an HTTPS QuickBooks/Intuit invoice or payment link. Other hosts are not allowed.')
    return value


def rate_limit(conn, bucket: str, limit: int, seconds=300):
    current = time.time()
    row = conn.execute('SELECT * FROM rate_limits WHERE bucket=?', (bucket,)).fetchone()
    if not row or row['resets_at'] <= current:
        conn.execute('INSERT OR REPLACE INTO rate_limits VALUES(?,?,?)', (bucket, 1, current + seconds))
        return True
    if row['count'] >= limit:
        return False
    conn.execute('UPDATE rate_limits SET count=count+1 WHERE bucket=?', (bucket,))
    return True
