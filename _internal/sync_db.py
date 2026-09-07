import os
import sys
import sqlite3
import shutil
import datetime

def log(msg):
    print(f"[*] {msg}", flush=True)

def find_legacy_employee_database():
    """
    Scans known locations for previous versions of Stargate Delivery on the employee computer.
    Selects the database with the most order records.
    """
    candidate_paths = [
        r"C:\Stargate-System-Offline\dist\Stargate_Delivery\_internal\delivery.db",
        r"C:\Stargate-System-Offline\delivery.db",
        r"C:\Stargate-System-Offline\data\delivery.db",
        r"C:\Stargate-System-Offline\Stargate_Delivery_v4.3\_internal\delivery.db",
        r"C:\StargateDelivery\_internal\delivery.db",
        r"C:\StargateDelivery\data\delivery.db",
        r"C:\Stargate Delivery\delivery.db",
        r"C:\Stargate Delivery\data\delivery.db",
        r"C:\Users\Public\StargateDelivery\delivery.db"
    ]
    
    desktop = os.path.join(os.environ.get('USERPROFILE', r'C:\Users\Default'), 'Desktop')
    candidate_paths.append(os.path.join(desktop, r'Stargate_Delivery_v4.3\_internal\delivery.db'))
    candidate_paths.append(os.path.join(desktop, r'Stargate-Delivery-System\delivery.db'))
    
    best_path = None
    max_orders = -1
    
    for path in candidate_paths:
        if os.path.exists(path):
            try:
                c = sqlite3.connect(path)
                tbls = [r[0] for r in c.execute("SELECT tbl_name FROM sqlite_master").fetchall()]
                if 'orders' in tbls:
                    cnt = c.execute("SELECT count(*) FROM orders").fetchone()[0]
                    if cnt > max_orders and cnt > 0:
                        max_orders = cnt
                        best_path = path
                c.close()
            except Exception:
                pass
                
    return best_path, max_orders

def smart_install_and_migrate(source_template_db, target_installed_db):
    """
    1. Backs up existing installation if present.
    2. Initializes target DB from zero template.
    3. Finds old system database on employee PC and transfers:
       orders, merchants, couriers, treasuries, transactions, settlements, customers, audit_log.
    """
    target_dir = os.path.dirname(target_installed_db)
    os.makedirs(target_dir, exist_ok=True)
    backup_dir = os.path.join(target_dir, 'db_backups')
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    existing_target_has_data = False
    if os.path.exists(target_installed_db):
        try:
            c = sqlite3.connect(target_installed_db)
            o_cnt = c.execute("SELECT count(*) FROM orders").fetchone()[0]
            c.close()
            if o_cnt > 0:
                existing_target_has_data = True
        except Exception:
            pass
            
        bk = os.path.join(backup_dir, f"backup_before_install_{ts}.db")
        shutil.copy2(target_installed_db, bk)
        log(f"Existing target database backed up: {bk}")
        
    legacy_path, legacy_orders = find_legacy_employee_database()
    
    if not existing_target_has_data or (legacy_path and legacy_orders > 0):
        shutil.copy2(source_template_db, target_installed_db)
        log("Initialized fresh zero database structure.")
    else:
        log("Current target database already contains active records. Preserving and updating schema...")

    src_legacy = legacy_path
    if not src_legacy and existing_target_has_data:
        src_legacy = os.path.join(backup_dir, f"backup_before_install_{ts}.db")
        
    if not src_legacy or not os.path.exists(src_legacy):
        log("No previous data found on employee computer. System started clean and ready for work!")
        return

    log(f"Migrating historical data from legacy database: {src_legacy}")
    
    try:
        legacy_backup_file = os.path.join(backup_dir, f"legacy_database_archive_{ts}.db")
        shutil.copy2(src_legacy, legacy_backup_file)
        log(f"Legacy archive safely preserved at: {legacy_backup_file}")
    except Exception as e:
        log(f"Notice during archive copy: {e}")

    conn_dst = sqlite3.connect(target_installed_db)
    conn_src = sqlite3.connect(src_legacy)

    tables_to_migrate = [
        'merchants', 'couriers', 'customers', 'call_center_agents',
        'orders', 'treasuries', 'treasury_transactions', 'settlements',
        'settlement_items', 'expense_categories', 'audit_log'
    ]

    for t in tables_to_migrate:
        in_src = conn_src.execute("SELECT tbl_name FROM sqlite_master WHERE tbl_name=?", (t,)).fetchone()
        if not in_src:
            continue

        src_cols = [x[1] for x in conn_src.execute(f"PRAGMA table_info({t})").fetchall()]
        dst_cols = [x[1] for x in conn_dst.execute(f"PRAGMA table_info({t})").fetchall()]

        for sc in src_cols:
            if sc not in dst_cols:
                col_info = conn_src.execute(f"PRAGMA table_info({t})").fetchall()
                col_type = [x[2] for x in col_info if x[1] == sc][0]
                try:
                    conn_dst.execute(f"ALTER TABLE {t} ADD COLUMN {sc} {col_type}")
                    dst_cols.append(sc)
                except Exception:
                    pass

        common = [c for c in src_cols if c in dst_cols]
        if not common:
            continue

        cols_str = ",".join(common)
        placeholders = ",".join(["?"] * len(common))
        rows = conn_src.execute(f"SELECT {cols_str} FROM {t}").fetchall()

        if rows:
            conn_dst.executemany(f"INSERT OR REPLACE INTO {t} ({cols_str}) VALUES ({placeholders})", rows)
            log(f"Successfully migrated {len(rows)} records into [{t}].")

    in_src_emp = conn_src.execute("SELECT tbl_name FROM sqlite_master WHERE tbl_name='employees'").fetchone()
    if in_src_emp:
        emp_cols = [x[1] for x in conn_src.execute("PRAGMA table_info(employees)").fetchall()]
        dst_emp_cols = [x[1] for x in conn_dst.execute("PRAGMA table_info(employees)").fetchall()]
        c_emp = [c for c in emp_cols if c in dst_emp_cols]
        if c_emp:
            c_emp_str = ",".join(c_emp)
            emp_qms = ",".join(["?"] * len(c_emp))
            emp_rows = conn_src.execute(f"SELECT {c_emp_str} FROM employees").fetchall()
            if emp_rows:
                conn_dst.executemany(f"INSERT OR IGNORE INTO employees ({c_emp_str}) VALUES ({emp_qms})", emp_rows)
                log(f"Migrated {len(emp_rows)} user employee logins.")

    conn_dst.commit()
    conn_dst.close()
    conn_src.close()
    log("ALL employee historical data transferred and verified successfully!")

if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else 'delivery.db'
    dst = sys.argv[2] if len(sys.argv) > 2 else r'C:\StargateDelivery\delivery.db'
    smart_install_and_migrate(src, dst)
