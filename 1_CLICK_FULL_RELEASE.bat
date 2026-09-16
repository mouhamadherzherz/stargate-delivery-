@echo off
chcp 65001 > nul
title Stargate Enterprise - 1-Click CI/CD Release Pipeline
cls
echo =====================================================================
echo    STARGATE ENTERPRISE - 1-CLICK AUTOMATED RELEASE PIPELINE
echo =====================================================================
echo.
echo [INFO] جاري تشغيل خط أنابيب النشر والتجميع الموحد...
echo.

python pipeline_release.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo =====================================================================
    echo [SUCCESS] اكتمل بناء وإصدار النسخة الإنتاجية بنجاح 100%%!
    echo مسار النسخة: D:\STARGATE_Enterprise_Full_System.zip
    echo =====================================================================
) else (
    echo.
    echo [ERROR] حدث خطأ أثناء تنفيذ خط أنابيب البناء.
)

pause
