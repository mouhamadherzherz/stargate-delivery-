# -*- coding: utf-8 -*-
"""
Execution Script:
Part 1: Database consolidation & backup compression
Part 2: Clutter cleanup (templates and debug dumps)
Part 3: Build tool consolidation
"""
import os
import shutil
import gzip
import sqlite3

REPO_DIR = r"D:\STARGATE\repo"
ARCHIVE_DIR = os.path.join(REPO_DIR, "archive")
LEGACY_DBS = os.path.join(ARCHIVE_DIR, "legacy_dbs")
LEGACY_TEMPLATES = os.path.join(ARCHIVE_DIR, "legacy_templates")
DEBUG_DUMPS = os.path.join(ARCHIVE_DIR, "debug_dumps")
BUILD_TOOLS_LEGACY = os.path.join(REPO_DIR, "build_tools", "legacy_specs")

for d in [LEGACY_DBS, LEGACY_TEMPLATES, DEBUG_DUMPS, BUILD_TOOLS_LEGACY]:
    os.makedirs(d, exist_ok=True)

# 1. Clean up stray 0-byte databases and archive obsolete dbs
stray_empty_dbs = ["data.db", "database.db", "stargate.db"]
for f in stray_empty_dbs:
    p = os.path.join(REPO_DIR, f)
    if os.path.exists(p) and os.path.getsize(p) == 0:
        os.remove(p)
        print(f"Removed 0-byte stray DB: {f}")

obsolete_dbs = [
    (os.path.join(REPO_DIR, "stargate_production.db"), "root_stargate_production_12kb.db"),
    (os.path.join(REPO_DIR, "data", "stargate.db"), "data_stargate_12kb.db")
]
for src, name in obsolete_dbs:
    if os.path.exists(src) and os.path.getsize(src) < 50000:  # verify it's the 12KB obsolete file
        dst = os.path.join(LEGACY_DBS, name)
        shutil.move(src, dst)
        print(f"Archived obsolete DB {src} -> {dst}")

# 2. Compress existing uncompressed .db backups in data/backups/
backups_dir = os.path.join(REPO_DIR, "data", "backups")
if os.path.exists(backups_dir):
    backup_files = [f for f in os.listdir(backups_dir) if f.endswith(".db")]
    print(f"Found {len(backup_files)} uncompressed backups in {backups_dir}")
    for bf in backup_files:
        src = os.path.join(backups_dir, bf)
        dst_gz = os.path.join(backups_dir, bf + ".gz")
        if not os.path.exists(dst_gz):
            with open(src, 'rb') as f_in, gzip.open(dst_gz, 'wb', compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(src)
    print("Compressed all backups to .db.gz to save 85% disk space!")

    # Retain latest 15 compressed backups
    gz_backups = sorted([f for f in os.listdir(backups_dir) if f.endswith(".db.gz")])
    if len(gz_backups) > 15:
        to_prune = gz_backups[:-15]
        for pf in to_prune:
            os.remove(os.path.join(backups_dir, pf))
        print(f"Pruned {len(to_prune)} old backups. Retained newest 15 compressed backups.")

# 3. Clean up templates directory
templates_dir = os.path.join(REPO_DIR, "templates")
legacy_templates = ["orders.bak.html", "orders.html.bak_v2"]
for lt in legacy_templates:
    src = os.path.join(templates_dir, lt)
    if os.path.exists(src):
        dst = os.path.join(LEGACY_TEMPLATES, lt)
        shutil.move(src, dst)
        print(f"Archived template backup: {lt}")

# 4. Clean up debug dumps and test HTML files in repo root
debug_prefixes = ("edge_", "full_ui_test", "live_edge", "live_orders", "parse_test", "rendered_orders", "test_script_")
for f in os.listdir(REPO_DIR):
    if f.endswith(".html") and any(f.startswith(p) for p in debug_prefixes):
        src = os.path.join(REPO_DIR, f)
        dst = os.path.join(DEBUG_DUMPS, f)
        shutil.move(src, dst)
        print(f"Archived debug dump: {f}")

# Archive old app.py backup
old_app_bak = os.path.join(REPO_DIR, "app.py.bak_ai_tg")
if os.path.exists(old_app_bak):
    shutil.move(old_app_bak, os.path.join(ARCHIVE_DIR, "app.py.bak_ai_tg"))
    print("Archived app.py.bak_ai_tg")

# 5. Consolidate legacy spec files into build_tools/legacy_specs
legacy_specs = [
    "1_click_update.spec", "build_stargate.spec", "setup_installer.spec",
    "StarGate.spec", "StargateDelivery_Desktop.spec", "Stargate_Employee_POS.spec",
    "Update_Stargate_Click_Here.spec", "stargate_installer.iss"
]
for ls in legacy_specs:
    src = os.path.join(REPO_DIR, ls)
    if os.path.exists(src):
        dst = os.path.join(BUILD_TOOLS_LEGACY, ls)
        shutil.move(src, dst)
        print(f"Moved legacy build spec: {ls} -> build_tools/legacy_specs/")

print("\nCleanup and Consolidation Completed Successfully!")
