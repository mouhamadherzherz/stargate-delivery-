@echo off
setlocal EnableExtensions
chcp 65001 > nul
title Stargate - Build Production Setup.exe for Clients
cls

echo.
echo ===================================================================
echo     STARGATE DELIVERY - بناء ملف التثبيت للزبائن
echo ===================================================================
echo.

cd /D "D:\STARGATE\repo"

:: ─── التحقق من PyInstaller ───
echo [1/4] التحقق من توفر PyInstaller...
python -m PyInstaller --version > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] PyInstaller غير مثبت. جاري التثبيت...
    python -m pip install pyinstaller
)
echo     ✅ PyInstaller جاهز

:: ─── بناء EXE من Python ───
echo.
echo [2/4] تحويل البرنامج إلى EXE مستقل (PyInstaller)...
echo     هذه العملية تأخذ 3-7 دقائق. يرجى الانتظار...
echo Building EXE with PyInstaller...
python create_empty_db.py
python -m PyInstaller StargateDelivery.spec --clean --noconfirm

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [❌ خطأ] فشل بناء EXE! راجع الرسائل أعلاه.
    pause
    exit /B 1
)
echo     ✅ تم بناء EXE بنجاح في: dist\StargateDelivery\

:: ─── التحقق من Inno Setup ───
echo.
echo [3/4] بناء ملف Setup.exe للزبائن (Inno Setup)...

set ISCC="C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
if not exist %ISCC% (
    set ISCC="C:\Program Files\Inno Setup 7\ISCC.exe"
)
if not exist %ISCC% (
    echo [❌ خطأ] Inno Setup 7 غير مثبت على هذا الجهاز!
    echo.
    echo → قم بتحميله من: https://jrsoftware.org/isdl.php
    echo → ثم أعد تشغيل هذا الملف
    pause
    exit /B 1
)

%ISCC% StarGate_Setup.iss

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [❌ خطأ] فشل بناء ملف Setup.exe!
    pause
    exit /B 1
)

:: ─── النتيجة ───
echo.
echo [4/4] التحقق من الناتج...
if exist "installer_output\StargateDelivery_Setup_v2.0.exe" (
    echo.
    echo ===================================================================
    echo   🎉 تم بناء ملف التثبيت بنجاح!
    echo.
    echo   📦 مسار الملف الجاهز للزبائن:
    echo      D:\STARGATE\repo\installer_output\StargateDelivery_Setup_v2.0.exe
    echo.
    echo   ✅ يمكنك الآن نقل هذا الملف لأي زبون وتثبيته مباشرة
    echo   ✅ لا يحتاج Python أو أي برامج أخرى
    echo   ✅ عند التشغيل يطلب كود التفعيل تلقائياً
    echo ===================================================================
    echo.
) else (
    echo [!] لم يُعثر على ملف الإخراج. راجع الأخطاء أعلاه.
)
exit /B 0