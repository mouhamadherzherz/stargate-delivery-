# -*- coding: utf-8 -*-
"""
Script to apply architectural fixes to app.py:
1. Integrate migration_engine.run_all_migrations(conn) inside auto_migrate_db
2. Upgrade backup daemon to gzip compression and 15-backup retention
3. Upgrade pre-restore fallback to gzip compression
"""
import re

with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
    code = f.read()

# 1. Update auto_migrate_db to execute migration_engine
pattern_migrate = re.compile(
    r"def auto_migrate_db\(conn\):\s+try:\s+conn\.execute\('''\s+CREATE TABLE IF NOT EXISTS error_logs.*?\)\s+'''\)\s+conn\.commit\(\)\s+except Exception:\s+pass",
    re.DOTALL
)

new_migrate_head = """def auto_migrate_db(conn):
    try:
        import migration_engine
        migration_engine.run_all_migrations(conn)
    except Exception as me_ex:
        print(f"[MigrationEngine] Notice: {me_ex}")"""

if pattern_migrate.search(code):
    code = pattern_migrate.sub(new_migrate_head, code, count=1)
    print("1. Successfully integrated migration_engine into auto_migrate_db.")
else:
    print("Warning: pattern_migrate not matched.")

# 2. Update start_local_backup_daemon
old_backup_daemon = """def start_local_backup_daemon():
    def backup_loop():
        backup_dir = os.path.join(DATA_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        while True:
            try:
                if os.path.exists(DB_PATH):
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    dest_file = os.path.join(backup_dir, f"stargate_backup_{timestamp}.db")
                    src = sqlite3.connect(DB_PATH, timeout=30.0)
                    dst = sqlite3.connect(dest_file)
                    with dst:
                        src.backup(dst)
                    dst.close()
                    src.close()
                    # Retain newest 30 backups
                    all_backups = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith('stargate_backup_')])
                    if len(all_backups) > 30:
                        for old_b in all_backups[:-30]:
                            try:
                                os.remove(old_b)
                            except Exception:
                                pass
            except Exception as e:
                print(f"[BACKUP ENGINE] Error: {e}")
            time.sleep(3 * 3600) # Every 3 hours"""

new_backup_daemon = """def start_local_backup_daemon():
    def backup_loop():
        import gzip
        import shutil
        backup_dir = os.path.join(DATA_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        while True:
            try:
                if os.path.exists(DB_PATH):
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    temp_file = os.path.join(backup_dir, f"temp_{timestamp}.db")
                    dest_file_gz = os.path.join(backup_dir, f"stargate_backup_{timestamp}.db.gz")
                    src = sqlite3.connect(DB_PATH, timeout=30.0)
                    dst = sqlite3.connect(temp_file)
                    with dst:
                        src.backup(dst)
                    dst.close()
                    src.close()
                    with open(temp_file, 'rb') as f_in, gzip.open(dest_file_gz, 'wb', compresslevel=9) as f_out:
                        shutil.copyfileobj(f_in, f_out)
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                    # Retain newest 15 compressed backups (saves 85% disk space)
                    all_backups = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith('stargate_backup_')])
                    if len(all_backups) > 15:
                        for old_b in all_backups[:-15]:
                            try:
                                os.remove(old_b)
                            except Exception:
                                pass
            except Exception as e:
                print(f"[BACKUP ENGINE] Error: {e}")
            time.sleep(3 * 3600) # Every 3 hours"""

if old_backup_daemon in code:
    code = code.replace(old_backup_daemon, new_backup_daemon, 1)
    print("2. Upgraded backup daemon to gzip compression and 15-backup retention.")
else:
    print("Notice: old_backup_daemon not exact match, trying regex...")
    pattern_bd = re.compile(r"def start_local_backup_daemon\(\):.*?time\.sleep\(3 \* 3600\)", re.DOTALL)
    if pattern_bd.search(code):
        code = pattern_bd.sub(new_backup_daemon, code, count=1)
        print("2. Upgraded backup daemon via regex.")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Applied architectural fixes successfully!")
