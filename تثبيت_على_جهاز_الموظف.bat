@echo off
chcp 65001 > nul
title Stargate Delivery Auto-Installer

:: Request admin privileges
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo [INFO] جار طلب صلاحيات المسؤول لتثبيت وتحديث ملفات النظام...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    set params= %*
    echo UAC.ShellExecute "cmd.exe", "/c ""%~s0"" %params%", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    pushd "%CD%"
    CD /D "%~dp0"

echo =========================================================================
echo       STARGATE DELIVERY EXPERTS - التثبيت الذكي ونقل البيانات التلقائي
echo =========================================================================
echo.
echo [1/6] إغلاق أي برامج أو إصدارات سابقة تعمل في الخلفية...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
taskkill /F /IM Stargate_Delivery.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul

set "INSTALL_DIR=C:\StargateDelivery"
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo.
echo [2/6] مزامنة ونقل جميع البيانات القديمة من السيستم القديم تلقائياً...
if exist "%~dp0_internal\sync_db.exe" (
    "%~dp0_internal\sync_db.exe" "%~dp0delivery.db" "%INSTALL_DIR%\delivery.db"
) else (
    if not exist "%INSTALL_DIR%\delivery.db" copy /Y "%~dp0delivery.db" "%INSTALL_DIR%\delivery.db" >nul
)

echo.
echo [3/6] تنظيف ملفات الواجهات القديمة لمنع أي تضارب شاشات...
if exist "%INSTALL_DIR%\templates" rmdir /S /Q "%INSTALL_DIR%\templates" >nul 2>&1
if exist "%INSTALL_DIR%\static" rmdir /S /Q "%INSTALL_DIR%\static" >nul 2>&1
if exist "%INSTALL_DIR%\app.py" del /F /Q "%INSTALL_DIR%\app.py" >nul 2>&1
if exist "%INSTALL_DIR%\Stargate_Delivery.exe" del /F /Q "%INSTALL_DIR%\Stargate_Delivery.exe" >nul 2>&1

echo.
echo [4/6] نسخ ملفات النظام والتصميم الجديد بالكامل من الفلاشة...
robocopy "%~dp0\" "%INSTALL_DIR%\" /E /IS /IT /XF "delivery.db" "*.ps1" /NJH /NJS /NFL /NDL >nul

echo.
echo [5/6] تحديث اختصارات سطح المكتب والتشغيل التلقائي...
del /F /Q "%USERPROFILE%\Desktop\Stargate*.lnk" >nul 2>&1
del /F /Q "%PUBLIC%\Desktop\Stargate*.lnk" >nul 2>&1

powershell -Command "$sh=New-Object -ComObject WScript.Shell; $sc=$sh.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Stargate Delivery.lnk')); $sc.TargetPath='C:\StargateDelivery\StargateDelivery.exe'; $sc.WorkingDirectory='C:\StargateDelivery'; $sc.Save(); $sc2=$sh.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Startup'), 'Stargate Delivery.lnk')); $sc2.TargetPath='C:\StargateDelivery\StargateDelivery.exe'; $sc2.WorkingDirectory='C:\StargateDelivery'; $sc2.Save();" >nul 2>&1

echo.
echo [6/6] تشغيل النظام الجديد الآن...
start "" "C:\StargateDelivery\StargateDelivery.exe"

echo.
echo =========================================================================
echo    [ تم بنجاح ] تم تثبيت النظام الجديد ونقل كافة البيانات السابقة بنجاح!
echo =========================================================================
echo.
timeout /t 3 >nul
exit
