param()

$ErrorActionPreference = "SilentlyContinue"

# Check administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# Resolve USB source root: the parent of _internal
$InternalDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CurrentDir = Split-Path -Parent $InternalDir
$InstallDir = "C:\StargateDelivery"

Write-Host "=========================================================================" -ForegroundColor Cyan
Write-Host "    STARGATE DELIVERY EXPERTS - AUTO UPGRADE & SMART DATA SYNC" -ForegroundColor Yellow
Write-Host "=========================================================================" -ForegroundColor Cyan

# 1. Kill old processes
Write-Host "[1/6] Stopping old system processes..." -ForegroundColor Gray
Stop-Process -Name "StargateDelivery", "Stargate_Delivery", "python" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# 2. Setup install directory
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

# 3. Smart database sync
Write-Host "[2/6] Smart syncing database and preserving employee data..." -ForegroundColor Green
$usbDb = Join-Path $CurrentDir "delivery.db"
$installedDb = Join-Path $InstallDir "delivery.db"
$syncExe = Join-Path $InternalDir "sync_db.exe"

if (Test-Path $installedDb) {
    if (Test-Path $syncExe) {
        & $syncExe $usbDb $installedDb
    }
} else {
    Copy-Item $usbDb $installedDb -Force
}

# 4. Clean old templates and scripts causing legacy views
Write-Host "[3/6] Cleaning outdated legacy files and templates causing old views..." -ForegroundColor Gray
Remove-Item (Join-Path $InstallDir "templates") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $InstallDir "static") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $InstallDir "app.py") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $InstallDir "Stargate_Delivery.exe") -Force -ErrorAction SilentlyContinue

# 5. Copy new release files
Write-Host "[4/6] Copying all new release system files from USB..." -ForegroundColor Green
robocopy "$CurrentDir" "$InstallDir" /E /IS /IT /XF "delivery.db" "*.ps1" /NJH /NJS /NFL /NDL | Out-Null

# 6. Shortcuts
Write-Host "[5/6] Updating desktop and startup shortcuts..." -ForegroundColor Gray
Remove-Item "C:\Users\*\Desktop\Stargate*.lnk" -Force -ErrorAction SilentlyContinue
Remove-Item "C:\Users\Public\Desktop\Stargate*.lnk" -Force -ErrorAction SilentlyContinue

$wsh = New-Object -ComObject WScript.Shell
$desktopLnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Stargate Delivery.lnk"
$sc = $wsh.CreateShortcut($desktopLnk)
$sc.TargetPath = Join-Path $InstallDir "StargateDelivery.exe"
$sc.WorkingDirectory = $InstallDir
$sc.Description = "Stargate Delivery System"
$sc.Save()

$startupFolder = [Environment]::GetFolderPath("Startup")
$startupLnk = Join-Path $startupFolder "Stargate Delivery.lnk"
$sc2 = $wsh.CreateShortcut($startupLnk)
$sc2.TargetPath = Join-Path $InstallDir "StargateDelivery.exe"
$sc2.WorkingDirectory = $InstallDir
$sc2.Save()

# 7. Start application
Write-Host "[6/6] Launching Stargate Delivery..." -ForegroundColor Cyan
Start-Process -FilePath (Join-Path $InstallDir "StargateDelivery.exe") -WorkingDirectory $InstallDir

Write-Host "=========================================================================" -ForegroundColor Green
Write-Host " [SUCCESS] System updated and all data synchronized successfully!" -ForegroundColor Green
Write-Host "=========================================================================" -ForegroundColor Green
Start-Sleep -Seconds 3
