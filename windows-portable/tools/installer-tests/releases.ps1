# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise dev/releases/install.ps1, Nexus Releases on Windows: the Start-menu entry and Desktop shortcut that start
# run.ps1 in the checkout (nothing copied), the icon, again without the Desktop shortcut, the refusals, uninstall
# (the settings kept) and --purge. The user's folders are a temp folder's, as in test.ps1.
#
#   powershell -ExecutionPolicy Bypass -File windows-portable\tools\installer-tests\releases.ps1
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$App = Join-Path $Repo 'dev\releases'
$T = Join-Path ([IO.Path]::GetTempPath()) 'nexus-releases-installer'
if (Test-Path -LiteralPath $T) { Remove-Item -LiteralPath $T -Recurse -Force }
New-Item -ItemType Directory -Path $T | Out-Null
$script:fail = 0
function Check($label, [scriptblock]$test) {
    if (& $test) { Write-Host "  ok   $label" } else { Write-Host "  FAIL $label"; $script:fail = 1 }
}

$env:LOCALAPPDATA = Join-Path $T 'local'
$env:APPDATA = Join-Path $T 'roaming'
$env:WPS_DESKTOP_DIR = Join-Path $T 'desktop'
$env:WPS_ELEVATED = '0'
$env:WPS_APP_ID_KEY = Join-Path $T 'app-id-key'        # the registry key the app registers, as a folder: no registry
$Menu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Nexus Releases.lnk'
$Desk = Join-Path $env:WPS_DESKTOP_DIR 'Nexus Releases.lnk'
$Icon = Join-Path $env:LOCALAPPDATA 'nexus-releases\nexus-releases.ico'
$Settings = Join-Path $env:APPDATA 'nexus-releases'
$Installer = Join-Path $App 'install.ps1'

function Run($log, [string[]]$options) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer @options *> (Join-Path $T $log)
    return $LASTEXITCODE
}
function Log($log) { Get-Content -Raw -LiteralPath (Join-Path $T $log) }
function Link($path) { (New-Object -ComObject WScript.Shell).CreateShortcut($path) }

Write-Host '== 1. install'
$rc = Run 'log1' @()
Check 'exit 0' { $rc -eq 0 }
Check 'Start-menu entry starts run.ps1 of this checkout, hidden' {
    $l = Link $Menu
    (Test-Path $Menu) -and $l.TargetPath -like '*\powershell.exe' -and $l.Arguments -like "*-WindowStyle Hidden*-File `"$App\run.ps1`"" -and $l.WorkingDirectory -eq $App
}
Check 'Desktop shortcut' { (Test-Path $Desk) -and (Link $Desk).Arguments -eq (Link $Menu).Arguments }
Check 'the icon: an .ico around the 128 px PNG' {
    $b = [IO.File]::ReadAllBytes($Icon)
    $png = [IO.File]::ReadAllBytes((Join-Path $App 'images\nexus-releases-128.png'))
    $b.Length -eq $png.Length + 22 -and $b[2] -eq 1 -and $b[4] -eq 1 -and $b[22] -eq 0x89 -and $b[23] -eq 0x50
}
Check 'the shortcuts use it' { (Link $Menu).IconLocation -eq "$Icon,0" }
Check 'nothing copied from the checkout' { -not (Get-ChildItem -Recurse -LiteralPath $env:LOCALAPPDATA -Filter *.py) }

Write-Host '== 2. again without the Desktop shortcut'
$rc = Run 'log2' @('--no-desktop-shortcut')
Check 'exit 0' { $rc -eq 0 }
Check 'Desktop shortcut removed, Start-menu entry kept' { -not (Test-Path $Desk) -and (Test-Path $Menu) }

Write-Host '== 3. refusals'
$env:WPS_ELEVATED = '1'
$rc = Run 'log3' @()
$env:WPS_ELEVATED = '0'
Check 'administrator refused' { $rc -ne 0 -and (Log 'log3') -match 'not as administrator' }
$rc = Run 'log3' @('--purge')
Check '--purge alone refused' { $rc -ne 0 -and (Log 'log3') -match 'only goes with --uninstall' }
$rc = Run 'log3' @('--bogus')
Check 'unknown option refused' { $rc -ne 0 -and (Log 'log3') -match 'Unknown option: --bogus' }
$rc = Run 'log3' @('--help')
Check '--help shows the usage' { $rc -eq 0 -and (Log 'log3') -match '(?m)^Installs Nexus Releases' -and (Log 'log3') -match '--uninstall --purge' }

Write-Host '== 4. uninstall keeps the settings'
New-Item -ItemType Directory -Force -Path $Settings | Out-Null
Set-Content -LiteralPath (Join-Path $Settings 'nexus-releases.ini') -Value '[General]' -Encoding ascii
New-Item -ItemType Directory -Force -Path $env:WPS_APP_ID_KEY | Out-Null          # as the app registers it
$rc = Run 'log4' @('--uninstall')
Check 'exit 0' { $rc -eq 0 }
Check 'shortcuts and icon gone' { -not (Test-Path $Menu) -and -not (Test-Path $Desk) -and -not (Test-Path $Icon) }
Check 'the app ID gone' { -not (Test-Path $env:WPS_APP_ID_KEY) }
Check 'settings kept, the checkout untouched' { (Test-Path (Join-Path $Settings 'nexus-releases.ini')) -and (Test-Path (Join-Path $App 'run.ps1')) }

Write-Host '== 5. reinstall, then uninstall --purge'
$rc = Run 'log5' @()
if ($rc -eq 0) { $rc = Run 'log5b' @('--uninstall', '--purge') }
Check 'exit 0' { $rc -eq 0 }
Check 'settings removed' { -not (Test-Path $Settings) }
Check 'the checkout untouched' { Test-Path (Join-Path $App 'install.ps1') }

if ($script:fail -eq 0) {
    Write-Host 'ALL OK'
} else {
    Get-ChildItem -LiteralPath $T -Filter 'log*' | ForEach-Object { Write-Host "--- $($_.Name)"; Get-Content -LiteralPath $_.FullName | Write-Host }
}
exit $script:fail
