# -*- coding: utf-8 -*-
"""Run database schema healing/migrations once before starting WSGI workers."""
from __future__ import annotations

import os
import shutil
from datetime import datetime

from app import app
from core.extensions import DB_PATH, DATA_DIR, get_db, heal_database_schema, auto_migrate_db, logger


def main() -> int:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(DATA_DIR, 'pre_migration_backups')
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f'pre_migration_{stamp}.db')
        shutil.copy2(DB_PATH, backup_path)
        os.chmod(backup_path, 0o600)
        logger.info('[MIGRATE] Safety backup created: %s', backup_path)

    with app.app_context():
        conn = get_db()
        heal_database_schema(conn)
        auto_migrate_db(conn)
        conn.commit()
    logger.info('[MIGRATE] Database migrations completed successfully.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
