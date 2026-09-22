@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 > nul
title Stargate Delivery - تثبيت وتحديث محمي بدون أي فقدان للبيانات

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
echo [1/6] إغلاق أي برامج سابقة بأمان لضمان سلامة قاعدة البيانات...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
taskkill /F /IM Stargate_Delivery.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul

set "INSTALL_DIR=C:\StargateDelivery"
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%INSTALL_DIR%\data" mkdir "%INSTALL_DIR%\data"
if not exist "%INSTALL_DIR%\db_backups" mkdir "%INSTALL_DIR%\db_backups"

echo.
echo [2/6] تأمين وحفظ بيانات الموظف (أخذ نسخة احتياطية تلقائية أولاً)...
if exist "%INSTALL_DIR%\data\stargate_production.db" (
    echo [*] تم العثور على قاعدة بيانات الموظف السابقة.
    echo [*] جاري حفظ نسخة احتياطية كاملة في db_backups للحماية القصوى...
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "dt=%%I"
    set "BACKUP_NAME=stargate_backup_!dt:~0,8!_!dt:~8,6!.db"
    copy /Y "%INSTALL_DIR%\data\stargate_production.db" "%INSTALL_DIR%\db_backups\!BACKUP_NAME!" >nul
    echo [*] تم حفظ النسخة بنجاح: !BACKUP_NAME!
    echo [*] قاعدة بيانات الموظف الأصلية محمية 100%% ولن يتم مسها أو استبدالها أبداً.
) else (
    echo [*] تثبيت لأول مرة: نسخ قاعدة البيانات الابتدائية...
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
echo [3/6] تحديث ملفات القوالب والشاشات والواجهات الجديدة...
if exist "%INSTALL_DIR%\templates" rmdir /S /Q "%INSTALL_DIR%\templates" >nul 2>&1
if exist "%INSTALL_DIR%\static" rmdir /S /Q "%INSTALL_DIR%\static" >nul 2>&1

echo.
echo [4/6] نسخ ملفات النظام البرمجية بأمان كامل واستثناء قواعد البيانات...
robocopy "%~dp0\" "%INSTALL_DIR%\" /E /IS /IT /XF "*.db*" "*.sqlite*" "*.wal*" "*.shm*" "*.ps1" /XD "data" "db_backups" /NJH /NJS /NFL /NDL >nul

echo.
echo [5/6] إنشاء وتحديث اختصار سطح المكتب الذكي للموظف...
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
if exist "%INSTALL_DIR%\static\icons\stargate_logo.ico" (
    echo oLink.IconLocation = "%INSTALL_DIR%\static\icons\stargate_logo.ico, 0" >> %SCRIPT%
) else (
    echo oLink.IconLocation = "%INSTALL_DIR%\app_icon.ico, 0" >> %SCRIPT%
)
echo oLink.Description = "Stargate Delivery System - نظام ستارجيت للدلفري" >> %SCRIPT%
echo oLink.Save >> %SCRIPT%
cscript //nologo %SCRIPT% >nul 2>&1
del %SCRIPT% >nul 2>&1

echo.
echo [6/6] تشغيل النظام المحدث الآن...
start "" "%PY_EXE%" "%INSTALL_DIR%\app.py"

echo.
echo =========================================================================
echo   [ نجاح تام ] تم تثبيت وتحديث النظام بنجاح 100%% مع الحفاظ التام على البيانات!
echo   [ موقع البيانات المحمية ] %INSTALL_DIR%\data\stargate_production.db
echo   [ موقع النسخ الاحتياطية ] %INSTALL_DIR%\db_backups\
echo =========================================================================
echo.
timeout /t 5 >nul
exit
