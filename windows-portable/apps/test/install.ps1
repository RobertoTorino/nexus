# SPDX-License-Identifier: GPL-3.0-or-later
# Installs Windows Portable Test from the extracted release (wp-test-v<x.y.z>.zip):
#
#   powershell -ExecutionPolicy Bypass -File install.ps1                          # install or update
#   powershell -ExecutionPolicy Bypass -File install.ps1 --no-desktop-shortcut    # Start-menu entry only
#   powershell -ExecutionPolicy Bypass -File install.ps1 --uninstall              # remove the app; keeps settings, log and reports
#   powershell -ExecutionPolicy Bypass -File install.ps1 --uninstall --purge      # also remove its settings, log and reports
#
# Run it as your own user, not as administrator: everything goes in your own folders.
#  * %LOCALAPPDATA%\windows-portable-suite\windows-portable-test\app: the program (Windows-Portable-Test.exe with
#    the Python, Qt and bc250_core it was tested with), its LICENSE and THIRD-PARTY-NOTICES.txt.
#  * %LOCALAPPDATA%\windows-portable-suite\windows-portable-test: the log, and reports\ with the saved device reports.
#  * %APPDATA%\windows-portable-suite\windows-portable-test.ini: the settings.
#  * A Start-menu entry in the Windows Portable Suite folder, and a Desktop shortcut.
# WPS_DESKTOP_DIR and WPS_ELEVATED stand in for the Desktop folder and the administrator check in the installer
# tests (windows-portable/tools/installer-tests/test.ps1).
$ErrorActionPreference = 'Stop'

$AppId = 'windows-portable-test'
$AppName = 'Windows Portable Test'
$Exe = 'Windows-Portable-Test.exe'
$Suite = 'windows-portable-suite'
$SuiteName = 'Windows Portable Suite'
$AppHome = Join-Path $env:LOCALAPPDATA "$Suite\$AppId"
$AppDir = Join-Path $AppHome 'app'
$Settings = Join-Path $env:APPDATA "$Suite\$AppId.ini"
$MenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$SuiteName"
$MenuEntry = Join-Path $MenuDir "$AppName.lnk"
if ($env:WPS_DESKTOP_DIR) { $DesktopDir = $env:WPS_DESKTOP_DIR } else { $DesktopDir = [Environment]::GetFolderPath('Desktop') }
$DesktopIcon = Join-Path $DesktopDir "$AppName.lnk"
$Src = $PSScriptRoot

function Info($text) { Write-Host '==> ' -ForegroundColor Magenta -NoNewline; Write-Host $text }
function Die($text) { Write-Host "ERROR: $text" -ForegroundColor Red; exit 1 }
function Usage { Get-Content -LiteralPath $PSCommandPath | Select-Object -Skip 1 -First 6 | ForEach-Object { $_ -replace '^# ?', '' } }

function Elevated {
    if ($env:WPS_ELEVATED) { return $env:WPS_ELEVATED -eq '1' }
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Remove-IfThere($path) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}

function Remove-IfEmpty($folder) {
    if ((Test-Path -LiteralPath $folder) -and -not (Get-ChildItem -LiteralPath $folder -Force)) {
        Remove-Item -LiteralPath $folder -Force
    }
}

function New-Shortcut($link, $target) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $link) | Out-Null
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = Split-Path -Parent $target
    $shortcut.IconLocation = "$target,0"
    $shortcut.Description = $AppName
    $shortcut.Save()
}

$DesktopShortcut = $true
$Uninstall = $false
$Purge = $false
foreach ($arg in $args) {
    switch -CaseSensitive ($arg) {
        '--no-desktop-shortcut' { $DesktopShortcut = $false }
        '--uninstall' { $Uninstall = $true }
        '--purge' { $Purge = $true }
        { $_ -in '-h', '--help' } { Usage; exit 0 }
        default { Usage | Write-Host; Die "Unknown option: $arg" }
    }
}
if ($Purge -and -not $Uninstall) { Die '--purge only goes with --uninstall.' }

if (Elevated) { Die "Run this as your own user, not as administrator: the app and its shortcuts belong in your own folders." }

if ($Uninstall) {
    Info 'Removing the Start-menu entry, the Desktop shortcut and the app'
    Remove-IfThere $MenuEntry
    Remove-IfThere $DesktopIcon
    Remove-IfEmpty $MenuDir
    try { Remove-IfThere $AppDir } catch { Die "$AppDir could not be removed: close $AppName first. ($_)" }
    if ($Purge) {
        Info 'Removing the settings, the log and the reports'
        Remove-IfThere $Settings
        Remove-IfThere $AppHome
        Remove-IfEmpty (Split-Path -Parent $Settings)
    } else {
        Info "Keeping your settings in $Settings and the log and reports in $AppHome"
        Remove-IfEmpty $AppHome
    }
    Remove-IfEmpty (Split-Path -Parent $AppHome)
    Info "$AppName is uninstalled."
    exit 0
}

# --- Checks ------------------------------------------------------------------------------------
$Program = Join-Path $Src 'program'
if (-not (Test-Path -LiteralPath (Join-Path $Program $Exe))) {
    Die ("No program\$Exe beside install.ps1: this installs a release (wp-test-v<x.y.z>.zip, unpacked). From the " +
         'checkout, start the app with run.ps1, or build a release with tools/build_release.py.')
}

# --- The app -----------------------------------------------------------------------------------
Info "Installing $AppName in $AppDir"
$New = "$AppDir.new"
Remove-IfThere $New
New-Item -ItemType Directory -Force -Path $New | Out-Null
Copy-Item -Path (Join-Path $Program '*') -Destination $New -Recurse -Force
foreach ($file in 'LICENSE', 'THIRD-PARTY-NOTICES.txt', 'MANUAL.md') {
    if (Test-Path -LiteralPath (Join-Path $Src $file)) { Copy-Item -LiteralPath (Join-Path $Src $file) -Destination $New }
}
try { Remove-IfThere $AppDir } catch { Remove-IfThere $New; Die "$AppDir could not be replaced: close $AppName first. ($_)" }
Rename-Item -LiteralPath $New -NewName 'app'

# --- Shortcuts ---------------------------------------------------------------------------------
$Target = Join-Path $AppDir $Exe
Info "Adding $AppName to the Start menu ($SuiteName)"
New-Shortcut $MenuEntry $Target
if ($DesktopShortcut) {
    Info 'Adding a Desktop shortcut'
    New-Shortcut $DesktopIcon $Target
} else {
    Remove-IfThere $DesktopIcon
}
Info "$AppName is installed. Start it from the Start menu, or run $Target"
