# SPDX-License-Identifier: GPL-3.0-or-later
# Installs the Windows Portable Suite's portal and Windows Portable Test, from the extracted portal release
# (wp-portal-v<x.y.z>.zip):
#
#   powershell -ExecutionPolicy Bypass -File install.ps1                          # install or update
#   powershell -ExecutionPolicy Bypass -File install.ps1 --no-desktop-shortcut    # the Start-menu entry only
#   powershell -ExecutionPolicy Bypass -File install.ps1 --xbox-menu              # also into the Xbox menu, unasked
#   powershell -ExecutionPolicy Bypass -File install.ps1 --no-xbox-menu           # not into the Xbox menu, unasked
#   powershell -ExecutionPolicy Bypass -File install.ps1 --uninstall              # remove the portal and Windows Portable Test; the other apps stay
#   powershell -ExecutionPolicy Bypass -File install.ps1 --uninstall --all        # the whole suite: every app the portal installed too
#   powershell -ExecutionPolicy Bypass -File install.ps1 --uninstall --purge      # also remove the settings, the log and the records
#
# Run it as your own user, not as administrator: everything goes in your own folders.
#  * %LOCALAPPDATA%\windows-portable-suite\portal\app: the program (Windows-Portable-Suite.exe with the Python, Qt
#    and bc250_core it was tested with), its LICENSE and THIRD-PARTY-NOTICES.txt.
#  * %LOCALAPPDATA%\windows-portable-suite\portal: installed.json (which release of each app the portal
#    installed), releases\<tag>\ (the extracted releases the apps were installed from, kept for their uninstallers)
#    and portal.log.
#  * %APPDATA%\windows-portable-suite\portal.ini: the settings.
#  * A Start-menu entry in the Windows Portable Suite folder, and a Desktop shortcut.
#  * Windows Portable Test, which the suite always includes, from bundle\wp-test-v<x.y.z>.zip through its own
#    installer (checked against bundle\SHA256SUMS), with its Start-menu entry and no Desktop shortcut: it is in the
#    portal. The other apps are installed from the portal, the same way.
# WPS_DESKTOP_DIR and WPS_ELEVATED stand in for the Desktop folder and the administrator check in the installer
# tests (windows-portable/tools/installer-tests/portal.ps1).
$ErrorActionPreference = 'Stop'

$AppName = 'Windows Portable Suite'
$Exe = 'Windows-Portable-Suite.exe'
$Suite = 'windows-portable-suite'
$SuiteName = 'Windows Portable Suite'
$TestId = 'windows-portable-test'
$TestName = 'Windows Portable Test'
$SuiteHome = Join-Path $env:LOCALAPPDATA $Suite
$PortalHome = Join-Path $SuiteHome 'portal'
$AppDir = Join-Path $PortalHome 'app'
$Releases = Join-Path $PortalHome 'releases'
$RecordsFile = Join-Path $PortalHome 'installed.json'
$Settings = Join-Path $env:APPDATA "$Suite\portal.ini"
$MenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$SuiteName"
$MenuEntry = Join-Path $MenuDir "$AppName.lnk"
if ($env:WPS_DESKTOP_DIR) { $DesktopDir = $env:WPS_DESKTOP_DIR } else { $DesktopDir = [Environment]::GetFolderPath('Desktop') }
$DesktopIcon = Join-Path $DesktopDir "$AppName.lnk"
$Src = $PSScriptRoot

function Info($text) { Write-Host '==> ' -ForegroundColor Magenta -NoNewline; Write-Host $text }
function Die($text) { Write-Host "ERROR: $text" -ForegroundColor Red; exit 1 }
function Usage { Get-Content -LiteralPath $PSCommandPath | Select-Object -Skip 1 -First 10 | ForEach-Object { $_ -replace '^# ?', '' } }

