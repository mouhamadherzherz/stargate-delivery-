# -*- coding: utf-8 -*-
"""Safe SQLite backup/restore primitives used by administration workflows."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(db_path: str, backup_dir: str, retention: int = 14) -> dict:
    """Create a consistent compressed backup and a signed-by-hash manifest."""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(db_path)
    os.makedirs(backup_dir, mode=0o700, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    temp_db = os.path.join(backup_dir, f'.stargate_{stamp}.db.tmp')
    raw_db = os.path.join(backup_dir, f'stargate_{stamp}.db')
    archive = raw_db + '.gz'
    try:
        source = sqlite3.connect(db_path, timeout=30)
        destination = sqlite3.connect(temp_db)
        with destination:
            source.backup(destination)
        destination.close()
        source.close()
        os.replace(temp_db, raw_db)
        os.chmod(raw_db, 0o600)
        with open(raw_db, 'rb') as source_file, gzip.open(archive, 'wb', compresslevel=9) as archive_file:
            shutil.copyfileobj(source_file, archive_file)
        os.chmod(archive, 0o600)
        digest = _sha256(archive)
        manifest = {'file': os.path.basename(archive), 'sha256': digest, 'created_at': stamp, 'size': os.path.getsize(archive)}
        manifest_path = archive + '.json'
        with open(manifest_path, 'w', encoding='utf-8') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
        os.chmod(manifest_path, 0o600)
    finally:
        for path in (temp_db, raw_db):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
    archives = sorted((os.path.join(backup_dir, name) for name in os.listdir(backup_dir) if name.endswith('.db.gz')), reverse=True)
    for old_archive in archives[max(1, retention):]:
        for path in (old_archive, old_archive + '.json'):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
    return manifest


def verify_backup(archive_path: str, manifest_path: str | None = None) -> bool:
    """Verify a backup against its SHA-256 manifest before restoration."""
    manifest_path = manifest_path or archive_path + '.json'
    with open(manifest_path, encoding='utf-8') as stream:
        manifest = json.load(stream)
    return os.path.basename(archive_path) == manifest['file'] and _sha256(archive_path) == manifest['sha256']


def restore_backup(archive_path: str, destination_db: str) -> None:
    """Restore only a verified gzip backup, replacing the DB atomically."""
    if not verify_backup(archive_path):
        raise ValueError('Backup integrity verification failed')
    directory = os.path.dirname(destination_db) or '.'
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='.restore_', suffix='.db', dir=directory)
    os.close(fd)
    try:
        with gzip.open(archive_path, 'rb') as source, open(temp_path, 'wb') as destination:
            shutil.copyfileobj(source, destination)
        check = sqlite3.connect(temp_path)
        result = check.execute('PRAGMA integrity_check').fetchone()[0]
        check.close()
        if result != 'ok':
            raise ValueError(f'Restored database integrity check failed: {result}')
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, destination_db)
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass
