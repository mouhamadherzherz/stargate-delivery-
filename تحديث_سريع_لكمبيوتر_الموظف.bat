@echo off
chcp 65001 >nul
title تحديث سريع لنظام ستارجيت على كمبيوتر الموظف
color 0b

echo ========================================================
echo     STARGATE ENTERPRISE - التحديث التلقائي للموظف
echo ========================================================
echo.

set "TARGET_DIR=C:\StargateDelivery"
set "USB_UPDATES=%~dp0Update_Package\Updates_Source"

if not exist "%TARGET_DIR%" (
    echo [!] لم يتم العثور على البرنامج في: %TARGET_DIR%
    echo     يرجى نسخ مجلد Update_Package يدوياً داخل مجلد البرنامج.
    echo.
    pause
    exit /b
)

echo [1/4] جاري إيقاف الخادم لفك قفل الملفات بأمان...
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/4] جاري إنشاء نسخة احتياطية آمنة لقاعدة البيانات...
set "BACKUP_DIR=%TARGET_DIR%\Backups_Safe\%date:~10,4%-%date:~4,2%-%date:~7,2%_%time:~0,2%-%time:~3,2%-%time:~6,2%"
set "BACKUP_DIR=%BACKUP_DIR: =0%"
mkdir "%BACKUP_DIR%" >nul 2>&1

if exist "%TARGET_DIR%\data\stargate_production.db" (
    copy /y "%TARGET_DIR%\data\stargate_production.db" "%BACKUP_DIR%\" >nul
    copy /y "%TARGET_DIR%\data\*.key" "%BACKUP_DIR%\" >nul 2>&1
    echo [+] تم حفظ نسخة احتياطية في: %BACKUP_DIR%
)

echo [3/4] جاري تحديث ملفات النظام بدون المساس بالبيانات...
robocopy "%USB_UPDATES%" "%TARGET_DIR%" /E /XD "data" "Backups_Safe" "venv" "__pycache__" /XF "stargate_production.db" "*.key" ".env" >nul

echo [4/4] جاري نسخ بيانات الدخول إلى سطح المكتب...
copy /y "%~dp0بيانات_الدخول_للموظف.txt" "%USERPROFILE%\Desktop\" >nul 2>&1

echo.
color 0a
echo ========================================================
echo       تم تحديث النظام بنجاح وحفظ كافة البيانات!
echo ========================================================
echo.
echo بيانات تسجيل الدخول:
echo   - يرجى استخدام اسم المستخدم وكلمة المرور الخاصة بكل حساب.
echo   - أو إدخال رمز PIN السريع المعتمد لكل موظف.
echo ========================================================
echo.
pause
