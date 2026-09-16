@echo off
chcp 65001 > nul
title Stargate Delivery - تشغيل شاشة الموظف عبر الشبكة

echo =========================================================================
echo          STARGATE DELIVERY - تشغيل واجهة الموظف الذكية
echo =========================================================================
echo.
echo جار الاتصال بالنظام المركزي وقاعدة البيانات المباشرة...

set "SERVER_URL=http://192.168.9.114:8085/orders?open_new=1"

:: Try Edge in App mode
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    start "" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" --app="%SERVER_URL%"
    exit
)
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
    start "" "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" --app="%SERVER_URL%"
    exit
)

:: Try Chrome in App mode
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" --app="%SERVER_URL%"
    exit
)
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    start "" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" --app="%SERVER_URL%"
    exit
)

:: Fallback default browser
start "" "%SERVER_URL%"
exit
