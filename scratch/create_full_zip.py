# -*- coding: utf-8 -*-
"""
Script to create a clean, comprehensive, standalone ZIP archive of the entire
Stargate Delivery Enterprise Edition on Drive D.
"""
import os
import zipfile
import sqlite3
import sys

# 1. First ensure WAL is truncated into the main DB file
repo_dir = r"D:\STARGATE\repo"
db_path = os.path.join(repo_dir, "data", "stargate_production.db")
if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.close()
        print(f"Checkpoint completed for {db_path}")
    except Exception as e:
        print(f"Checkpoint warning: {e}")

# Targets for ZIP archive:
target_zip_d = r"D:\STARGATE_Enterprise_Full_System.zip"
target_zip_stargate = r"D:\STARGATE\STARGATE_Enterprise_Full_System.zip"

# Extensions / Folders to exclude
EXCLUDE_DIRS = {'.git', '__pycache__', 'build', 'dist', 'installer_output', 'scratch'}
EXCLUDE_FILES = {'update.zip', 'app.py.bak_ai_tg'}
EXCLUDE_EXTS = {'.pyc', '.pyo', '.tmp'}

def should_include(rel_path):
    parts = rel_path.replace('\\', '/').split('/')
    for p in parts:
        if p in EXCLUDE_DIRS:
            return False
    fname = os.path.basename(rel_path)
    if fname in EXCLUDE_FILES:
        return False
    if fname.startswith(('edge_', 'full_ui_test', 'test_script_', 'rendered_orders', 'parse_test')):
        return False
    ext = os.path.splitext(fname)[1].lower()
    if ext in EXCLUDE_EXTS:
        return False
    if fname.endswith(('-wal', '-shm')) and 'stargate_production' in fname:
        # After checkpoint truncate, we don't need temporary wal/shm files in backup
        return False
    return True

print("Creating ZIP archive...")
files_added = 0
total_uncompressed_bytes = 0

with zipfile.ZipFile(target_zip_stargate, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(repo_dir):
        # Skip excluded dirs in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, repo_dir)
            if should_include(rel_path):
                # Archive with clean folder prefix 'Stargate_Enterprise'
                archive_name = os.path.join('Stargate_Enterprise', rel_path)
                zf.write(full_path, archive_name)
                files_added += 1
                total_uncompressed_bytes += os.path.getsize(full_path)

zip_size_mb = os.path.getsize(target_zip_stargate) / (1024 * 1024)
print(f"Archive created at: {target_zip_stargate}")
print(f"Files included: {files_added}")
print(f"Total size: {zip_size_mb:.2f} MB (uncompressed: {total_uncompressed_bytes / (1024*1024):.2f} MB)")

# Also copy/create at D:\ directly if permissible
try:
    import shutil
    shutil.copy2(target_zip_stargate, target_zip_d)
    print(f"Also copied to root D drive: {target_zip_d}")
except Exception as ex:
    print(f"Notice regarding copying to D root: {ex}")

print("ZIP Generation Completed Successfully!")
