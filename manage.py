"""Explicit local administrative commands. Run backups while app writes are paused."""
from __future__ import annotations
import argparse
from getpass import getpass
from pathlib import Path
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from app.db import transaction, audit
from app.security import password_hash, email


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['reset-password','backup'])
    parser.add_argument('--email')
    parser.add_argument('--output', default='backups')
    args = parser.parse_args()
    folder = Path(os.getenv('DATA_DIR', './data')).resolve()
    database = folder / 'signshop.sqlite3'
    if not database.exists():
        raise SystemExit('No database yet. Run the application once first.')
    if args.command == 'reset-password':
        address = email(args.email or input('Staff email: '))
        password = getpass('New password (12-128 characters): ')
        if password != getpass('Repeat password: '):
            raise SystemExit('Passwords do not match.')
        with transaction(database, True) as conn:
            user = conn.execute('SELECT id FROM users WHERE email=?', (address,)).fetchone()
            if not user:
                raise SystemExit('No staff account with this email.')
            conn.execute('UPDATE users SET password_hash=?,active=1 WHERE id=?', (password_hash(password), user['id']))
            conn.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
            audit(conn, None, 'Local administrator CLI', 'staff.password_reset', {'user_id': user['id']})
        print('Password reset. Existing sessions for this account were revoked.')
    else:
        target = Path(args.output).resolve()
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        filename = target / f'signshop-backup-{stamp}.zip'
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / 'signshop.sqlite3'
            source = sqlite3.connect(database)
            destination = sqlite3.connect(snapshot)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()
            with zipfile.ZipFile(filename, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, 'signshop.sqlite3')
                for item in (folder / 'uploads').glob('*'):
                    if item.is_file():
                        archive.write(item, 'uploads/' + item.name)
        try:
            filename.chmod(0o600)
        except OSError:
            pass
        print(f'Backup created: {filename}')
        print('Contains private job files and password hashes. Encrypt and store securely off-server. Test restores.')


if __name__ == '__main__':
    main()
