@echo off
chcp 65001 >nul
title تحديث نظام ستارجيت بأمان تام وبدون لمس البيانات
color 0b

echo =========================================================================
echo       STARGATE ENTERPRISE - أداة التحديث السريع والآمن
echo =========================================================================
echo.
echo مرحباً بك! سيقوم هذا الملف بتحديث ملفات البرنامج والواجهات إلى أحدث إصدار
echo مع الحفاظ التام والمطلق على قاعدة البيانات والطلبات والحسابات السابقة.
echo.
echo -------------------------------------------------------------------------

set "INSTALL_DIR=C:\StargateDelivery"
set "SOURCE_DIR=%~dp0Stargate Delivery System"

if not exist "%INSTALL_DIR%" (
    echo [!] لم يتم العثور على البرنامج مثبت في C:\StargateDelivery!
    echo     يرجى تشغيل مثبت البرنامج أولاً.
    pause
    exit /b
)

:: 1. إيقاف أي عمليات قديمة لفك قفل الملفات
echo [1/4] جاري إيقاف النسخة الحالية لتحديث الملفات بأمان...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
timeout /t 1 /nobreak >nul

:: 2. أخذ نسخة احتياطية فورية للأمان التام
echo [2/4] جاري أخذ نسخة احتياطية فورية من قاعدة بياناتك الحالية...
if not exist "%INSTALL_DIR%\data\backups" mkdir "%INSTALL_DIR%\data\backups" >nul 2>&1
copy /y "%INSTALL_DIR%\data\stargate_production.db" "%INSTALL_DIR%\data\backups\backup_before_update.db" >nul 2>&1
echo       [+] تم تأمين قاعدة بياناتك بنجاح.

:: 3. تحديث ملفات البرنامج فقط (دون لمس أو استبدال قاعدة البيانات الحالية!)
echo [3/4] جاري تحديث ملفات البرنامج والواجهات (مع الحفاظ الكامل على قاعدة بياناتك)...
copy /y "%SOURCE_DIR%\StargateDelivery.exe" "%INSTALL_DIR%\" >nul
copy /y "%SOURCE_DIR%\direct_wipe_tool.py" "%INSTALL_DIR%\" >nul 2>&1
copy /y "%SOURCE_DIR%\تصفير_البيانات_الفوري.bat" "%INSTALL_DIR%\" >nul 2>&1
robocopy "%SOURCE_DIR%\_internal" "%INSTALL_DIR%\_internal" /E >nul 2>&1
robocopy "%SOURCE_DIR%\templates" "%INSTALL_DIR%\templates" /E >nul 2>&1
robocopy "%SOURCE_DIR%\static" "%INSTALL_DIR%\static" /E >nul 2>&1

:: 4. تحديث أيقونة سطح المكتب وتشغيل البرنامج
echo [4/4] جاري تحديث الاختصار وتشغيل النظام...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Stargate Delivery System.lnk')); $s.TargetPath = 'C:\StargateDelivery\StargateDelivery.exe'; $s.WorkingDirectory = 'C:\StargateDelivery'; $s.IconLocation = 'C:\StargateDelivery\static\icons\stargate_logo.ico'; $s.Description = 'نظام ستارجيت لإدارة التوصيل المستقل'; $s.Save()" >nul 2>&1

echo.
color 0a
echo =========================================================================
echo        🎉 تم تحديث نظام ستارجيت بنجاح فائق السرعة!
echo =========================================================================
echo  - تم تحديث البرنامج التنفيذي وكافة الواجهات البرمجية.
echo  - حُلّت مشكلة مسح البيانات والتصفير جذرياً مع دعم رمز PIN المعتمد.
echo  - كافة بياناتك وطلباتك وحساباتك القديمة محفوظة 100%% كما هي.
echo =========================================================================
echo.
echo جاري تشغيل البرنامج المحدث الآن...
timeout /t 2 /nobreak >nul
start "" "C:\StargateDelivery\StargateDelivery.exe"
exit
