@echo off
chcp 65001 > nul
echo ============================================================
echo   Stargate Delivery System - Desktop Build Script
echo ============================================================
echo.

cd /d D:\STARGATE\repo

echo [1/4] تثبيت المتطلبات...
pip install pywebview pyinstaller --quiet
if %errorlevel% neq 0 (
    echo [ERROR] فشل تثبيت المتطلبات!
    pause
    exit /b 1
)

echo [2/4] تجميع التطبيق بـ PyInstaller...
pyinstaller --clean --noconfirm ^
    --noconsole ^
    --onefile ^
    --icon="static\icons\stargate_logo.ico" ^
    --name="StargateDelivery" ^
    --add-data="templates;templates" ^
    --add-data="static;static" ^
    --add-data="config.py;." ^
    --hidden-import=webview ^
    --hidden-import=webview.platforms.winforms ^
    --hidden-import=clr ^
    --hidden-import=flask ^
    --hidden-import=jinja2 ^
    --hidden-import=sqlite3 ^
    --hidden-import=werkzeug ^
    --hidden-import=requests ^
    app.py

if %errorlevel% neq 0 (
    echo [ERROR] فشل التجميع!
    pause
    exit /b 1
)

echo [3/4] نسخ الملف التنفيذي إلى مجلد الإنتاج...
if not exist "C:\StargateDelivery" mkdir "C:\StargateDelivery"
if not exist "C:\StargateDelivery\data" mkdir "C:\StargateDelivery\data"
copy /Y "dist\StargateDelivery.exe" "C:\StargateDelivery\StargateDelivery.exe"

echo [4/4] تحديث المتطلبات...
copy /Y "requirements.txt" "C:\StargateDelivery\requirements.txt"
xcopy /E /I /Y "static" "C:\StargateDelivery\static" > nul
xcopy /E /I /Y "templates" "C:\StargateDelivery\templates" > nul

echo.
echo ============================================================
echo   تم البناء بنجاح!
echo   الملف التنفيذي: C:\StargateDelivery\StargateDelivery.exe
echo   لإنشاء مثبت رسمي: افتح StarGate_Setup.iss بـ Inno Setup
echo ============================================================
echo.
pause
