; =====================================================================
; Stargate Delivery System - Inno Setup Script
; يُنشئ برنامج تثبيت رسمي لنظام ويندوز
; =====================================================================

#define MyAppName "Stargate Delivery System"
#define MyAppVersion "2.0"
#define MyAppPublisher "Stargate Tech"
#define MyAppExeName "StargateDelivery.exe"
#define MyInstallDir "C:\StargateDelivery"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={#MyInstallDir}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=.\installer_output
OutputBaseFilename=StargateDelivery_Setup_v{#MyAppVersion}
SetupIconFile=static\icons\stargate_logo.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableDirPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "arabic"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "إنشاء اختصار على سطح المكتب"; GroupDescription: "اختصارات:"; Flags: checked
Name: "startmenuicon"; Description: "إنشاء اختصار في قائمة ابدأ"; GroupDescription: "اختصارات:"; Flags: checked

[Dirs]
; إنشاء مجلد البيانات بشكل آمن - لن يُحذف أو يُستبدل عند التحديث
Name: "{#MyInstallDir}\data"; Flags: uninsneveruninstall

[Files]
; نسخ الملف التنفيذي والملفات المساعدة
Source: "dist\StargateDelivery.exe"; DestDir: "{#MyInstallDir}"; Flags: ignoreversion
Source: "static\*"; DestDir: "{#MyInstallDir}\static"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "templates\*"; DestDir: "{#MyInstallDir}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs

; قاعدة البيانات: لا تُنسخ إذا كانت موجودة مسبقاً (حماية البيانات عند التحديث)
Source: "data\stargate_production.db"; DestDir: "{#MyInstallDir}\data"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
; اختصار سطح المكتب
Name: "{userdesktop}\{#MyAppName}"; Filename: "{#MyInstallDir}\{#MyAppExeName}"; IconFilename: "{#MyInstallDir}\static\icons\stargate_logo.ico"; Tasks: desktopicon
; اختصار قائمة ابدأ
Name: "{group}\{#MyAppName}"; Filename: "{#MyInstallDir}\{#MyAppExeName}"; IconFilename: "{#MyInstallDir}\static\icons\stargate_logo.ico"; Tasks: startmenuicon
Name: "{group}\إلغاء التثبيت"; Filename: "{uninstallexe}"

[Run]
; تشغيل البرنامج مباشرة بعد التثبيت (اختياري)
Filename: "{#MyInstallDir}\{#MyAppExeName}"; Description: "تشغيل Stargate الآن"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; حذف الملفات المؤقتة عند إلغاء التثبيت (مع الحفاظ على مجلد data)
Type: filesandordirs; Name: "{#MyInstallDir}\__pycache__"
Type: filesandordirs; Name: "{#MyInstallDir}\*.log"

[Code]
// التحقق من عدم تشغيل البرنامج أثناء التثبيت
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then begin
    // إنشاء مجلد البيانات إذا لم يكن موجوداً
    ForceDirectories(ExpandConstant('{#MyInstallDir}\data'));
  end;
end;
