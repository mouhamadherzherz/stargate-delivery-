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

print("Starting clean synchronization of USB F: ...")

repo_dir = r"D:\STARGATE\repo"
target_sys_dir = r"F:\Stargate Delivery System"

# 1. Sync code, templates, static, configs from repo into F:\Stargate Delivery System
# Preserving the upgraded data/ directory!
items_to_sync = [
    'app.py', 'config.py', 'secure_env.py', 'migration_engine.py', 
    'stargate_ai_engine.py', 'backup_lifecycle_manager.py', 
    'telegram_reporter.py', 'requirements.txt'
]
for itm in items_to_sync:
    src = os.path.join(repo_dir, itm)
    dst = os.path.join(target_sys_dir, itm)
    if os.path.exists(src):
        shutil.copy2(src, dst)

# Sync templates & static
shutil.copytree(os.path.join(repo_dir, 'templates'), os.path.join(target_sys_dir, 'templates'), dirs_exist_ok=True)
shutil.copytree(os.path.join(repo_dir, 'static'), os.path.join(target_sys_dir, 'static'), dirs_exist_ok=True)
if os.path.exists(os.path.join(repo_dir, 'stargate_erp')):
    shutil.copytree(os.path.join(repo_dir, 'stargate_erp'), os.path.join(target_sys_dir, 'stargate_erp'), dirs_exist_ok=True)

# Also ensure F:\Stargate Delivery System\data\stargate_production.db has the upgraded DB
shutil.copy2(os.path.join(repo_dir, 'data', 'stargate_production.db'), os.path.join(target_sys_dir, 'data', 'stargate_production.db'))

# 2. Clean up obsolete installer duplicates from inside F:\Stargate Delivery System
obsolete_files = [
    'StargateDelivery_Setup.exe',
    'StargateDelivery_Setup_v7.exe',
    'تثبيت_وترقية_النظام_تلقائيا.bat',
    'تحديث.bat',
    'تحديث_ستارجيت_بضغطة_زر_واحدة.bat'
]
for ob in obsolete_files:
    safe_remove(os.path.join(target_sys_dir, ob))

# 3. Clean up obsolete folders from root of F:\
for root_ob in ['New folder', 'New folder (2)', 'StargateDelivery_v7', 'StargateDelivery_v8']:
    safe_remove(os.path.join(r"F:", root_ob))

# 4. Create simple, clean text guide on F:\
guide_content = """==============================================================
             STARGATE ENTERPRISE - بيانات الدخول الرسمية
==============================================================

الإصدار المعتمد: v3.0.0 Enterprise
حالة البيانات: محفوظة 100% مع كافة الطلبات السابقة (14 طلباً).

--------------------------------------------------------------
طرق تسجيل الدخول المتاحة على كمبيوتر الموظف:
--------------------------------------------------------------

1) عبر رمز PIN السريع (موصى به - أسرع طريقة):
   - اضغط على تبويب [رمز PIN سريع]
   - أدخل الرمز: 20122020   (أو الرمز البديل: 19701313)
   - رموز الموظفين الأخرى مفعلة أيضاً:
     * دعاء: 81097175
     * آدم:  090921
     * نور:  121314

2) عبر اسم المستخدم وكلمة المرور:
   - اسم المستخدم: stargate   (أو admin)
   - كلمة المرور:   stargate@19701313
   (أو اكتب رمز الـ PIN 20122020 في خانة كلمة المرور)

--------------------------------------------------------------
كيفية عمل التحديثات لاحقاً بسهولة تامة:
--------------------------------------------------------------
1. من داخل البرنامج مباشرة:
   ادخل إلى القائمة الجانبية -> [تزامن وتحديث الأجهزة]
   واضغط زر: [🚀 تحديث النظام وترقية الجداول فوراً]
   ليقوم النظام بتحديث نفسه تلقائياً دون لمس أي بيانات!

2. عبر الفلاشة:
   اضغط مرتين على ملف: [تثبيت_وتحديث_كمبيوتر_الموظف_بضغطة_زر.bat]
==============================================================
"""

with open(r"F:\بيانات_الدخول_الرسمية.txt", "w", encoding="utf-8") as f:
    f.write(guide_content)

with open(os.path.join(target_sys_dir, "بيانات_الدخول_الرسمية.txt"), "w", encoding="utf-8") as f:
    f.write(guide_content)

print("USB F: cleaned, synchronized, and prepared successfully!")