function Add-ToXboxMenu($program) {
    # The suite in the Xbox app's library, so Xbox mode starts it from its home (owner, 30-10-2026): asked on a
    # first install (an update keeps what was chosen; the Suite page adds it any time), --xbox-menu and
    # --no-xbox-menu answer without the question, WPS_XBOX_MENU (y or n) in the installer tests. The portal itself
    # writes it (--xbox-menu, core's xbox.py): the Xbox app closes for a moment.
    if ($XboxMenu -eq $false) { return }
    if (-not (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.GamingApp_8wekyb3d8bbwe'))) { return }
    if ($XboxMenu -ne $true) {
        if (-not $FirstInstall) { return }
        $answer = $env:WPS_XBOX_MENU
        if (-not $answer) {
            if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) { return }
            $answer = Read-Host "Add $AppName to the Xbox menu, so Xbox mode starts it from its home? The Xbox app closes for a moment. [Y/n]"
        }
        if ($answer -and $answer -notmatch '^\s*y') { Info 'Not added to the Xbox menu (the Suite page adds it any time)'; return }
    }
    Info "Adding $AppName to the Xbox menu"
    try { $run = Start-Process -FilePath $program -ArgumentList '--xbox-menu' -Wait -PassThru -WindowStyle Hidden }
    catch { Info "Not added to the Xbox menu: $_ (the Suite page tries again)"; return }
    if ($run.ExitCode -eq 0) { Info "$AppName is in the Xbox menu" }
    else { Info "Not added to the Xbox menu: $PortalHome\portal.log says why (the Suite page tries again)" }
}

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
    # working directory (the window an older portal's update ran in) cannot be removed or renamed, and removing
    # it deleted the program and then failed. Then its contents move instead, and the folder stays.
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
    # After an install from a download (owner, 28-10-2026): the zip, its SHA256SUMS and the unpacked folder, on a
    # yes. A second download would otherwise be saved as "SHA256SUMS (1)" beside the old one, and the check read the
    # old one. Not asked when the portal runs the installer (its releases are in the suite's folder), or when nobody
    # can answer; WPS_REMOVE_DOWNLOAD (y or n) answers in the installer tests.
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

# installed.json: which release of each app the portal installed (portable_portal/sources.py reads it). Written
# without a byte order mark, as the portal's Python reads it.
function Read-Records {
    $records = @{}
    if (Test-Path -LiteralPath $RecordsFile) {
        try {
            $data = Get-Content -Raw -LiteralPath $RecordsFile | ConvertFrom-Json
            foreach ($property in $data.PSObject.Properties) { $records[$property.Name] = [string]$property.Value }
        } catch { }
    }
    return $records
}
function Write-Records($records) {
    New-Item -ItemType Directory -Force -Path $PortalHome | Out-Null
    $json = if ($records.Count) { $records | ConvertTo-Json } else { '{}' }
    [IO.File]::WriteAllText($RecordsFile, $json + "`n")
}

# An app's own installer, in the extracted release the portal keeps: "<tag>" is wp-<app>-v<x.y.z>.
function Invoke-AppInstaller($tag, [string[]]$options) {
    $installer = Join-Path $Releases "$tag\install.ps1"
    if (-not (Test-Path -LiteralPath $installer)) { return $false }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer @options
    return ($LASTEXITCODE -eq 0)
}

$DesktopShortcut = $true
$XboxMenu = $null                               # $null: asked on a first install
$Uninstall = $false
$All = $false
$Purge = $false
foreach ($arg in $args) {
    switch -CaseSensitive ($arg) {
        '--no-desktop-shortcut' { $DesktopShortcut = $false }
        '--xbox-menu' { $XboxMenu = $true }
        '--no-xbox-menu' { $XboxMenu = $false }
        '--uninstall' { $Uninstall = $true }
        '--all' { $All = $true }
        '--purge' { $Purge = $true }
        { $_ -in '-h', '--help' } { Usage; exit 0 }
        default { Usage | Write-Host; Die "Unknown option: $arg" }
    }
}
if ($Purge -and -not $Uninstall) { Die '--purge only goes with --uninstall.' }
if ($All -and -not $Uninstall) { Die '--all only goes with --uninstall.' }

if (Elevated) { Die "Run this as your own user, not as administrator: the suite and its shortcuts belong in your own folders." }

if ($Uninstall) {
    Info 'Removing the Start-menu entry, the Desktop shortcut and the portal'
    Remove-IfThere $MenuEntry
    Remove-IfThere $DesktopIcon
    try { Remove-IfThere $AppDir } catch { Die "$AppDir could not be removed: close $AppName first. ($_)" }
    $records = Read-Records
    $appOptions = @('--uninstall')
    if ($Purge) { $appOptions += '--purge' }
    $kept = @()
    foreach ($key in @($records.Keys)) {
        $tag = $records[$key]
        if ($key -ne 'test' -and -not $All) { $kept += "$key ($tag)"; continue }
        Info "Removing $key through its own installer ($tag)"
        if (-not (Invoke-AppInstaller $tag $appOptions)) { Die "The uninstaller of $key ($tag) failed; the rest is left as it is." }
        $records.Remove($key)
        Remove-IfThere (Join-Path $Releases $tag)
    }
    if ($kept) {
        Info ("Still installed (the portal installed them): " + ($kept -join ', ') + ". Remove them with --uninstall --all, or each from its own installer.")
    }
    if ($Purge) {
        Info 'Removing the settings, the log and the records'
        Remove-IfThere $Settings
        Remove-IfThere $PortalHome
        Remove-IfEmpty (Split-Path -Parent $Settings)
    } else {
        Write-Records $records
        Remove-IfEmpty $Releases
        Info "Keeping your settings in $Settings and the log and records in $PortalHome"
    }
    Remove-IfEmpty $MenuDir
    Remove-IfEmpty $SuiteHome
    Info "$AppName is uninstalled."
    exit 0
}

# --- Checks ------------------------------------------------------------------------------------
$Program = Join-Path $Src 'program'
if (-not (Test-Path -LiteralPath (Join-Path $Program $Exe))) {
    Die ("No program\$Exe beside install.ps1: this installs a release (wp-portal-v<x.y.z>.zip, unpacked). From the " +
         'checkout, start the portal with run.ps1, or build a release with tools/build_release.py.')
}
$Bundle = Join-Path $Src 'bundle'
$TestZip = $null
if (Test-Path -LiteralPath $Bundle) {
    $TestZip = Get-ChildItem -LiteralPath $Bundle -Filter 'wp-test-v*.zip' | Select-Object -First 1
}
if ($TestZip) {
    $Sums = Join-Path $Bundle 'SHA256SUMS'
    if (-not (Test-Path -LiteralPath $Sums)) { Die "bundle\SHA256SUMS is missing: the bundled $TestName cannot be checked." }
    $want = (Get-Content -LiteralPath $Sums | Where-Object { $_ -match "\s\*?$([regex]::Escape($TestZip.Name))$" } | Select-Object -First 1) -replace '\s.*$', ''
    $got = (Get-FileHash -LiteralPath $TestZip.FullName -Algorithm SHA256).Hash.ToLower()
    if (-not $want -or $want.ToLower() -ne $got) { Die "bundle\$($TestZip.Name) does not match bundle\SHA256SUMS: not installed." }
}

# --- The portal --------------------------------------------------------------------------------
$FirstInstall = -not (Test-Path -LiteralPath (Join-Path $AppDir $Exe))
Info "Installing $AppName in $AppDir"
$New = "$AppDir.new"
Remove-IfThere $New
New-Item -ItemType Directory -Force -Path $New | Out-Null
Copy-Item -Path (Join-Path $Program '*') -Destination $New -Recurse -Force
foreach ($file in 'LICENSE', 'THIRD-PARTY-NOTICES.txt') {
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

# --- Windows Portable Test, from the bundle ----------------------------------------------------
if ($TestZip) {
    $Tag = $TestZip.BaseName
    Info "Installing $TestName ($Tag) through its own installer"
    $Tmp = Join-Path $Releases ".$Tag.part"
    Remove-IfThere $Tmp
    New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
    Expand-Archive -LiteralPath $TestZip.FullName -DestinationPath $Tmp
    $Inner = Join-Path $Tmp $Tag
    if (-not (Test-Path -LiteralPath (Join-Path $Inner 'install.ps1'))) { Remove-IfThere $Tmp; Die "bundle\$($TestZip.Name) has no $Tag\install.ps1." }
    $Folder = Join-Path $Releases $Tag
    Remove-IfThere $Folder
    Move-Item -LiteralPath $Inner -Destination $Folder
    Remove-IfThere $Tmp
    [IO.File]::WriteAllText((Join-Path $Folder '.complete'), $got + "`n")     # the portal reuses the folder
    $testOptions = @('--no-desktop-shortcut')            # the portal starts it (owner, 28-10-2026)
    if (-not (Invoke-AppInstaller $Tag $testOptions)) { Die "The installer of $TestName ($Tag) failed." }
    $records = Read-Records
    $records['test'] = $Tag
    Write-Records $records
    Get-ChildItem -LiteralPath $Releases -Directory -Filter 'wp-test-v*' | Where-Object { $_.Name -ne $Tag } |
        ForEach-Object { Remove-IfThere $_.FullName }                      # older releases of the test app
} else {
    Info "No $TestName in bundle\ (a build from the checkout): install it from the portal."
}
Add-ToXboxMenu $Target
Info "$AppName is installed. Start it from the Start menu, or run $Target"
Remove-Download
