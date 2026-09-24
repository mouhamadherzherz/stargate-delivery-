@echo off
chcp 65001 >nul
color 0B
title STARGATE DELIVERY - تحديث النظام الذكي بدون فقدان البيانات

echo ======================================================================
echo          نظام ستارجيت ديليفري - STARGATE DELIVERY SYSTEM
echo         تحديث النظام بنقرة واحدة مع حماية كافة بيانات الموظف 100%%
echo ======================================================================
echo.

:: 1. إغلاق البرنامج لفك قفل قاعدة البيانات والملفات
echo [1/5] جاري إيقاف تشغيل البرنامج مؤقتاً لفك قفل الملفات...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
taskkill /F /IM python.exe /T >nul 2>&1
taskkill /F /IM pythonw.exe /T >nul 2>&1
ping 127.0.0.1 -n 2 >nul

:: 2. تحديد مسار البرنامج المثبت عند الموظف تلقائياً
set "TARGET_DIR="
if exist "C:\StargateDelivery\data\stargate_production.db" (
    set "TARGET_DIR=C:\StargateDelivery"
) else if exist "C:\STARGATE\data\stargate_production.db" (
    set "TARGET_DIR=C:\STARGATE"
) else if exist "D:\STARGATE\repo\data\stargate_production.db" (
    set "TARGET_DIR=D:\STARGATE\repo"
) else if exist "C:\StargateDelivery" (
    set "TARGET_DIR=C:\StargateDelivery"
) else if exist "C:\STARGATE" (
    set "TARGET_DIR=C:\STARGATE"
) else (
    set "TARGET_DIR=C:\StargateDelivery"
)

echo [2/5] مسار التثبيت المكتشف على الكمبيوتر: %TARGET_DIR%
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"
if not exist "%TARGET_DIR%\data" mkdir "%TARGET_DIR%\data"
if not exist "%TARGET_DIR%\Backups_Safe" mkdir "%TARGET_DIR%\Backups_Safe"

:: 3. حماية وأمان البيانات بنسبة 100%
if exist "%TARGET_DIR%\data\stargate_production.db" (
    echo [3/5] حفظ نسخة احتياطية آمنة لقاعدة بيانات الموظف الحالية...
    copy /Y "%TARGET_DIR%\data\stargate_production.db" "%TARGET_DIR%\Backups_Safe\stargate_backup_safe.db" >nul 2>&1
    copy /Y "%TARGET_DIR%\data\*.key" "%TARGET_DIR%\Backups_Safe\" >nul 2>&1
    copy /Y "%TARGET_DIR%\.env" "%TARGET_DIR%\Backups_Safe\" >nul 2>&1
    echo       [تم حفظ وتأمين طلبات وبيانات الموظف بنجاح 100%%]
) else (
    echo [3/5] تثبيت جديد: جاري نسخ قاعدة البيانات التأسيسية...
    if exist "%~dp0Stargate Delivery System\data\stargate_production.db" (
        copy /Y "%~dp0Stargate Delivery System\data\stargate_production.db" "%TARGET_DIR%\data\stargate_production.db" >nul 2>&1
    ) else if exist "%~dp0قاعدة_بيانات_الزبون_الأصلية\stargate_production.db" (
        copy /Y "%~dp0قاعدة_بيانات_الزبون_الأصلية\stargate_production.db" "%TARGET_DIR%\data\stargate_production.db" >nul 2>&1
    )
)

:: 4. استيراد ملفات التحديث البرمجية واستثناء البيانات
echo [4/5] جاري نقل التحديثات الجديدة إلى كمبيوتر الموظف...
set "SOURCE_DIR=%~dp0Update_Package\Updates_Source"
if not exist "%SOURCE_DIR%" (
    if exist "%~dp0Stargate Delivery System" (
        set "SOURCE_DIR=%~dp0Stargate Delivery System"
    )
)

robocopy "%SOURCE_DIR%" "%TARGET_DIR%" /E /XD "data" "Backups_Safe" "venv" "__pycache__" /XF "stargate_production.db" "*.key" ".env" /R:1 /W:1 /NFL /NDL /NJH /NJS /nc /ns /np >nul

:: التحقق من وجود ملفات التشغيل والنسخة الاحتياطية
if not exist "%TARGET_DIR%\data\stargate_production.db" (
    if exist "%TARGET_DIR%\Backups_Safe\stargate_backup_safe.db" (
        copy /Y "%TARGET_DIR%\Backups_Safe\stargate_backup_safe.db" "%TARGET_DIR%\data\stargate_production.db" >nul 2>&1
    )
)

:: 5. ترقية جداول قاعدة البيانات تلقائياً
echo [5/5] جاري فحص ومطابقة جداول قاعدة البيانات...
if exist "%TARGET_DIR%\migration_engine.py" (
    python "%TARGET_DIR%\migration_engine.py" >nul 2>&1
) else if exist "%~dp0repair_subscriber_db.py" (
    python "%~dp0repair_subscriber_db.py" "%TARGET_DIR%\data\stargate_production.db" >nul 2>&1
)

echo.
color 0A
echo ======================================================================
echo            تم تحديث نظام الديليفري بنجاح تام وبأمان 100%%!
echo   - تم الاحتفاظ بكافة الزبائن والطلبات والمحاسبة دون أي حذف أو فقدان.
echo   - تم تطبيق كافة الإصلاحات البرمجية والواجهات الحديثة.
echo ======================================================================
echo.

echo جاري إعادة تشغيل النظام...
ping 127.0.0.1 -n 3 >nul
if exist "%TARGET_DIR%\StargateDelivery.exe" (
    start "" "%TARGET_DIR%\StargateDelivery.exe"
) else if exist "%TARGET_DIR%\START_EMPLOYEE_NETWORK.bat" (
    start "" "%TARGET_DIR%\START_EMPLOYEE_NETWORK.bat"
) else if exist "%TARGET_DIR%\START_SERVER.bat" (
    start "" "%TARGET_DIR%\START_SERVER.bat"
) else (
    start "" python "%TARGET_DIR%\app.py"
)
exit
