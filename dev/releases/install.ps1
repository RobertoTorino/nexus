# SPDX-License-Identifier: GPL-3.0-or-later
# Installs Nexus Releases on Windows for the current user: a Start-menu entry and a Desktop shortcut that start
# run.ps1 in this checkout, as install.sh does on Linux. Nothing is copied: the app edits the checkout it lives in,
# so it always runs the checkout's own code. Moving the checkout needs install.ps1 again.
#
#   powershell -ExecutionPolicy Bypass -File dev\releases\install.ps1                          # Start menu and Desktop
#   powershell -ExecutionPolicy Bypass -File dev\releases\install.ps1 --no-desktop-shortcut    # Start-menu entry only
#   powershell -ExecutionPolicy Bypass -File dev\releases\install.ps1 --uninstall              # remove them; the checkout and the settings stay
#   powershell -ExecutionPolicy Bypass -File dev\releases\install.ps1 --uninstall --purge      # also remove the settings
#
# Run it as your own user, not as administrator. The shortcuts start run.ps1 in a hidden PowerShell window, with
# the icon written to %LOCALAPPDATA%\nexus-releases. The settings are in %APPDATA%\nexus-releases.
# WPS_DESKTOP_DIR and WPS_ELEVATED stand in for the Desktop folder and the administrator check in the installer
# test (windows-portable/tools/installer-tests/releases.ps1).
$ErrorActionPreference = 'Stop'

$AppId = 'nexus-releases'
$AppName = 'Nexus Releases'
$App = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $App '..\..')).Path
$DataDir = Join-Path $env:LOCALAPPDATA $AppId
$ConfigDir = Join-Path $env:APPDATA $AppId
$Icon = Join-Path $DataDir "$AppId.ico"
$MenuEntry = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName.lnk"
if ($env:WPS_DESKTOP_DIR) { $DesktopDir = $env:WPS_DESKTOP_DIR } else { $DesktopDir = [Environment]::GetFolderPath('Desktop') }
$DesktopIcon = Join-Path $DesktopDir "$AppName.lnk"

function Info($text) { Write-Host '==> ' -ForegroundColor Magenta -NoNewline; Write-Host $text }
function Die($text) { Write-Host "ERROR: $text" -ForegroundColor Red; exit 1 }
function Usage { Get-Content -LiteralPath $PSCommandPath | Select-Object -Skip 1 -First 8 | ForEach-Object { $_ -replace '^# ?', '' } }

function Elevated {
    if ($env:WPS_ELEVATED) { return $env:WPS_ELEVATED -eq '1' }
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Remove-IfThere($path) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}

# A .lnk takes its icon from an .ico: one that holds the app's 128 px PNG as it is (Windows reads PNG in an .ico).
function Write-Icon($png, $ico) {
    $bytes = [IO.File]::ReadAllBytes($png)
    $stream = New-Object IO.MemoryStream
    $writer = New-Object IO.BinaryWriter($stream)
    $writer.Write([UInt16]0); $writer.Write([UInt16]1); $writer.Write([UInt16]1)      # an icon with one image
    $writer.Write([Byte]128); $writer.Write([Byte]128); $writer.Write([Byte]0); $writer.Write([Byte]0)
    $writer.Write([UInt16]1); $writer.Write([UInt16]32); $writer.Write([UInt32]$bytes.Length); $writer.Write([UInt32]22)
    $writer.Write($bytes)
    $writer.Flush()
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ico) | Out-Null
    [IO.File]::WriteAllBytes($ico, $stream.ToArray())
}

function New-Shortcut($link) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $link) | Out-Null
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
    $shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $App 'run.ps1')`""
    $shortcut.WorkingDirectory = $App
    $shortcut.WindowStyle = 7                                   # minimized: no console shows while it starts
    $shortcut.IconLocation = "$Icon,0"
    $shortcut.Description = "Versions, CHANGELOG entries, pins and portal bumps of a suite release ($Repo)"
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
        default { Die "Unknown option: $arg (use --help)." }
    }
}
if ($Purge -and -not $Uninstall) { Die '--purge only goes with --uninstall.' }

if (Elevated) { Die 'Run this as your own user, not as administrator.' }

if ($Uninstall) {
    Info 'Removing the Start-menu entry, the Desktop shortcut and the icon'
    Remove-IfThere $MenuEntry
    Remove-IfThere $DesktopIcon
    Remove-IfThere $DataDir
    if ($Purge) {
        Info 'Removing the settings'
        Remove-IfThere $ConfigDir
        Info "$AppName is uninstalled; the checkout stays."
    } else {
        Info "$AppName is uninstalled; the checkout and its settings stay."
    }
    exit 0
}

if (-not (Test-Path -LiteralPath (Join-Path $Repo '.venv-windows\Scripts\python.exe'))) {
    Info 'Note: no .venv-windows yet; create it (see CLAUDE.md) before you start the app.'
}

Write-Icon (Join-Path $App "images\$AppId-128.png") $Icon
Info 'Adding the Start-menu entry'
New-Shortcut $MenuEntry
if ($DesktopShortcut) {
    Info 'Adding the Desktop shortcut'
    New-Shortcut $DesktopIcon
} else {
    Remove-IfThere $DesktopIcon
}
Info "Done. Start `"$AppName`" from the Start menu$(if ($DesktopShortcut) { ' or the Desktop' }), or run dev\releases\run.ps1"
