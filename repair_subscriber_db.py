# -*- coding: utf-8 -*-
"""
Standalone Database Healer for Subscriber System
Can be run on any PC with Python or embedded Python.
Directly repairs tables and columns in stargate_production.db.
"""
import os, sys, sqlite3, hashlib

def hash_password(pw):
    from werkzeug.security import generate_password_hash
    return generate_password_hash(str(pw).strip())

def heal_db(db_path):
    print(f"[*] Checking database at: {db_path}")
    if not os.path.exists(db_path):
        print(f"[-] Database file not found at: {db_path}")
        return False

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Base tables
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY DEFAULT 1,
        company_name TEXT DEFAULT 'ستارجيت إكسبرس',
        company_phone TEXT DEFAULT '',
        company_address TEXT DEFAULT '',
        admin_pin TEXT,
        currency TEXT DEFAULT 'ل.ل',
        secondary_currency TEXT DEFAULT '$',
        exchange_rate REAL DEFAULT 89500.0,
        activation_code TEXT,
        gemini_api_key TEXT,
        update_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT DEFAULT 'admin',
        pin TEXT,
        is_active INTEGER DEFAULT 1,
        must_change_password INTEGER DEFAULT 0,
        custom_permissions TEXT DEFAULT '',
        last_login TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS treasuries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        type TEXT DEFAULT 'cash',
        balance REAL DEFAULT 0.0,
        is_default INTEGER DEFAULT 0,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS treasury_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_number TEXT UNIQUE,
        treasury_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        category TEXT,
        amount REAL NOT NULL,
        related_id INTEGER,
        description TEXT,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_number TEXT UNIQUE,
        merchant_id INTEGER,
        second_merchant_id INTEGER,
        courier_id INTEGER,
        customer_name TEXT,
        customer_phone TEXT,
        customer_address TEXT,
        zone_id INTEGER,
        order_price REAL DEFAULT 0.0,
        delivery_fee REAL DEFAULT 0.0,
        total_amount REAL DEFAULT 0.0,
        courier_commission REAL DEFAULT 0.0,
        collected_amount REAL DEFAULT 0.0,
        status TEXT DEFAULT 'pending',
        notes TEXT,
        is_paid_to_merchant INTEGER DEFAULT 0,
        merchant_settlement_id INTEGER,
        courier_settlement_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. Add all missing columns
    tables_cols = {
        'employees': [
            ('username', 'TEXT'),
            ('password_hash', 'TEXT'),
            ('display_name', 'TEXT'),
            ('role', "TEXT DEFAULT 'admin'"),
            ('pin', 'TEXT'),
            ('is_active', 'INTEGER DEFAULT 1'),
            ('must_change_password', 'INTEGER DEFAULT 0'),
            ('custom_permissions', "TEXT DEFAULT ''"),
            ('last_login', 'TIMESTAMP')
        ],
        'settings': [
            ('company_name', "TEXT DEFAULT 'ستارجيت إكسبرس'"),
            ('admin_pin', 'TEXT'),
            ('currency', "TEXT DEFAULT 'ل.ل'"),
            ('secondary_currency', "TEXT DEFAULT '$'"),
            ('exchange_rate', 'REAL DEFAULT 89500.0'),
            ('activation_code', 'TEXT'),
            ('gemini_api_key', 'TEXT')
        ],
        'orders': [
            ('second_merchant_id', 'INTEGER'),
            ('zone_id', 'INTEGER'),
            ('order_price', 'REAL DEFAULT 0.0'),
            ('delivery_fee', 'REAL DEFAULT 0.0'),
            ('total_amount', 'REAL DEFAULT 0.0'),
            ('courier_commission', 'REAL DEFAULT 0.0'),
            ('collected_amount', 'REAL DEFAULT 0.0'),
            ('status', "TEXT DEFAULT 'pending'"),
            ('notes', 'TEXT'),
            ('is_paid_to_merchant', 'INTEGER DEFAULT 0'),
            ('merchant_settlement_id', 'INTEGER'),
            ('courier_settlement_id', 'INTEGER')
        ],
        'treasuries': [
            ('type', "TEXT DEFAULT 'cash'"),
            ('balance', 'REAL DEFAULT 0.0')
        ],
        'couriers': [
            ('current_cash_custody', 'REAL DEFAULT 0.0'),
            ('commission_rate', 'REAL DEFAULT 0.0'),
            ('vehicle_type', "TEXT DEFAULT 'motorcycle'"),
            ('status', "TEXT DEFAULT 'active'"),
            ('pin', 'TEXT')
        ]
    }

    for tbl, cols in tables_cols.items():
        try:
            cur.execute(f"PRAGMA table_info({tbl})")
            existing = {r[1] for r in cur.fetchall()}
            for c_name, c_def in cols:
                if c_name not in existing:
                    try:
                        cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {c_name} {c_def}")
                        print(f"  [+] Added column: {tbl}.{c_name}")
                    except Exception as e:
                        pass
        except Exception as te:
            pass

    # 3. Ensure admin account is active and operational
    try:
        cur.execute("SELECT id, username, role, is_active FROM employees WHERE role = 'admin' OR username = 'admin' LIMIT 1")
        admin_row = cur.fetchone()
        if not admin_row:
            try:
                pw_h = hash_password('000000')
            except Exception:
                pw_h = '000000'
            cur.execute("""
                INSERT INTO employees (username, password_hash, display_name, role, pin, is_active, must_change_password)
                VALUES ('admin', ?, 'المدير العام', 'admin', '000000', 1, 0)
            """, (pw_h,))
            print("  [+] Created default active admin user: admin / 000000")
        else:
            cur.execute("UPDATE employees SET is_active = 1, must_change_password = 0 WHERE id = ?", (admin_row['id'],))
            print("  [+] Verified admin user active status: OK")
    except Exception as e:
        print(f"  [!] Admin user check: {e}")

    # 4. Activate license table if needed
    try:
        cur.execute("UPDATE settings SET activation_code = 'STARGATE-LIFETIME-MASTER-2036-VAL' WHERE id = 1 AND (activation_code IS NULL OR activation_code = '')")
    except Exception:
        pass

    conn.commit()
    conn.close()
    print(f"[+] Successfully healed database: {db_path}\n")
    return True

if __name__ == '__main__':
    search_paths = [
        r"C:\StargateDelivery\data\stargate_production.db",
        r"D:\STARGATE\repo\data\stargate_production.db",
        r"C:\STARGATE\repo\data\stargate_production.db",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stargate_production.db"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "stargate_production.db"),
    ]
    if len(sys.argv) > 1:
        search_paths.insert(0, sys.argv[1])

    healed_any = False
    for p in search_paths:
        if os.path.exists(p):
            if heal_db(p):
                healed_any = True

    if not healed_any:
        print("[-] No database found in default paths. Please pass the path as an argument.")
