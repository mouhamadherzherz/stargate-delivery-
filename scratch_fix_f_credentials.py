import sqlite3
import os
import shutil
import sys
from werkzeug.security import generate_password_hash

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

db_paths = [
    r"F:\Stargate Delivery System\data\stargate_production.db",
    r"F:\تثبيت_نظام_ستارجيت_للموظف\stargate_production.db",
    r"D:\STARGATE\repo\data\stargate_production.db"
]

default_hash = generate_password_hash("stargate@19701313")

for db_path in db_paths:
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("UPDATE employees SET password_hash = ?, pin = '20122020' WHERE username = 'stargate'", (default_hash,))
        cur.execute("UPDATE settings SET admin_pin = '20122020' WHERE id = 1")
        conn.commit()
        conn.close()
        print("Updated DB:", db_path)

# Sync app.py and templates
src_app = r"D:\STARGATE\repo\app.py"
dest_app = r"F:\Stargate Delivery System\app.py"
if os.path.exists(dest_app):
    shutil.copy2(src_app, dest_app)
    print("Synced app.py")

src_templates = r"D:\STARGATE\repo\templates"
dest_templates = r"F:\Stargate Delivery System\templates"
if os.path.exists(dest_templates):
    shutil.copytree(src_templates, dest_templates, dirs_exist_ok=True)
    print("Synced templates")

# Also sync to Update_Package
shutil.copy2(src_app, r"F:\Update_Package\Updates_Source\app.py")
shutil.copytree(src_templates, r"F:\Update_Package\Updates_Source\templates", dirs_exist_ok=True)
print("Synced to F:\\Update_Package")

print("SUCCESS: Everything on F: is updated and fixed!")
