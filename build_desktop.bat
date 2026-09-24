@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   Stargate Delivery - Windows Desktop Build
echo ============================================================

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3 is not installed or is not on PATH.
  exit /b 1
)

if not exist .venv (
  echo [1/5] Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
)
call .venv\Scripts\activate.bat

echo [2/5] Installing desktop build dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt
if errorlevel 1 exit /b 1

echo [3/5] Validating Python source...
python -m compileall -q app.py core routes services
if errorlevel 1 exit /b 1

echo [4/5] Building executable...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller --clean --noconfirm --onefile --windowed ^
  --name StargateDelivery ^
  --icon="static\icons\stargate_logo.ico" ^
  --add-data="templates;templates" ^
  --add-data="static;static" ^
  --add-data="core;core" ^
  --add-data="routes;routes" ^
  --add-data="services;services" ^
  --hidden-import=webview ^
  --hidden-import=webview.platforms.edgechromium ^
  --hidden-import=webview.platforms.winforms ^
  --hidden-import=sqlite3 ^
  app.py
if errorlevel 1 exit /b 1

echo [5/5] Preparing portable distribution...
if not exist release mkdir release
copy /Y "dist\StargateDelivery.exe" "release\StargateDelivery.exe" >nul
if not exist "release\data" mkdir "release\data"
if not exist "release\README.txt" (
  >"release\README.txt" echo Stargate Delivery Desktop
  >>"release\README.txt" echo Run StargateDelivery.exe. User data is stored in the data folder.
)

echo Build completed: %CD%\release\StargateDelivery.exe
echo Optional: open StargateDelivery.iss with Inno Setup to create an installer.
exit /b 0
