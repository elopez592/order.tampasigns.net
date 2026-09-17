from __future__ import annotations
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
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
        if versions not in ([1], [1, 2]):
            raise RuntimeError('Unsupported database schema; back up and migrate explicitly.')
        conn.execute('INSERT OR IGNORE INTO schema_version VALUES (2)')
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
