@echo off
chcp 65001 > nul
title Stargate Delivery System - Enterprise Edition
cd /d "%~dp0"

:: Auto-cleanup any old/duplicate hosts on port 8085 and stale tunnels
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :8085 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
taskkill /F /IM cloudflared.exe >nul 2>&1
taskkill /F /IM ngrok.exe >nul 2>&1

echo ========================================================
echo   🚀 Stargate Delivery Enterprise - Master Server
echo   Local Host: http://localhost:8085
echo   Network IP: http://192.168.9.114:8085
echo ========================================================
python app.py
pause
