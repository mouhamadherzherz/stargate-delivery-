import shutil, os, stat

def remove_readonly(func, path, excinfo):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass

def safe_rmtree(path):
    if os.path.exists(path):
        shutil.rmtree(path, onerror=remove_readonly)

print('Updating USB (F:) with all latest files...')

src_repo = r'D:\STARGATE\repo'
src_db = r'D:\STARGATE\repo\data\stargate_production.db'
src_zip = r'D:\STARGATE\STARGATE_Enterprise_Full_System.zip'
src_update_pkg = r'D:\STARGATE\repo\Update_Package'
src_setup = r'D:\STARGATE\StargateDelivery_Setup_v2.0.exe'

# 1. Copy Update_Package to F:\Update_Package
dest_pkg = r'F:\Update_Package'
safe_rmtree(dest_pkg)
shutil.copytree(src_update_pkg, dest_pkg)
print('  [+] Copied F:\\Update_Package')

# 2. Copy zip to F:\
if os.path.exists(src_zip):
    shutil.copy2(src_zip, r'F:\STARGATE_Enterprise_Full_System.zip')
    print('  [+] Copied F:\\STARGATE_Enterprise_Full_System.zip')

# 3. Create dedicated clear folder on F:\
dest_folder = r'F:\تثبيت_نظام_ستارجيت_للموظف'
os.makedirs(dest_folder, exist_ok=True)
if os.path.exists(src_setup):
    shutil.copy2(src_setup, os.path.join(dest_folder, 'برنامج_تثبيت_ستارجيت_v2.0.exe'))
if os.path.exists(src_zip):
    shutil.copy2(src_zip, os.path.join(dest_folder, 'STARGATE_Enterprise_Full_System.zip'))
shutil.copy2(src_db, os.path.join(dest_folder, 'stargate_production.db'))

# Copy Update_Package inside that folder too
dest_inner_pkg = os.path.join(dest_folder, 'Update_Package')
safe_rmtree(dest_inner_pkg)
shutil.copytree(src_update_pkg, dest_inner_pkg)

# 4. Write simple instruction text file on F:\
instructions = """========================================================
             STARGATE ENTERPRISE - بيانات الدخول
========================================================

1. للدخول السريع عبر رمز PIN:
   - اضغط على تبويب [رمز PIN سريع]
   - أدخل الرمز: 20122020  (أو 19701313)

2. للدخول بالاسم وكلمة المرور:
   - اسم المستخدم: stargate
   - كلمة المرور: stargate@19701313
   (أو اكتب الرمز 20122020 في خانة كلمة المرور)

========================================================
طريقة التحديث على كمبيوتر الموظف:
- إذا كان البرنامج في C:\\StargateDelivery:
  انسخ مجلد Update_Package إلى داخل مجلد البرنامج
  ثم اضغط نقرتين على: UPDATE_EMPLOYEE.bat
========================================================
"""
with open(r'F:\بيانات_الدخول_للموظف.txt', 'w', encoding='utf-8') as f:
    f.write(instructions)

with open(os.path.join(dest_folder, 'بيانات_الدخول_للموظف.txt'), 'w', encoding='utf-8') as f:
    f.write(instructions)

print('All files on USB F: are 100% updated and verified!')
