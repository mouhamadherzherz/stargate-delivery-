import sqlite3
import os
import shutil
import sys
from werkzeug.security import generate_password_hash

sys.stdout.reconfigure(encoding='utf-8')

emp_db = r"F:\Stargate Delivery System\data\stargate_production.db"
backup_db = r"F:\Stargate Delivery System\data\stargate_production_backup_original.db"

# 1. Take a safe backup of the employee DB
if not os.path.exists(backup_db):
    shutil.copy2(emp_db, backup_db)
    print(f"Safe original backup created at: {backup_db}")

# 2. Inspect and fix credentials in employee DB
conn = sqlite3.connect(emp_db)
cur = conn.cursor()

default_pw = "stargate@19701313"
pw_hash = generate_password_hash(default_pw)

# Update stargate user
cur.execute("UPDATE employees SET password_hash = ?, pin = '20122020' WHERE username = 'stargate'", (pw_hash,))

# Ensure admin user exists with PIN 19701313
cur.execute("SELECT id FROM employees WHERE username = 'admin'")
if cur.fetchone():
    cur.execute("UPDATE employees SET password_hash = ?, pin = '19701313', role = 'admin', is_active = 1 WHERE username = 'admin'", (pw_hash,))
else:
    cur.execute("""
        INSERT INTO employees (username, password_hash, display_name, role, pin, is_active)
        VALUES ('admin', ?, 'الإدارة العامة', 'admin', '19701313', 1)
    """, (pw_hash,))

# Update other employees' password hashes to default_pw as well so they can log in via password or PIN
cur.execute("UPDATE employees SET password_hash = ? WHERE username IN ('douaa-a', 'a_yassine', 'nour-h')", (pw_hash,))

# Update settings
cur.execute("UPDATE settings SET admin_pin = '20122020' WHERE id = 1")

conn.commit()

# Print verified employee records
print("=== VERIFIED EMPLOYEES IN EMPLOYEE DB ===")
for r in cur.execute("SELECT id, username, display_name, role, pin FROM employees").fetchall():
    print(f"  ID: {r[0]} | Username: {r[1]} | Name: {r[2]} | Role: {r[3]} | PIN: {r[4]}")

orders_cnt = cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
print(f"Orders preserved: {orders_cnt}")

conn.close()

# Also run migration engine on this database to apply all new schema revisions
sys.path.insert(0, r"D:\STARGATE\repo")
import migration_engine
conn2 = sqlite3.connect(emp_db)
ok, revs = migration_engine.run_all_migrations(conn2)
conn2.close()
print(f"Migrations applied to employee DB: {revs} revisions (Status: {ok})")

# Copy the upgraded DB to repo data and F:\ root
repo_db = r"D:\STARGATE\repo\data\stargate_production.db"
shutil.copy2(emp_db, repo_db)
print("Synchronized upgraded employee DB into repository.")
