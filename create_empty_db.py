import sqlite3
import os

source_db = 'data/stargate_production.db'
empty_db = 'data/stargate_empty.db'

if os.path.exists(empty_db):
    os.remove(empty_db)

conn_src = sqlite3.connect(source_db)
cur_src = conn_src.cursor()

cur_src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
tables = cur_src.fetchall()

conn_dst = sqlite3.connect(empty_db)
cur_dst = conn_dst.cursor()

for table in tables:
    if table[0]:
        cur_dst.execute(table[0])

try:
    cur_src.execute("SELECT * FROM settings WHERE id=1")
    settings_row = cur_src.fetchone()
    if settings_row:
        cur_src.execute("PRAGMA table_info(settings)")
        cols = [col[1] for col in cur_src.fetchall()]
        placeholders = ','.join(['?'] * len(cols))
        query = f"INSERT INTO settings ({','.join(cols)}) VALUES ({placeholders})"
        row_dict = dict(zip(cols, settings_row))
        if 'activation_code' in row_dict: row_dict['activation_code'] = None
        if 'hardware_lock_signature' in row_dict: row_dict['hardware_lock_signature'] = None
        if 'is_activated' in row_dict: row_dict['is_activated'] = 0
        cur_dst.execute(query, tuple(row_dict[col] for col in cols))
except Exception as e:
    print("Error copying settings:", e)
    
try:
    cur_src.execute("SELECT * FROM employees WHERE id=1")
    admin_row = cur_src.fetchone()
    if admin_row:
        cur_src.execute("PRAGMA table_info(employees)")
        cols = [col[1] for col in cur_src.fetchall()]
        placeholders = ','.join(['?'] * len(cols))
        query = f"INSERT INTO employees ({','.join(cols)}) VALUES ({placeholders})"
        
        import werkzeug.security
        row_dict = dict(zip(cols, admin_row))
        row_dict['username'] = 'admin'
        if 'password_hash' in cols:
            row_dict['password_hash'] = werkzeug.security.generate_password_hash('admin')
        if 'display_name' in cols:
            row_dict['display_name'] = 'مدير النظام'
        if 'name' in cols:
            row_dict['name'] = 'مدير النظام'
        if 'pin' in cols:
            row_dict['pin'] = '000000'
            
        cur_dst.execute(query, tuple(row_dict[col] for col in cols))
except Exception as e:
    print("Error creating default admin:", e)

conn_dst.commit()
conn_dst.close()
conn_src.close()
print("Empty DB created successfully")