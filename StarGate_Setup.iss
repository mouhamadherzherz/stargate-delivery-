; =====================================================================
; Stargate Delivery System - Inno Setup 7 Script
; =====================================================================

#define MyAppName      "Stargate Delivery System"
#define MyAppVersion   "4.2.0"
#define MyAppPublisher "Stargate Tech"
#define MyAppExeName   "StargateDelivery.exe"
#define MyDistDir      "dist\StargateDelivery"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\StargateDelivery
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=.\installer_output
OutputBaseFilename=StargateDelivery_Setup_v{#MyAppVersion}
SetupIconFile=static\icons\stargate_logo.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableDirPage=no
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startupicon"; Description: "Run at Windows startup"; GroupDescription: "Auto-start:"

[Dirs]
Name: "{app}\data";         Permissions: users-full; Flags: uninsneveruninstall
Name: "{app}\Backups_Safe"; Permissions: users-full; Flags: uninsneveruninstall
Name: "{app}\db_backups";   Permissions: users-full; Flags: uninsneveruninstall

[Files]
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "data\stargate_empty.db"; DestDir: "{app}\data"; DestName: "stargate_production.db"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\{#MyAppName}";       Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startupicon

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\update_temp"
Type: files;          Name: "{app}\*.log"

[Code]
// Guarantee user data and password preservation
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDb, BackupDb, AppDir, BackupDir: String;
begin
  if CurStep = ssInstall then
  begin
    AppDir := ExpandConstant('{app}');
    DataDb := AppDir + '\data\stargate_production.db';
    BackupDir := AppDir + '\Backups_Safe';
    BackupDb := BackupDir + '\stargate_backup_before_v4.2.0.db';
    
    // Automatically save a safeguard copy of existing database
    if FileExists(DataDb) then
    begin
      ForceDirectories(BackupDir);
      FileCopy(DataDb, BackupDb, False);
    end;
  end;
end;