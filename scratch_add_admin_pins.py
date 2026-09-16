import sqlite3
import sys
from werkzeug.security import generate_password_hash

sys.stdout.reconfigure(encoding='utf-8')

db_paths = [
    r"F:\Stargate Delivery System\data\stargate_production.db",
    r"F:\تثبيت_نظام_ستارجيت_للموظف\stargate_production.db",
    r"F:\Update_Package\Updates_Source\data\stargate_production.db",
    r"D:\STARGATE\repo\data\stargate_production.db"
]

default_pw = "stargate@19701313"
pw_hash = generate_password_hash(default_pw)

for db_path in db_paths:
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # 1. Update stargate user
        cur.execute("UPDATE employees SET password_hash = ?, pin = '20122020' WHERE username = 'stargate'", (pw_hash,))
        
        # 2. Check if admin user exists, if not create it with PIN 19701313
        cur.execute("SELECT id FROM employees WHERE username = 'admin'")
        admin_row = cur.fetchone()
        if admin_row:
            cur.execute("UPDATE employees SET password_hash = ?, pin = '19701313', role = 'admin', is_active = 1 WHERE username = 'admin'", (pw_hash,))
        else:
            cur.execute("""
                INSERT INTO employees (username, password_hash, display_name, role, pin, is_active)
                VALUES ('admin', ?, 'الإدارة العامة', 'admin', '19701313', 1)
            """, (pw_hash,))
            
        # 3. Update all other existing employees with a known fallback password just in case
        cur.execute("UPDATE employees SET password_hash = ? WHERE username IN ('douaa-a', 'a_yassine', 'nour-h')", (pw_hash,))
        
        # 4. Update settings admin_pin to 20122020
        cur.execute("UPDATE settings SET admin_pin = '20122020' WHERE id = 1")
        
        conn.commit()
        conn.close()
        print(f"Successfully configured credentials in: {db_path}")
    except Exception as e:
        print(f"Skipped {db_path}: {e}")

print("DONE ALL DATABASE UPDATES!")
