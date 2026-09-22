@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Stargate Update Builder
echo ========================================================
echo        STARGATE ENTERPRISE - Build Update Package
echo ========================================================
echo.
echo Packaging clean update files...

if not exist "Update_Package\Updates_Source" mkdir "Update_Package\Updates_Source" >nul 2>&1

robocopy "." "Update_Package\Updates_Source" /E /XD "data" "backups" "Backups_Safe" "venv" "__pycache__" "Update_Package" "release_output" "installer_output" "build" "dist" "protected_src" /XF "stargate_production.db" "*.key" ".env" "license_generator_gui.py" "build_protected.py" "StargateDelivery.spec" "Protected_StargateDelivery.spec" >nul 2>&1

copy /y "UPDATE_EMPLOYEE.bat" "Update_Package\" >nul 2>&1

echo.
echo ========================================================
echo [SUCCESS] Update_Package has been created successfully!
echo You can now copy Update_Package to the employee computer.
echo ========================================================
echo.
pause
