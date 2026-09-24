@echo off
chcp 65001 >nul
title STARGATE ENTERPRISE - تصفير ومسح البيانات الفوري
color 0c

echo =========================================================================
echo       STARGATE ENTERPRISE - أداة مسح وتصفير البيانات الفورية
echo =========================================================================
echo.
echo تحذير: هذه الأداة تقوم بمسح الشحنات والحركات المالية وتصفير الخزائن فورياً.
echo يتم حفظ نسخة احتياطية آمنة من قاعدة البيانات تلقائياً قبل البدء.
echo.
echo اختر نوع المسح المطلوب:
echo  [1] مسح الشحنات والحركات المالية فقط (مع الحفاظ على التجار والمناديب والإعدادات)
echo  [2] تصفير وضبط مصنع شامل 100%% (حذف كل شيء والبدء من الصفر التام)
echo  [3] إلغاء وخروج
echo.
set /p choice="أدخل رقم خيارك (1 أو 2 أو 3): "

if "%choice%"=="1" goto wipe_operational
if "%choice%"=="2" goto wipe_all
if "%choice%"=="3" exit /b
goto invalid_choice

:wipe_operational
echo.
echo [1/3] إيقاف تشغيل البرنامج لفك قفل قاعدة البيانات...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
timeout /t 1 /nobreak >nul

echo [2/3] جاري مسح الشحنات وتصفير الحركات المالية...
python "%~dp0direct_wipe_tool.py" operational
goto finish

:wipe_all
echo.
echo [1/3] إيقاف تشغيل البرنامج لفك قفل قاعدة البيانات...
taskkill /F /IM StargateDelivery.exe >nul 2>&1
timeout /t 1 /nobreak >nul

echo [2/3] جاري تنفيذ ضبط المصنع والتصفير الكامل 100%%...
python "%~dp0direct_wipe_tool.py" all
goto finish

:finish
echo.
echo [3/3] اكتملت العملية بنجاح.
echo =========================================================================
echo تم تصفير البيانات بنجاح تام! يمكنك الآن فتح البرنامج من جديد.
echo =========================================================================
echo.
pause
exit /b

:invalid_choice
echo خيار غير صحيح، يرجى إعادة التشغيل واختيار 1 أو 2.
pause
exit /b
