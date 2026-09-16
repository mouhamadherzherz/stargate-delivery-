@echo off
chcp 65001 >nul
title STARGATE ENTERPRISE - MASTER SECURITY & RECOVERY CONSOLE
color 0B
cls
echo ====================================================================
echo        STARGATE ENTERPRISE - بوابة الأمان واسترداد الحسابات
echo ====================================================================
echo.
echo جاري فتح وحدة الأمان والتحكم الماستر...
echo.
python "%~dp0stargate_security_manager.py"
pause
