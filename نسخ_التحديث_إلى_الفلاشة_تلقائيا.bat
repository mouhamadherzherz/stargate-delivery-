@echo off
chcp 65001 >nul
title أداة النسخ التلقائي للتحديث إلى الفلاشة USB
color 0b

echo =========================================================================
echo       STARGATE ENTERPRISE - أداة نسخ التحديث V3.5 إلى الفلاشة
echo =========================================================================
echo.
echo يرجى التأكد من إدخال الفلاشة (USB) في هذا الكمبيوتر...
echo.

set "TARGET_DRIVE="
for %%D in (F E G H I J K D) do (
    if exist "%%D:\Stargate Delivery System" (
        set "TARGET_DRIVE=%%D:"
        goto :found
    )
)

:: If not found by folder, look for drive with label or prompt
for %%D in (F E H I J K) do (
    if exist "%%D:\" (
        set "TARGET_DRIVE=%%D:"
        goto :found
    )
)

:not_found
echo [!] لم يتم العثور على الفلاشة تلقائياً!
echo     يرجى إدخال الفلاشة في مدخل USB والضغط على أي زر لإعادة المحاولة...
pause
goto :check_again

:check_again
for %%D in (F E G H I J K) do (
    if exist "%%D:\" (
        set "TARGET_DRIVE=%%D:"
        goto :found
    )
)
echo [!] لم يتم اكتشاف الفلاشة. يرجى التأكد من توصيلها.
pause
exit /b

:found
echo [+] تم اكتشاف الفلاشة بنجاح في المحرك: %TARGET_DRIVE%
echo.
echo جاري نسخ ملف التثبيت المحدث V3.5...
copy /y "%~dp0StargateDelivery_Setup_v3.5.exe" "%TARGET_DRIVE%\" >nul
copy /y "%~dp0تحديث_شامل_وفوري_للبرنامج.bat" "%TARGET_DRIVE%\" >nul
copy /y "%~dp0تحديث_شامل_وفوري_للبرنامج.bat" "%TARGET_DRIVE%\تحديث_البرنامج_على_هذا_الكمبيوتر.bat" >nul
copy /y "%~dp0Stargate_Update.zip" "%TARGET_DRIVE%\" >nul 2>&1

if exist "%TARGET_DRIVE%\Stargate Delivery System" (
    echo جاري مزامنة ملفات البرنامج في المجلد...
    robocopy "d:\STARGATE\repo\dist\StargateDelivery" "%TARGET_DRIVE%\Stargate Delivery System" /E /NFL /NDL /NP >nul 2>&1
    copy /y "d:\STARGATE\repo\dist\StargateDelivery\StargateDelivery.exe" "%TARGET_DRIVE%\Stargate Delivery System\" >nul
)

echo.
color 0a
echo =========================================================================
echo        🎉 تم نسخ التحديث الشامل V3.5 إلى الفلاشة بنجاح تام!
echo =========================================================================
echo يمكنك الآن أخذ الفلاشة إلى كمبيوتر الموظف وتشغيل:
echo %TARGET_DRIVE%\StargateDelivery_Setup_v3.5.exe
echo أو الضغط على: %TARGET_DRIVE%\تحديث_شامل_وفوري_للبرنامج.bat
echo =========================================================================
pause
exit
