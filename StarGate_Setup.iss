; =====================================================================
; Stargate Delivery System - Inno Setup 7 Script
; Version 4.3.0 - Final Comprehensive Fix
; =====================================================================

#define MyAppName      "Stargate Delivery"
#define MyAppVersion   "4.3.0"
#define MyAppPublisher "Stargate Tech"
#define MyAppURL       "https://github.com/mouhamadherzherz/stargate-delivery-"
#define MyAppExeName   "StargateDelivery.exe"
#define MyDistDir      "dist\StargateDelivery"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName=C:\StargateDelivery
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=.\installer_output
OutputBaseFilename=StargateDelivery_Setup_v{#MyAppVersion}
SetupIconFile=static\icons\stargate_logo.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
DisableDirPage=no
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
CloseApplications=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} v{#MyAppVersion}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Stargate Delivery Management System
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}.0
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startupicon"; Description: "Run at Windows startup"; GroupDescription: "Auto-start:"

[Dirs]
Name: "{app}\data";         Permissions: users-full; Flags: uninsneveruninstall
Name: "{app}\Backups_Safe"; Permissions: users-full; Flags: uninsneveruninstall
Name: "{app}\db_backups";   Permissions: users-full; Flags: uninsneveruninstall
Name: "{app}\logs";         Permissions: users-full; Flags: uninsneveruninstall

[Files]
; Full application (exe + _internal libraries)
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Empty DB - only installed if no existing database (protects subscriber data)
Source: "{#MyDistDir}\stargate_empty.db"; DestDir: "{app}\data"; DestName: "stargate_production.db"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{userdesktop}\{#MyAppName}";       Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\stargate_logo.ico"
Name: "{group}\{#MyAppName}";             Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\stargate_logo.ico"
Name: "{group}\Uninstall {#MyAppName}";   Filename: "{uninstallexe}"
Name: "{userstartup}\{#MyAppName}";       Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startupicon

[Registry]
Root: HKLM; Subkey: "SOFTWARE\StargateDelivery"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Stargate Delivery now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\update_temp"
Type: files;          Name: "{app}\*.log"

[Code]
// Automatic safe backup of database before upgrade
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDb, BackupDb, AppDir, BackupDir: String;
begin
  if CurStep = ssInstall then
  begin
    AppDir    := ExpandConstant('{app}');
    DataDb    := AppDir + '\data\stargate_production.db';
    BackupDir := AppDir + '\Backups_Safe';
    BackupDb  := BackupDir + '\stargate_backup_before_v4.3.0.db';
    if FileExists(DataDb) then
    begin
      ForceDirectories(BackupDir);
      FileCopy(DataDb, BackupDb, False);
      Log('Safe backup created: ' + BackupDb);
    end;
  end;
end;

// Welcome dialog
function InitializeSetup(): Boolean;
begin
  Result := True;
  if MsgBox(
    'Stargate Delivery v4.3.0 - Installer' + #13#10 + #13#10 +
    '- All 28 pages fully tested and working' + #13#10 +
    '- Your data and password will be preserved' + #13#10 +
    '- Automatic database backup before install' + #13#10 + #13#10 +
    'Proceed with installation?',
    mbConfirmation, MB_YESNO) = IDNO then
    Result := False;
end;