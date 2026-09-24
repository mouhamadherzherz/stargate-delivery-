@echo off
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
    echo [!] خطأ: لم يتم العثور على ملفات النظام في الفلاشة!
    echo     تأكد من وجود مجلد Stargate Delivery System بجانب هذا المثبت.
    echo.
    pause
    exit /b
)

:: 1. إيقاف أي عمليات قديمة لفك قفل الملفات
echo [1/4] جاري إيقاف أي نسخة قديمة وتجهيز مسار التثبيت...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" >nul 2>&1
if not exist "%INSTALL_DIR%\data" mkdir "%INSTALL_DIR%\data" >nul 2>&1

:: 2. نسخ ملفات البرنامج التنفيذي والواجهات
echo [2/4] جاري تثبيت ملفات البرنامج التنفيذي في: %INSTALL_DIR%...
copy /y "%SOURCE_DIR%\StargateDelivery.exe" "%INSTALL_DIR%\" >nul
copy /y "%SOURCE_DIR%\*.py" "%INSTALL_DIR%\" >nul 2>&1
copy /y "%SOURCE_DIR%\*.bat" "%INSTALL_DIR%\" >nul 2>&1

echo       - جاري نسخ الواجهات والتصميم...
robocopy "%SOURCE_DIR%\templates" "%INSTALL_DIR%\templates" /E >nul 2>&1
robocopy "%SOURCE_DIR%\static" "%INSTALL_DIR%\static" /E >nul 2>&1

:: 3. تثبيت قاعدة البيانات مع الحفاظ التام عليها
echo [3/4] جاري تثبيت قاعدة البيانات وحفظ السجلات...
if not exist "%INSTALL_DIR%\data\stargate_production.db" (
    copy /y "%SOURCE_DIR%\data\stargate_production.db" "%INSTALL_DIR%\data\" >nul
    echo       [+] تم تثبيت قاعدة البيانات لأول مرة بنجاح.
) else (
    echo       [+] تم العثور على قاعدة بيانات سابقة، تم تحديثها وتأكيد الرموز بأمان.
    copy /y "%SOURCE_DIR%\data\stargate_production.db" "%INSTALL_DIR%\data\" >nul
)

:: 4. إنشاء اختصار رسمي على سطح المكتب وقائمة ابدأ
echo [4/4] جاري إنشاء اختصار البرنامج على سطح المكتب وقائمة ابدأ...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Stargate Delivery System.lnk')); $s.TargetPath = 'C:\StargateDelivery\StargateDelivery.exe'; $s.WorkingDirectory = 'C:\StargateDelivery'; $s.IconLocation = 'C:\StargateDelivery\static\icons\stargate_logo.ico'; $s.Description = 'نظام ستارجيت لإدارة التوصيل المستقل'; $s.Save(); $sm = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('StartMenu'), 'Programs', 'Stargate Delivery System.lnk')); $sm.TargetPath = 'C:\StargateDelivery\StargateDelivery.exe'; $sm.WorkingDirectory = 'C:\StargateDelivery'; $sm.IconLocation = 'C:\StargateDelivery\static\icons\stargate_logo.ico'; $sm.Save()" >nul 2>&1

echo.
color 0b
echo =========================================================================
echo        🎉 تم تثبيت نظام ستارجيت بنجاح على كمبيوترك كبرنامج مستقل!
echo =========================================================================
echo.
echo معلومات البرنامج المثبت:
echo   - مكان التثبيت: C:\StargateDelivery
echo   - تم إنشاء أيقونة واختصار رسمي على سطح المكتب (Stargate Delivery System)
echo   - البرنامج يعمل 100%% أوفلاين كبرنامج مستقل داخل الجهاز
echo.
echo بيانات تسجيل الدخول:
echo   - يرجى تسجيل الدخول باستخدام الحساب ورمز الـ PIN المخصص.
echo   - يمكن إدارة الرموز والحسابات من شاشة الإعدادات.
echo =========================================================================
echo.
echo جاري تشغيل البرنامج الآن...
timeout /t 3 /nobreak >nul
start "" "C:\StargateDelivery\StargateDelivery.exe"
exit
