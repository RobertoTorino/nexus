# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/test/install.ps1: install from a release folder, an update without the Desktop shortcut, the
# refusals (administrator, --purge alone, an unknown option, the checkout without a built program), uninstall
# (settings, log and reports kept) and --purge. The user's folders are a temp folder's: LOCALAPPDATA, APPDATA and
# the Desktop (WPS_DESKTOP_DIR); WPS_ELEVATED stands in for the administrator check, since CI's runner is one.
#
#   powershell -ExecutionPolicy Bypass -File windows-portable\tools\installer-tests\test.ps1
#   ... test.ps1 -Release dist\wp-test-v0.1.0.zip     # the built release instead of a stand-in program
param([string]$Release = '')
$ErrorActionPreference = 'Stop'
$Suite = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$T = Join-Path ([IO.Path]::GetTempPath()) 'windows-portable-test-installer'
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
$AppId = 'windows-portable-test'
$Exe = 'Windows-PT.exe'
$AppHome = Join-Path $env:LOCALAPPDATA "windows-portable-suite\$AppId"
$A = Join-Path $AppHome 'app'
$Ini = Join-Path $env:APPDATA "windows-portable-suite\$AppId.ini"
$MenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Windows Portable Suite'
$Menu = Join-Path $MenuDir 'Windows Portable Test.lnk'
$Desk = Join-Path $env:WPS_DESKTOP_DIR 'Windows Portable Test.lnk'

# The release folder: the built one, or a stand-in with the same layout (a program\ with the exe and _internal\).
if ($Release) {
    Expand-Archive -LiteralPath $Release -DestinationPath (Join-Path $T 'release')
    $R = (Get-ChildItem -LiteralPath (Join-Path $T 'release') -Directory | Select-Object -First 1).FullName
} else {
    $R = Join-Path $T 'release\wp-test-v0.0.0'
    New-Item -ItemType Directory -Force -Path (Join-Path $R 'program\_internal') | Out-Null
    Set-Content -LiteralPath (Join-Path $R "program\$Exe") -Value 'stand-in' -Encoding ascii
    Set-Content -LiteralPath (Join-Path $R 'program\_internal\marker.txt') -Value 'marker' -Encoding ascii
    Copy-Item -LiteralPath (Join-Path $Suite 'apps\test\install.ps1'), (Join-Path $Suite 'apps\test\LICENSE') -Destination $R
}
$Installer = Join-Path $R 'install.ps1'

function Run($log, [string[]]$options, $installer = $Installer) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer @options *> (Join-Path $T $log)
    return $LASTEXITCODE
}
function Log($log) { Get-Content -Raw -LiteralPath (Join-Path $T $log) }
function Target($link) { (New-Object -ComObject WScript.Shell).CreateShortcut($link).TargetPath }

Write-Host '== 1. install from the release folder'
$rc = Run 'log1' @()
Check 'exit 0' { $rc -eq 0 }
Check 'program copied with its _internal folder' { (Test-Path (Join-Path $A $Exe)) -and (Test-Path (Join-Path $A '_internal')) }
Check 'LICENSE copied, install.ps1 not' { (Test-Path (Join-Path $A 'LICENSE')) -and -not (Test-Path (Join-Path $A 'install.ps1')) }
Check 'Start-menu entry starts the installed exe' { (Test-Path $Menu) -and ((Target $Menu) -eq (Join-Path $A $Exe)) }
Check 'Desktop shortcut' { (Test-Path $Desk) -and ((Target $Desk) -eq (Join-Path $A $Exe)) }

Write-Host '== 2. update without the Desktop shortcut'
Set-Content -LiteralPath (Join-Path $A 'stale.txt') -Value 'from an older release' -Encoding ascii
$rc = Run 'log2' @('--no-desktop-shortcut')
Check 'exit 0' { $rc -eq 0 }
Check 'the old program replaced, nothing left over' { -not (Test-Path (Join-Path $A 'stale.txt')) -and -not (Test-Path "$A.new") }
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
$rc = Run 'log3' @() (Join-Path $Suite 'apps\test\install.ps1')
Check 'the checkout has no program to install' { $rc -ne 0 -and (Log 'log3') -match 'No program' }
$rc = Run 'log3' @('--help')
Check '--help shows the usage' { $rc -eq 0 -and (Log 'log3') -match '(?m)^Installs Windows Portable Test' -and (Log 'log3') -match '--uninstall --purge' }
Check 'the installed app untouched' { Test-Path (Join-Path $A $Exe) }

Write-Host '== 4. uninstall keeps the settings, the log and the reports'
New-Item -ItemType Directory -Force -Path (Join-Path $AppHome 'reports'), (Split-Path -Parent $Ini) | Out-Null
Set-Content -LiteralPath $Ini, (Join-Path $AppHome "$AppId.log"), (Join-Path $AppHome 'reports\device.txt') -Value 'x' -Encoding ascii
$rc = Run 'log4' @('--uninstall')
Check 'exit 0' { $rc -eq 0 }
Check 'app gone' { -not (Test-Path $A) }
Check 'Start-menu entry and its folder gone' { -not (Test-Path $Menu) -and -not (Test-Path $MenuDir) }
Check 'settings, log and reports kept' { (Test-Path $Ini) -and (Test-Path (Join-Path $AppHome "$AppId.log")) -and (Test-Path (Join-Path $AppHome 'reports\device.txt')) }

Write-Host '== 5. reinstall, then uninstall --purge'
$rc = Run 'log5' @()
if ($rc -eq 0) { $rc = Run 'log5b' @('--uninstall', '--purge') }
Check 'exit 0' { $rc -eq 0 }
Check 'Desktop shortcut removed' { -not (Test-Path $Desk) }
Check 'settings, log and reports removed' { -not (Test-Path $Ini) -and -not (Test-Path $AppHome) }
Check 'the empty suite folders removed' { -not (Test-Path (Join-Path $env:LOCALAPPDATA 'windows-portable-suite')) -and -not (Test-Path (Join-Path $env:APPDATA 'windows-portable-suite')) }

if ($script:fail -eq 0) {
    Write-Host 'ALL OK'
} else {
    Get-ChildItem -LiteralPath $T -Filter 'log*' | ForEach-Object { Write-Host "--- $($_.Name)"; Get-Content -LiteralPath $_.FullName | Write-Host }
}
exit $script:fail
