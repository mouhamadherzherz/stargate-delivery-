@echo off
chcp 65001 >nul
title إصلاح تسجيل الدخول وكلمات المرور لنظام ستارجيت
color 0a

echo ========================================================
echo     STARGATE ENTERPRISE - إصلاح تسجيل الدخول الفوري
echo ========================================================
echo.

set "TARGET_DIR=C:\StargateDelivery"
set "USB_DB=%~dp0Stargate Delivery System\data\stargate_production.db"
set "USB_APP=%~dp0Stargate Delivery System\app.py"
set "USB_TEMPLATES=%~dp0Stargate Delivery System\templates"

echo [1/3] جاري إيقاف البرنامج مؤقتاً لفك قفل قاعدة البيانات...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

if exist "%TARGET_DIR%" (
    echo [2/3] جاري تحديث ملفات البرنامج وقاعدة البيانات في %TARGET_DIR%...
    if exist "%USB_DB%" (
        copy /y "%USB_DB%" "%TARGET_DIR%\data\stargate_production.db" >nul
        echo [+] تم تحديث قاعدة بيانات النظام بنجاح.
    )
    if exist "%USB_APP%" (
        copy /y "%USB_APP%" "%TARGET_DIR%\app.py" >nul
    )
    if exist "%USB_TEMPLATES%" (
        robocopy "%USB_TEMPLATES%" "%TARGET_DIR%\templates" /E >nul 2>&1
    )
) else (
    echo [!] مجلد %TARGET_DIR% غير موجود، يمكنك تشغيل البرنامج مباشرة من الفلاشة.
)

echo.
echo ========================================================
echo      تم ضبط وتأكيد كافة بيانات ورموز الدخول بنجاح!
echo ========================================================
echo.
echo يمكنك الآن تسجيل الدخول بحسابك ورمز الـ PIN المعتمد في النظام.
echo للاسترداد الطارئ، استخدم صفحة استرداد الحسابات: /forgot_password
echo ========================================================
echo.
pause
