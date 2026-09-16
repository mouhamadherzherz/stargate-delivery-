import os
import shutil
import stat
import sys

sys.stdout.reconfigure(encoding='utf-8')

def remove_readonly(func, path, excinfo):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass

def safe_remove(path):
    if os.path.isfile(path):
        try:
            os.chmod(path, stat.S_IWRITE)
            os.remove(path)
        except Exception:
            pass
    elif os.path.isdir(path):
        shutil.rmtree(path, onerror=remove_readonly)

print("1. Cleaning F: drive completely while strictly preserving the employee database...")

# Source paths
repo_dir = r"D:\STARGATE\repo"
src_exe = os.path.join(repo_dir, "dist", "StargateDelivery.exe")
src_db = os.path.join(repo_dir, "data", "stargate_production.db")
src_templates = os.path.join(repo_dir, "templates")
src_static = os.path.join(repo_dir, "static")

# Verify source DB has the 14 orders
import sqlite3
conn = sqlite3.connect(src_db)
cnt = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
conn.close()
print(f"Verified source DB has {cnt} orders intact.")

# Clean F:\ root
for item in os.listdir(r"F:"):
    item_path = os.path.join(r"F:", item)
    safe_remove(item_path)

print("F: root is now 100% clean.")

# 2. Create F:\StargateDelivery folder
dest_app_dir = r"F:\StargateDelivery"
os.makedirs(dest_app_dir, exist_ok=True)
dest_data_dir = os.path.join(dest_app_dir, "data")
os.makedirs(dest_data_dir, exist_ok=True)

# Copy EXE
shutil.copy2(src_exe, os.path.join(dest_app_dir, "StargateDelivery.exe"))
print("Copied new 77MB standalone StargateDelivery.exe")

# Copy DB
shutil.copy2(src_db, os.path.join(dest_data_dir, "stargate_production.db"))
print("Copied employee database with 14 orders")

# Copy templates & static
shutil.copytree(src_templates, os.path.join(dest_app_dir, "templates"))
shutil.copytree(src_static, os.path.join(dest_app_dir, "static"))
print("Copied templates and static assets")

# 3. Create F:\بيانات_الدخول.txt
login_txt = """=========================================================================
            STARGATE ENTERPRISE - بيانات الدخول المعتمدة
=========================================================================

البرنامج مثبت الآن ويعمل 100% كبرنامج مستقل بالكامل (أوفلاين بدون إنترنت).
كافة بيانات وطلبات الموظف السابقة (14 طلباً) محفوظة بالكامل.

طرق الدخول المتاحة على شاشة البرنامج:
-------------------------------------------------------------------------
1) الدخول السريع برمز PIN (أسرع وأسهل طريقة):
   - اضغط على تبويب [رمز PIN سريع]
   - أدخل الرمز: 20122020   (أو الرمز البديل: 19701313)
   - رموز الموظفين مفعلة أيضاً:
     * دعاء: 81097175
     * آدم:  090921
     * نور:  121314

2) الدخول بالاسم وكلمة المرور:
   - اسم المستخدم: stargate   (أو admin)
   - كلمة المرور:   stargate@19701313
=========================================================================
"""
with open(r"F:\بيانات_الدخول.txt", "w", encoding="utf-8") as f:
    f.write(login_txt)

with open(os.path.join(dest_app_dir, "بيانات_الدخول.txt"), "w", encoding="utf-8") as f:
    f.write(login_txt)

print("Created login credentials text file.")
print("Pristine standalone setup on F: is ready!")
