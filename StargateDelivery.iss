#define MyAppName "Stargate Delivery"
#define MyAppVersion "8.0.0"
#define MyAppPublisher "Stargate"
#define MyAppExeName "StargateDelivery.exe"

[Setup]
AppId={{D8D68E2A-6F4C-4DF0-AE65-7B3CBF8A4D55}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Stargate Delivery
DefaultGroupName={#MyAppName}
OutputDir=installer
OutputBaseFilename=StargateDelivery-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
SetupIconFile=static\icons\stargate_logo.ico

[Files]
Source: "dist\StargateDelivery.exe"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\data"

[Icons]
Name: "{autodesktop}\Stargate Delivery"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Stargate Delivery"; Filename: "{app}\{#MyAppExeName}"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
; لا تحذف مجلد data عند إزالة التثبيت للحفاظ على بيانات المستخدم.
