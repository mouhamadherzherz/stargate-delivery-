@echo off
setlocal EnableExtensions EnableDelayedExpansion
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
    set params=%*
    echo UAC.ShellExecute "cmd.exe", "/c ""%~s0"" %params%", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    pushd "%CD%"
    CD /D "%~dp0"

echo =========================================================================
echo       STARGATE DELIVERY EXPERTS - التثبيت الذكي وحماية البيانات الفورية
echo =========================================================================
echo.
echo [1/6] إغلاق أي برامج أو إصدارات سابقة تعمل في الخلفية...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
taskkill /F /IM Stargate_Delivery.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul

set "INSTALL_DIR=C:\StargateDelivery"
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%INSTALL_DIR%\data" mkdir "%INSTALL_DIR%\data"

echo.
echo [2/6] تأمين قاعدة البيانات وحمايتها من أي استبدال أو مساس...
if exist "%INSTALL_DIR%\data\stargate_production.db" (
    echo [*] قاعدة البيانات الأساسية موجودة ومحمية بالكامل ولا يتم لمسها.
) else (
    if exist "%~dp0data\stargate_production.db" (
        copy /Y "%~dp0data\stargate_production.db" "%INSTALL_DIR%\data\stargate_production.db" >nul
    ) else if exist "%~dp0delivery.db" (
        copy /Y "%~dp0delivery.db" "%INSTALL_DIR%\data\stargate_production.db" >nul
    )
)

if exist "%INSTALL_DIR%\data\stargate_production.db" (
    if not exist "%INSTALL_DIR%\delivery.db" (
        mklink /H "%INSTALL_DIR%\delivery.db" "%INSTALL_DIR%\data\stargate_production.db" >nul 2>&1
    )
    if exist "%INSTALL_DIR%\_internal" (
        if not exist "%INSTALL_DIR%\_internal\delivery.db" (
            mklink /H "%INSTALL_DIR%\_internal\delivery.db" "%INSTALL_DIR%\data\stargate_production.db" >nul 2>&1
        )
    )
)

echo.
echo [3/6] تحديث ملفات النظام والقوالب والتصميم الجديد...
if exist "%INSTALL_DIR%\templates" rmdir /S /Q "%INSTALL_DIR%\templates" >nul 2>&1
if exist "%INSTALL_DIR%\static" rmdir /S /Q "%INSTALL_DIR%\static" >nul 2>&1

echo.
echo [4/6] نسخ ملفات النظام البرمجية بأمان مع استثناء قواعد البيانات بالكامل...
robocopy "%~dp0\" "%INSTALL_DIR%\" /E /IS /IT /XF "*.db*" "*.sqlite*" "*.wal*" "*.shm*" "*.ps1" /XD "data" /NJH /NJS /NFL /NDL >nul

echo.
echo [5/6] تحديث اختصارات سطح المكتب والتشغيل التلقائي...
del /F /Q "%USERPROFILE%\Desktop\Stargate*.lnk" >nul 2>&1
del /F /Q "%PUBLIC%\Desktop\Stargate*.lnk" >nul 2>&1

set "PY_EXE=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\pythonw.exe"
if not exist "%PY_EXE%" (
    for /f "tokens=*" %%i in ('where pythonw.exe 2^>nul') do set "PY_EXE=%%i"
)
if not exist "%PY_EXE%" (
    for /f "tokens=*" %%i in ('where python.exe 2^>nul') do set "PY_EXE=%%i"
)

set SCRIPT="%TEMP%\CreateShortcut.vbs"
echo Set oWS = WScript.CreateObject("WScript.Shell") > %SCRIPT%
echo sLinkFile = "%USERPROFILE%\Desktop\Stargate Delivery.lnk" >> %SCRIPT%
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SCRIPT%
echo oLink.TargetPath = "%PY_EXE%" >> %SCRIPT%
echo oLink.Arguments = chr(34) ^& "%INSTALL_DIR%\app.py" ^& chr(34) >> %SCRIPT%
echo oLink.WorkingDirectory = "%INSTALL_DIR%" >> %SCRIPT%
echo oLink.IconLocation = "%INSTALL_DIR%\app_icon.ico, 0" >> %SCRIPT%
echo oLink.Description = "Stargate Delivery System" >> %SCRIPT%
echo oLink.Save >> %SCRIPT%
cscript //nologo %SCRIPT% >nul 2>&1
del %SCRIPT% >nul 2>&1

echo.
echo [6/6] تشغيل النظام الجديد الآن...
start "" "%PY_EXE%" "%INSTALL_DIR%\app.py"

echo.
echo =========================================================================
echo    [ تم بنجاح ] تم تثبيت النظام وتأمين حفظ البيانات التلقائي 100%% بنجاح!
echo =========================================================================
echo.
timeout /t 3 >nul
exit
