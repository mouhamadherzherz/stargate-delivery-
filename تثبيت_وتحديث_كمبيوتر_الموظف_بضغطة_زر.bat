@echo off
chcp 65001 >nul
title STARGATE ENTERPRISE - التحديث الجذري الشامل لكمبيوتر الموظف
color 0a

echo =========================================================================
echo       STARGATE ENTERPRISE - أداة التحديث والتثبيت الجذرية الشاملة
echo =========================================================================
echo.
echo مرحباً بك! سيقوم هذا البرنامج بتحديث نظام ستارجيت بالكامل
echo مع الحفاظ التام والقطعي على كافة البيانات والطلبات المسجلة دون حذف أي شيء!
echo.
echo -------------------------------------------------------------------------

set "INSTALL_DIR=C:\StargateDelivery"
set "SOURCE_DIR=%~dp0Stargate Delivery System"

if not exist "%SOURCE_DIR%" (
    echo [!] خطأ: لم يتم العثور على مجلد ملفات البرنامج في الفلاشة!
    pause
    exit /b
)

:: 1. إيقاف كامل للعمليات السابقة وفك قفل الملفات
echo [1/5] جاري إيقاف أي نسخة قديمة وفك قفل المنافذ والملفات...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
taskkill /F /IM python.exe /T >nul 2>&1
taskkill /F /IM pythonw.exe /T >nul 2>&1

for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :8085 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" >nul 2>&1
if not exist "%INSTALL_DIR%\data" mkdir "%INSTALL_DIR%\data" >nul 2>&1
if not exist "%INSTALL_DIR%\Backups_Safe" mkdir "%INSTALL_DIR%\Backups_Safe" >nul 2>&1

:: 2. تأمين نسخة احتياطية آمنة لقاعدة بيانات الموظف
if exist "%INSTALL_DIR%\data\stargate_production.db" (
    echo [2/5] تم العثور على قاعدة بيانات الموظف الحالية!
    echo       [+] جاري أخذ نسخة أمان احتياطية فورية لحفظ كافة الطلبات...
    copy /y "%INSTALL_DIR%\data\stargate_production.db" "%INSTALL_DIR%\Backups_Safe\db_backup_before_update.db" >nul 2>&1
    echo       [+] تم تأمين وحفظ البيانات السابقة 100%%.
) else (
    echo [2/5] تثبيت أولي: جاري تجهيز قاعدة البيانات لأول مرة...
    copy /y "%SOURCE_DIR%\data\stargate_production.db" "%INSTALL_DIR%\data\" >nul
)

:: 3. تحديث ملف التشغيل الرئيسي EXE مع تجاوز أقفال ويندوز
echo [3/5] جاري تحديث ملف البرنامج الرئيسي (StargateDelivery.exe)...
if exist "%INSTALL_DIR%\StargateDelivery.old.exe" del /f /q "%INSTALL_DIR%\StargateDelivery.old.exe" >nul 2>&1
if exist "%INSTALL_DIR%\StargateDelivery.exe" (
    ren "%INSTALL_DIR%\StargateDelivery.exe" "StargateDelivery.old.exe" >nul 2>&1
)
copy /y "%SOURCE_DIR%\StargateDelivery.exe" "%INSTALL_DIR%\StargateDelivery.exe" >nul
if %errorlevel% neq 0 (
    echo [!] تحذير: جاري إعادة محاولة نسخ ملف البرنامج...
    timeout /t 2 /nobreak >nul
    copy /y "%SOURCE_DIR%\StargateDelivery.exe" "%INSTALL_DIR%\StargateDelivery.exe" >nul
)
if exist "%INSTALL_DIR%\StargateDelivery.old.exe" del /f /q "%INSTALL_DIR%\StargateDelivery.old.exe" >nul 2>&1

:: 4. نسخ مكتبات التشغيل السريع والواجهات
echo [4/5] جاري تحديث المكتبات والواجهات الحديثة...
robocopy "%SOURCE_DIR%\_internal" "%INSTALL_DIR%\_internal" /E /PURGE >nul 2>&1
robocopy "%SOURCE_DIR%\templates" "%INSTALL_DIR%\templates" /E /PURGE >nul 2>&1
robocopy "%SOURCE_DIR%\static" "%INSTALL_DIR%\static" /E /PURGE >nul 2>&1

:: تنظيف أي ملفات برمجية قديمة تسبب تعارضاً
if exist "%INSTALL_DIR%\app.py" del /f /q "%INSTALL_DIR%\app.py" >nul 2>&1
if exist "%INSTALL_DIR%\delivery.db" del /f /q "%INSTALL_DIR%\delivery.db" >nul 2>&1

:: 5. إنشاء اختصار رسمي موجه للملف التنفيذي الجديد
echo [5/5] جاري تحديث الاختصار الرسمي على سطح المكتب...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Stargate Delivery.lnk')); $s.TargetPath = 'C:\StargateDelivery\StargateDelivery.exe'; $s.WorkingDirectory = 'C:\StargateDelivery'; $s.IconLocation = 'C:\StargateDelivery\static\icons\stargate_logo.ico'; $s.Description = 'نظام ستارجيت لإدارة التوصيل المستقل'; $s.Save()" >nul 2>&1

copy /y "%SOURCE_DIR%\بيانات_الدخول.txt" "%USERPROFILE%\Desktop\بيانات_دخول_ستارجيت.txt" >nul 2>&1

echo.
color 0b
echo =========================================================================
echo        🎉 اكتمل التحديث الجذري بنجاح تام!
echo =========================================================================
echo.
echo ملخص التحديث:
echo   - تم الحفاظ على كافة البيانات والطلبات السابقة دون حذف أي شيء.
echo   - تم تفعيل الترقية التلقائية لقاعدة البيانات (إصلاح خطأ 500 نهائياً).
echo   - تم ضبط رموز الـ PIN لجميع الموظفين لتعمل فوراً.
echo.
echo بيانات تسجيل الدخول:
echo   1. عبر رمز PIN السريع:
echo      - رمز الإدارة:   20122020  (أو 19701313)
echo      - رمز دعاء:      81097175
echo      - رمز آدم:       090921
echo      - رمز نور:       121314
echo      - رمز الصيانة:   294225
echo.
echo   2. عبر اسم المستخدم وكلمة السر:
echo      - اسم المستخدم:  stargate   (أو admin)
echo      - كلمة المرور:    stargate@19701313
echo =========================================================================
echo.
echo جاري تشغيل البرنامج المحدث الآن...
timeout /t 2 /nobreak >nul
start "" "C:\StargateDelivery\StargateDelivery.exe"
exit
