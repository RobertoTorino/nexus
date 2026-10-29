# SPDX-License-Identifier: GPL-3.0-or-later
# Installs shadPS4 Manager from the extracted release (wp-shadps4-v<x.y.z>.zip):
#
#   powershell -ExecutionPolicy Bypass -File install.ps1                          # install or update
#   powershell -ExecutionPolicy Bypass -File install.ps1 --no-desktop-shortcut    # Start-menu entry only
#   powershell -ExecutionPolicy Bypass -File install.ps1 --uninstall              # remove the app; keeps settings, log and shadPS4
#   powershell -ExecutionPolicy Bypass -File install.ps1 --uninstall --purge      # also remove its settings, log and shadPS4
#
# Run it as your own user, not as administrator: everything goes in your own folders.
#  * %LOCALAPPDATA%\windows-portable-suite\windows-portable-shadps4\app: the program (shadPS4-Manager.exe with the Python, Qt and bc250_core it was
#    tested with), its LICENSE and THIRD-PARTY-NOTICES.txt.
#  * %LOCALAPPDATA%\windows-portable-suite\windows-portable-shadps4: the log, and emulator\ with shadPS4 the app installs
#    (shadPS4 keeps its settings, the saves and the system modules in user\ beside its program).
#  * %APPDATA%\windows-portable-suite\windows-portable-shadps4.ini: the settings.
#  * A Start-menu entry in the Windows Portable Suite folder, and a Desktop shortcut.
# WPS_DESKTOP_DIR and WPS_ELEVATED stand in for the Desktop folder and the administrator check in the installer
# tests (windows-portable/tools/installer-tests/shadps4.ps1).
$ErrorActionPreference = 'Stop'

$AppId = 'windows-portable-shadps4'
$AppName = 'shadPS4 Manager'
$Exe = 'shadPS4-Manager.exe'
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

function Install-Folder($new, $dir, $name) {
    # $new in the place of $dir, deleting nothing of $dir until $new is in place: a folder a process uses as its
    # working directory cannot be removed or renamed, so then its contents move instead, and the folder stays.
    $running = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith("$dir\", [StringComparison]::OrdinalIgnoreCase) }
    if ($running) { Remove-IfThere $new; Die "$dir could not be replaced: close $name first." }
    $old = "$dir.old"
    try { Remove-IfThere $old } catch { $old = "$dir.old-" + [guid]::NewGuid().ToString('N').Substring(0, 8) }
    if (Test-Path -LiteralPath $dir) {
        try {
            Rename-Item -LiteralPath $dir -NewName (Split-Path -Leaf $old) -ErrorAction Stop
        } catch {
            New-Item -ItemType Directory -Force -Path $old | Out-Null
            $moved = @()
            try {
                foreach ($item in Get-ChildItem -LiteralPath $dir -Force) {
                    Move-Item -LiteralPath $item.FullName -Destination $old -ErrorAction Stop
                    $moved += $item.Name
                }
            } catch {
                foreach ($item in $moved) { Move-Item -LiteralPath (Join-Path $old $item) -Destination $dir }
                Remove-IfThere $new
                Die "$dir could not be replaced: close $name first. ($_)"
            }
            foreach ($item in Get-ChildItem -LiteralPath $new -Force) {
                Move-Item -LiteralPath $item.FullName -Destination $dir
            }
            Remove-IfThere $new
            try { Remove-IfThere $old } catch { }
            return
        }
    }
    Rename-Item -LiteralPath $new -NewName (Split-Path -Leaf $dir)
    try { Remove-IfThere $old } catch { }
}

function Remove-Download {
    # After an install from a download: the zip, its SHA256SUMS and the unpacked folder, on a yes. Not asked when
    # the portal runs the installer (its releases are in the suite's folder), or when nobody can answer;
    # WPS_REMOVE_DOWNLOAD (y or n) answers in the installer tests.
    $suiteData = Join-Path $env:LOCALAPPDATA "$Suite\"
    if ($Src.StartsWith($suiteData, [StringComparison]::OrdinalIgnoreCase)) { return }
    $tag = Split-Path -Leaf $Src
    $downloads = Split-Path -Parent $Src
    $zip = Join-Path $downloads "$tag.zip"
    if (-not (Test-Path -LiteralPath $zip)) { return }
    $sums = @(Get-ChildItem -LiteralPath $downloads -File -Filter 'SHA256SUMS*' |
        Where-Object { (Get-Content -Raw -LiteralPath $_.FullName) -match "\s\*?$([regex]::Escape("$tag.zip"))\s*$" })
    $answer = $env:WPS_REMOVE_DOWNLOAD
    if (-not $answer) {
        if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) { return }
        $names = (@("$tag.zip") + ($sums | ForEach-Object { $_.Name }) + @("$tag\")) -join ', '
        $answer = Read-Host "Remove the download from $downloads ($names)? [Y/n]"
    }
    if ($answer -and $answer -notmatch '^\s*y') { Info "Keeping the download in $downloads"; return }
    Set-Location -LiteralPath $downloads
    [Environment]::CurrentDirectory = $downloads           # out of the unpacked folder, so it can go
    Remove-IfThere $zip
    foreach ($file in $sums) { Remove-IfThere $file.FullName }
    try {
        Remove-IfThere $Src
        Info 'Removed the download'
    } catch {
        Info "Removed the zip and SHA256SUMS; remove $Src yourself once no window is in it"
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
        Info 'Removing the settings, the log and shadPS4 with its settings, saves and system modules'
        Remove-IfThere $Settings
        Remove-IfThere $AppHome
        Remove-IfEmpty (Split-Path -Parent $Settings)
    } else {
        Info "Keeping your settings in $Settings, and the log and shadPS4 in $AppHome"
        Remove-IfEmpty $AppHome
    }
    Remove-IfEmpty (Split-Path -Parent $AppHome)
    Info "$AppName is uninstalled."
    exit 0
}

# --- Checks ------------------------------------------------------------------------------------
$Program = Join-Path $Src 'program'
if (-not (Test-Path -LiteralPath (Join-Path $Program $Exe))) {
    Die ("No program\$Exe beside install.ps1: this installs a release (wp-shadps4-v<x.y.z>.zip, unpacked). From the " +
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
Install-Folder $New $AppDir $AppName

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
Remove-Download
