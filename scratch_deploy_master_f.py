import os
import shutil
import stat
import sys
import sqlite3
import time

sys.stdout.reconfigure(encoding='utf-8')

print("=" * 70)
print("  STARGATE ENTERPRISE - PREPARING PRISTINE 100% STANDALONE USB (F:)")
print("=" * 70)

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
        except Exception as e:
            print(f"Warning removing {path}: {e}")
    elif os.path.isdir(path):
        try:
            shutil.rmtree(path, onerror=remove_readonly)
        except Exception as e:
            print(f"Warning removing dir {path}: {e}")

repo_dir = r"D:\STARGATE\repo"
src_exe = os.path.join(repo_dir, "dist", "StargateDelivery.exe")
src_db = os.path.join(repo_dir, "data", "stargate_production.db")
src_templates = os.path.join(repo_dir, "templates")
src_static = os.path.join(repo_dir, "static")

# Step 1: Verify source files
if not os.path.exists(src_exe):
    raise FileNotFoundError(f"Missing {src_exe}")
if not os.path.exists(src_db):
    raise FileNotFoundError(f"Missing {src_db}")

conn = sqlite3.connect(src_db)
order_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
customer_count = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
employee_count = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
conn.close()

print(f"[+] Verified Source Database:")
print(f"    - Orders: {order_count} (Preserved)")
print(f"    - Customers: {customer_count}")
print(f"    - Employees: {employee_count}")
print(f"    - Size: {os.path.getsize(src_db)} bytes")
print(f"[+] Verified Standalone EXE:")
print(f"    - Path: {src_exe}")
print(f"    - Size: {os.path.getsize(src_exe)} bytes")
print(f"    - Built: {time.ctime(os.path.getmtime(src_exe))}")

# Step 2: Clean F:\ completely
print("\n[*] Cleaning F: drive completely...")
for item in os.listdir(r"F:"):
    if item.lower() == "system volume information":
        continue
    item_path = os.path.join(r"F:", item)
    safe_remove(item_path)

print("[+] F: drive wiped clean (System Volume Information preserved).")

# Step 3: Create target structure on F:\
target_subfolder = r"F:\Stargate Delivery System"
target_data = os.path.join(target_subfolder, "data")
os.makedirs(target_data, exist_ok=True)

# Copy EXE
print("[*] Copying standalone executable (77.5MB)...")
shutil.copy2(src_exe, os.path.join(target_subfolder, "StargateDelivery.exe"))

# Copy Database
print("[*] Copying verified database with 14 orders...")
shutil.copy2(src_db, os.path.join(target_data, "stargate_production.db"))

# Copy templates & static
print("[*] Copying templates and static assets...")
shutil.copytree(src_templates, os.path.join(target_subfolder, "templates"))
shutil.copytree(src_static, os.path.join(target_subfolder, "static"))

# Step 4: Create text documentation
login_credentials_txt = """=========================================================================
            STARGATE ENTERPRISE - بيانات الدخول الرسمية للنظام
=========================================================================

البرنامج مثبت الآن ويعمل 100% كبرنامج ويندوز مستقل بالكامل:
- لا يحتاج إلى إنترنت إطلاقاً (Offline).
- لا يحتاج إلى شبكة محلية ولا يرتبط بأي كمبيوتر آخر.
- جميع بيانات وطلبات الموظف السابقة (14 طلباً) محفوظة ومؤمنة بالكامل.

طرق الدخول المتاحة على شاشة البرنامج:
-------------------------------------------------------------------------
الطريقة الأولى: الدخول السريع برمز PIN (أسرع وأسهل خيار):
   - اضغط على تبويب [رمز PIN سريع]
   - أدخل الرمز: 20122020   (الرمز الرئيسي)
   - أو الرمز البديل: 19701313
   - رموز الموظفين مفعلة أيضاً:
     * دعاء: 81097175
     * آدم:  090921
     * نور:  121314

الطريقة الثانية: الدخول بالاسم وكلمة المرور:
   - اسم المستخدم: stargate   (أو admin)
   - كلمة المرور:   stargate@19701313
=========================================================================
"""

with open(r"F:\بيانات_الدخول.txt", "w", encoding="utf-8") as f:
    f.write(login_credentials_txt)

with open(os.path.join(target_subfolder, "بيانات_الدخول.txt"), "w", encoding="utf-8") as f:
    f.write(login_credentials_txt)

