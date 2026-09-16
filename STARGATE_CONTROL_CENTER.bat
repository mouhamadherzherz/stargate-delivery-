@echo off
chcp 65001 > nul
title STARGATE ENTERPRISE - CONTROL CENTER
cd /d "%~dp0"

:MENU
cls
echo ===========================================================================
echo   🚀 STARGATE DELIVERY SYSTEM - ENTERPRISE CONTROL CENTER
echo ===========================================================================
echo.
echo   [1] تشغيل السيرفر الرئيسي وفتح المتصفح (Start Server & Open Dashboard)
echo   [2] تشغيل محطة الموظف على الشبكة (Connect Employee Client Node)
echo   [3] فحص صحة النظام وتنظيف الذاكرة (Health Check & Storage Optimization)
echo   [4] خط أنابيب النشر وبناء الحزمة (1-Click CI/CD Release Pipeline)
echo   [5] الخروج (Exit)
echo.
echo ===========================================================================
set /p choice="اختر رقم العملية [الافتراضي: 1]: "
if "%choice%"=="" set choice=1
if "%choice%"=="1" goto START_SERVER
if "%choice%"=="2" goto EMPLOYEE_NODE
if "%choice%"=="3" goto HEALTH_CHECK
if "%choice%"=="4" goto RELEASE_PIPELINE
if "%choice%"=="5" exit /b 0
goto MENU

:START_SERVER
echo.
echo 🚀 جاري بدء تشغيل السيرفر الرئيسي وفتح المتصفح...
start http://localhost:8085
python app.py
pause
goto MENU

:EMPLOYEE_NODE
echo.
echo 💻 جاري الاتصال بالسيرفر المركزي لمحطة الموظف...
if exist START_EMPLOYEE_NETWORK.bat (
    call START_EMPLOYEE_NETWORK.bat
) else (
    start http://localhost:8085/login
)
pause
goto MENU

:HEALTH_CHECK
echo.
echo 🩺 جاري فحص النظام وإدارة دورة حياة النسخ الاحتياطية...
python -c "import backup_lifecycle_manager, os; stats = backup_lifecycle_manager.enforce_backup_lifecycle(r'data/backups'); print('Status:', stats)"
echo.
pause
goto MENU

:RELEASE_PIPELINE
echo.
echo 📦 جاري تنفيذ خط أنابيب البناء والإصدار المعتمد...
python pipeline_release.py
echo.
pause
goto MENU
