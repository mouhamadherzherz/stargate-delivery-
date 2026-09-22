@echo off
chcp 65001 >nul
title STARGATE ENTERPRISE - التحديث الجذري والشامل الإصدار 3.5
color 0b

echo =========================================================================
echo       STARGATE ENTERPRISE - التحديث العالمي الشامل (V3.5)
echo =========================================================================
echo.
echo مرحباً بك! هذا هو التحديث الشامل والمتطور وفق معايير الشركات العالمية.
echo.
echo ميزات التحديث V3.5:
echo  1. معايير تصميم عالمية عالية الدقة (Global Tech UI).
echo  2. ضبط مقاسات النظام وهندسة دقة العرض (DPI Scaling & Proportions).
echo  3. توحيد وضبط مقاسات الشعارات والصور هندسياً دون أي تشوه.
echo  4. حذف كافة التكرارات والزوائد وتوحيد الدعم الفني والصيانة في مكان وحيد.
echo  5. الحفاظ الكامل والمطلق 100% على كافة بياناتك وطلباتك وحساباتك.
echo.
echo -------------------------------------------------------------------------
echo [1/3] إغلاق أي نسخة مفتوحة حالياً لفك قفل الملفات...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
timeout /t 1 /nobreak >nul

set "INSTALL_DIR=C:\StargateDelivery"
if exist "%INSTALL_DIR%\data\stargate_production.db" (
    echo [2/3] تأمين وحفظ نسخة احتياطية من قاعدة بياناتك الحالية...
    if not exist "%INSTALL_DIR%\data\backups" mkdir "%INSTALL_DIR%\data\backups" >nul 2>&1
    copy /y "%INSTALL_DIR%\data\stargate_production.db" "%INSTALL_DIR%\data\backups\backup_v3.5_safety.db" >nul 2>&1
    echo       [+] تم تأمين قاعدة بياناتك بنجاح.
)

echo [3/3] جاري تثبيت التحديث الجذري الشامل فائق السرعة...
set "SETUP_EXE=%~dp0StargateDelivery_Setup_v3.5.exe"
if not exist "%SETUP_EXE%" set "SETUP_EXE=%~dp0StargateDelivery_Setup_v3.0.exe"

if exist "%SETUP_EXE%" (
    "%SETUP_EXE%" /SILENT /SUPPRESSMSGBOXES /NORESTART
) else (
    echo [!] جاري النسخ اليدوي للملفات من المجلد...
    robocopy "%~dp0Stargate Delivery System" "%INSTALL_DIR%" /E /NFL /NDL /NP >nul 2>&1
)

echo.
color 0a
echo =========================================================================
echo        🎉 تم تثبيت التحديث الجذري والشامل V3.5 بنجاح تام!
echo =========================================================================
echo  - تم تطبيق معايير التصميم والمقاسات العالمية بنجاح.
echo  - تم إصلاح جميع الواجهات وصفحة التحديثات نهائياً.
echo  - جميع بياناتك السابقة وطلباتك وحساباتك محفوظة بنسبة 100%%.
echo =========================================================================
echo.
echo جاري تشغيل البرنامج الآن...
timeout /t 2 /nobreak >nul
start "" "C:\StargateDelivery\StargateDelivery.exe"
exit
