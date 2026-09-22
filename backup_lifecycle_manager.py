# -*- coding: utf-8 -*-
"""
Automated Backup Lifecycle Policy Manager - Stargate Delivery
Enforces strict local retention policies, time-to-live (TTL) expiration,
and automated offsite/external cloud archival to prevent disk bloat.
"""
import os
import time
import shutil
import gzip
from datetime import datetime

# Maximum active snapshots to keep on local machine
DEFAULT_MAX_LOCAL_KEEP = 3
# Maximum age in hours for local snapshots (48 hours)
DEFAULT_MAX_AGE_HOURS = 48


def enforce_backup_lifecycle(backup_dir, max_keep=DEFAULT_MAX_LOCAL_KEEP, max_age_hours=DEFAULT_MAX_AGE_HOURS, offsite_dir=None):
    """
    تطبيق سياسة دورة حياة النسخ الاحتياطي:
    1. حذف أي نسخة يتجاوز عمرها 48 ساعة محلياً.
    2. الإبقاء على أحدث 3 نسخ فقط كحد أقصى.
    3. النقل التلقائي إلى مسار خارجي / سحابي إن وُجد قبل الحذف.
    """
    if not os.path.exists(backup_dir):
        return {"pruned": 0, "remaining": 0, "offsite_synced": 0}

    now = time.time()
    all_files = []

    for f in os.listdir(backup_dir):
        if (f.endswith(".db") or f.endswith(".db.gz")) and ("stargate" in f.lower() or "backup" in f.lower()):
            full_p = os.path.join(backup_dir, f)
            if os.path.isfile(full_p):
                mtime = os.path.getmtime(full_p)
                size_kb = os.path.getsize(full_p) / 1024
                all_files.append({
                    "filename": f,
                    "path": full_p,
                    "mtime": mtime,
                    "age_hours": (now - mtime) / 3600.0,
                    "size_kb": size_kb
                })

    # Sort descending by mtime (newest first)
    all_files.sort(key=lambda x: x["mtime"], reverse=True)

    pruned_count = 0
    offsite_synced_count = 0

    # Retain only newest max_keep files, prune the rest
    to_keep = all_files[:max_keep]
    to_delete = all_files[max_keep:]

    # Also check TTL for files within to_keep: if older than max_age_hours and count > 1
    retained = []
    for idx, item in enumerate(to_keep):
        # Always keep at least 1 most recent snapshot regardless of age
        if idx == 0 or item["age_hours"] <= max_age_hours:
            retained.append(item)
        else:
            to_delete.append(item)

    for item in to_delete:
        f_path = item["path"]
        # Sync offsite if configured before deletion
        if offsite_dir and os.path.exists(offsite_dir):
            try:
                dest_offsite = os.path.join(offsite_dir, item["filename"])
                if not os.path.exists(dest_offsite):
                    shutil.copy2(f_path, dest_offsite)
                    offsite_synced_count += 1
            except Exception as e:
                print(f"[Lifecycle Sync Error] {e}")

        try:
            os.remove(f_path)
            pruned_count += 1
            print(f"[Lifecycle Policy] Pruned expired backup: {item['filename']} (Age: {item['age_hours']:.1f}h)")
        except Exception as ex:
            print(f"[Lifecycle Prune Error] Could not delete {f_path}: {ex}")

    return {
        "pruned": pruned_count,
        "remaining": len(retained),
        "offsite_synced": offsite_synced_count
    }


def create_compressed_snapshot(db_path, backup_dir, offsite_dir=None):
    """إنشاء نسخة احتياطية مضغوطة فورية وتطبيق سياسة دورة الحياة مباشرة."""
    import sqlite3
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    temp_file = os.path.join(backup_dir, f"temp_{timestamp}.db")
    dest_file_gz = os.path.join(backup_dir, f"stargate_backup_{timestamp}.db.gz")

    src = sqlite3.connect(db_path, timeout=30.0)
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

    # Immediately enforce lifecycle policy
    lifecycle_stats = enforce_backup_lifecycle(backup_dir, max_keep=DEFAULT_MAX_LOCAL_KEEP, offsite_dir=offsite_dir)
    return dest_file_gz, lifecycle_stats