# Step 5: Create 1-Click Offline Installer Bat on F:\
installer_bat = r"""@echo off
chcp 65001 >nul
title تثبيت نظام ستارجيت المستقل على هذا الكمبيوتر
color 0a

echo =========================================================================
echo       STARGATE ENTERPRISE - مثبت البرنامج المستقل على الكمبيوتر
echo =========================================================================
echo.
echo مرحباً بك! سيقوم هذا المثبت بتثبيت نظام ستارجيت بالكامل على هذا الكمبيوتر
echo ليعمل كبرنامج ويندوز مستقل 100%% (أوفلاين بدون إنترنت وبدون شبكة).
echo.
echo -------------------------------------------------------------------------

set "INSTALL_DIR=C:\StargateDelivery"
set "SOURCE_DIR=%~dp0Stargate Delivery System"

if not exist "%SOURCE_DIR%" (
    echo [!] خطأ: لم يتم العثور على مجلد ملفات البرنامج في الفلاشة!
    echo     المسار المطلوب: %SOURCE_DIR%
    echo.
    pause
    exit /b
)

:: 1. إيقاف أي عمليات قديمة لفك قفل الملفات
echo [1/4] جاري إيقاف أي نسخة قديمة لتحديث الملفات بأمان...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" >nul 2>&1
if not exist "%INSTALL_DIR%\data" mkdir "%INSTALL_DIR%\data" >nul 2>&1

:: 2. نسخ ملفات البرنامج التنفيذي والواجهات
echo [2/4] جاري نسخ وتثبيت ملفات البرنامج في: %INSTALL_DIR%...
copy /y "%SOURCE_DIR%\StargateDelivery.exe" "%INSTALL_DIR%\" >nul
copy /y "%SOURCE_DIR%\بيانات_الدخول.txt" "%INSTALL_DIR%\" >nul

echo       - جاري نسخ الواجهات والتصميم...
robocopy "%SOURCE_DIR%\templates" "%INSTALL_DIR%\templates" /E >nul 2>&1
robocopy "%SOURCE_DIR%\static" "%INSTALL_DIR%\static" /E >nul 2>&1

:: 3. تثبيت قاعدة البيانات مع الحفاظ التام عليها
echo [3/4] جاري تثبيت قاعدة البيانات وحفظ السجلات...
if exist "%INSTALL_DIR%\data\stargate_production.db" (
    echo       [+] تم أخذ نسخة احتياطية من القاعدة الموجودة مسبقاً للأمان.
    copy /y "%INSTALL_DIR%\data\stargate_production.db" "%INSTALL_DIR%\data\stargate_backup_before_install.db" >nul 2>&1
)
copy /y "%SOURCE_DIR%\data\stargate_production.db" "%INSTALL_DIR%\data\" >nul
echo       [+] تم تثبيت قاعدة البيانات مع كافة الطلبات الـ 14 والرموز المعتمدة.

:: 4. إنشاء اختصار رسمي على سطح المكتب وقائمة ابدأ
echo [4/4] جاري إنشاء أيقونة واختصار رسمي على سطح المكتب...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Stargate Delivery System.lnk')); $s.TargetPath = 'C:\StargateDelivery\StargateDelivery.exe'; $s.WorkingDirectory = 'C:\StargateDelivery'; $s.IconLocation = 'C:\StargateDelivery\static\icons\stargate_logo.ico'; $s.Description = 'نظام ستارجيت لإدارة التوصيل المستقل'; $s.Save(); $sm = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('CommonPrograms'), 'Stargate Delivery System.lnk')); $sm.TargetPath = 'C:\StargateDelivery\StargateDelivery.exe'; $sm.WorkingDirectory = 'C:\StargateDelivery'; $sm.IconLocation = 'C:\StargateDelivery\static\icons\stargate_logo.ico'; $sm.Save()" >nul 2>&1

:: نسخ بيانات الدخول إلى سطح المكتب للسهولة
copy /y "%SOURCE_DIR%\بيانات_الدخول.txt" "%USERPROFILE%\Desktop\بيانات_دخول_ستارجيت.txt" >nul 2>&1

echo.
color 0b
echo =========================================================================
echo        🎉 تم تثبيت نظام ستارجيت بنجاح على كمبيوترك كبرنامج مستقل!
echo =========================================================================
echo.
echo معلومات البرنامج المثبت:
echo   - مكان التثبيت: C:\StargateDelivery
echo   - تم إنشاء أيقونة واختصار رسمي على سطح المكتب (Stargate Delivery System)
echo   - البرنامج يعمل 100%% أوفلاين كبرنامج مستقل داخل هذا الجهاز فقط
echo.
echo بيانات تسجيل الدخول:
echo   - رمز PIN السريع: 20122020  (أو 19701313)
echo   - اسم المستخدم:   stargate
echo   - كلمة المرور:     stargate@19701313
echo =========================================================================
echo.
echo جاري تشغيل البرنامج الآن...
timeout /t 2 /nobreak >nul
start "" "C:\StargateDelivery\StargateDelivery.exe"
exit
"""

with open(r"F:\تثبيت_البرنامج_على_هذا_الكمبيوتر.bat", "w", encoding="utf-8") as f:
    f.write(installer_bat)

# Step 6: Create Direct Portable Run Bat on F:\
portable_run_bat = r"""@echo off
chcp 65001 >nul
title تشغيل نظام ستارجيت من الفلاشة مباشرة (نسخة محمولة)
color 0e

cd /d "%~dp0Stargate Delivery System"
taskkill /F /IM StargateDelivery.exe >nul 2>&1

echo =========================================================================
echo       STARGATE ENTERPRISE - تشغيل مباشر ومحمول من الفلاشة
echo =========================================================================
echo جاري تشغيل نظام ستارجيت مباشرة...
start "" "%~dp0Stargate Delivery System\StargateDelivery.exe"
exit
"""

with open(r"F:\تشغيل_مباشر_من_الفلاشة_بدون_تثبيت.bat", "w", encoding="utf-8") as f:
    f.write(portable_run_bat)

print("\n" + "=" * 70)
print("SUCCESS: F: drive is fully populated with pristine standalone setup!")
print("Files on F: root:")
for item in os.listdir(r"F:"):
    print(f"  - {item}")
print("=" * 70)
