# -*- coding: utf-8 -*-
"""
Script to purge clutter from repo, move archives outside repo,
and clean backup directory.
"""
import os
import shutil

REPO_DIR = r"D:\STARGATE\repo"
EXTERNAL_BACKUP_DIR = r"D:\STARGATE\archive_safety_backup_20260908"

# 1. Move archive folder completely outside the repo
repo_archive = os.path.join(REPO_DIR, "archive")
dest_external = os.path.join(EXTERNAL_BACKUP_DIR, "repo_legacy_archive")
if os.path.exists(repo_archive):
    if os.path.exists(dest_external):
        shutil.rmtree(dest_external)
    shutil.move(repo_archive, dest_external)
    print(f"Moved archive folder outside repo -> {dest_external}")

# 2. Clean build_tools if unnecessary or keep clean
build_tools = os.path.join(REPO_DIR, "build_tools")
if os.path.exists(build_tools):
    dest_bt = os.path.join(EXTERNAL_BACKUP_DIR, "build_tools_legacy")
    if os.path.exists(dest_bt):
        shutil.rmtree(dest_bt)
    shutil.move(build_tools, dest_bt)
    print(f"Moved legacy build specs outside repo -> {dest_bt}")

# 3. Clean root from any leftover images or test files
for f in ["pos_modal_no_cod.png", "pos_modal_verified.png"]:
    p = os.path.join(REPO_DIR, f)
    if os.path.exists(p):
        os.remove(p)
        print(f"Removed test screenshot: {f}")

# 4. Prune local data/backups to only keep the 3 newest snapshots
backups_dir = os.path.join(REPO_DIR, "data", "backups")
if os.path.exists(backups_dir):
    gz_files = sorted([f for f in os.listdir(backups_dir) if f.endswith(".gz") or f.endswith(".db")])
    if len(gz_files) > 3:
        to_prune = gz_files[:-3]
        for pf in to_prune:
            os.remove(os.path.join(backups_dir, pf))
        print(f"Pruned {len(to_prune)} old backups. Kept only the 3 newest baseline snapshots.")

print("Repo cleanup completed successfully!")
