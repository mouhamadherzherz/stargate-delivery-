@echo off
chcp 65001 >nul
cd /d "%~dp0"
title تحديث نظام Stargate Enterprise - بنقرة واحدة
color 0b

echo ========================================================
echo        STARGATE ENTERPRISE - تحديث النظام التلقائي
echo ========================================================
echo.

:: 1. إيقاف أي سيرفر يعمل حالياً لفك قفل قاعدة البيانات
echo [1/5] جاري إيقاف الخادم مؤقتاً لفك قفل الملفات...
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

:: 2. إنشاء نسخة احتياطية فورية للبيانات الحالية
echo [2/5] جاري حفظ نسخة احتياطية للأمان التام للبيانات...
set "BACKUP_DIR=Backups_Safe\%date:~10,4%-%date:~4,2%-%date:~7,2%_%time:~0,2%-%time:~3,2%-%time:~6,2%"
set "BACKUP_DIR=%BACKUP_DIR: =0%"
mkdir "%BACKUP_DIR%" >nul 2>&1

if exist "data\stargate_production.db" (
    copy /y "data\stargate_production.db" "%BACKUP_DIR%\" >nul
    copy /y "data\*.key" "%BACKUP_DIR%\" >nul 2>&1
    copy /y ".env" "%BACKUP_DIR%\" >nul 2>&1
    echo [+] تم حفظ نسخة احتياطية آمنة في: %BACKUP_DIR%
) else (
    echo [!] لم يتم العثور على قاعدة بيانات سابقة، سيتم إنشاء واحدة جديدة.
)

:: 3. استيراد التحديثات (من فلاشة USB أو مجلد التحديثات أو الشبكة)
:: ملاحظة: حدد مسار مجلد التحديث، مثلاً مجلد Updates_Source أو مسار فلاشة D:\Update
echo [3/5] جاري نسخ ملفات النظام الجديدة مع حماية البيانات السابقة...

set "SOURCE_DIR=Updates_Source"

if not exist "%SOURCE_DIR%" (
    echo [!] مجلد ملفات التحديث "%SOURCE_DIR%" غير موجود.
    echo     تأكد من وضع ملفات التحديث داخل مجلد Updates_Source بجانب هذا الملف.
    pause
    exit /b
)

:: استخدام robocopy لاستبدال ملفات الكود والواجهات واستثناء قاعدة البيانات والمفاتيح
robocopy "%SOURCE_DIR%" "." /E /XD "data" "Backups_Safe" "venv" "__pycache__" /XF "stargate_production.db" "*.key" ".env" >nul

echo [+] تم تحديث ملفات النظام بنجاح دون المساس بقاعدة البيانات.

:: 4. ترقية هيكل الجداول إذا وُجدت تحديثات برمجية (Migrations)
echo [4/5] جاري مطابقة وتحديث جداول قاعدة البيانات...
if exist "migration_engine.py" (
    python migration_engine.py
)

:: 5. تشغيل البرنامج مجدداً
echo [5/5] جاري إعادة تشغيل النظام...
if exist "START_EMPLOYEE_NETWORK.bat" (
    start "" START_EMPLOYEE_NETWORK.bat
) else if exist "START_SERVER.bat" (
    start "" START_SERVER.bat
) else (
    start "" python app.py
)

echo.
color 0a
echo ========================================================
echo    تم تحديث البرنامج بنجاح وحفظ كافة البيانات السابقة!
echo ========================================================
timeout /t 4 >nul
exit
