from __future__ import annotations
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=20, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=20000')
    return conn


@contextmanager
def transaction(path: Path, write: bool = False) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.executescript(Path(__file__).with_name('schema.sql').read_text())
        versions = [r[0] for r in conn.execute('SELECT version FROM schema_version')]
        if versions not in ([1], [1, 2], [1, 2, 3], [1, 2, 3, 4], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6, 7], [1, 2, 3, 4, 5, 6, 7, 8]):
            raise RuntimeError('Unsupported database schema; back up and migrate explicitly.')
        conn.execute('INSERT OR IGNORE INTO schema_version VALUES (2)')
        conn.execute('INSERT OR IGNORE INTO schema_version VALUES (3)')
        conn.execute('INSERT OR IGNORE INTO schema_version VALUES (4)')
        columns = {r[1] for r in conn.execute("PRAGMA table_info(wholesale_clients)")}
        if 'username' not in columns:
            conn.execute('ALTER TABLE wholesale_clients ADD COLUMN username TEXT COLLATE NOCASE')
            for row in conn.execute('SELECT id FROM wholesale_clients WHERE username IS NULL OR username=""').fetchall():
                conn.execute('UPDATE wholesale_clients SET username=? WHERE id=?', (f'client{row["id"]}', row['id']))
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS wholesale_clients_username ON wholesale_clients(username COLLATE NOCASE)')
        conn.execute('INSERT OR IGNORE INTO schema_version VALUES (5)')
        conn.execute('INSERT OR IGNORE INTO schema_version VALUES (6)')
        conn.execute('INSERT OR IGNORE INTO schema_version VALUES (7)')
        if 8 not in versions:
            # Earlier live Decals had a $50 line floor in addition to the $50 shop
            # minimum. Move only that known rate profile to area-based pricing once.
            for row in conn.execute("SELECT id,config FROM products WHERE name='Decals'").fetchall():
                cfg = json.loads(row['config'])
                try:
                    legacy_rate = (Decimal(str(cfg.get('minimum_price'))) == 50 and
                                   Decimal(str(cfg.get('setup_price'))) == 10 and
                                   Decimal(str(cfg.get('sell_per_sqft'))) == 18)
                except InvalidOperation:
                    legacy_rate = False
                if legacy_rate:
                    cfg['minimum_price'] = '0'
                    conn.execute('UPDATE products SET config=?,version=version+1,updated_at=? WHERE id=?',
                                 (json.dumps(cfg), now(), row['id']))
            conn.execute('INSERT OR IGNORE INTO schema_version VALUES (8)')
    finally:
        conn.close()
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def settings(conn) -> dict:
    row = conn.execute('SELECT data FROM settings WHERE id=1').fetchone()
    return json.loads(row['data']) if row else {}


def audit(conn, job_id, actor, action, details, public=False):
    conn.execute('INSERT INTO events(job_id,actor,action,details,public,created_at) VALUES(?,?,?,?,?,?)',
                 (job_id, actor, action, json.dumps(details), int(public), now()))
