@echo off
chcp 65001 >nul
cd /d "%~dp0Stargate Delivery System"
title STARGATE ENTERPRISE - تشغيل مباشر من الفلاشة
color 0b

echo =========================================================================
echo       STARGATE ENTERPRISE - تشغيل مباشر من الفلاشة
echo =========================================================================
echo.
echo جاري تشغيل الخادم وفتح الواجهة...

start "" python app.py
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8085/login
exit
